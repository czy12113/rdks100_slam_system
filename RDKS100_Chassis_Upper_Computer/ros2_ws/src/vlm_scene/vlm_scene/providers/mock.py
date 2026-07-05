"""
vlm_scene.providers.mock
------------------------
离线 / 无 API Key 时的兜底实现，仅按检测结果合成模板描述。
用于：
  - CI / 单元测试，不消耗真实 API；
  - 缺网络环境演示视频流；
  - provider 工厂回退路径。
"""

from __future__ import annotations

import time
from typing import List

from .base import BaseVLMProvider, VLMRequest, VLMResponse, Detection


# 中文位置词
def _pos_word(cx: float, frame_w: float) -> str:
    if frame_w <= 0:
        return "前方"
    r = cx / frame_w
    if r < 0.33:
        return "左前方"
    if r > 0.66:
        return "右前方"
    return "正前方"


def _dist_word(d_m: float) -> str:
    if d_m <= 0:
        return "距离未知"
    if d_m < 1.0:
        return f"约 {d_m:.1f}米（很近）"
    if d_m < 3.0:
        return f"约 {d_m:.1f}米"
    return f"约 {d_m:.1f}米（较远）"


class MockProvider(BaseVLMProvider):
    name = "mock"
    default_model = "template-v1"

    def describe(self, req: VLMRequest) -> VLMResponse:
        t0 = time.time()
        dets: List[Detection] = req.detections
        if not dets:
            text = "[模拟描述] 当前画面未检测到障碍物，前方畅通。"
        else:
            h, w = req.frame_bgr.shape[:2]
            parts = []
            for d in dets[:5]:
                cx = (d.x1 + d.x2) / 2
                parts.append(f"{_pos_word(cx, w)}有一个{d.class_name}，{_dist_word(d.distance_m)}")
            text = "[模拟描述] " + "；".join(parts) + "。"
        return VLMResponse(
            description=text,
            provider=self.name,
            model=self.model,
            elapsed_ms=(time.time() - t0) * 1000.0,
        )
