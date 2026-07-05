"""
vlm_scene.providers.internvl_local
----------------------------------
本地轻量化 VLM Provider（离线、不依赖公网）。

===== 设计目标 =====
    比赛现场断网/防火墙拦截云端 API 时，仍然能：
      1. 用本地视觉模型对关键帧做一次“行人 / 通道 / 危险”场景理解；
      2. 输出结构化 JSON（scene / risk / reason / suggestion / elapsed_ms）；
      3. 与 dynamic_person_obstacle_node 协同：安全动作（stop/reroute）
         由 YOLO+Depth+Nav2 完成，VLM 只提供“语义确认”和“告警文本”。

===== 双路兜底 =====
    - Path A：真实推理（推荐）
        通过 transformers 加载 Qwen2-VL-2B-Instruct / MiniCPM-V-2.6 /
        InternVL2-2B 等 HF 格式模型。加载失败时自动降级 Path B。
        环境变量：
          VLM_LOCAL_MODEL_PATH    HF 目录（包含 config.json / *.safetensors）
          VLM_LOCAL_MODEL_TYPE    auto / qwen2_vl / minicpmv / internvl（默认 auto）
          VLM_LOCAL_DEVICE        cpu / cuda / auto（默认 auto）
          VLM_LOCAL_DTYPE         float16 / bfloat16 / float32（默认 float16）
          VLM_LOCAL_MAX_NEW_TOKENS 生成 token 上限（默认 128）

    - Path B：结构化本地规则（无模型时兜底）
        只用 detection_node 的检测框 + distance_m + bbox 位置做启发式判定，
        产出与 Path A 完全一致的 JSON 结构。比赛现场即使模型没转换好也能
        演示“本地决策”闭环，绝对不请求公网。

===== 输出格式 =====
    VLMResponse.description 是一段 JSON 文本（前端 VideoView 已经能渲染
    自然语言，同时 dynamic_person_obstacle_node 可 parse risk 字段）：
        {
          "scene":      "前方 1.2m 处有一个行人，位于正前方通道",
          "risk":       "stop" | "reroute" | "clear",
          "reason":     "行人距离过近且位于路径中心",
          "suggestion": "停车等待行人通过",
          "elapsed_ms": 650
        }
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import List, Optional, Tuple

import numpy as np

from .base import BaseVLMProvider, Detection, VLMRequest, VLMResponse

logger = logging.getLogger("vlm_scene.internvl_local")


# =============================================================================
# 结构化 System Prompt：让本地 VLM 直接吐 JSON，不要长篇散文
# =============================================================================
DEFAULT_SAFETY_PROMPT = (
    "你是一台移动机器人的车载视觉安全助手。请仔细观察下面这张相机画面，"
    "并结合前置检测器提供的目标列表（class_name / distance_m / bbox），"
    "严格输出一个 JSON 对象（不要 markdown 代码块，不要额外解释）：\n"
    "{\n"
    '  "scene":      "一句中文场景描述，例如：前方1.2米处有行人正在横穿",\n'
    '  "risk":       "stop" | "reroute" | "clear",\n'
    '  "reason":     "中文一句话，说明为什么这样判定",\n'
    '  "suggestion": "中文一句话，给小车的动作建议"\n'
    "}\n\n"
    "判定标准：\n"
    "  risk=stop    ：路径上出现行人/障碍且距离 < 0.8m，或占据画面中央 40% 区域\n"
    "  risk=reroute ：路径上出现行人/障碍但距离 0.8~2.5m，建议绕行\n"
    "  risk=clear   ：前方无障碍，或障碍位于两侧安全区外\n"
)


# =============================================================================
# Path B 结构化兜底：基于检测框的规则化判定（无模型时使用）
# =============================================================================
def _rule_based_infer(
    frame_bgr: np.ndarray,
    dets: List[Detection],
    stop_distance: float = 0.8,
    reroute_distance: float = 2.5,
    center_ratio: float = 0.4,
) -> dict:
    """
    纯规则本地兜底：不依赖任何模型权重，只用检测框做判定。
    完全离线、~0.5ms、CPU 占用可忽略。
    """
    if frame_bgr is None or not hasattr(frame_bgr, "shape"):
        return {
            "scene": "无可用画面",
            "risk": "clear",
            "reason": "未收到有效相机帧",
            "suggestion": "等待相机数据",
        }

    h, w = frame_bgr.shape[:2]
    if not dets:
        return {
            "scene": "前方通道畅通，未检测到目标",
            "risk": "clear",
            "reason": "检测器未上报任何目标",
            "suggestion": "保持当前速度前进",
        }

    # 中心危险区
    cx_min = w * (0.5 - center_ratio / 2)
    cx_max = w * (0.5 + center_ratio / 2)

    # 优先关注行人，其它类别退化处理
    priority = {"person": 3, "rider": 3, "bicycle": 2, "motorbike": 2, "car": 2}

    # 找出最"危险"的目标：距离最近、位置最靠中央、类别优先级最高
    def _risk_key(d: Detection) -> Tuple[int, float]:
        cx = (d.x1 + d.x2) * 0.5
        in_center = cx_min <= cx <= cx_max
        prio = priority.get(d.class_name, 1)
        # 未知距离按 5m 处理，避免因为 distance=0 就被判危险
        dist = d.distance_m if d.distance_m and d.distance_m > 0 else 5.0
        # 综合分数：越危险越小（distance小 + prio高 + 在中心 → 优先）
        score = dist - (prio * 0.3) - (0.5 if in_center else 0.0)
        return (0 if in_center else 1, score)

    dets_sorted = sorted(dets, key=_risk_key)
    top = dets_sorted[0]
    cx = (top.x1 + top.x2) * 0.5
    in_center = cx_min <= cx <= cx_max
    dist = top.distance_m if top.distance_m and top.distance_m > 0 else -1.0

    pos_word = "正前方" if in_center else ("左前方" if cx < w * 0.5 else "右前方")
    dist_word = f"约 {dist:.2f} 米" if dist > 0 else "距离未知"

    # 判定 risk
    if in_center and dist > 0 and dist < stop_distance:
        risk = "stop"
        reason = f"{top.class_name} 位于路径正中央且距离 {dist:.2f}m < {stop_distance}m"
        suggestion = "立即停车等待障碍离开"
    elif in_center and (dist < 0 or dist <= reroute_distance):
        risk = "reroute"
        reason = f"{top.class_name} 位于路径正中央（{dist_word}），需要绕行"
        suggestion = "降速并从侧向绕行"
    elif dist > 0 and dist < stop_distance and top.class_name in ("person", "rider"):
        # 侧向近距行人：安全起见也停车
        risk = "stop"
        reason = f"{pos_word}行人距离过近（{dist_word}），存在横穿风险"
        suggestion = "停车等待行人通过"
    else:
        risk = "clear"
        reason = f"最近目标 {top.class_name} 位于{pos_word}，{dist_word}，未阻挡路径"
        suggestion = "保持当前速度前进"

    scene = (
        f"{pos_word}有一个 {top.class_name}，{dist_word}"
        f"，共检测到 {len(dets)} 个目标"
    )
    return {
        "scene": scene,
        "risk": risk,
        "reason": reason,
        "suggestion": suggestion,
    }


# =============================================================================
# Provider
# =============================================================================
class InternVLLocalProvider(BaseVLMProvider):
    """
    本地轻量化 VLM。
    - 有模型（VLM_LOCAL_MODEL_PATH 指向的目录）→ 真实推理；
    - 无模型 → 规则兜底，仍然输出同样的 JSON schema。
    """

    name = "internvl_local"
    default_model = "internvl2-2b-int8"

    def __init__(
        self,
        model: Optional[str] = None,
        model_path: Optional[str] = None,
        tokenizer_path: Optional[str] = None,
        max_image_side: int = 448,
        timeout: float = 10.0,
        **kwargs,
    ):
        super().__init__(model=model, **kwargs)
        self.model_path = (model_path
                            or os.getenv("VLM_LOCAL_MODEL_PATH", "").strip()
                            or os.getenv("VLM_INTERNVL_MODEL_PATH", "").strip())
        self.tokenizer_path = (tokenizer_path
                                or os.getenv("VLM_LOCAL_TOKENIZER", "").strip()
                                or self.model_path)
        self.model_type = os.getenv("VLM_LOCAL_MODEL_TYPE", "auto").lower().strip()
        self.device_pref = os.getenv("VLM_LOCAL_DEVICE", "auto").lower().strip()
        self.dtype_name = os.getenv("VLM_LOCAL_DTYPE", "float16").lower().strip()
        self.max_new_tokens = int(os.getenv("VLM_LOCAL_MAX_NEW_TOKENS", "128"))
        self.max_image_side = int(max_image_side or 448)
        self.timeout = float(timeout)

        # 懒加载状态
        self._engine = None            # {"kind": "qwen2_vl"/"minicpmv"/..., "model":..., "processor":...}
        self._load_lock = threading.Lock()
        self._load_attempted = False   # 尝试过一次后就不再重试，避免每次推理都卡
        self._load_ok = False
        self._load_error: Optional[str] = None

        # 系统提示（可被 VLMRequest.system_prompt 覆盖）
        self._safety_prompt = DEFAULT_SAFETY_PROMPT

    # -----------------------------------------------------------------
    # 健康检查
    # -----------------------------------------------------------------
    def healthcheck(self) -> bool:
        """节点启动时调用，检测是否具备真实模型；即使返回 False，节点仍能
        通过规则兜底提供离线服务，因此这里只用于日志友好提示。
        """
        if not self.model_path:
            logger.warning(
                "[InternVL-Local] 未设置 VLM_LOCAL_MODEL_PATH，"
                "将使用规则兜底输出结构化 JSON（仍完全离线）"
            )
            return True   # 规则兜底也算"就绪"
        if not os.path.isdir(self.model_path):
            logger.warning(
                "[InternVL-Local] 模型目录不存在: %s，降级为规则兜底",
                self.model_path,
            )
            return True
        try:
            import transformers  # noqa: F401
        except Exception:
            logger.warning(
                "[InternVL-Local] transformers 未安装，降级为规则兜底"
            )
            return True
        return True

    # -----------------------------------------------------------------
    # 推理入口
    # -----------------------------------------------------------------
    def describe(self, req: VLMRequest) -> VLMResponse:
        t0 = time.time()

        # 尝试加载真实模型（懒加载，加载失败后自动降级）
        self._try_load_once()

        result: Optional[dict] = None
        used_backend = "rule"
        err: Optional[str] = None

        if self._load_ok:
            try:
                text = self._infer_with_hf(req)
                result = self._parse_json(text)
                used_backend = self._engine.get("kind", "hf") if self._engine else "hf"
            except Exception as e:
                err = f"{type(e).__name__}: {e}"
                logger.error("[InternVL-Local] HF 推理失败，降级规则兜底: %s", err)
                result = None

        if result is None:
            # 规则兜底
            rule = _rule_based_infer(req.frame_bgr, req.detections)
            result = rule
            used_backend = "rule"

        elapsed = (time.time() - t0) * 1000.0
        result.setdefault("scene", "")
        result.setdefault("risk", "clear")
        result.setdefault("reason", "")
        result.setdefault("suggestion", "")
        result["elapsed_ms"] = round(elapsed, 1)
        result["backend"] = used_backend
        if err:
            result["_error"] = err

        description = json.dumps(result, ensure_ascii=False)
        return VLMResponse(
            description=description,
            provider=self.name,
            model=self.model,
            elapsed_ms=elapsed,
            extra={"backend": used_backend, "risk": result["risk"]},
        )

    def close(self):
        # 释放模型显存
        try:
            if self._engine is not None:
                for k in ("model", "processor", "tokenizer"):
                    if k in self._engine:
                        del self._engine[k]
                self._engine = None
            import gc
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        except Exception:
            pass

    # -----------------------------------------------------------------
    # HF 模型加载 / 推理
    # -----------------------------------------------------------------
    def _try_load_once(self):
        if self._load_attempted:
            return
        with self._load_lock:
            if self._load_attempted:
                return
            self._load_attempted = True
            if not self.model_path or not os.path.isdir(self.model_path):
                self._load_ok = False
                self._load_error = "no_model_path"
                return
            try:
                self._load_hf_model()
                self._load_ok = True
                logger.info(
                    "[InternVL-Local] HF 模型加载成功: kind=%s path=%s",
                    self._engine.get("kind"), self.model_path,
                )
            except Exception as e:
                self._load_ok = False
                self._load_error = f"{type(e).__name__}: {e}"
                logger.warning(
                    "[InternVL-Local] HF 模型加载失败，将全程使用规则兜底: %s",
                    self._load_error,
                )

    def _load_hf_model(self):
        import torch
        from transformers import AutoConfig, AutoProcessor, AutoTokenizer

        # 设备 / 精度
        device = self.device_pref
        if device == "auto":
            device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype_map = {
            "float16": torch.float16, "fp16": torch.float16,
            "bfloat16": torch.bfloat16, "bf16": torch.bfloat16,
            "float32": torch.float32, "fp32": torch.float32,
        }
        dtype = dtype_map.get(self.dtype_name, torch.float16)
        if device == "cpu" and dtype == torch.float16:
            # CPU 上 fp16 慢且不稳，强制回退 fp32
            dtype = torch.float32

        # 识别模型类型
        cfg = AutoConfig.from_pretrained(self.model_path, trust_remote_code=True)
        arch = ""
        try:
            arch = (cfg.architectures[0] if cfg.architectures else "").lower()
        except Exception:
            arch = ""
        model_type = self.model_type
        if model_type == "auto":
            if "qwen2vl" in arch or "qwen2-vl" in arch:
                model_type = "qwen2_vl"
            elif "minicpmv" in arch or "minicpm-v" in arch:
                model_type = "minicpmv"
            elif "internvl" in arch or "internvlchatmodel" in arch:
                model_type = "internvl"
            else:
                model_type = "auto_vision2seq"

        logger.info(
            "[InternVL-Local] 检测模型类型 arch=%s -> kind=%s device=%s dtype=%s",
            arch, model_type, device, dtype,
        )

        if model_type == "qwen2_vl":
            from transformers import Qwen2VLForConditionalGeneration
            processor = AutoProcessor.from_pretrained(
                self.model_path, trust_remote_code=True
            )
            model = Qwen2VLForConditionalGeneration.from_pretrained(
                self.model_path, torch_dtype=dtype, trust_remote_code=True
            ).to(device).eval()
            self._engine = {
                "kind": "qwen2_vl",
                "model": model,
                "processor": processor,
                "device": device,
                "dtype": dtype,
            }
            return

        if model_type == "minicpmv":
            from transformers import AutoModel
            tokenizer = AutoTokenizer.from_pretrained(
                self.tokenizer_path or self.model_path, trust_remote_code=True
            )
            model = AutoModel.from_pretrained(
                self.model_path, torch_dtype=dtype, trust_remote_code=True
            ).to(device).eval()
            self._engine = {
                "kind": "minicpmv",
                "model": model,
                "tokenizer": tokenizer,
                "device": device,
                "dtype": dtype,
            }
            return

        if model_type == "internvl":
            from transformers import AutoModel
            tokenizer = AutoTokenizer.from_pretrained(
                self.tokenizer_path or self.model_path, trust_remote_code=True
            )
            model = AutoModel.from_pretrained(
                self.model_path, torch_dtype=dtype, trust_remote_code=True
            ).to(device).eval()
            self._engine = {
                "kind": "internvl",
                "model": model,
                "tokenizer": tokenizer,
                "device": device,
                "dtype": dtype,
            }
            return

        # 通用 fallback：AutoModelForVision2Seq
        from transformers import AutoModelForVision2Seq
        processor = AutoProcessor.from_pretrained(
            self.model_path, trust_remote_code=True
        )
        model = AutoModelForVision2Seq.from_pretrained(
            self.model_path, torch_dtype=dtype, trust_remote_code=True
        ).to(device).eval()
        self._engine = {
            "kind": "auto_vision2seq",
            "model": model,
            "processor": processor,
            "device": device,
            "dtype": dtype,
        }

    def _infer_with_hf(self, req: VLMRequest) -> str:
        assert self._engine is not None
        kind = self._engine["kind"]
        device = self._engine["device"]

        # ── 构造 prompt ─────────────────────────────────────────────
        sys_prompt = req.system_prompt or self._safety_prompt
        det_lines = self._format_detections(req.detections)
        user_prompt = (
            f"检测器上报（class_name / conf / bbox / distance_m）：\n{det_lines}\n"
            f"请严格按 JSON 输出结果。"
        )
        if req.user_prompt:
            user_prompt = req.user_prompt + "\n" + user_prompt

        # ── 转 PIL Image ────────────────────────────────────────────
        pil_img = self._to_pil(req.frame_bgr)

        if kind == "qwen2_vl":
            return self._gen_qwen2_vl(sys_prompt, user_prompt, pil_img)
        if kind == "minicpmv":
            return self._gen_minicpmv(sys_prompt, user_prompt, pil_img)
        if kind == "internvl":
            return self._gen_internvl(sys_prompt, user_prompt, pil_img)
        return self._gen_auto_vision2seq(sys_prompt, user_prompt, pil_img)

    # ------------------------------------------------------------------
    # 各家 chat 模板
    # ------------------------------------------------------------------
    def _gen_qwen2_vl(self, sys_p, user_p, pil_img) -> str:
        import torch
        model = self._engine["model"]
        processor = self._engine["processor"]
        device = self._engine["device"]

        messages = [
            {"role": "system", "content": sys_p},
            {"role": "user", "content": [
                {"type": "image", "image": pil_img},
                {"type": "text", "text": user_p},
            ]},
        ]
        text = processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        inputs = processor(
            text=[text], images=[pil_img], padding=True, return_tensors="pt"
        ).to(device)
        with torch.no_grad():
            out_ids = model.generate(
                **inputs, max_new_tokens=self.max_new_tokens, do_sample=False,
            )
        gen_ids = [o[len(i):] for i, o in zip(inputs.input_ids, out_ids)]
        return processor.batch_decode(
            gen_ids, skip_special_tokens=True, clean_up_tokenization_spaces=False
        )[0]

    def _gen_minicpmv(self, sys_p, user_p, pil_img) -> str:
        import torch
        model = self._engine["model"]
        tokenizer = self._engine["tokenizer"]
        # MiniCPM-V 的 .chat() API 是最稳定入口
        msgs = [{"role": "user", "content": [pil_img, f"{sys_p}\n\n{user_p}"]}]
        with torch.no_grad():
            resp = model.chat(
                image=None, msgs=msgs, tokenizer=tokenizer,
                sampling=False, max_new_tokens=self.max_new_tokens,
            )
        return resp if isinstance(resp, str) else str(resp)

    def _gen_internvl(self, sys_p, user_p, pil_img) -> str:
        import torch
        model = self._engine["model"]
        tokenizer = self._engine["tokenizer"]
        # InternVL2 的 .chat() API
        prompt = f"{sys_p}\n\n{user_p}"
        with torch.no_grad():
            resp = model.chat(
                tokenizer=tokenizer,
                pixel_values=self._internvl_preprocess(pil_img),
                question=prompt,
                generation_config=dict(
                    max_new_tokens=self.max_new_tokens, do_sample=False,
                ),
            )
        return resp if isinstance(resp, str) else str(resp)

    def _internvl_preprocess(self, pil_img):
        """InternVL2 需要 pixel_values（[N,3,H,W] float tensor）。
        这里做最简单的 448x448 缩放 + Normalize，尽量避免依赖 model 内置的
        动态分块（那部分依赖 timm 附加处理，可能环境缺）。"""
        import torch
        from torchvision import transforms
        img = pil_img.convert("RGB").resize((448, 448))
        tf = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                 std=[0.229, 0.224, 0.225]),
        ])
        return tf(img).unsqueeze(0).to(
            self._engine["device"], dtype=self._engine["dtype"]
        )

    def _gen_auto_vision2seq(self, sys_p, user_p, pil_img) -> str:
        import torch
        model = self._engine["model"]
        processor = self._engine["processor"]
        device = self._engine["device"]
        prompt = f"{sys_p}\n\n{user_p}"
        inputs = processor(images=pil_img, text=prompt, return_tensors="pt").to(device)
        with torch.no_grad():
            out_ids = model.generate(**inputs, max_new_tokens=self.max_new_tokens)
        return processor.batch_decode(out_ids, skip_special_tokens=True)[0]

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------
    def _to_pil(self, bgr: np.ndarray):
        from PIL import Image
        if bgr is None:
            return Image.new("RGB", (16, 16), (0, 0, 0))
        rgb = bgr[..., ::-1]  # BGR -> RGB
        h, w = rgb.shape[:2]
        side = max(h, w)
        if side > self.max_image_side:
            scale = self.max_image_side / side
            new_w = max(1, int(w * scale))
            new_h = max(1, int(h * scale))
            img = Image.fromarray(np.ascontiguousarray(rgb)).resize((new_w, new_h))
        else:
            img = Image.fromarray(np.ascontiguousarray(rgb))
        return img

    @staticmethod
    def _format_detections(dets: List[Detection]) -> str:
        if not dets:
            return "  (无)"
        lines = []
        for i, d in enumerate(dets[:10]):
            lines.append(
                f"  [{i}] {d.class_name}(conf={d.confidence:.2f}) "
                f"bbox=[{d.x1:.0f},{d.y1:.0f},{d.x2:.0f},{d.y2:.0f}] "
                f"dist={d.distance_m:.2f}m"
            )
        return "\n".join(lines)

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        """把模型输出解析成 dict；失败返回 None（触发规则兜底）。"""
        if not text:
            return None
        # 先尝试整段 parse
        s = text.strip()
        try:
            return json.loads(s)
        except Exception:
            pass
        # 抠第一个 {...}
        m = re.search(r"\{[\s\S]*\}", s)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
