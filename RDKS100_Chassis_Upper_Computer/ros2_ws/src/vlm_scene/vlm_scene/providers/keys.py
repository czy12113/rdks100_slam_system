"""Default VLM provider configuration.

This file is safe for open-source release: it does not contain any API keys.
Provide secrets through environment variables at runtime.

Example:
    export DASHSCOPE_API_KEY="sk-..."
    export OPENAI_API_KEY="sk-..."
    export DEEPSEEK_API_KEY="sk-..."

Read priority:
    environment variable > constant in this file > fallback argument
"""

import os as _os


# DashScope / Qwen-VL
# Apply for a key in Alibaba Cloud Model Studio:
# https://bailian.console.aliyun.com/
DASHSCOPE_API_KEY: str = ""
VLM_QWEN_MODEL: str = "qwen-vl-plus"
VLM_QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# OpenAI-compatible vision providers
# Examples:
#   OpenAI:   base=https://api.openai.com/v1, model=gpt-4o-mini
#   GLM:      base=https://open.bigmodel.cn/api/paas/v4, model=glm-4v
#   Moonshot: base=https://api.moonshot.cn/v1, model=moonshot-v1-8k-vision-preview
#   vLLM:     base=http://your-server:8000/v1, model=<your-model>
OPENAI_API_KEY: str = ""
VLM_OPENAI_MODEL: str = "gpt-4o-mini"
VLM_OPENAI_BASE_URL: str = "https://api.openai.com/v1"


# DeepSeek text fallback. DeepSeek does not provide a vision model here, so it
# is only used as a text-only fallback provider.
DEEPSEEK_API_KEY: str = ""
VLM_DEEPSEEK_MODEL: str = "deepseek-chat"
VLM_DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"


# Local InternVL placeholder.
INTERNVL_MODEL_PATH: str = "/home/sunrise/models/internvl2_2b.hbm"


def get(name: str, fallback: str = "") -> str:
    """Read a configuration value from env, this module, then fallback."""
    env_val = _os.getenv(name, "").strip()
    if env_val:
        return env_val
    const_val = globals().get(name, "")
    if isinstance(const_val, str) and const_val:
        return const_val
    return fallback
