#!/usr/bin/env python3
"""
阿克曼底盘键盘控制节点（优化版）
功能：通过键盘控制阿克曼底盘的电机速度和舵机转向
优化：
1. 后退时强制清零角速度，避免舵机转动
2. 增加死区处理，提高稳定性
3. 调整默认参数，提高响应速度
4. 增加更多控制模式
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist
import sys
import termios
import tty


class AckermannTeleopKey(Node):
    def __init__(self):
        super().__init__('ackermann_teleop_key')
        
        # 声明参数（优化后的默认值）
        self.declare_parameter('max_linear_vel', 0.8)  # 提高到0.8 m/s
        self.declare_parameter('max_angular_vel', 1.2)  # 提高到1.2 rad/s
        self.declare_parameter('linear_step', 0.1)  # 增大步进
        self.declare_parameter('angular_step', 0.15)  # 增大步进
        self.declare_parameter('linear_deadzone', 0.02)  # 线速度死区
        self.declare_parameter('angular_deadzone', 0.05)  # 角速度死区
        
        self.max_linear_vel = self.get_parameter('max_linear_vel').value
        self.max_angular_vel = self.get_parameter('max_angular_vel').value
        self.linear_step = self.get_parameter('linear_step').value
        self.angular_step = self.get_parameter('angular_step').value
        self.linear_deadzone = self.get_parameter('linear_deadzone').value
        self.angular_deadzone = self.get_parameter('angular_deadzone').value
        
        # 发布速度命令
        self.cmd_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        
        # 当前速度
        self.current_linear = 0.0
        self.current_angular = 0.0
        
        # 保存终端设置
        self.settings = termios.tcgetattr(sys.stdin)
        
        self.get_logger().info('阿克曼键盘控制节点已启动（优化版）')
        self.print_usage()
    
    def print_usage(self):
        """打印使用说明"""
        msg = """
========================================
    阿克曼底盘键盘控制（优化版）
========================================
基本控制：
    w/s : 增加/减少前进速度
    a/d : 左转/右转（控制舵机）
    x   : 后退（自动清零角速度）
    空格 : 紧急停止
    
直接控制（推荐）：
    i   : 前进（固定速度）
    ,   : 后退（固定速度）
    j   : 原地左转
    l   : 原地右转
    u   : 前进+左转
    o   : 前进+右转
    m   : 后退+左转
    .   : 后退+右转
    k   : 停止
    
其他：
    q   : 退出程序

当前设置：
    最大线速度: {:.2f} m/s
    最大角速度: {:.2f} rad/s
    线速度步进: {:.2f} m/s
    角速度步进: {:.2f} rad/s
    线速度死区: {:.3f} m/s
    角速度死区: {:.3f} rad/s
========================================
""".format(self.max_linear_vel, self.max_angular_vel, 
           self.linear_step, self.angular_step,
           self.linear_deadzone, self.angular_deadzone)
        print(msg)
    
    def get_key(self):
        """获取键盘输入"""
        tty.setraw(sys.stdin.fileno())
        key = sys.stdin.read(1)
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self.settings)
        return key
    
    def apply_deadzone(self):
        """应用死区处理"""
        if abs(self.current_linear) < self.linear_deadzone:
            self.current_linear = 0.0
        if abs(self.current_angular) < self.angular_deadzone:
            self.current_angular = 0.0
    
    def publish_cmd(self):
        """发布速度命令"""
        # 应用死区
        self.apply_deadzone()
        
        msg = Twist()
        msg.linear.x = self.current_linear
        msg.angular.z = self.current_angular
        self.cmd_pub.publish(msg)
        
        # 显示当前状态
        status = "线速度: {:.2f} m/s | 角速度: {:.2f} rad/s".format(
            self.current_linear, self.current_angular)
        
        # 添加方向指示
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
        """主循环"""
        try:
            while rclpy.ok():
                key = self.get_key()
                
                # ========== 渐进式控制 ==========
                if key == 'w':
                    # 增加前进速度
                    self.current_linear = min(
                        self.current_linear + self.linear_step,
                        self.max_linear_vel
                    )
                    self.publish_cmd()
                
                elif key == 's':
                    # 减少速度（可以变为后退）
                    self.current_linear = max(
                        self.current_linear - self.linear_step,
                        -self.max_linear_vel
                    )
                    # 如果是后退，清零角速度（避免舵机转动）
                    if self.current_linear < 0:
                        self.current_angular = 0.0
                    self.publish_cmd()
                
                elif key == 'x':
                    # 直接后退（强制清零角速度）
                    self.current_linear = -self.max_linear_vel * 0.5
                    self.current_angular = 0.0  # 关键：清零角速度
                    self.publish_cmd()
                
                elif key == 'a':
                    # 左转（增加正角速度）
                    self.current_angular = min(
                        self.current_angular + self.angular_step,
                        self.max_angular_vel
                    )
                    self.publish_cmd()
                
                elif key == 'd':
                    # 右转（增加负角速度）
                    self.current_angular = max(
                        self.current_angular - self.angular_step,
                        -self.max_angular_vel
                    )
                    self.publish_cmd()
                
                # ========== 直接控制（推荐）==========
                elif key == 'i':
                    # 前进
                    self.current_linear = self.max_linear_vel * 0.6
                    self.current_angular = 0.0
                    self.publish_cmd()
                
                elif key == ',':
                    # 后退（强制清零角速度）
                    self.current_linear = -self.max_linear_vel * 0.5
                    self.current_angular = 0.0
                    self.publish_cmd()
                
                elif key == 'j':
                    # 原地左转
                    self.current_linear = 0.0
                    self.current_angular = self.max_angular_vel * 0.6
                    self.publish_cmd()
                
                elif key == 'l':
                    # 原地右转
                    self.current_linear = 0.0
                    self.current_angular = -self.max_angular_vel * 0.6
                    self.publish_cmd()
                
                elif key == 'u':
                    # 前进+左转
                    self.current_linear = self.max_linear_vel * 0.5
                    self.current_angular = self.max_angular_vel * 0.5
                    self.publish_cmd()
                
                elif key == 'o':
                    # 前进+右转
                    self.current_linear = self.max_linear_vel * 0.5
                    self.current_angular = -self.max_angular_vel * 0.5
                    self.publish_cmd()
                
                elif key == 'm':
                    # 后退+左转
                    self.current_linear = -self.max_linear_vel * 0.4
                    self.current_angular = self.max_angular_vel * 0.4
                    self.publish_cmd()
                
                elif key == '.':
                    # 后退+右转
                    self.current_linear = -self.max_linear_vel * 0.4
                    self.current_angular = -self.max_angular_vel * 0.4
                    self.publish_cmd()
                
                elif key == 'k' or key == ' ':
                    # 停止
                    self.current_linear = 0.0
                    self.current_angular = 0.0
                    self.publish_cmd()
                    if key == ' ':
                        print("\n[紧急停止]")
                
                elif key == 'q':
                    # 退出
                    print("\n退出控制...")
                    break
                
                elif key == '\x03':  # Ctrl+C
                    break
        
        except Exception as e:
            self.get_logger().error(f'错误: {e}')
        
        finally:
            # 停止小车
            self.current_linear = 0.0
            self.current_angular = 0.0
            self.publish_cmd()
            print("\n小车已停止")
            
            # 恢复终端设置
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
