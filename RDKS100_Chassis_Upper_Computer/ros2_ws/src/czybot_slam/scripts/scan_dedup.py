#!/usr/bin/env python3

import rclpy
from builtin_interfaces.msg import Time
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan


def ts_to_ns(t: Time) -> int:
    return t.sec * 1_000_000_000 + t.nanosec


def ns_to_ts(ns: int) -> Time:
    t = Time()
    t.sec = int(ns // 1_000_000_000)
    t.nanosec = int(ns % 1_000_000_000)
    return t


class ScanDedup(Node):
    def __init__(self):
        super().__init__('scan_dedup')

        self.declare_parameter('min_interval_ms', 80.0)
        self.declare_parameter('rewrite_stamps', True)
        self.declare_parameter('stamp_step_ms', 1.0)

        min_interval_ms = float(self.get_parameter('min_interval_ms').value)
        stamp_step_ms = float(self.get_parameter('stamp_step_ms').value)

        self.min_interval_ns = int(max(0.0, min_interval_ms) * 1_000_000)
        self.stamp_step_ns = int(max(0.001, stamp_step_ms) * 1_000_000)
        self.rewrite_stamps = bool(self.get_parameter('rewrite_stamps').value)

        self._last_out_ts_ns = 0
        self._dropped_fast = 0
        self._dropped_non_monotonic = 0
        self._passed = 0
        self._fixed = 0

        self._pub = self.create_publisher(LaserScan, '/scan_dedup', 10)
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self._sub = self.create_subscription(LaserScan, '/scan', self._cb, qos)

        self.create_timer(10.0, self._report)
        self.get_logger().info(
            'scan_dedup started: min_interval_ms=%.1f rewrite_stamps=%s'
            % (min_interval_ms, self.rewrite_stamps)
        )

    def _cb(self, msg: LaserScan):
        ts = ts_to_ns(msg.header.stamp)

        if self._last_out_ts_ns > 0:
            gap = ts - self._last_out_ts_ns
            if 0 < gap < self.min_interval_ns:
                self._dropped_fast += 1
                return

            if gap <= 0:
                if not self.rewrite_stamps:
                    self._dropped_non_monotonic += 1
                    return
                ts = self._last_out_ts_ns + self.stamp_step_ns
                msg.header.stamp = ns_to_ts(ts)
                self._fixed += 1

        self._last_out_ts_ns = ts
        self._passed += 1
        self._pub.publish(msg)

    def _report(self):
        self.get_logger().info(
            'scan_dedup: passed=%d dropped_fast=%d '
            'dropped_non_monotonic=%d fixed=%d'
            % (
                self._passed,
                self._dropped_fast,
                self._dropped_non_monotonic,
                self._fixed,
            )
        )


def main():
    rclpy.init()
    node = ScanDedup()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
