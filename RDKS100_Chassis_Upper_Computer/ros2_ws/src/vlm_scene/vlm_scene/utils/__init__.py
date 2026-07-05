"""vlm_scene.utils - 帮助节点逻辑保持纯函数化，便于单元测试与移植。"""
from .keyframe import KeyframeSelector, TriggerDecision
from .image_ops import ros_image_to_bgr, crop_roi, clip_box, downsample_keep_aspect

__all__ = [
    "KeyframeSelector", "TriggerDecision",
    "ros_image_to_bgr", "crop_roi", "clip_box", "downsample_keep_aspect",
]
