"""
vlm_scene.providers.factory
---------------------------
按名字实例化 VLM provider。新增 provider 只需：
  1. 在本目录加 .py 实现 BaseVLMProvider；
  2. 在 _REGISTRY 中注册 name → class；
其余代码（节点、launch、配置）保持不变。
"""

from __future__ import annotations

from typing import Dict, Type, List

from .base import BaseVLMProvider
from .qwen_vl import QwenVLProvider
from .openai_vision import OpenAIVisionProvider
from .deepseek_text import DeepSeekTextProvider
from .internvl_local import InternVLLocalProvider
from .mock import MockProvider


_REGISTRY: Dict[str, Type[BaseVLMProvider]] = {
    "qwen_vl":         QwenVLProvider,
    "openai_vision":   OpenAIVisionProvider,
    "deepseek_text":   DeepSeekTextProvider,
    "internvl_local":  InternVLLocalProvider,
    "mock":            MockProvider,
}


def list_providers() -> List[str]:
    return sorted(_REGISTRY.keys())


def create_provider(name: str, **kwargs) -> BaseVLMProvider:
    """
    根据名字构造 provider 实例。

    传入 kwargs 会被透传给子类构造函数；未知 key 不会报错（由 BaseVLMProvider 兜底）。
    遇到未注册 name 时回退到 MockProvider，保证节点在缺 SDK / 缺 API Key
    的环境也能起来，不会因为一个第三方依赖把整条管线打死。
    """
    key = (name or "").strip().lower()
    cls = _REGISTRY.get(key)
    if cls is None:
        # 主动告警 + 降级 mock，让节点至少能跑起来
        import logging
        logging.getLogger("vlm_scene").warning(
            "[VLM] 未知 provider '%s'，降级为 mock；可用: %s",
            name, list_providers(),
        )
        cls = MockProvider
    return cls(**kwargs)
