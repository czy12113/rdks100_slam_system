#!/usr/bin/env python3
"""
向 Nav2 发送单点导航目标的命令行工具
=========================================
用途：不开 RViz 时，用一行命令把小车送到 (x, y, yaw)。
依赖：Nav2 已经启动并完成激活，且 AMCL 完成定位。

用法：
  ros2 run czybot_navigation2 send_goal <x> <y> [yaw_deg]
示例：
  ros2 run czybot_navigation2 send_goal 1.5 0.0
  ros2 run czybot_navigation2 send_goal 1.5 0.0 90
"""
import math
import sys

import rclpy
from action_msgs.msg import GoalStatus
from geometry_msgs.msg import PoseStamped
from nav2_msgs.action import NavigateToPose
from rclpy.action import ActionClient
from rclpy.node import Node


class GoalSender(Node):
    def __init__(self, x: float, y: float, yaw_rad: float):
        super().__init__('send_goal_cli')
        self._client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        self._x = x
        self._y = y
        self._yaw = yaw_rad

    def send(self) -> int:
        self.get_logger().info('等待 navigate_to_pose action server …')
        if not self._client.wait_for_server(timeout_sec=10.0):
            self.get_logger().error('action server 未就绪，请确认 Nav2 已激活')
            return 2

        pose = PoseStamped()
        pose.header.frame_id = 'map'
        pose.header.stamp = self.get_clock().now().to_msg()
        pose.pose.position.x = self._x
        pose.pose.position.y = self._y
        pose.pose.orientation.z = math.sin(self._yaw / 2.0)
        pose.pose.orientation.w = math.cos(self._yaw / 2.0)

        goal = NavigateToPose.Goal()
        goal.pose = pose

        self.get_logger().info(
            f'发送目标: x={self._x:.3f}, y={self._y:.3f}, '
            f'yaw={math.degrees(self._yaw):.1f}°'
        )
        send_future = self._client.send_goal_async(goal)
        rclpy.spin_until_future_complete(self, send_future)
        gh = send_future.result()
        if gh is None or not gh.accepted:
            self.get_logger().error('目标被 Nav2 拒绝')
            return 3

        self.get_logger().info('目标已被接受，等待执行结果 …')
        result_future = gh.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        status = result_future.result().status
        if status == GoalStatus.STATUS_SUCCEEDED:
            self.get_logger().info('✓ 到达目标')
            return 0
        self.get_logger().error(f'✗ 导航失败，status={status}')
        return 1


def main():
    if len(sys.argv) < 3:
        print('用法: send_goal <x> <y> [yaw_deg]')
        sys.exit(64)

    x = float(sys.argv[1])
    y = float(sys.argv[2])
    yaw_deg = float(sys.argv[3]) if len(sys.argv) >= 4 else 0.0
    yaw_rad = math.radians(yaw_deg)

    rclpy.init()
    node = GoalSender(x, y, yaw_rad)
    try:
        code = node.send()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    sys.exit(code)


if __name__ == '__main__':
    main()
