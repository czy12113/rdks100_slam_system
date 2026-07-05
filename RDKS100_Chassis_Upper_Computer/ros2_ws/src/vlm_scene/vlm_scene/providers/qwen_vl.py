"""
vlm_scene.providers.qwen_vl
---------------------------
通义千问视觉理解模型（DashScope 的 OpenAI 兼容接口）。

为什么默认推荐：
  - 国内访问稳定，无需代理；
  - 与 OpenAI Vision 接口完全兼容，未来切到 OpenAI 改一个 base_url 即可；
  - qwen-vl-plus / qwen-vl-max 价格便宜，新用户有免费额度；
  - 支持图片 base64 直传，单次几百 KB 完全没问题。

配置（在 vlm_scene.providers.keys 文件里集中预设）：
  DASHSCOPE_API_KEY   阿里云百炼控制台获取（必填）
  VLM_QWEN_MODEL      默认 qwen-vl-plus，可改 qwen-vl-max 等
  VLM_QWEN_BASE_URL   默认 DashScope 兼容地址
读取优先级：构造参数 > 环境变量 > keys.py 常量

如何获取 API Key：
  1. 注册阿里云账号 → 进入 "百炼" 控制台
     https://bailian.console.aliyun.com/
  2. 左侧 "模型广场"，搜 qwen-vl-plus / qwen-vl-max，确认已开通
  3. 右上头像 → API-KEY 管理 → 创建新 API-KEY
  4. 把 sk-xxxxx 粘贴到 vlm_scene/providers/keys.py 的 DASHSCOPE_API_KEY
     或 export DASHSCOPE_API_KEY=sk-xxxxx 后再起 vlm_node
"""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import time
from typing import List, Optional, Tuple

import numpy as np

from .base import BaseVLMProvider, VLMRequest, VLMResponse, Detection
from . import keys

logger = logging.getLogger("vlm_scene.qwen_vl")


class QwenVLProvider(BaseVLMProvider):
    """阿里通义千问 VL（DashScope OpenAI 兼容）"""

    name = "qwen_vl"
    # qwen-vl-plus：性价比首选；qwen-vl-max：精度更高、价格略贵
    default_model = "qwen-vl-plus"

    DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    # 配置键名（子类可覆盖以复用整段 HTTP 逻辑，见 OpenAIVisionProvider）
    KEY_API_KEY: str = "DASHSCOPE_API_KEY"
    KEY_MODEL: str = "VLM_QWEN_MODEL"
    KEY_BASE_URL: str = "VLM_QWEN_BASE_URL"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 20.0,
        max_image_side: int = 768,
        jpeg_quality: int = 80,
        max_tokens: int = 512,
        **kwargs,
    ):
        super().__init__(model=model, **kwargs)
        # 读取顺序：构造参数 > 环境变量 > keys.py 常量
        self.api_key = (api_key or keys.get(self.KEY_API_KEY)).strip()
        self.base_url = (
            base_url
            or keys.get(self.KEY_BASE_URL, self.DEFAULT_BASE_URL)
        ).rstrip("/")
        self.timeout = float(timeout)
        self.max_image_side = int(max_image_side)
        self.jpeg_quality = int(jpeg_quality)
        self.max_tokens = int(max_tokens)
        # 模型名同样三级读取
        configured_model = keys.get(self.KEY_MODEL)
        if configured_model:
            self.model = configured_model

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------
    def healthcheck(self) -> bool:
        if not self.api_key:
            logger.warning("[Qwen] DASHSCOPE_API_KEY 未设置，将无法调用 VLM")
            return False
        return True

    def describe(self, req: VLMRequest) -> VLMResponse:
        t0 = time.time()
        if not self.api_key:
            return VLMResponse(
                description="[Qwen] DASHSCOPE_API_KEY 未配置，无法调用 VLM。",
                provider=self.name, model=self.model,
            )

        # 1) 编码图像（下采样 + JPEG 压缩）
        img_b64 = self._encode_image(req.frame_bgr)

        # 2) 构造 messages
        # raw_prompt=True：火警等场景需要严格 prompt，不要再混入默认导航话术
        if req.raw_prompt and req.user_prompt:
            sys_text = req.system_prompt or "你是一台具备视觉理解能力的安全监测助手。"
            user_text = req.user_prompt
        else:
            sys_text = req.system_prompt or self._default_system_prompt()
            user_text = self._build_user_prompt(req.detections, req.user_prompt)

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": sys_text},
                {
                    "role": "user",
                    "content": [
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}},
                        {"type": "text", "text": user_text},
                    ],
                },
            ],
        }

        # 3) 发请求（标准库 urllib，避免强依赖 requests）
        try:
            text, usage = self._http_post(payload)
        except Exception as e:
            logger.error("[Qwen] 调用失败: %s", e)
            return VLMResponse(
                description=f"[Qwen 调用失败] {e}",
                provider=self.name, model=self.model,
                elapsed_ms=(time.time() - t0) * 1000.0,
            )

        elapsed_ms = (time.time() - t0) * 1000.0
        return VLMResponse(
            description=text.strip() or "[Qwen 返回为空]",
            provider=self.name,
            model=self.model,
            elapsed_ms=elapsed_ms,
            tokens_in=int(usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(usage.get("completion_tokens", 0) or 0),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _default_system_prompt(self) -> str:
        return (
            "你是一台移动机器人的视觉理解模块。请用一段简洁、客观的中文"
            "描述画面里正在发生的事情，重点突出与机器人导航和避障相关的信息："
            "前方/左右两侧有哪些人或物，他们的姿态/动作/相对位置，是否构成"
            "障碍。每段输出控制在 80 字以内，不要列表，不要多余客套。"
        )

    def _build_user_prompt(self, dets: List[Detection],
                            user_prompt: Optional[str]) -> str:
        # 把 YOLO 检测结果作为辅助上下文给 VLM
        lines = []
        for i, d in enumerate(dets[:8]):  # 最多列 8 个，避免 prompt 过长
            dist_txt = f"{d.distance_m:.2f}m" if d.distance_m > 0 else "未知"
            lines.append(
                f"- #{i} {d.class_name} 置信度 {d.confidence:.2f}，"
                f"框=({int(d.x1)},{int(d.y1)})-({int(d.x2)},{int(d.y2)})，距离 {dist_txt}"
            )
        det_text = "\n".join(lines) if lines else "（无检测框）"
        base = (
            "下面是检测器给出的初步目标列表（仅供参考，可能漏检/误检）：\n"
            f"{det_text}\n\n"
            "请结合图像内容输出场景描述。"
        )
        if user_prompt:
            base += f"\n\n用户附加问题：{user_prompt}\n请同时给出回答。"
        return base

    def _encode_image(self, bgr: np.ndarray) -> str:
        """下采样到 max_image_side 以内并 JPEG-base64，节省 token / 带宽。"""
        import cv2
        h, w = bgr.shape[:2]
        scale = min(1.0, self.max_image_side / max(h, w))
        if scale < 1.0:
            new_w = int(w * scale)
            new_h = int(h * scale)
            bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, self.jpeg_quality])
        if not ok:
            raise RuntimeError("JPEG 编码失败")
        return base64.b64encode(buf.tobytes()).decode("ascii")

    def _http_post(self, payload: dict) -> Tuple[str, dict]:
        """直接用标准库 urllib 调用兼容接口，避免新增依赖。"""
        import urllib.request
        import urllib.error

        url = f"{self.base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace") if e.fp else ""
            raise RuntimeError(f"HTTP {e.code}: {detail[:300]}") from None
        except urllib.error.URLError as e:
            raise RuntimeError(f"网络错误: {e.reason}") from None

        data = json.loads(raw)
        choices = data.get("choices") or []
        if not choices:
            raise RuntimeError(f"返回缺少 choices: {raw[:300]}")
        msg = choices[0].get("message", {})
        content = msg.get("content", "")
        # content 可能是 list（多模态返回）也可能是 str
        if isinstance(content, list):
            text = "".join(
                part.get("text", "") for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            text = str(content)
        usage = data.get("usage", {}) or {}
        return text, usage
