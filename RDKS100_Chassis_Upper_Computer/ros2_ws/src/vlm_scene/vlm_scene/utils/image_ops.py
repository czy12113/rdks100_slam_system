"""
vlm_scene.utils.image_ops
-------------------------
图像辅助工具：ROS Image 转 ndarray、ROI 裁剪 + padding、关键帧选择。
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import numpy as np

# 提示：本模块刻意不依赖 cv_bridge，避免 venv / 系统 Python 路径冲突时
# 编译失败。所有解码都手动用 numpy reshape 完成，与 detection_node 一致。


def ros_image_to_bgr(msg) -> Optional[np.ndarray]:
    """sensor_msgs/Image → HxWx3 BGR uint8 ndarray。

    支持 rgb8 / bgr8 两种 encoding，其它返回 None。
    """
    try:
        arr = np.frombuffer(msg.data, dtype=np.uint8)
        h, w = int(msg.height), int(msg.width)
        if h <= 0 or w <= 0 or arr.size < h * w * 3:
            return None
        img = arr.reshape((h, w, 3))
        enc = (msg.encoding or "").lower()
        if "rgb" in enc:
            img = img[..., ::-1]
        return np.ascontiguousarray(img)
    except Exception:
        return None


def clip_box(x1: float, y1: float, x2: float, y2: float,
             w: int, h: int) -> Tuple[int, int, int, int]:
    """把 [x1,y1,x2,y2] 限制在画面内，并保证 x2>x1, y2>y1。"""
    x1i = int(max(0, min(w - 1, round(x1))))
    y1i = int(max(0, min(h - 1, round(y1))))
    x2i = int(max(0, min(w, round(x2))))
    y2i = int(max(0, min(h, round(y2))))
    if x2i <= x1i:
        x2i = min(w, x1i + 1)
    if y2i <= y1i:
        y2i = min(h, y1i + 1)
    return x1i, y1i, x2i, y2i


def crop_roi(bgr: np.ndarray, x1: float, y1: float, x2: float, y2: float,
             padding: float = 0.1) -> np.ndarray:
    """按比例向外 padding 后裁剪出 ROI（保证至少 1x1 像素）"""
    h, w = bgr.shape[:2]
    bw = max(1.0, x2 - x1)
    bh = max(1.0, y2 - y1)
    pw = bw * padding
    ph = bh * padding
    xx1, yy1, xx2, yy2 = clip_box(x1 - pw, y1 - ph, x2 + pw, y2 + ph, w, h)
    return bgr[yy1:yy2, xx1:xx2].copy()


def downsample_keep_aspect(bgr: np.ndarray, max_side: int) -> np.ndarray:
    """限制最长边 <= max_side，避免给 VLM 喂太大图片"""
    import cv2
    h, w = bgr.shape[:2]
    side = max(h, w)
    if side <= max_side:
        return bgr
    scale = max_side / side
    return cv2.resize(bgr, (int(w * scale), int(h * scale)),
                      interpolation=cv2.INTER_AREA)
