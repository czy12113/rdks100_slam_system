#!/usr/bin/env python3
"""
陶晶驰串口屏通信桥接节点 (TJC8048X571_011C)

重要配置说明：
- 波特率：115200（必须与STM32保持一致，需在TJC HMI软件中设置为115200）
- 串口：/dev/ttyUSB1（TJC串口屏）
- STM32串口：/dev/ttyUSB0（波特率115200）

功能：
1. 订阅机器人状态（速度、位置、电池等），更新到串口屏显示
2. 接收串口屏的控制指令（导航目标、模式切换等），发布ROS话题
3. 提供本地控制界面

按钮ID映射（根据实际HMI配置）：
- 前进: 12
- 后退: 13
- 急停: 14
- 左转: 15
- 停止: 16
- 右转: 17
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, PoseStamped
from nav_msgs.msg import Odometry
from sensor_msgs.msg import BatteryState
from std_msgs.msg import String, Bool
import serial
import threading
import time
import math


class TJCHMIBridge(Node):
    def __init__(self):
        super().__init__('tjc_hmi_bridge')
        
        # 声明参数
        self.declare_parameter('port', '/dev/ttyUSB1')  # TJC串口屏端口（STM32是ttyUSB0）
        self.declare_parameter('baudrate', 115200)      # 波特率115200
        self.declare_parameter('update_rate', 10.0)     # 屏幕更新频率 Hz
        
        # 速度控制参数（参考ackermann_teleop_key）
        self.declare_parameter('max_linear_vel', 0.8)   # 最大线速度 m/s
        self.declare_parameter('max_angular_vel', 1.2)  # 最大角速度 rad/s
        self.declare_parameter('linear_step', 0.1)      # 线速度递增步长
        self.declare_parameter('angular_step', 0.15)    # 角速度递增步长
        self.declare_parameter('linear_deadzone', 0.02) # 线速度死区
        self.declare_parameter('angular_deadzone', 0.05)# 角速度死区
        # v11.1 防锁死：HMI 递增按键 N 秒内无新按下 → 自动归零并发零速
        # 0 或负数 = 关闭（保持旧的"按一次走到底直到停止/急停"行为）
        self.declare_parameter('auto_zero_timeout_sec', 3.0)
        
        port = self.get_parameter('port').value
        baudrate = self.get_parameter('baudrate').value
        update_rate = self.get_parameter('update_rate').value
        
        self.max_linear_vel = self.get_parameter('max_linear_vel').value
        self.max_angular_vel = self.get_parameter('max_angular_vel').value
        self.linear_step = self.get_parameter('linear_step').value
        self.angular_step = self.get_parameter('angular_step').value
        self.linear_deadzone = self.get_parameter('linear_deadzone').value
        self.angular_deadzone = self.get_parameter('angular_deadzone').value
        self.auto_zero_timeout_sec = float(
            self.get_parameter('auto_zero_timeout_sec').value)
        
        # 当前速度状态（递增控制）
        self.current_linear = 0.0
        self.current_angular = 0.0
        # v11.1 防锁死：最近一次按键时间戳（time.monotonic）
        # publish_current_velocity 中按需刷新；auto_zero_check 周期性比对
        self.last_button_press_ts = 0.0
        
        # 初始化串口
        try:
            self.serial = serial.Serial(port, baudrate, timeout=0.1)
            time.sleep(0.1)  # 等待串口稳定
            self.get_logger().info(f'TJC串口屏已连接: {port} @ {baudrate}')
            
            # 初始化屏幕
            self.init_screen()
        except Exception as e:
            self.get_logger().error(f'无法打开串口屏 {port}: {e}')
            raise
        
        # 机器人状态数据
        self.robot_state = {
            'linear_vel': 0.0,      # m/s
            'angular_vel': 0.0,     # rad/s
            'pos_x': 0.0,           # m
            'pos_y': 0.0,           # m
            'yaw': 0.0,             # rad
            'battery_voltage': 0.0, # V
            'battery_percent': 0,   # %
            'mode': 'IDLE',         # IDLE, MANUAL, AUTO, SLAM
            'nav_status': 'READY',  # READY, NAVIGATING, ARRIVED, FAILED
        }
        
        # 订阅机器人状态
        self.odom_sub = self.create_subscription(
            Odometry, 'odom', self.odom_callback, 10)
        
        self.battery_sub = self.create_subscription(
            BatteryState, 'battery_state', self.battery_callback, 10)
        
        self.mode_sub = self.create_subscription(
            String, 'robot_mode', self.mode_callback, 10)
        
        self.nav_status_sub = self.create_subscription(
            String, 'nav_status', self.nav_status_callback, 10)
        
        # 发布控制命令
        self.cmd_vel_pub = self.create_publisher(Twist, 'cmd_vel', 10)
        self.goal_pub = self.create_publisher(PoseStamped, 'goal_pose', 10)
        self.mode_pub = self.create_publisher(String, 'robot_mode_cmd', 10)
        self.emergency_stop_pub = self.create_publisher(Bool, 'emergency_stop', 10)
        
        # 接收缓冲区
        self.rx_buffer = bytearray()
        
        # 启动接收线程
        self.running = True
        self.rx_thread = threading.Thread(target=self.receive_thread, daemon=True)
        self.rx_thread.start()
        
        # 创建定时器更新屏幕
        self.update_timer = self.create_timer(
            1.0 / update_rate, self.update_screen_callback)
        
        # v11.1 防锁死：自动归零检查定时器（0.5Hz 足以）
        # 仅当 auto_zero_timeout_sec > 0 时启用
        if self.auto_zero_timeout_sec > 0:
            self.auto_zero_timer = self.create_timer(
                0.5, self.auto_zero_check)
            self.get_logger().info(
                f'已启用 HMI 按键自动归零保护：{self.auto_zero_timeout_sec}s 无新按键 → 自动停车')
        else:
            self.auto_zero_timer = None
        
        self.get_logger().info('TJC串口屏桥接节点已启动')
    
    def auto_zero_check(self):
        """
        v11.1 防锁死兜底：
        HMI 递增按键模式下，按一次"前进"current_linear 就一直保持非零，
        sendLoop 会持续发非零 Twist，遇到通信抖动/按钮失联时小车会走到撞墙。
        本回调每 0.5s 检查一次，若当前速度非零且距上次按键超过
        auto_zero_timeout_sec，强制清零并发布零速。
        """
        if self.current_linear == 0.0 and self.current_angular == 0.0:
            return
        if self.last_button_press_ts <= 0.0:
            return
        elapsed = time.monotonic() - self.last_button_press_ts
        if elapsed < self.auto_zero_timeout_sec:
            return
        self.get_logger().warn(
            f'[自动归零] {elapsed:.1f}s 无新按键，强制停车 '
            f'(原速度 linear={self.current_linear:.2f}, angular={self.current_angular:.2f})')
        self.current_linear = 0.0
        self.current_angular = 0.0
        msg = Twist()
        msg.linear.x = 0.0
        msg.angular.z = 0.0
        self.cmd_vel_pub.publish(msg)
    
    def init_screen(self):
        """初始化屏幕，跳转到主页面"""
        try:
            # 跳转到主页面 (page 0)
            self.send_command('page 0')
            time.sleep(0.1)
            
            # 设置初始文本
            self.send_text('t_status', '系统初始化...')
            self.send_text('t_mode', 'IDLE')
            self.send_text('t_speed', '0.00')
            self.send_text('t_battery', '0%')
            
            self.get_logger().info('串口屏初始化完成')
        except Exception as e:
            self.get_logger().error(f'串口屏初始化失败: {e}')
    
    def send_command(self, cmd):
        """发送指令到串口屏"""
        try:
            # TJC串口屏指令格式: 指令内容 + 0xFF 0xFF 0xFF
            data = cmd.encode('utf-8') + b'\xff\xff\xff'
            self.serial.write(data)
            self.get_logger().debug(f'发送指令: {cmd}')
        except Exception as e:
            self.get_logger().error(f'发送指令失败: {e}')
    
    def send_text(self, component, text):
        """更新文本组件（支持中文GB2312编码）"""
        try:
            # 尝试将文本编码为GB2312（TJC串口屏支持的中文编码）
            # 如果文本包含中文，使用GB2312编码
            if any('\u4e00' <= char <= '\u9fff' for char in text):
                # 包含中文字符，使用GB2312编码
                text_bytes = text.encode('gb2312', errors='ignore')
                # 构造指令：component.txt="text"
                cmd_prefix = f'{component}.txt="'.encode('utf-8')
                cmd_suffix = b'"\xff\xff\xff'
                data = cmd_prefix + text_bytes + cmd_suffix
                self.serial.write(data)
                self.get_logger().debug(f'发送中文文本: {component}="{text}"')
            else:
                # 纯ASCII文本，使用普通方式
                cmd = f'{component}.txt="{text}"'
                self.send_command(cmd)
        except Exception as e:
            self.get_logger().error(f'发送文本失败: {e}')
            # 降级方案：发送英文替代
            fallback_text = {
                '待机': 'IDLE',
                '手动': 'MANUAL',
                '自动': 'AUTO',
                '建图': 'SLAM',
                '就绪': 'READY',
                '导航中': 'NAV',
                '已到达': 'ARRIVED',
                '失败': 'FAILED',
                '未知': 'UNKNOWN'
            }.get(text, text)
            cmd = f'{component}.txt="{fallback_text}"'
            self.send_command(cmd)
    
    def send_value(self, component, value):
        """更新数值组件"""
        cmd = f'{component}.val={value}'
        self.send_command(cmd)
    
    def send_progress(self, component, value):
        """更新进度条 (0-100)"""
        self.send_value(component, int(value))
    
    def odom_callback(self, msg):
        """里程计回调"""
        self.robot_state['linear_vel'] = msg.twist.twist.linear.x
        self.robot_state['angular_vel'] = msg.twist.twist.angular.z
        self.robot_state['pos_x'] = msg.pose.pose.position.x
        self.robot_state['pos_y'] = msg.pose.pose.position.y
        
        # 从四元数计算yaw角
        q = msg.pose.pose.orientation
        siny_cosp = 2 * (q.w * q.z + q.x * q.y)
        cosy_cosp = 1 - 2 * (q.y * q.y + q.z * q.z)
        self.robot_state['yaw'] = math.atan2(siny_cosp, cosy_cosp)
    
    def battery_callback(self, msg):
        """电池状态回调"""
        self.robot_state['battery_voltage'] = msg.voltage
        self.robot_state['battery_percent'] = int(msg.percentage * 100)
    
    def mode_callback(self, msg):
        """模式回调"""
        self.robot_state['mode'] = msg.data
    
    def nav_status_callback(self, msg):
        """导航状态回调"""
        self.robot_state['nav_status'] = msg.data
    
    def update_screen_callback(self):
        """定时更新屏幕显示"""
        try:
            # 更新当前控制速度显示（递增控制的目标速度）
            self.send_text('t_cmd_linear', f'{self.current_linear:.2f}')
            self.send_text('t_cmd_angular', f'{self.current_angular:.2f}')
            
            # 更新实际速度显示 (m/s) - 来自里程计反馈
            speed = abs(self.robot_state['linear_vel'])
            self.send_text('t_speed', f'{speed:.2f}')
            
            # 更新位置显示
            x = self.robot_state['pos_x']
            y = self.robot_state['pos_y']
            self.send_text('t_position', f'X:{x:.2f} Y:{y:.2f}')
            
            # 更新角度显示 (转换为度)
            yaw_deg = math.degrees(self.robot_state['yaw'])
            self.send_text('t_angle', f'{yaw_deg:.1f}°')
            
            # 更新电池显示
            battery_pct = self.robot_state['battery_percent']
            self.send_text('t_battery', f'{battery_pct}%')
            self.send_progress('j_battery', battery_pct)
            
            # 更新模式显示
            mode_text = {
                'IDLE': '待机',
                'MANUAL': '手动',
                'AUTO': '自动',
                'SLAM': '建图'
            }.get(self.robot_state['mode'], '未知')
            self.send_text('t_mode', mode_text)
            
            # 更新导航状态
            nav_text = {
                'READY': '就绪',
                'NAVIGATING': '导航中',
                'ARRIVED': '已到达',
                'FAILED': '失败'
            }.get(self.robot_state['nav_status'], '未知')
            self.send_text('t_nav_status', nav_text)
            
        except Exception as e:
            self.get_logger().error(f'更新屏幕失败: {e}')
    
    def receive_thread(self):
        """接收线程，处理串口屏发来的数据"""
        consecutive_errors = 0
        max_consecutive_errors = 10
        
        while self.running and rclpy.ok():
            try:
                # 检查串口是否打开
                if not self.serial.is_open:
                    self.get_logger().warn('串口已关闭，尝试重新打开...')
                    time.sleep(1)
                    try:
                        self.serial.open()
                        self.get_logger().info('串口重新打开成功')
                        consecutive_errors = 0
                    except Exception as e:
                        self.get_logger().error(f'重新打开串口失败: {e}')
                        time.sleep(5)
                        continue
                
                # 读取数据
                if self.serial.in_waiting > 0:
                    data = self.serial.read(self.serial.in_waiting)
                    if data:  # 确保读取到数据
                        self.rx_buffer.extend(data)
                        self.process_rx_buffer()
                        consecutive_errors = 0  # 重置错误计数
                    else:
                        # 读取到0字节，可能是设备断开
                        consecutive_errors += 1
                        if consecutive_errors >= max_consecutive_errors:
                            self.get_logger().warn(
                                f'连续{consecutive_errors}次读取失败，TJC串口屏可能未连接或未上电')
                            consecutive_errors = 0  # 重置计数，避免日志刷屏
                            time.sleep(2)  # 等待更长时间
                        
            except serial.SerialException as e:
                self.get_logger().error(f'串口异常: {e}')
                consecutive_errors += 1
                time.sleep(1)
            except Exception as e:
                self.get_logger().error(f'接收数据错误: {e}')
                consecutive_errors += 1
                
            time.sleep(0.01)
    
    def process_rx_buffer(self):
        """处理接收缓冲区，解析串口屏返回的数据"""
        while len(self.rx_buffer) >= 7:  # TJC返回数据最小长度
            # 查找帧尾 0xFF 0xFF 0xFF
            end_idx = -1
            for i in range(len(self.rx_buffer) - 2):
                if (self.rx_buffer[i] == 0xFF and 
                    self.rx_buffer[i+1] == 0xFF and 
                    self.rx_buffer[i+2] == 0xFF):
                    end_idx = i
                    break
            
            if end_idx == -1:
                # 没有找到完整帧，等待更多数据
                if len(self.rx_buffer) > 100:  # 防止缓冲区溢出
                    self.rx_buffer.clear()
                break
            
            # 提取一帧数据
            frame = self.rx_buffer[:end_idx]
            
            # 处理帧数据
            if len(frame) > 0:
                self.parse_hmi_command(frame)
            
            # 移除已处理的帧（包括帧尾）
            self.rx_buffer = self.rx_buffer[end_idx+3:]
    
    def parse_hmi_command(self, data):
        """解析串口屏发来的指令"""
        try:
            # TJC触摸事件格式: 0x65 page_id component_id event_type
            if len(data) >= 4 and data[0] == 0x65:
                page_id = data[1]
                component_id = data[2]
                event_type = data[3]  # 0x01=按下, 0x00=释放
                
                if event_type == 0x01:  # 按下事件
                    self.handle_button_press(page_id, component_id)
            
            # 数值返回格式: 0x71 value(4字节)
            elif len(data) >= 5 and data[0] == 0x71:
                value = int.from_bytes(data[1:5], byteorder='big', signed=True)
                self.handle_value_return(value)
            
            # 字符串返回格式: 0x70 string_data
            elif len(data) >= 2 and data[0] == 0x70:
                text = data[1:].decode('utf-8', errors='ignore')
                self.handle_string_return(text)
                
        except Exception as e:
            self.get_logger().error(f'解析HMI指令失败: {e}')
    
    def apply_deadzone(self):
        """应用死区，过滤微小速度"""
        if abs(self.current_linear) < self.linear_deadzone:
            self.current_linear = 0.0
        if abs(self.current_angular) < self.angular_deadzone:
            self.current_angular = 0.0
    
    def publish_current_velocity(self):
        """发布当前速度（应用死区后）"""
        self.apply_deadzone()
        
        msg = Twist()
        msg.linear.x = self.current_linear
        msg.angular.z = self.current_angular
        self.cmd_vel_pub.publish(msg)
        
        # 日志输出
        direction = ""
        if self.current_linear > 0:
            direction = "前进"
        elif self.current_linear < 0:
            direction = "后退"
        else:
            direction = "停止"
        
        if self.current_angular > 0:
            direction += "+左转"
        elif self.current_angular < 0:
            direction += "+右转"
        
        self.get_logger().info(
            f'[{direction}] 线速度: {self.current_linear:.2f} m/s | 角速度: {self.current_angular:.2f} rad/s')
    
    def send_hmi_button_feedback(self, button_id, state):
        """发送按钮反馈到HMI（可选功能）
        示例: printh 65 00 0C 01 FF FF FF (前进按钮按下)
        """
        try:
            # printh 65 00 button_id state FF FF FF
            cmd = f'printh 65 00 {button_id:02X} {state:02X}'
            self.send_command(cmd)
        except Exception as e:
            self.get_logger().debug(f'发送HMI按钮反馈失败: {e}')
    
    def handle_button_press(self, page_id, component_id):
        """处理按钮按下事件（递增控制逻辑）"""
        self.get_logger().info(f'按钮按下: page={page_id}, component={component_id}')
        
        # 主页面 (page 0)
        if page_id == 0:
            # v11.1：运动相关按键统一刷新"最近按键时间戳"，
            # 供 auto_zero_check 判断是否需要自动归零
            if component_id in (12, 13, 15, 17):
                self.last_button_press_ts = time.monotonic()

            if component_id == 12:  # 前进按钮 - 递增前进速度
                self.current_linear = min(
                    self.current_linear + self.linear_step,
                    self.max_linear_vel
                )
                # 前进时保持当前角速度（允许边前进边转向）
                self.publish_current_velocity()
                
            elif component_id == 13:  # 后退按钮 - 递增后退速度
                self.current_linear = max(
                    self.current_linear - self.linear_step,
                    -self.max_linear_vel
                )
                # 后退时清零角速度（安全考虑）
                if self.current_linear < 0:
                    self.current_angular = 0.0
                self.publish_current_velocity()
                
            elif component_id == 15:  # 左转按钮 - 递增左转角速度
                self.current_angular = min(
                    self.current_angular + self.angular_step,
                    self.max_angular_vel
                )
                self.publish_current_velocity()
                
            elif component_id == 17:  # 右转按钮 - 递增右转角速度
                self.current_angular = max(
                    self.current_angular - self.angular_step,
                    -self.max_angular_vel
                )
                self.publish_current_velocity()
                
            elif component_id == 16:  # 停止按钮 - 清零所有速度
                self.current_linear = 0.0
                self.current_angular = 0.0
                self.last_button_press_ts = 0.0  # 主动停止 → 清零超时戳
                self.publish_current_velocity()
                self.get_logger().info('[停止] 所有速度已清零')
                
            elif component_id == 14:  # 急停按钮 - 立即停止
                self.current_linear = 0.0
                self.current_angular = 0.0
                self.last_button_press_ts = 0.0  # 急停 → 清零超时戳
                self.emergency_stop()
                
            elif component_id == 7:  # 切换到导航页面
                self.send_command('page 1')
            elif component_id == 8:  # 切换到设置页面
                self.send_command('page 2')
        
        # 导航页面 (page 1)
        elif page_id == 1:
            if component_id == 1:  # 目标点1
                self.send_goal(1.0, 0.0, 0.0)
            elif component_id == 2:  # 目标点2
                self.send_goal(2.0, 1.0, 0.0)
            elif component_id == 3:  # 目标点3
                self.send_goal(0.0, 2.0, 1.57)
            elif component_id == 4:  # 取消导航
                self.cancel_navigation()
            elif component_id == 5:  # 返回主页
                self.send_command('page 0')
        
        # 设置页面 (page 2)
        elif page_id == 2:
            if component_id == 1:  # 手动模式
                self.set_mode('MANUAL')
            elif component_id == 2:  # 自动模式
                self.set_mode('AUTO')
            elif component_id == 3:  # 建图模式
                self.set_mode('SLAM')
            elif component_id == 4:  # 返回主页
                self.send_command('page 0')
    
    def handle_value_return(self, value):
        """处理数值返回"""
        self.get_logger().debug(f'收到数值: {value}')
        # 可以用于滑块、进度条等组件的值
    
    def handle_string_return(self, text):
        """处理字符串返回"""
        self.get_logger().debug(f'收到字符串: {text}')
        # 可以用于文本输入框等组件
    
    def send_velocity(self, linear, angular):
        """发送速度命令（直接设置，不使用递增逻辑）"""
        self.current_linear = linear
        self.current_angular = angular
        self.publish_current_velocity()
    
    def send_goal(self, x, y, yaw):
        """发送导航目标点"""
        msg = PoseStamped()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = 'map'
        msg.pose.position.x = x
        msg.pose.position.y = y
        msg.pose.position.z = 0.0
        
        # 转换yaw为四元数
        cy = math.cos(yaw / 2.0)
        sy = math.sin(yaw / 2.0)
        msg.pose.orientation.w = cy
        msg.pose.orientation.z = sy
        
        self.goal_pub.publish(msg)
        self.get_logger().info(f'发送目标点: x={x}, y={y}, yaw={yaw}')
    
    def cancel_navigation(self):
        """取消导航"""
        # 发送停止命令
        self.send_velocity(0.0, 0.0)
        self.get_logger().info('取消导航')
    
    def emergency_stop(self):
        """急停"""
        msg = Bool()
        msg.data = True
        self.emergency_stop_pub.publish(msg)
        
        # 立即停止
        msg_twist = Twist()
        msg_twist.linear.x = 0.0
        msg_twist.angular.z = 0.0
        self.cmd_vel_pub.publish(msg_twist)
        
        self.get_logger().warn('⚠️ 急停触发！所有运动已停止')
    
    def set_mode(self, mode):
        """设置机器人模式"""
        msg = String()
        msg.data = mode
        self.mode_pub.publish(msg)
        self.get_logger().info(f'切换模式: {mode}')
    
    def destroy_node(self):
        """清理资源"""
        self.running = False
        if hasattr(self, 'rx_thread'):
            self.rx_thread.join(timeout=1.0)
        if hasattr(self, 'serial') and self.serial.is_open:
            self.serial.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = TJCHMIBridge()
    
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
