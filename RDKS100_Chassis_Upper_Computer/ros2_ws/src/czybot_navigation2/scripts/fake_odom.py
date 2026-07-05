#!/usr/bin/env python3
"""
假里程计节点 - 基于 cmd_vel 估算位置
注意：这是临时方案，精度较差，仅用于测试
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from tf2_ros import TransformBroadcaster
import math


class FakeOdom(Node):
    def __init__(self):
        super().__init__('fake_odom')
        
        # 订阅速度命令
        self.cmd_sub = self.create_subscription(
            Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        
        # 发布里程计
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        
        # TF广播
        self.tf_broadcaster = TransformBroadcaster(self)
        
        # 状态变量
        self.x = 0.0
        self.y = 0.0
        self.theta = 0.0
        self.vx = 0.0
        self.vth = 0.0
        
        # 上次更新时间
        self.last_time = self.get_clock().now()
        
        # 定时发布里程计（20Hz）
        self.create_timer(0.05, self.publish_odom)
        
        self.get_logger().info('假里程计节点已启动（基于 cmd_vel 估算）')
        self.get_logger().warn('注意：这是临时方案，精度较差！建议修复 STM32 里程计')
    
    def cmd_vel_callback(self, msg):
        """更新速度"""
        self.vx = msg.linear.x
        self.vth = msg.angular.z
    
    def publish_odom(self):
        """发布里程计"""
        current_time = self.get_clock().now()
        dt = (current_time - self.last_time).nanoseconds / 1e9
        self.last_time = current_time
        
        # 更新位置（简单的积分）
        delta_x = self.vx * math.cos(self.theta) * dt
        delta_y = self.vx * math.sin(self.theta) * dt
        delta_theta = self.vth * dt
        
        self.x += delta_x
        self.y += delta_y
        self.theta += delta_theta
        
        # 归一化角度
        while self.theta > math.pi:
            self.theta -= 2 * math.pi
        while self.theta < -math.pi:
            self.theta += 2 * math.pi
        
        # 发布TF
        t = TransformStamped()
        t.header.stamp = current_time.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'
        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0
        
        # 四元数
        cy = math.cos(self.theta / 2.0)
        sy = math.sin(self.theta / 2.0)
        t.transform.rotation.w = cy
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = sy
        
        self.tf_broadcaster.sendTransform(t)
        
        # 发布Odometry
        odom = Odometry()
        odom.header.stamp = current_time.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        
        odom.pose.pose.position.x = self.x
        odom.pose.pose.position.y = self.y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.w = cy
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = sy
        
        odom.twist.twist.linear.x = self.vx
        odom.twist.twist.linear.y = 0.0
        odom.twist.twist.angular.z = self.vth
        
        self.odom_pub.publish(odom)


def main(args=None):
    rclpy.init(args=args)
    node = FakeOdom()
    
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
