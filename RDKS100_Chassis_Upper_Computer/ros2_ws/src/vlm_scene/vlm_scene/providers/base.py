"""
vlm_scene.providers.base
------------------------
VLM Provider 抽象基类。

所有 provider 必须实现 `describe()`，输入统一的 VLMRequest（含一张
关键帧 + 若干检测框 + 可选 prompt），输出统一的 VLMResponse（自然
语言场景描述 + 可选的细粒度对象描述）。

节点本身不感知任何 SDK / HTTP 细节。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any

import numpy as np


@dataclass
class Detection:
    """单个检测框（与 detection_node 发布的格式对齐）"""
    class_id: int
    class_name: str
    confidence: float
    # 左上 / 右下像素坐标（原图坐标系）
    x1: float
    y1: float
    x2: float
    y2: float
    # 估算距离（米），depth 不可用时为 0.0
    distance_m: float = 0.0


@dataclass
class VLMRequest:
    """一次 VLM 推理请求"""
    # 原始 BGR 帧（HxWx3，uint8），节点已 deep-copy，可自由处理
    frame_bgr: np.ndarray
    # 该帧上的检测结果（已按置信度从高到低排序）
    detections: List[Detection]
    # 用户额外 prompt（可空），来自 REST /api/vlm/ask 或 ROS service
    user_prompt: Optional[str] = None
    # 节点级 prompt 模板（system role），由 config 注入
    system_prompt: Optional[str] = None
    # 是否裁剪 ROI 单独喂给 VLM（True：细节描述；False：整图描述）
    crop_roi: bool = False
    # 帧 metadata，仅用于日志 / 透传
    frame_id: int = 0
    timestamp: float = 0.0
    # True 时 provider 必须把 user_prompt 当作完整 user 消息直接发，
    # 不再追加自带的“下面是检测器给出的初步目标列表…”模板。
    # 火警二次确认要求严格 JSON 输出，必须用 True 避免提示词冲突。
    raw_prompt: bool = False


@dataclass
class VLMResponse:
    """一次 VLM 推理结果"""
    # 整体场景描述（必填）
    description: str
    # 各检测框的逐对象细描述（key = 检测框索引，可选）
    per_object: Dict[int, str] = field(default_factory=dict)
    # 实际调用的 provider 名 + 模型名（用于前端展示）
    provider: str = ""
    model: str = ""
    # 推理耗时（毫秒）
    elapsed_ms: float = 0.0
    # token 占用（若 API 返回）
    tokens_in: int = 0
    tokens_out: int = 0
    # 任意附加字段（如 raw response，仅 debug）
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseVLMProvider:
    """所有 VLM provider 的统一抽象。"""

    #: 子类必须重写
    name: str = "base"
    #: 默认模型名，可被参数覆盖
    default_model: str = ""

    def __init__(self, model: Optional[str] = None, **kwargs):
        self.model: str = model or self.default_model
        # 各 provider 自由消费 kwargs，禁止抛 unknown key 错误
        self._opts: Dict[str, Any] = dict(kwargs)

    # ---------------------------------------------------------------------
    # 子类需要实现的核心接口
    # ---------------------------------------------------------------------
    def describe(self, req: VLMRequest) -> VLMResponse:
        """同步调用 VLM 服务，返回场景描述。"""
        raise NotImplementedError

    # ---------------------------------------------------------------------
    # 可选 hooks
    # ---------------------------------------------------------------------
    def healthcheck(self) -> bool:
        """检查 API Key / 网络 / 本地模型是否就绪，仅供启动日志使用。"""
        return True

    def close(self):
        """释放资源（关闭 session、卸载本地模型等）。"""
        return
