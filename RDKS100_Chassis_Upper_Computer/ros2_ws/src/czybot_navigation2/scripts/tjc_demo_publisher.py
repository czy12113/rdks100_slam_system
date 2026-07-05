#!/usr/bin/env python3
"""
TJC串口屏演示数据发布器
用于测试串口屏显示功能，发布模拟的机器人状态数据
"""
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState
from std_msgs.msg import String
from geometry_msgs.msg import Quaternion
import math
import time


class TJCDemoPublisher(Node):
    def __init__(self):
        super().__init__('tjc_demo_publisher')
        
        # 发布器
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        self.battery_pub = self.create_publisher(BatteryState, 'battery_state', 10)
        self.mode_pub = self.create_publisher(String, 'robot_mode', 10)
        self.nav_status_pub = self.create_publisher(String, 'nav_status', 10)
        
        # 模拟数据
        self.t = 0.0
        self.mode_index = 0
        self.modes = ['IDLE', 'MANUAL', 'AUTO', 'SLAM']
        self.nav_index = 0
        self.nav_statuses = ['READY', 'NAVIGATING', 'ARRIVED', 'FAILED']
        
        # 定时器
        self.timer = self.create_timer(0.1, self.timer_callback)  # 10Hz
        self.mode_timer = self.create_timer(5.0, self.mode_callback)  # 5秒切换一次模式
        
        self.get_logger().info('TJC演示数据发布器已启动')
        self.get_logger().info('发布模拟数据到: /odom, /battery_state, /robot_mode, /nav_status')
    
    def timer_callback(self):
        """发布模拟的里程计和电池数据"""
        self.t += 0.1
        
        # 模拟圆周运动
        radius = 2.0
        angular_vel = 0.5  # rad/s
        linear_vel = radius * angular_vel
        
        x = radius * math.cos(angular_vel * self.t)
        y = radius * math.sin(angular_vel * self.t)
        yaw = angular_vel * self.t + math.pi / 2
        
        # 发布里程计
        odom = Odometry()
        odom.header.stamp = self.get_clock().now().to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.position.z = 0.0
        
        # 转换yaw为四元数
        cy = math.cos(yaw / 2.0)
        sy = math.sin(yaw / 2.0)
        odom.pose.pose.orientation.w = cy
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = sy
        
        odom.twist.twist.linear.x = linear_vel
        odom.twist.twist.angular.z = angular_vel
        
        self.odom_pub.publish(odom)
        
        # 发布电池状态（模拟缓慢放电）
        battery = BatteryState()
        battery.voltage = 12.6 - (self.t % 100) * 0.01  # 12.6V -> 11.6V
        battery.percentage = 1.0 - (self.t % 100) * 0.01  # 100% -> 0%
        
        self.battery_pub.publish(battery)
    
    def mode_callback(self):
        """定期切换模式和导航状态"""
        # 切换模式
        mode_msg = String()
        mode_msg.data = self.modes[self.mode_index]
        self.mode_pub.publish(mode_msg)
        self.get_logger().info(f'切换模式: {mode_msg.data}')
        
        self.mode_index = (self.mode_index + 1) % len(self.modes)
        
        # 切换导航状态
        nav_msg = String()
        nav_msg.data = self.nav_statuses[self.nav_index]
        self.nav_status_pub.publish(nav_msg)
        self.get_logger().info(f'切换导航状态: {nav_msg.data}')
        
        self.nav_index = (self.nav_index + 1) % len(self.nav_statuses)


def main(args=None):
    rclpy.init(args=args)
    node = TJCDemoPublisher()
    
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
