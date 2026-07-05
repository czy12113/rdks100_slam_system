"""
vlm_scene.providers
-------------------
VLM 服务提供方插件体系。

设计目标：
  - 节点逻辑（订阅、ROI 裁剪、节流、发布）与具体 VLM API 解耦
  - 通过环境变量 / ROS 参数 `provider` 切换实现，不改动节点代码
  - 同一份 prompt + 图像 + 检测结果，由不同 provider 自己处理细节

可选 provider（详见各 .py 文件顶部说明）：
  - qwen_vl       —— 通义千问 VL（默认推荐，DashScope OpenAI 兼容接口）
  - openai_vision —— 任意 OpenAI 兼容 + Vision 端点（智谱 GLM-4V/Moonshot/OpenAI 自家等）
  - deepseek_text —— DeepSeek 纯文本，把检测框翻译成自然语言（看不到画面）
  - internvl_local—— 本地 InternVL2-2B（板端 BPU / CPU，预留接口）
  - mock          —— 离线测试，固定返回模板
"""

from .base import BaseVLMProvider, VLMRequest, VLMResponse
from .factory import create_provider, list_providers

__all__ = [
    "BaseVLMProvider",
    "VLMRequest",
    "VLMResponse",
    "create_provider",
    "list_providers",
]
