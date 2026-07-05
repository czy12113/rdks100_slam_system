#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
阿克曼底盘键盘控制节点（优化版）
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import sys
import termios
import tty
import select


class AckermannTeleopKey(Node):
    def __init__(self):
        super().__init__('ackermann_teleop_key')
        
        # 优化后的参数
        self.declare_parameter('max_linear_vel', 0.5)  # 限制到0.5 m/s，防止速度过大导致失控
        self.declare_parameter('max_angular_vel', 0.8)  # 限制到0.8 rad/s，防止舵机过激
        self.declare_parameter('linear_step', 0.1)
        self.declare_parameter('angular_step', 0.15)
        self.declare_parameter('linear_deadzone', 0.02)
        self.declare_parameter('angular_deadzone', 0.05)
        
        self.max_linear_vel = self.get_parameter('max_linear_vel').value
        self.max_angular_vel = self.get_parameter('max_angular_vel').value
        self.linear_step = self.get_parameter('linear_step').value
        self.angular_step = self.get_parameter('angular_step').value
        self.linear_deadzone = self.get_parameter('linear_deadzone').value
        self.angular_deadzone = self.get_parameter('angular_deadzone').value
        
        self.cmd_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        
        self.current_linear = 0.0
        self.current_angular = 0.0
        
        self.settings = termios.tcgetattr(sys.stdin)
        
        self.get_logger().info('阿克曼键盘控制节点已启动（优化版）')
        self.print_usage()
    
    def print_usage(self):
        msg = """
========================================
    阿克曼底盘键盘控制（优化版）
========================================
基本控制：
    w/s : 增加/减少前进速度
    a/d : 左转/右转
    x   : 后退（自动清零角速度）
    空格 : 紧急停止
    
直接控制（推荐）：
    i   : 前进
    ,   : 后退
    j   : 原地左转
    l   : 原地右转
    u   : 前进+左转
    o   : 前进+右转
    m   : 后退+左转
    .   : 后退+右转
    k   : 停止
    
其他：
    q   : 退出

当前设置：
    最大线速度: {:.2f} m/s
    最大角速度: {:.2f} rad/s
========================================
""".format(self.max_linear_vel, self.max_angular_vel)
        print(msg)
    
    def get_key(self):
        """阻塞读取单个按键（保留，供外部调用）"""
        tty.setraw(sys.stdin.fileno())
        key = sys.stdin.read(1)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)
        return key
    
    def apply_deadzone(self):
        if abs(self.current_linear) < self.linear_deadzone:
            self.current_linear = 0.0
        if abs(self.current_angular) < self.angular_deadzone:
            self.current_angular = 0.0
    
    def publish_cmd(self):
        self.apply_deadzone()
        
        msg = Twist()
        msg.linear.x = self.current_linear
        msg.angular.z = self.current_angular
        self.cmd_pub.publish(msg)
        
        status = "线速度: {:.2f} m/s | 角速度: {:.2f} rad/s".format(
            self.current_linear, self.current_angular)
        
        if self.current_linear > 0:
            direction = "前进"
        elif self.current_linear < 0:
            direction = "后退"
        else:
            direction = "停止"
        
        if self.current_angular > 0:
            direction += " + 左转"
        elif self.current_angular < 0:
            direction += " + 右转"
        
        print("\r{} [{}]".format(status, direction), end='', flush=True)
    
    def run(self):
        try:
            while rclpy.ok():
                # 非阻塞读取：超时 50ms，超时则重复发送当前速度保持 STM32 连接活跃
                # 每次读键前设 raw，读完后立即恢复，避免终端状态污染
                rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist:
                    tty.setraw(sys.stdin.fileno())
                    key = sys.stdin.read(1)
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)
                else:
                    # 超时：无按键输入，重复发送当前速度保持 STM32 心跳
                    self.publish_cmd()
                    continue

                if key == 'w':
                    self.current_linear = min(
                        self.current_linear + self.linear_step,
                        self.max_linear_vel
                    )
                    self.publish_cmd()
                
                elif key == 's':
                    self.current_linear = max(
                        self.current_linear - self.linear_step,
                        -self.max_linear_vel
                    )
                    if self.current_linear < 0:
                        self.current_angular = 0.0
                    self.publish_cmd()
                
                elif key == 'x':
                    self.current_linear = -self.max_linear_vel * 0.5
                    self.current_angular = 0.0  # 关键：清零角速度
                    self.publish_cmd()
                
                elif key == 'a':
                    self.current_angular = min(
                        self.current_angular + self.angular_step,
                        self.max_angular_vel
                    )
                    self.publish_cmd()
                
                elif key == 'd':
                    self.current_angular = max(
                        self.current_angular - self.angular_step,
                        -self.max_angular_vel
                    )
                    self.publish_cmd()
                
                elif key == 'i':
                    self.current_linear = self.max_linear_vel * 0.6
                    self.current_angular = 0.0
                    self.publish_cmd()
                
                elif key == ',':
                    self.current_linear = -self.max_linear_vel * 0.5
                    self.current_angular = 0.0
                    self.publish_cmd()
                
                elif key == 'j':
                    self.current_linear = 0.0
                    self.current_angular = self.max_angular_vel * 0.6
                    self.publish_cmd()
                
                elif key == 'l':
                    self.current_linear = 0.0
                    self.current_angular = -self.max_angular_vel * 0.6
                    self.publish_cmd()
                
                elif key == 'u':
                    self.current_linear = self.max_linear_vel * 0.5
                    self.current_angular = self.max_angular_vel * 0.5
                    self.publish_cmd()
                
                elif key == 'o':
                    self.current_linear = self.max_linear_vel * 0.5
                    self.current_angular = -self.max_angular_vel * 0.5
                    self.publish_cmd()
                
                elif key == 'm':
                    self.current_linear = -self.max_linear_vel * 0.4
                    self.current_angular = self.max_angular_vel * 0.4
                    self.publish_cmd()
                
                elif key == '.':
                    self.current_linear = -self.max_linear_vel * 0.4
                    self.current_angular = -self.max_angular_vel * 0.4
                    self.publish_cmd()
                
                elif key == 'k' or key == ' ':
                    self.current_linear = 0.0
                    self.current_angular = 0.0
                    self.publish_cmd()
                    if key == ' ':
                        print("\n[紧急停止]")
                
                elif key == 'q':
                    print("\n退出控制...")
                    break
                
                elif key == '\x03':
                    break
        
        except Exception as e:
            self.get_logger().error(f'错误: {e}')

        finally:
            self.current_linear = 0.0
            self.current_angular = 0.0
            self.publish_cmd()
            print("\n小车已停止")
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)


def main(args=None):
    rclpy.init(args=args)
    node = AckermannTeleopKey()
    
    try:
        node.run()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()