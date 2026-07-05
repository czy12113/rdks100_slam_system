"""
vlm_scene.providers.openai_vision
---------------------------------
通用 OpenAI Chat Completions + Vision 兼容 provider。

适配以下服务（只需改 VLM_OPENAI_BASE_URL / VLM_OPENAI_MODEL）：
  - OpenAI 官方：              base_url=https://api.openai.com/v1，model=gpt-4o-mini
  - 智谱 GLM-4V：             base_url=https://open.bigmodel.cn/api/paas/v4，model=glm-4v
  - Moonshot kimi-vl：        base_url=https://api.moonshot.cn/v1，model=moonshot-v1-8k-vision-preview
  - 任意自建 vLLM/LMDeploy：  填本机/集群地址即可

配置（在 vlm_scene.providers.keys 里集中预设）：
  OPENAI_API_KEY        通用 API Key
  VLM_OPENAI_BASE_URL   端点地址
  VLM_OPENAI_MODEL      模型名
读取优先级：构造参数 > 环境变量 > keys.py 常量
"""

from __future__ import annotations

from typing import Optional

from .qwen_vl import QwenVLProvider   # 复用 HTTP/编码逻辑


class OpenAIVisionProvider(QwenVLProvider):
    """与 Qwen-VL 共用 OpenAI Chat Completions 协议，只是换 Key/URL/模型"""

    name = "openai_vision"
    default_model = "gpt-4o-mini"

    DEFAULT_BASE_URL = "https://api.openai.com/v1"

    # 父类构造器会用这些 key 名去 keys.get() 拿值
    KEY_API_KEY = "OPENAI_API_KEY"
    KEY_MODEL = "VLM_OPENAI_MODEL"
    KEY_BASE_URL = "VLM_OPENAI_BASE_URL"

    def healthcheck(self) -> bool:
        if not self.api_key:
            import logging
            logging.getLogger("vlm_scene.openai_vision").warning(
                "[OpenAIVision] 缺少 OPENAI_API_KEY")
            return False
        if not self.base_url:
            import logging
            logging.getLogger("vlm_scene.openai_vision").warning(
                "[OpenAIVision] 缺少 VLM_OPENAI_BASE_URL")
            return False
        return True
