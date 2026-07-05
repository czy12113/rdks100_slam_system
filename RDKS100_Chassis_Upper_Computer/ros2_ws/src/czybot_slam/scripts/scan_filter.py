#!/usr/bin/env python3

import math

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import LaserScan


def is_finite_range(value: float) -> bool:
    return math.isfinite(value)


class ScanFilter(Node):
    def __init__(self):
        super().__init__('scan_filter')

        self.declare_parameter('input_topic', '/scan_dedup')
        self.declare_parameter('output_topic', '/scan_filtered')
        self.declare_parameter('range_min', 0.20)
        self.declare_parameter('range_max', 12.0)
        self.declare_parameter('neighbor_radius', 2)
        self.declare_parameter('min_neighbors', 1)
        self.declare_parameter('max_neighbor_delta', 0.45)
        self.declare_parameter('temporal_min_hits', 2)
        self.declare_parameter('temporal_delta', 0.50)
        self.declare_parameter('use_inf', True)

        self.range_min = float(self.get_parameter('range_min').value)
        self.range_max = float(self.get_parameter('range_max').value)
        self.neighbor_radius = max(
            1, int(self.get_parameter('neighbor_radius').value)
        )
        self.min_neighbors = max(0, int(self.get_parameter('min_neighbors').value))
        self.max_neighbor_delta = float(
            self.get_parameter('max_neighbor_delta').value
        )
        self.temporal_min_hits = max(
            1, int(self.get_parameter('temporal_min_hits').value)
        )
        self.temporal_delta = float(self.get_parameter('temporal_delta').value)
        self.use_inf = bool(self.get_parameter('use_inf').value)

        input_topic = str(self.get_parameter('input_topic').value)
        output_topic = str(self.get_parameter('output_topic').value)

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self._pub = self.create_publisher(LaserScan, output_topic, 10)
        self._sub = self.create_subscription(LaserScan, input_topic, self._cb, qos)

        self._received = 0
        self._removed = 0
        self._temporal_passed = 0
        self._last_ranges = []
        self._hit_counts = []
        self.create_timer(10.0, self._report)
        self.get_logger().info(
            'scan_filter started: %s -> %s range=[%.2f, %.2f] '
            'neighbor_radius=%d min_neighbors=%d max_neighbor_delta=%.2f '
            'temporal_min_hits=%d temporal_delta=%.2f'
            % (
                input_topic,
                output_topic,
                self.range_min,
                self.range_max,
                self.neighbor_radius,
                self.min_neighbors,
                self.max_neighbor_delta,
                self.temporal_min_hits,
                self.temporal_delta,
            )
        )

    def _invalid_value(self) -> float:
        return math.inf if self.use_inf else math.nan

    def _range_is_valid(self, value: float) -> bool:
        return is_finite_range(value) and self.range_min <= value <= self.range_max

    def _has_enough_neighbors(self, ranges, index: int) -> bool:
        if self.min_neighbors == 0:
            return True

        value = ranges[index]
        count = 0
        size = len(ranges)
        for offset in range(-self.neighbor_radius, self.neighbor_radius + 1):
            if offset == 0:
                continue
            neighbor = ranges[(index + offset) % size]
            if not self._range_is_valid(neighbor):
                continue
            if abs(neighbor - value) <= self.max_neighbor_delta:
                count += 1
                if count >= self.min_neighbors:
                    return True
        return False

    def _ensure_temporal_history(self, size: int):
        if len(self._last_ranges) == size:
            return
        self._last_ranges = [math.nan] * size
        self._hit_counts = [0] * size

    def _update_temporal_history(self, index: int, value: float) -> bool:
        previous = self._last_ranges[index]
        previous_hits = self._hit_counts[index]

        if self._range_is_valid(previous) and abs(previous - value) <= self.temporal_delta:
            hits = min(previous_hits + 1, self.temporal_min_hits)
        else:
            hits = 1

        self._last_ranges[index] = value
        self._hit_counts[index] = hits
        return hits >= self.temporal_min_hits

    def _reset_temporal_history(self, index: int):
        self._last_ranges[index] = math.nan
        self._hit_counts[index] = 0

    def _cb(self, msg: LaserScan):
        self._received += 1
        self._ensure_temporal_history(len(msg.ranges))

        out = LaserScan()
        out.header = msg.header
        out.angle_min = msg.angle_min
        out.angle_max = msg.angle_max
        out.angle_increment = msg.angle_increment
        out.time_increment = msg.time_increment
        out.scan_time = msg.scan_time
        out.range_min = self.range_min
        out.range_max = self.range_max
        out.intensities = msg.intensities

        invalid = self._invalid_value()
        filtered = []
        removed = 0

        for i, value in enumerate(msg.ranges):
            if not self._range_is_valid(value):
                self._reset_temporal_history(i)
                filtered.append(invalid)
                removed += 1
                continue

            has_neighbors = self._has_enough_neighbors(msg.ranges, i)
            has_temporal_support = self._update_temporal_history(i, value)

            if not has_neighbors and not has_temporal_support:
                filtered.append(invalid)
                removed += 1
                continue
            if not has_neighbors and has_temporal_support:
                self._temporal_passed += 1
            filtered.append(value)

        self._removed += removed
        out.ranges = filtered
        self._pub.publish(out)

    def _report(self):
        self.get_logger().info(
            'scan_filter: received=%d removed_ranges=%d temporal_passed=%d'
            % (self._received, self._removed, self._temporal_passed)
        )


def main():
    rclpy.init()
    node = ScanFilter()
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
