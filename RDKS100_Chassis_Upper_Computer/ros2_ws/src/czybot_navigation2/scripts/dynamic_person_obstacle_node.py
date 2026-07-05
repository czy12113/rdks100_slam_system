#!/usr/bin/env python3
"""
dynamic_person_obstacle_node.py — 动态行人障碍 & 安全决策节点
==============================================================

创新点核心：
    公网不可用时，本节点与 d435i_detection + Nav2 组成
    “离线自主安全决策” 闭环：
      1. 订阅 /detection/results（class_name=person 且 conf>=阈值），
         把行人像素框 + distance_m 反投影为相机系下的 3D 点；
      2. 发布到 /dynamic_person_points（sensor_msgs/PointCloud2），
         Nav2 local/global costmap 把它当作 obstacle_layer 观测源，
         从而 “看见”→ 膨胀 → 重规划 → 绕行；
      3. 距离过近或位于危险中心区时，主动发布 /cmd_vel_estop（std_msgs/Empty），
         由 stm32_bridge 立刻停车，无需等 Nav2 规划失败；
      4. 每一次判定都发布 /vlm/safety_event（std_msgs/String, JSON），
         后端推给前端做告警展示；同时把最近一条 vlm_summary 附上，
         形成 “本地视觉理解 + 本地安全决策” 的对外语义证据。

订阅：
    /detection/results               std_msgs/String(JSON)   YOLO/DOSOD 检测
    /vlm/scene_description           std_msgs/String(JSON)   本地/云端 VLM 描述（可选）
    /camera/camera/color/camera_info sensor_msgs/CameraInfo  用来把像素 → 相机系 3D 点

发布：
    /dynamic_person_points           sensor_msgs/PointCloud2  Nav2 观测源
    /vlm/safety_event                std_msgs/String(JSON)    结构化安全事件
    /cmd_vel_estop                   std_msgs/Empty           急停信号

关键参数（可通过 launch parameters 覆盖）：
    person_conf_threshold      float, 默认 0.55
    stop_distance_m            float, 默认 0.8
    reroute_distance_m         float, 默认 2.5
    center_ratio               float, 默认 0.4   （画面中央宽度比例）
    publish_rate_hz            float, 默认 5.0
    frame_id                   str,   默认 "camera_color_optical_frame"
    # 相机内参兜底（CameraInfo 未到时使用）
    default_fx / default_fy    float, 默认 615.0 / 615.0
    default_cx / default_cy    float, 默认 320.0 / 240.0

日志前缀：
    [SAFETY] ...           安全动作
    [DYNP] ...             行人观测发布
    [SAFEEVT] ...          事件 JSON 发布

不改变现有 Nav2 主链行为：本节点只是往 costmap 里“喂”额外观测源，
只在近距离危险时主动发 estop；如果不希望 estop 生效，可以把 stop_distance_m
设置为 0（此时只会做 reroute 提示，不发急停）。
"""

from __future__ import annotations

import json
import math
import struct
import time
from typing import List, Optional, Tuple

import rclpy
from rclpy.node import Node
from rclpy.qos import (
    QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy,
)

from std_msgs.msg import String, Empty, Header
from sensor_msgs.msg import PointCloud2, PointField, CameraInfo


class DynamicPersonObstacleNode(Node):

    def __init__(self):
        super().__init__("dynamic_person_obstacle_node")

        # ── 参数 ────────────────────────────────────────────────────────
        self.declare_parameter("sub_topic_detection", "/detection/results")
        self.declare_parameter("sub_topic_vlm",       "/vlm/scene_description")
        self.declare_parameter("sub_topic_caminfo",   "/camera/camera/color/camera_info")
        self.declare_parameter("pub_topic_points",    "/dynamic_person_points")
        self.declare_parameter("pub_topic_safety",    "/vlm/safety_event")
        self.declare_parameter("pub_topic_estop",     "/cmd_vel_estop")

        self.declare_parameter("person_conf_threshold", 0.55)
        self.declare_parameter("stop_distance_m",       0.8)
        self.declare_parameter("reroute_distance_m",    2.5)
        self.declare_parameter("center_ratio",          0.4)
        self.declare_parameter("recovery_distance_m",   1.2)   # 停车恢复迟滞
        self.declare_parameter("publish_rate_hz",       5.0)
        self.declare_parameter("frame_id",              "camera_color_optical_frame")

        # 相机内参兜底
        self.declare_parameter("default_fx", 615.0)
        self.declare_parameter("default_fy", 615.0)
        self.declare_parameter("default_cx", 320.0)
        self.declare_parameter("default_cy", 240.0)
        self.declare_parameter("default_width",  640)
        self.declare_parameter("default_height", 480)

        # 每个行人 bbox 在点云中撒的点数量（>=1）；点云由 Nav2 costmap raytrace
        # 用来 marking obstacle，密一点更稳
        self.declare_parameter("points_per_person", 12)

        self.person_conf = float(self.get_parameter("person_conf_threshold").value)
        self.stop_d      = float(self.get_parameter("stop_distance_m").value)
        self.reroute_d   = float(self.get_parameter("reroute_distance_m").value)
        self.center_r    = float(self.get_parameter("center_ratio").value)
        self.recovery_d  = float(self.get_parameter("recovery_distance_m").value)
        self.rate_hz     = float(self.get_parameter("publish_rate_hz").value)
        self.frame_id    = self.get_parameter("frame_id").value or "camera_color_optical_frame"
        self.ppp         = max(1, int(self.get_parameter("points_per_person").value))

        # 内参
        self._fx = float(self.get_parameter("default_fx").value)
        self._fy = float(self.get_parameter("default_fy").value)
        self._cx = float(self.get_parameter("default_cx").value)
        self._cy = float(self.get_parameter("default_cy").value)
        self._img_w = int(self.get_parameter("default_width").value)
        self._img_h = int(self.get_parameter("default_height").value)
        self._caminfo_ready = False

        # ── QoS ─────────────────────────────────────────────────────────
        qos_reliable = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST, depth=10,
        )
        qos_sensor = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST, depth=1,
            durability=DurabilityPolicy.VOLATILE,
        )

        # ── 订阅 ────────────────────────────────────────────────────────
        self.create_subscription(
            String, self.get_parameter("sub_topic_detection").value,
            self._cb_det, qos_reliable,
        )
        self.create_subscription(
            String, self.get_parameter("sub_topic_vlm").value,
            self._cb_vlm, qos_reliable,
        )
        self.create_subscription(
            CameraInfo, self.get_parameter("sub_topic_caminfo").value,
            self._cb_caminfo, qos_sensor,
        )

        # ── 发布 ────────────────────────────────────────────────────────
        self._pub_points = self.create_publisher(
            PointCloud2, self.get_parameter("pub_topic_points").value, qos_reliable,
        )
        self._pub_safety = self.create_publisher(
            String, self.get_parameter("pub_topic_safety").value, qos_reliable,
        )
        self._pub_estop = self.create_publisher(
            Empty, self.get_parameter("pub_topic_estop").value, qos_reliable,
        )

        # ── 状态 ────────────────────────────────────────────────────────
        # 最近一次检测结果（带 timestamp）
        self._latest_dets: List[dict] = []
        self._latest_det_ts: float = 0.0
        self._latest_det_frame: int = 0

        # 最近一次 VLM 结构化输出（可选，用于 safety_event.vlm_summary）
        self._latest_vlm: Optional[dict] = None

        # 停车状态迟滞：进入 stop 后需要 recovery_distance_m 才恢复
        self._current_action: str = "clear"    # clear / reroute / stop
        self._last_event_key: str = ""         # 变化时才发事件，避免刷屏
        self._replan_count: int = 0
        self._last_replan_ms: float = 0.0

        # 定时器：以固定频率把最新观测转成点云 + 判定安全动作
        period = 1.0 / max(0.5, self.rate_hz)
        self._timer = self.create_timer(period, self._tick)

        self.get_logger().info(
            f"[DYNP] 启动 conf>={self.person_conf} stop<{self.stop_d}m "
            f"reroute<{self.reroute_d}m rate={self.rate_hz}Hz "
            f"frame={self.frame_id}"
        )

    # ------------------------------------------------------------------
    # 订阅回调
    # ------------------------------------------------------------------
    def _cb_det(self, msg: String):
        try:
            data = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"[DYNP] 解析 detection_results 失败: {e}")
            return
        dets = data.get("detections") or []
        # 只保留 person 且置信度达标
        keep = []
        for d in dets:
            try:
                if str(d.get("class_name", "")).lower() != "person":
                    continue
                if float(d.get("confidence", 0.0)) < self.person_conf:
                    continue
                bbox = d.get("bbox") or {}
                keep.append({
                    "class_name": d.get("class_name"),
                    "confidence": float(d.get("confidence", 0.0)),
                    "x1": float(bbox.get("x1", 0.0)),
                    "y1": float(bbox.get("y1", 0.0)),
                    "x2": float(bbox.get("x2", 0.0)),
                    "y2": float(bbox.get("y2", 0.0)),
                    "distance_m": float(d.get("distance_m", 0.0) or 0.0),
                })
            except (TypeError, ValueError):
                continue
        self._latest_dets = keep
        self._latest_det_ts = float(data.get("timestamp", time.time()) or time.time())
        self._latest_det_frame = int(data.get("frame_id", 0) or 0)

    def _cb_vlm(self, msg: String):
        # vlm_node 的 scene_description 里 description 字段可能是 JSON 字符串
        try:
            payload = json.loads(msg.data)
        except Exception:
            return
        desc = payload.get("description")
        parsed = None
        if isinstance(desc, str):
            try:
                parsed = json.loads(desc)
            except Exception:
                parsed = {"scene": desc}
        elif isinstance(desc, dict):
            parsed = desc
        if parsed is None:
            return
        self._latest_vlm = {
            "provider": payload.get("provider"),
            "model": payload.get("model"),
            "elapsed_ms": payload.get("elapsed_ms"),
            "trigger": payload.get("trigger"),
            "scene": parsed.get("scene"),
            "risk": parsed.get("risk"),
            "reason": parsed.get("reason"),
            "suggestion": parsed.get("suggestion"),
            "backend": parsed.get("backend"),
            "ts": payload.get("timestamp"),
        }

    def _cb_caminfo(self, msg: CameraInfo):
        try:
            k = list(msg.k)
            if len(k) == 9 and k[0] > 1.0:
                self._fx = float(k[0])
                self._fy = float(k[4])
                self._cx = float(k[2])
                self._cy = float(k[5])
                self._img_w = int(msg.width or self._img_w)
                self._img_h = int(msg.height or self._img_h)
                if not self._caminfo_ready:
                    self._caminfo_ready = True
                    self.get_logger().info(
                        f"[DYNP] 相机内参已就绪 fx={self._fx:.1f} fy={self._fy:.1f} "
                        f"cx={self._cx:.1f} cy={self._cy:.1f} size={self._img_w}x{self._img_h}"
                    )
        except Exception as e:
            self.get_logger().warn(f"[DYNP] 解析 CameraInfo 失败: {e}")

    # ------------------------------------------------------------------
    # 主循环
    # ------------------------------------------------------------------
    def _tick(self):
        dets = list(self._latest_dets)

        # ---- 1. 把 person 检测转成 3D 点，发布 PointCloud2 ----------------
        # 即使没有 person，也发一次空点云，触发 costmap clearing（否则障碍不消失）
        points_cam: List[Tuple[float, float, float]] = []
        for d in dets:
            pts = self._person_to_points(d)
            points_cam.extend(pts)

        self._publish_pointcloud(points_cam)

        # ---- 2. 判定安全动作 ----------------------------------------------
        action, reason, danger = self._decide_action(dets)

        # 触发急停（stop 且首次进入）
        if action == "stop" and self._current_action != "stop":
            try:
                self._pub_estop.publish(Empty())
                self.get_logger().warn(
                    f"[SAFETY] estop 已发送 reason={reason}"
                )
            except Exception as e:
                self.get_logger().error(f"[SAFETY] 发布 estop 失败: {e}")

        # 从 stop 恢复要求距离 > recovery_d（迟滞防抖）
        if self._current_action == "stop" and action != "stop":
            if danger and danger.get("distance_m", 999.0) < self.recovery_d:
                action = "stop"
                reason = f"仍在恢复迟滞区（{danger.get('distance_m', 0.0):.2f}m < {self.recovery_d}m）"

        # replan 计数（reroute 首次进入时 +1）
        now_ms = time.time() * 1000.0
        if action == "reroute" and self._current_action != "reroute":
            self._replan_count += 1
            self._last_replan_ms = now_ms

        # 事件去抖：同一 action + 同一最近距离段变化才发
        dist_bucket = -1
        if danger and danger.get("distance_m", 0.0) > 0:
            dist_bucket = int(danger["distance_m"] * 4)   # 0.25m 一档
        event_key = f"{action}:{dist_bucket}"
        if event_key != self._last_event_key or action == "stop":
            self._publish_safety_event(action, reason, dets, danger)
            self._last_event_key = event_key

        self._current_action = action

    # ------------------------------------------------------------------
    # 像素框 → 相机系 3D 点
    # ------------------------------------------------------------------
    def _person_to_points(self, det: dict) -> List[Tuple[float, float, float]]:
        """
        把行人 bbox + distance_m 反投影为若干相机光学系（右-下-前，Z 向前）的 3D 点。
        camera_color_optical_frame 是 REP-103 光学系：X 右，Y 下，Z 前。
        """
        z = det.get("distance_m", 0.0)
        if not z or z <= 0.1 or z > 15.0:
            # 距离不可用：跳过，避免噪声进入 costmap
            return []

        x1, y1, x2, y2 = det["x1"], det["y1"], det["x2"], det["y2"]
        cu = (x1 + x2) * 0.5
        cv = (y1 + y2) * 0.5

        # bbox 内均匀采样 self.ppp 个像素，反投影到 3D
        pts: List[Tuple[float, float, float]] = []
        n = self.ppp
        # 取一个 3x4 的网格再插值到 n 点
        cols = max(2, int(math.ceil(math.sqrt(n * (x2 - x1) / max(1.0, y2 - y1)))))
        rows = max(2, int(math.ceil(n / cols)))
        for r in range(rows):
            for c in range(cols):
                if len(pts) >= n:
                    break
                # 采样点偏画面下半部分（脚部反投影更贴近地面高度，Nav2 costmap 更喜欢）
                u = x1 + (c + 0.5) / cols * (x2 - x1)
                v = y1 + (r + 0.6) / rows * (y2 - y1)
                X = (u - self._cx) / self._fx * z
                Y = (v - self._cy) / self._fy * z
                Z = z
                # 中心点距离 z 已经是深度，边缘点略偏但足够 Nav2 marking
                pts.append((X, Y, Z))
        # 至少给一个中心点作为兜底
        if not pts:
            X = (cu - self._cx) / self._fx * z
            Y = (cv - self._cy) / self._fy * z
            pts.append((X, Y, z))
        return pts

    # ------------------------------------------------------------------
    # 发布 PointCloud2
    # ------------------------------------------------------------------
    def _publish_pointcloud(self, points: List[Tuple[float, float, float]]):
        header = Header()
        header.stamp = self.get_clock().now().to_msg()
        header.frame_id = self.frame_id

        msg = PointCloud2()
        msg.header = header
        msg.height = 1
        msg.width = len(points)
        msg.is_dense = True
        msg.is_bigendian = False

        # 3 个 float32 字段：x/y/z
        fields = [
            PointField(name="x", offset=0,  datatype=PointField.FLOAT32, count=1),
            PointField(name="y", offset=4,  datatype=PointField.FLOAT32, count=1),
            PointField(name="z", offset=8,  datatype=PointField.FLOAT32, count=1),
        ]
        msg.fields = fields
        msg.point_step = 12
        msg.row_step = msg.point_step * msg.width

        buf = bytearray()
        for x, y, z in points:
            buf += struct.pack("<fff", float(x), float(y), float(z))
        msg.data = bytes(buf)
        try:
            self._pub_points.publish(msg)
        except Exception as e:
            self.get_logger().error(f"[DYNP] 发布 pointcloud 失败: {e}")

    # ------------------------------------------------------------------
    # 安全动作判定
    # ------------------------------------------------------------------
    def _decide_action(self, dets: List[dict]) -> Tuple[str, str, Optional[dict]]:
        """
        返回 (action, reason, danger_det)
        action: clear / reroute / stop
        """
        if not dets:
            return "clear", "无行人在视场内", None

        w = max(1, self._img_w)
        cx_min = w * (0.5 - self.center_r / 2)
        cx_max = w * (0.5 + self.center_r / 2)

        def _score(d):
            cx = (d["x1"] + d["x2"]) * 0.5
            in_center = 1 if (cx_min <= cx <= cx_max) else 0
            dist = d["distance_m"] if d["distance_m"] > 0 else 99.0
            return (-in_center, dist)  # 中心优先、近的优先

        dets_sorted = sorted(dets, key=_score)
        top = dets_sorted[0]
        cx = (top["x1"] + top["x2"]) * 0.5
        in_center = cx_min <= cx <= cx_max
        d = top["distance_m"] if top["distance_m"] > 0 else 99.0

        if in_center and d < self.stop_d:
            return "stop", (
                f"行人位于路径中央且距离 {d:.2f}m < {self.stop_d:.2f}m"
            ), top
        if d < self.stop_d:
            return "stop", (
                f"侧向行人距离 {d:.2f}m 过近，触发保守停车"
            ), top
        if in_center and d < self.reroute_d:
            return "reroute", (
                f"行人位于路径中央 {d:.2f}m，需要绕行"
            ), top
        if in_center:
            return "reroute", (
                f"行人位于路径中央（距离 {d:.2f}m），降速观察"
            ), top
        return "clear", (
            f"检测到 {len(dets)} 名行人，均位于路径外，最近 {d:.2f}m"
        ), top

    # ------------------------------------------------------------------
    # 发布 safety_event
    # ------------------------------------------------------------------
    def _publish_safety_event(
        self, action: str, reason: str,
        dets: List[dict], danger: Optional[dict],
    ):
        vlm_summary = None
        if self._latest_vlm is not None:
            vlm_summary = {
                "provider":   self._latest_vlm.get("provider"),
                "backend":    self._latest_vlm.get("backend"),
                "scene":      self._latest_vlm.get("scene"),
                "risk":       self._latest_vlm.get("risk"),
                "reason":     self._latest_vlm.get("reason"),
                "suggestion": self._latest_vlm.get("suggestion"),
                "elapsed_ms": self._latest_vlm.get("elapsed_ms"),
            }
        payload = {
            "timestamp":  time.time(),
            "event":      action,           # clear / reroute / stop
            "action":     action,
            "reason":     reason,
            "person_count": len(dets),
            "danger": (None if not danger else {
                "class_name": danger.get("class_name"),
                "confidence": round(float(danger.get("confidence", 0.0)), 3),
                "distance_m": round(float(danger.get("distance_m", 0.0)), 3),
                "bbox": {
                    "x1": danger.get("x1"), "y1": danger.get("y1"),
                    "x2": danger.get("x2"), "y2": danger.get("y2"),
                },
            }),
            "detection_frame_id": self._latest_det_frame,
            "detection_ts": self._latest_det_ts,
            "vlm_summary": vlm_summary,
            "replan_count": self._replan_count,
            "last_replan_ms": round(self._last_replan_ms, 1),
            "params": {
                "stop_distance_m": self.stop_d,
                "reroute_distance_m": self.reroute_d,
                "recovery_distance_m": self.recovery_d,
                "person_conf_threshold": self.person_conf,
                "center_ratio": self.center_r,
            },
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        try:
            self._pub_safety.publish(msg)
        except Exception as e:
            self.get_logger().error(f"[SAFEEVT] 发布失败: {e}")
            return
        # 关键动作打 warn，便于终端截屏
        if action == "stop":
            self.get_logger().warn(f"[SAFETY] action=stop reason={reason}")
        elif action == "reroute":
            self.get_logger().warn(f"[SAFETY] action=reroute reason={reason}")
        else:
            self.get_logger().info(f"[SAFETY] action=clear reason={reason}")


def main(args=None):
    rclpy.init(args=args)
    node = DynamicPersonObstacleNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
