"""
vlm_scene.providers.deepseek_text
---------------------------------
DeepSeek 纯文本 provider。

⚠️ 重要：DeepSeek 官方目前 **没有开放视觉 API**，所有 deepseek-chat /
deepseek-reasoner 都只能看文本。所以这里的做法是把 detection_node 输出
的检测框列表当作"视觉 perception"喂给 LLM，让它合成一段自然语言描述。
**它实际看不到画面**，只能凭检测结果"脑补"。

如果你需要真正基于图像理解，请使用 `qwen_vl` / `openai_vision` /
`internvl_local`。

配置（在 vlm_scene.providers.keys 里集中预设）：
  DEEPSEEK_API_KEY        DeepSeek API Key
  VLM_DEEPSEEK_MODEL      默认 deepseek-chat
  VLM_DEEPSEEK_BASE_URL   默认 https://api.deepseek.com/v1
读取优先级：构造参数 > 环境变量 > keys.py 常量
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import List, Optional, Tuple

from .base import BaseVLMProvider, VLMRequest, VLMResponse, Detection
from . import keys

logger = logging.getLogger("vlm_scene.deepseek_text")


class DeepSeekTextProvider(BaseVLMProvider):
    name = "deepseek_text"
    default_model = "deepseek-chat"
    DEFAULT_BASE_URL = "https://api.deepseek.com/v1"

    def __init__(
        self,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = 15.0,
        max_tokens: int = 256,
        **kwargs,
    ):
        super().__init__(model=model, **kwargs)
        # 读取顺序：构造参数 > 环境变量 > keys.py 常量
        self.api_key = (api_key or keys.get("DEEPSEEK_API_KEY")).strip()
        self.base_url = (
            base_url
            or keys.get("VLM_DEEPSEEK_BASE_URL", self.DEFAULT_BASE_URL)
        ).rstrip("/")
        configured_model = keys.get("VLM_DEEPSEEK_MODEL")
        if configured_model:
            self.model = configured_model
        self.timeout = float(timeout)
        self.max_tokens = int(max_tokens)

    def healthcheck(self) -> bool:
        if not self.api_key:
            logger.warning("[DeepSeek] DEEPSEEK_API_KEY 未设置")
            return False
        return True

    def describe(self, req: VLMRequest) -> VLMResponse:
        t0 = time.time()
        if not self.api_key:
            return VLMResponse(
                description="[DeepSeek] DEEPSEEK_API_KEY 未配置。",
                provider=self.name, model=self.model,
            )

        sys_prompt = req.system_prompt or (
            "你是一台移动机器人的语义模块。给你一组检测框（不是图片本身），"
            "请基于这些目标位置/类别/距离，用一段简洁中文描述机器人前方画面，"
            "重点是与导航/避障相关的目标。100 字以内，不要列表。"
        )
        user_prompt = self._build_user_prompt(req.detections, req.user_prompt)

        payload = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            text, usage = self._http_post(payload)
        except Exception as e:
            logger.error("[DeepSeek] 调用失败: %s", e)
            return VLMResponse(
                description=f"[DeepSeek 调用失败] {e}",
                provider=self.name, model=self.model,
                elapsed_ms=(time.time() - t0) * 1000.0,
            )

        return VLMResponse(
            description=text.strip() or "[DeepSeek 返回为空]",
            provider=self.name,
            model=self.model,
            elapsed_ms=(time.time() - t0) * 1000.0,
            tokens_in=int(usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(usage.get("completion_tokens", 0) or 0),
        )

    # ------------------------------------------------------------------
    def _build_user_prompt(self, dets: List[Detection],
                           user_prompt: Optional[str]) -> str:
        if not dets:
            base = "当前画面：检测器没有检测到任何目标。"
        else:
            lines = []
            for i, d in enumerate(dets[:10]):
                dist = f"{d.distance_m:.2f}m" if d.distance_m > 0 else "距离未知"
                cx = (d.x1 + d.x2) / 2
                # 简单分左/中/右
                pos = "中"
                if cx < 213:
                    pos = "左"
                elif cx > 426:
                    pos = "右"
                lines.append(
                    f"- {d.class_name}（{pos}侧），置信度{d.confidence:.2f}，{dist}"
                )
            base = "检测到的目标：\n" + "\n".join(lines)
        if user_prompt:
            base += f"\n\n用户问题：{user_prompt}\n请同时回答。"
        return base

    def _http_post(self, payload: dict) -> Tuple[str, dict]:
        import urllib.request, urllib.error
        url = f"{self.base_url}/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url=url, data=body, method="POST",
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
        text = choices[0].get("message", {}).get("content", "")
        return str(text), (data.get("usage") or {})
