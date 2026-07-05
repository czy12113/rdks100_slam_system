"""
vlm_scene.utils.keyframe
------------------------
关键帧筛选器：避免每一帧都送 VLM（贵 + 慢）。

触发逻辑（任一满足即触发，并且距上次触发 >= cooldown）：
  A. 检测结果集合变化：与上一帧相比新增/删除目标类别；
  B. 任意目标距离穿越阈值（例如从 1.5m → 0.8m）；
  C. 长时间未触发（heartbeat_sec）兜底，保证前端面板有内容刷新；
  D. 外部强制触发（REST 手动 ask、跌倒、急停等）。

实现要点：
  - 完全无锁，所有状态都属于单线程使用方（vlm_node 推理线程）；
  - 不依赖 ROS，方便单测；
  - cooldown 用 time.monotonic，避免 NTP 跳时间影响。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Set

from ..providers.base import Detection


@dataclass
class TriggerDecision:
    fire: bool
    reason: str  # 触发原因，便于日志与前端展示


class KeyframeSelector:
    def __init__(
        self,
        cooldown_sec: float = 3.0,
        heartbeat_sec: float = 20.0,
        distance_threshold_m: float = 0.5,
        near_distance_m: float = 1.0,
    ):
        self.cooldown_sec = float(cooldown_sec)
        self.heartbeat_sec = float(heartbeat_sec)
        self.distance_threshold_m = float(distance_threshold_m)
        self.near_distance_m = float(near_distance_m)

        # 状态：上一次触发的检测集合 + 时间
        self._last_classes: Set[str] = set()
        # class_name -> 上次记录的最小距离
        self._last_min_dist: dict = {}
        self._last_fire_ts: float = 0.0
        self._last_check_ts: float = 0.0

    # ------------------------------------------------------------------
    def decide(self, dets: List[Detection],
                force: bool = False) -> TriggerDecision:
        """判定本帧是否需要触发 VLM。"""
        now = time.monotonic()
        self._last_check_ts = now

        if force:
            self._update_state(dets, now)
            return TriggerDecision(True, "external_force")

        # cooldown：刚发过一次就静默一会
        if now - self._last_fire_ts < self.cooldown_sec:
            return TriggerDecision(False, "cooldown")

        # heartbeat 兜底
        if now - self._last_fire_ts >= self.heartbeat_sec:
            self._update_state(dets, now)
            return TriggerDecision(True, "heartbeat")

        cur_classes = {d.class_name for d in dets}
        if cur_classes != self._last_classes:
            self._update_state(dets, now)
            diff = (cur_classes ^ self._last_classes) or {"<empty>"}
            return TriggerDecision(True, f"class_change:{','.join(sorted(diff))}")

        # 距离穿越：任一类别的最小距离变化超过阈值
        cur_min = self._min_dist_by_class(dets)
        for cls, d in cur_min.items():
            prev = self._last_min_dist.get(cls)
            if prev is None:
                continue
            if abs(prev - d) >= self.distance_threshold_m:
                self._update_state(dets, now)
                return TriggerDecision(True,
                    f"distance_change:{cls}:{prev:.2f}->{d:.2f}m")
            # 由远变近，越过 near 阈值（更严格警示）
            if prev > self.near_distance_m and d <= self.near_distance_m:
                self._update_state(dets, now)
                return TriggerDecision(True,
                    f"near_threshold:{cls}:{d:.2f}m")

        return TriggerDecision(False, "no_change")

    # ------------------------------------------------------------------
    def _update_state(self, dets: List[Detection], now: float):
        self._last_classes = {d.class_name for d in dets}
        self._last_min_dist = self._min_dist_by_class(dets)
        self._last_fire_ts = now

    @staticmethod
    def _min_dist_by_class(dets: Iterable[Detection]) -> dict:
        out: dict = {}
        for d in dets:
            if d.distance_m <= 0:
                continue
            prev = out.get(d.class_name)
            if prev is None or d.distance_m < prev:
                out[d.class_name] = d.distance_m
        return out

    def force_reset(self):
        """前端切换 provider / 修改 prompt 时调用，下一帧立刻触发一次。"""
        self._last_fire_ts = 0.0
        self._last_classes.clear()
        self._last_min_dist.clear()
