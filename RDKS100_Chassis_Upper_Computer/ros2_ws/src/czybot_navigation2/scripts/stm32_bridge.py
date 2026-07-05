#!/usr/bin/env python3
"""
STM32 串口通信桥接节点  v5 —— 与 STM32 ChassisParams.h 全面对齐 + 独立急停通道

本版本重点（相对 v4）：
  1. 速度硬限幅与 STM32 一致：MAX_LINEAR_SPEED=0.60 m/s, MAX_ANGULAR_SPEED=1.20 rad/s
     （v4 误用 1.0/1.57，会让下位机进入超限保护）
  2. 死区与 STM32 ChassisParams.h 大致对齐：上位机略小，让下位机做最终判定，
     防止 RDK 把"非零但很小"的指令一直发给电机引起抖动。
  3. 新增独立急停订阅 topic /cmd_vel_estop（std_msgs/Empty）：
     上位机/前端/导航任意一侧只要发布到该 topic，本节点立刻
     连续发送 N 帧零速并清零 latest_*，与 cmd_vel 通道彼此正交。
  4. 所有阈值改为 ROS2 参数，可在 launch 时覆盖：
       max_linear, max_angular, linear_deadzone, angular_deadzone,
       cmd_timeout, watchdog_timeout, estop_repeats, estop_lock_seconds.
  5. 急停锁：触发后短时间内（estop_lock_seconds）忽略所有非零 cmd_vel，
     防止某个上层节点（前端/Nav2 智能恢复）在急停后继续覆盖速度。
  6. 节点关闭时主动多次写零速，避免守护进程被杀后下位机仍在跑。

  v3/v4 已确立的架构在 v5 中保留：
    - cmd_vel 回调和 ROS2 spin 完全无串口 I/O，仅写共享内存
    - 串口写线程（25 Hz）独立运行，不阻塞 spin
    - 看门狗线程独立运行，不依赖 ROS 定时器
    - 接收线程独立解析 STM32 上行 20 字节 odom 帧

参数说明：
  port              : 串口设备（自动 fallback 到 /dev/ttyUSB0~2）
  baudrate          : 波特率（与 STM32 一致，默认 115200）
  publish_tf        : 是否广播 odom→base_link TF（默认 True）
  odom_source       : 里程计来源策略，决定 /odom 与 TF 由谁发布
                        - 'auto'      ：默认。STM32 上行 odom 帧时优先用
                                        STM32；超过 odom_stm32_timeout
                                        没有 STM32 帧就切到开环积分兜底。
                                        ★ 这是 STM32 关闭编码器（v6）后
                                        Nav2 不漂的关键：STM32 一旦不再
                                        发 odom，上位机必须自己接管，
                                        否则 AMCL/MPPI 会因为 TF 中断
                                        把车定位飘走。
                        - 'stm32'     ：只信 STM32 上行，不做开环兜底
                        - 'open_loop' ：无视 STM32 上行，仅按 cmd_vel
                                        积分得到 /odom（编码器始终关闭
                                        且想完全旁路 STM32 时使用）
                        - 'disabled'  ：完全不发 /odom 也不发 TF
  odom_stm32_timeout: 'auto' 模式下，多久（秒）没有收到 STM32 odom 帧
                        判定为"STM32 不上行"，开始用开环 odom 兜底。
                        默认 0.5s。
  odom_open_loop_hz : 开环 odom 发布频率 (Hz)，默认 20.0
  max_linear        : 线速度硬限幅 (m/s)，默认 0.60 与 STM32 对齐
  max_angular       : 角速度硬限幅 (rad/s)，默认 1.20 与 STM32 对齐
  linear_deadzone   : 线速度死区 (m/s)，低于此值发零速；默认 0.005
  angular_deadzone  : 角速度死区 (rad/s)，低于此值发零速；默认 0.002（v11.0）
                       v11 前为 0.010，但配合 vx_max=0.10 / wz_max=0.33 后，
                       1° 朝向修正只需要 ω≈0.017 rad/s，0.010 死区会把
                       MPPI 的小角度修正命令吃掉一大半（这是"只直走、
                       不拐小角度"的 ROS 侧第一道死区）。
                       0.002 rad/s ≈ 0.11°/s，远低于舵机分辨率门槛，
                       不会引起舵机抖动，但能把所有有意义的微转向命令
                       透传到 STM32。
                       ⚠ STM32 端 ChassisParams.h: ANGULAR_DEADBAND 默认
                       0.03 rad/s 是第二道死区，需要在 Keil 同步降到
                       0.005 才能彻底解锁小角度修正。
  min_motion_linear : 线速度最小启动门槛 (m/s)，默认 0.18
                       Nav2 起步阶段 cmd_vel 常在 0.05~0.18 区间，
                       但电机 + STM32 最小占空比约 0.18 m/s，
                       小于该值时电机不转。设了之后：
                       deadzone < |v| < min_motion_linear → 抬到 ±min_motion_linear
                       关掉则设为 0.0。
                       注意：只对 linear 做补偿，不对 angular 做（避免舵机抖）。
  min_motion_angular: 角速度最小启动门槛 (rad/s)，默认 0.0 = 关闭
                       ⚠ 强烈不建议开启：阿克曼前轮舵机的"小角度低速命令"
                       是正常 MPPI 输出，硬抬到大值会让舵机左右剧烈抖动。
                       仅在差速底盘上才考虑打开。
  cmd_timeout       : 无 cmd_vel 多久自动发停车帧 (s)，默认 0.3
                       与 STM32 CMD_TIMEOUT_MS=300 完全对齐
  watchdog_timeout  : 看门狗兜底超时 (s)，默认 0.5
  estop_repeats     : 急停/归零时连发零速次数，默认 15
  estop_lock_seconds: 急停锁定时长 (s)，期间忽略非零 cmd_vel，默认 0.4
  write_hz          : 串口写线程频率 (Hz)，默认 25
"""
import math
import os
import struct
import threading
import time

import rclpy
import serial
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from rclpy.time import Time as RclpyTime
from std_msgs.msg import Bool, Empty, Int32MultiArray
from tf2_ros import TransformBroadcaster


# 协议常量（与 STM32/USER/ROS2Protocol.h 一致）
FRAME_HEADER_0 = 0xAA
FRAME_HEADER_1 = 0x55
FRAME_TAIL = 0x0D
ODOM_HEADER_0 = 0xBB
ODOM_HEADER_1 = 0x66
CMD_VELOCITY = 0x01
DATA_TYPE_ODOM = 0x01
ODOM_FRAME_LEN = 20  # BB 66 type x(4) y(4) yaw(2) v(2) w(2) reserved cs 0D


class STM32Bridge(Node):
    def __init__(self):
        super().__init__('stm32_bridge')

        # ── ROS2 参数声明（统一管理，可在 launch 时覆盖）─────────────────────
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('publish_tf', True)

        # 与 STM32 ChassisParams.h 对齐
        self.declare_parameter('max_linear', 0.60)
        self.declare_parameter('max_angular', 1.20)
        self.declare_parameter('linear_deadzone', 0.005)
        # v11.0：angular_deadzone 默认 0.010 → 0.002（详见文件头注释）
        self.declare_parameter('angular_deadzone', 0.002)
        # ★ 真车启动补偿：解决 Nav2 输出 0.10~0.18 m/s 时电机不转的问题
        # 仅 linear 补偿；angular 补偿在阿克曼上会让前轮舵机剧烈抖动，
        # 默认关闭（=0.0），如需打开请自行评估。
        self.declare_parameter('min_motion_linear', 0.18)
        self.declare_parameter('min_motion_angular', 0.0)

        self.declare_parameter('cmd_timeout', 0.3)
        self.declare_parameter('watchdog_timeout', 0.5)
        self.declare_parameter('estop_repeats', 15)
        self.declare_parameter('estop_lock_seconds', 0.4)
        self.declare_parameter('write_hz', 25.0)

        # ── v6.5 修复 AMCL 漂移：odom 时间戳要尽量贴近"测量时刻" ─────────
        # 旧实现把 self.get_clock().now() 当 odom 时间戳，
        # 但这个"现在"已经包含：串口读 + buffer 解析 + rclpy 调用 + TF 广播
        # 路径上 5~30 ms 不可预测的处理延迟。在 0.15 m/s 巡航下，30ms 误差
        # 等价于 4.5mm 位置错位；转弯 0.5 rad/s 时是 0.86° 偏航误差，
        # 反映到 5m 远处墙体就是 7.5cm 偏差，AMCL 直接判定"环境不一致"
        # 把 map→odom TF 拽走 → 看上去就是图相对车体在飘。
        #
        # 修复：read() 返回那一刻就打时间戳 t_arrival，再减去固定的串口
        # 传输延迟（odom_stamp_offset_ms 负值），作为 Odometry / TF 的 stamp。
        # 默认 -2.0 ms = 20 字节 @115200bps（≈1.74ms）+ 一点点 OS 调度抖动。
        # 如果你的 STM32 是以固定周期 N ms 累积上行，可在 launch 里把它
        # 设为 -N/2，使时间戳落到测量窗口中点。
        self.declare_parameter('odom_stamp_offset_ms', -2.0)

        # ── v6.7 修复 Nav2 漂移：开环 odom 兜底 ────────────────────────────
        # 背景：STM32 v6 之后 ODOMETRY_READ_ENCODER=0 时不再发送 odom 帧
        # （旧版会发全零 odom，导致 AMCL 看到"车一直停在原点"，配合 MPPI
        # 输出非零 cmd_vel，整条 TF 链就被拽飞）。
        # 但 Nav2 / AMCL / MPPI 必须有连续的 /odom 和 odom→base_link TF
        # 才能正常工作，所以这里加一个旁路：当 STM32 沉默时，本节点用
        # 已经发到串口的 last_tx_v / last_tx_w 做一次性差分积分，得到
        # "上位机自洽"的开环 odom，AMCL 用它来做相对运动估计，map→odom
        # 校正剩余的累计误差。这正好把"上位机已经知道车在跑多快"这件事
        # 变成一份合法 /odom，比 STM32 发零强得多。
        self.declare_parameter('odom_source', 'auto')          # auto/stm32/open_loop/disabled
        self.declare_parameter('odom_stm32_timeout', 0.5)
        self.declare_parameter('odom_open_loop_hz', 20.0)

        port = self.get_parameter('port').value
        baudrate = self.get_parameter('baudrate').value
        self.publish_tf = self.get_parameter('publish_tf').value

        self.max_linear = float(self.get_parameter('max_linear').value)
        self.max_angular = float(self.get_parameter('max_angular').value)
        self.linear_deadzone = float(self.get_parameter('linear_deadzone').value)
        self.angular_deadzone = float(self.get_parameter('angular_deadzone').value)
        self.min_motion_linear = float(self.get_parameter('min_motion_linear').value)
        self.min_motion_angular = float(self.get_parameter('min_motion_angular').value)

        self.CMD_TIMEOUT = float(self.get_parameter('cmd_timeout').value)
        self.WATCHDOG_TIMEOUT = float(self.get_parameter('watchdog_timeout').value)
        self.ESTOP_REPEATS = int(self.get_parameter('estop_repeats').value)
        self.ESTOP_LOCK_SECONDS = float(self.get_parameter('estop_lock_seconds').value)
        self.WRITE_HZ = float(self.get_parameter('write_hz').value)
        self.odom_stamp_offset_ns = int(
            float(self.get_parameter('odom_stamp_offset_ms').value) * 1_000_000
        )

        # 解析 odom_source 并做容错（未知值回落到 'auto'）
        raw_odom_source = str(self.get_parameter('odom_source').value).lower()
        if raw_odom_source not in ('auto', 'stm32', 'open_loop', 'disabled'):
            self.get_logger().warn(
                f'未知 odom_source="{raw_odom_source}"，回落到 auto')
            raw_odom_source = 'auto'
        self.odom_source = raw_odom_source
        self.odom_stm32_timeout = float(
            self.get_parameter('odom_stm32_timeout').value)
        self.odom_open_loop_hz = float(
            self.get_parameter('odom_open_loop_hz').value)

        # 整数化的硬限幅（mm/s, mrad/s），用于 cmd_vel 入口快速比较
        self._max_linear_mm = int(self.max_linear * 1000)
        self._max_angular_mrad = int(self.max_angular * 1000)
        self._linear_deadzone_mm = max(1, int(self.linear_deadzone * 1000))
        self._angular_deadzone_mrad = max(1, int(self.angular_deadzone * 1000))
        # 启动补偿门槛（mm/s, mrad/s）
        self._min_motion_linear_mm = int(self.min_motion_linear * 1000)
        self._min_motion_angular_mrad = int(self.min_motion_angular * 1000)

        # ── 自动探测串口 ────────────────────────────────────────────────────
        candidate_ports = [port] + [
            p for p in ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB2']
            if p != port
        ]
        actual_port = None
        for p in candidate_ports:
            if os.path.exists(p):
                actual_port = p
                break

        if actual_port is None:
            self.get_logger().error(
                f'未找到任何串口设备，已尝试: {candidate_ports}')
            raise RuntimeError(f'No serial port found, tried: {candidate_ports}')

        if actual_port != port:
            self.get_logger().warn(
                f'指定端口 {port} 不存在，自动切换到 {actual_port}')

        # ── 打开串口 ────────────────────────────────────────────────────────
        try:
            self.serial = serial.Serial(actual_port, baudrate, timeout=0.1)
            self.get_logger().info(f'串口已打开: {actual_port} @ {baudrate}')
        except Exception as e:
            self.get_logger().error(f'无法打开串口 {actual_port}: {e}')
            raise

        # ── 共享状态（仅内存操作，所有 I/O 在写线程）───────────────────────
        self.latest_linear = 0          # mm/s
        self.latest_angular = 0         # mrad/s
        self.last_cmd_time = 0.0
        self._estop_pending = False     # 写线程检测到此标志立即发零速
        self._estop_lock_until = 0.0    # 急停锁定结束时刻
        self._lock = threading.Lock()

        # ── 开环 odom 兜底状态（v6.7） ─────────────────────────────────────
        # 当 STM32 不上行 odom（编码器关闭）时，本节点用最近一次成功写入
        # 串口的 (last_tx_v, last_tx_w) 做差分积分，对外发布一份连续的
        # /odom 与 odom→base_link TF，喂给 Nav2 / AMCL / MPPI。
        self._ol_x = 0.0
        self._ol_y = 0.0
        self._ol_yaw = 0.0
        self._ol_last_time = 0.0
        self._last_stm32_odom_time = 0.0   # 上一次成功收到 STM32 odom 帧的 time.time()

        # ── 可观测性统计（用于 1 Hz info 日志和 /stm32_bridge/tx_cmd）──────
        # 现场可用 ros2 topic echo /stm32_bridge/tx_cmd 直接看实际写串口的值，
        # 避免被 /cmd_vel → bridge → 串口 → STM32 任意一段卡死时无法定位。
        self._last_rx_time = 0.0     # 最近一次 cmd_vel 回调时间（time.time()）
        self._last_rx_v = 0          # 最近一次 cmd_vel 入参（限幅+死区+补偿后, mm/s）
        self._last_rx_w = 0
        # ★ v8.0 开环 odom 修复：记录"启动补偿前"的 MPPI 真实意图速度
        # ─────────────────────────────────────────────────────────────
        # _last_rx_v 是经过启动补偿（kickstart 0.08m/s）后的值，比 MPPI
        # 实际想发的命令大 0.02~0.07m/s。用它做开环积分会导致 /odom 持续
        # 系统性高估车走的距离（map 里 base_link 比真车多走一段），
        # AMCL 又压不回来 → 静态停车后红框（实时点云）不能回到蓝框
        # （建图静态障碍物），且行驶中障碍物在 costmap 里持续朝车方向漂移。
        # _last_intent_v / _last_intent_w 记录"限幅 + 死区过滤后但未经
        # 启动补偿"的值，即 MPPI 真实想发的速度；_publish_open_loop_odom
        # 用这个值做积分，odom 误差从 ~50% 降到电机响应延迟量级（~10%）。
        self._last_intent_v = 0      # 限幅+死区后、补偿前 (mm/s)
        self._last_intent_w = 0
        self._last_tx_time = 0.0     # 最近一次实际写串口时间
        self._last_tx_v = 0
        self._last_tx_w = 0
        self._rx_count = 0           # 累计 cmd_vel 回调次数
        self._tx_count = 0           # 累计 _raw_write 成功次数
        self._prev_rx_count = 0
        self._prev_tx_count = 0

        # ── ROS2 订阅/发布 ──────────────────────────────────────────────────
        # 主控制通道：cmd_vel
        self.cmd_sub = self.create_subscription(
            Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        # 独立急停通道：发布任意 std_msgs/Empty 或 Bool 都视为急停
        self.estop_empty_sub = self.create_subscription(
            Empty, 'cmd_vel_estop', self._estop_callback_empty, 10)
        self.estop_bool_sub = self.create_subscription(
            Bool, 'estop', self._estop_callback_bool, 10)
        # 上行：里程计
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        # 调试：实际写入串口的速度 [linear_mm/s, angular_mrad/s]
        # 现场用 `ros2 topic echo /stm32_bridge/tx_cmd` 验证：
        #   - 没有任何输出   → bridge 完全没向串口写（被死区/急停/超时清零）
        #   - 输出值非零但车不动 → 问题在串口/STM32/电机/odom 反馈
        #   - 输出值持续为 0 但 /cmd_vel 非零 → bridge 入口被清零（看 1Hz log）
        self.tx_cmd_pub = self.create_publisher(
            Int32MultiArray, 'stm32_bridge/tx_cmd', 10)

        # 注意：即使 odom_source='disabled'，也保留 TF broadcaster（外部
        # 可能仍然需要 odom→base_link，例如手动定位）。但 disabled 模式
        # 不会主动发任何 TF。
        self.tf_broadcaster = None
        if self.publish_tf and self.odom_source != 'disabled':
            self.tf_broadcaster = TransformBroadcaster(self)
            self.publish_initial_tf()
            self.initial_tf_timer = self.create_timer(
                0.05, self.publish_initial_tf_callback)
            self.received_odom_data = False
        else:
            # disabled 或 publish_tf=False：占位，让 _parse_odom_data
            # 与 _publish_open_loop_odom 的判空逻辑一致
            self.received_odom_data = True

        # 接收缓冲区 + 串口读到达时间戳（用于给 odom 打更准的 stamp）
        self.rx_buffer = bytearray()
        # 最近一次 serial.read() 返回的 ROS 时刻，原子写入即可（GIL 保证 64bit 整数原子性）
        self._last_serial_arrival_ns = 0

        # ── 启动后台线程 ────────────────────────────────────────────────────
        self.running = True

        self.rx_thread = threading.Thread(
            target=self._receive_thread, daemon=True, name='stm32_rx')
        self.rx_thread.start()

        self._write_thread = threading.Thread(
            target=self._serial_write_thread, daemon=True, name='stm32_tx')
        self._write_thread.start()

        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name='stm32_wd')
        self._watchdog_thread.start()

        # 1 Hz 可观测性日志（rx/tx 速率 + 最近值 + 急停锁状态）
        self._observability_timer = self.create_timer(
            1.0, self._observability_callback)

        # 开环 odom 定时器：'auto' / 'open_loop' 都启用
        if self.odom_source in ('auto', 'open_loop'):
            ol_period = 1.0 / max(1.0, self.odom_open_loop_hz)
            self._open_loop_timer = self.create_timer(
                ol_period, self._publish_open_loop_odom)
        else:
            self._open_loop_timer = None

        self.get_logger().info(
            f'[stm32_bridge v6] 已就绪：限速 v={self.max_linear:.2f}m/s, '
            f'w={self.max_angular:.2f}rad/s, cmd_timeout={self.CMD_TIMEOUT}s, '
            f'watchdog={self.WATCHDOG_TIMEOUT}s, '
            f'odom_source={self.odom_source}, '
            f'stm32_timeout={self.odom_stm32_timeout:.2f}s, '
            f'open_loop_hz={self.odom_open_loop_hz:.1f}')

    # ────────────────────────────────────────────────────────────────────────
    # TF 初始化
    # ────────────────────────────────────────────────────────────────────────
    def publish_initial_tf_callback(self):
        if not self.received_odom_data:
            self.publish_initial_tf()
        else:
            if hasattr(self, 'initial_tf_timer'):
                self.initial_tf_timer.cancel()
                self.get_logger().info('收到真实里程计数据，停止发布初始 TF')

    def publish_initial_tf(self):
        if self.tf_broadcaster is None:
            return
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'
        t.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t)

    # ────────────────────────────────────────────────────────────────────────
    # 开环 odom 兜底（v6.7）
    # ────────────────────────────────────────────────────────────────────────
    def _publish_open_loop_odom(self):
        """
        当 STM32 不再上行 odom 帧（编码器关闭）时，由本节点根据 MPPI 真实
        意图速度 (last_intent_v, last_intent_w) 积分得到 /odom 与
        odom→base_link TF。Nav2 / AMCL / MPPI 依赖这条 TF 链才能正确做
        相对运动估计。

        关键点：
          1. v8.0 修复（关键）：积分用 _last_intent_*（限幅+死区后但补偿前），
             不再用 _last_tx_*（启动补偿后写串口的值）。
             ─────────────────────────────────────────────────────
             历史教训：v6.7 用 _last_tx_* 的初衷是"积分和实际发给电机的
             速度严格一致"，但在阿克曼车低速场景下，bridge 把 0.05m/s 的
             MPPI 命令抬升到 0.08m/s 启动门槛才能爬出静摩擦——这是给电机
             看的，不是车真实速度。继续用它积分，odom 会持续高估行驶距离，
             map→base_link 比真车多走一段，激光投影到 map 后就落在"真实
             障碍物-多走出的距离"位置，红框相对蓝框朝车方向偏，停车后
             AMCL 都纠不回来。改用 _last_intent_* 后误差从 ~50% 降到电机
             响应延迟量级（~10%）。
          2. 用 _last_tx_* 判断"是否实际在发车"：tx=0（急停/超时停车）时
             积分按 0，即使 intent 非零也不积。这样保证急停后 odom 立刻冻结，
             而不是继续按 intent 漂移。
          3. 'auto' 模式下，只有 STM32 odom 帧超时（>odom_stm32_timeout）
             才接管 /odom 发布，避免和 STM32 odom 抢话题。
          4. 'open_loop' 模式无视 STM32，始终发布。
          5. covariance 比 STM32 odom 略宽，告诉下游"这是开环估计，
             请配合 AMCL/SLAM 的位置校正使用"。
          6. odom_source == 'disabled' 不会启用本定时器。
        """
        if not self.running:
            return
        if self.odom_source == 'auto':
            if (self._last_stm32_odom_time > 0.0
                    and (time.time() - self._last_stm32_odom_time)
                    < self.odom_stm32_timeout):
                # STM32 还在按时上行，让真实 odom 优先
                return

        now = time.time()
        with self._lock:
            # v8.0：用 MPPI 意图速度积分（未经启动补偿），用 tx 状态判断是否在发
            v_intent_mm = int(self._last_intent_v)
            w_intent_mrad = int(self._last_intent_w)
            v_tx_mm = int(self._last_tx_v)
            w_tx_mrad = int(self._last_tx_w)
        # tx=0 说明 bridge 当前实际未向电机输出（急停/超时停车/启动前）
        # → 不论 intent 是什么，积分按 0，保证 odom 冻结与车真实状态一致
        v_mm = v_intent_mm if v_tx_mm != 0 else 0
        w_mrad = w_intent_mrad if w_tx_mrad != 0 else 0

        if self._ol_last_time == 0.0:
            self._ol_last_time = now
            return
        dt = now - self._ol_last_time
        self._ol_last_time = now
        if dt <= 0.0 or dt > 1.0:
            # 第一拍或大跳变（节点刚启动 / 长时间挂起）：只更新时间戳，
            # 下一拍再积分
            return

        v = v_mm / 1000.0
        w = w_mrad / 1000.0

        # 标准 2D 自行车积分（在 yaw + dt*w/2 中点处投影），与
        # STM32 Odometry.c 的积分模型一致，所以 'auto' 模式两边切换
        # 不会造成位姿跳变。
        mid_yaw = self._ol_yaw + 0.5 * w * dt
        self._ol_x += v * math.cos(mid_yaw) * dt
        self._ol_y += v * math.sin(mid_yaw) * dt
        self._ol_yaw += w * dt
        # wrap to [-pi, pi]
        while self._ol_yaw > math.pi:
            self._ol_yaw -= 2.0 * math.pi
        while self._ol_yaw < -math.pi:
            self._ol_yaw += 2.0 * math.pi

        stamp = self.get_clock().now().to_msg()
        cy = math.cos(self._ol_yaw / 2.0)
        sy = math.sin(self._ol_yaw / 2.0)

        if self.publish_tf and self.tf_broadcaster is not None:
            t = TransformStamped()
            t.header.stamp = stamp
            t.header.frame_id = 'odom'
            t.child_frame_id = 'base_link'
            t.transform.translation.x = self._ol_x
            t.transform.translation.y = self._ol_y
            t.transform.translation.z = 0.0
            t.transform.rotation.w = cy
            t.transform.rotation.x = 0.0
            t.transform.rotation.y = 0.0
            t.transform.rotation.z = sy
            self.tf_broadcaster.sendTransform(t)

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = self._ol_x
        odom.pose.pose.position.y = self._ol_y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.w = cy
        odom.pose.pose.orientation.z = sy
        odom.twist.twist.linear.x = v
        odom.twist.twist.angular.z = w
        # 开环噪声更大，给下游一个清晰的信号
        odom.pose.covariance[0] = 5e-3
        odom.pose.covariance[7] = 5e-3
        odom.pose.covariance[14] = 1e6
        odom.pose.covariance[21] = 1e6
        odom.pose.covariance[28] = 1e6
        odom.pose.covariance[35] = 1e-2
        odom.twist.covariance[0] = 5e-3
        odom.twist.covariance[7] = 1e6
        odom.twist.covariance[14] = 1e6
        odom.twist.covariance[21] = 1e6
        odom.twist.covariance[28] = 1e6
        odom.twist.covariance[35] = 1e-2
        self.odom_pub.publish(odom)

    # ────────────────────────────────────────────────────────────────────────
    # cmd_vel 回调（纯内存操作）
    # ────────────────────────────────────────────────────────────────────────
    def cmd_vel_callback(self, msg):
        """
        统一控制入口：
          - 急停锁定期间（_estop_lock_until），一律按零速处理，
            阻止 Nav2 智能恢复或前端误发把急停冲掉。
          - 硬限幅与 STM32 ChassisParams.h 一致。
          - 死区过滤：低于阈值视为 0。
        """
        now = time.time()
        linear_mm = int(msg.linear.x * 1000)
        angular_mrad = int(msg.angular.z * 1000)

        # 硬限幅（mm/s, mrad/s）
        if linear_mm > self._max_linear_mm:
            linear_mm = self._max_linear_mm
        elif linear_mm < -self._max_linear_mm:
            linear_mm = -self._max_linear_mm
        if angular_mrad > self._max_angular_mrad:
            angular_mrad = self._max_angular_mrad
        elif angular_mrad < -self._max_angular_mrad:
            angular_mrad = -self._max_angular_mrad

        # 死区
        if abs(linear_mm) < self._linear_deadzone_mm:
            linear_mm = 0
        if abs(angular_mrad) < self._angular_deadzone_mrad:
            angular_mrad = 0

        # ★ v8.0：在启动补偿前先抓一份"MPPI 真实意图"快照
        # ──────────────────────────────────────────────────────────
        # 这个值给 _publish_open_loop_odom 做积分用。intent 不带启动补偿
        # 抬升，反映 MPPI 真正想让车走多快，odom 才不会被人为放大。
        # 注意：限幅、死区过滤仍然作用（< 死区 → 0，否则保留原值），
        # 这是 MPPI 进入电机前的"应当发生"的物理速度估计。
        intent_v = linear_mm
        intent_w = angular_mrad

        # ★ 启动补偿（kickstart）：
        # 死区之外但低于电机最小启动门槛的值，统一抬到门槛值，
        # 否则 Nav2 在 0.10~0.18 m/s 命令下电机会原地卡死。
        # 仅对 linear 做：angular 补偿会让阿克曼前轮舵机抖动（实测有效）。
        if self._min_motion_linear_mm > 0 and 0 < abs(linear_mm) < self._min_motion_linear_mm:
            linear_mm = self._min_motion_linear_mm if linear_mm > 0 else -self._min_motion_linear_mm
        # angular 默认关闭补偿（min_motion_angular=0.0）。如需开启，
        # 在 launch 显式设置 min_motion_angular > 0.0
        if self._min_motion_angular_mrad > 0 and 0 < abs(angular_mrad) < self._min_motion_angular_mrad:
            angular_mrad = self._min_motion_angular_mrad if angular_mrad > 0 else -self._min_motion_angular_mrad

        with self._lock:
            # 可观测性：无论是否被急停清零，都先记录"上层确实送来了命令"
            self._last_rx_time = now
            self._last_rx_v = linear_mm
            self._last_rx_w = angular_mrad
            # ★ v8.0 开环 odom 修复：记录补偿前的 MPPI 意图速度
            self._last_intent_v = intent_v
            self._last_intent_w = intent_w
            self._rx_count += 1

            if now < self._estop_lock_until:
                # 急停锁定中：强制零速，不更新 last_cmd_time，
                # 这样如果上层一直发非零速，watchdog 仍会兜底。
                self.latest_linear = 0
                self.latest_angular = 0
                return
            self.latest_linear = linear_mm
            self.latest_angular = angular_mrad
            self.last_cmd_time = now

    # ────────────────────────────────────────────────────────────────────────
    # 独立急停回调
    # ────────────────────────────────────────────────────────────────────────
    def _estop_callback_empty(self, _msg):
        self._trigger_estop('topic:cmd_vel_estop')

    def _estop_callback_bool(self, msg):
        # /estop True → 触发；False 不解锁（解锁由超时自动完成）
        if msg.data:
            self._trigger_estop('topic:estop')

    def _trigger_estop(self, source: str):
        with self._lock:
            self._estop_pending = True
            self.latest_linear = 0
            self.latest_angular = 0
            self._estop_lock_until = time.time() + self.ESTOP_LOCK_SECONDS
        self.get_logger().warn(f'[ESTOP] 急停触发，来源={source}')

    # ────────────────────────────────────────────────────────────────────────
    # 串口写线程
    # ────────────────────────────────────────────────────────────────────────
    def _serial_write_thread(self):
        """
        25 Hz 独立运行的串口写线程。
        优先级：急停 > cmd_timeout 自动停车 > 正常发送。
        """
        interval = 1.0 / max(1.0, self.WRITE_HZ)
        sent_linear = 0
        sent_angular = 0

        while self.running:
            loop_start = time.time()

            with self._lock:
                estop = self._estop_pending
                latest_v = self.latest_linear
                latest_w = self.latest_angular
                last_t = self.last_cmd_time

            # ── 1. 急停（最高优先级）──────────────────────────────────────
            if estop:
                self.get_logger().info(
                    f'[TX] 急停：连发 {self.ESTOP_REPEATS} 帧零速')
                for _ in range(self.ESTOP_REPEATS):
                    self._raw_write(0, 0)
                    time.sleep(0.02)
                sent_linear = 0
                sent_angular = 0
                with self._lock:
                    self._estop_pending = False
                    self.latest_linear = 0
                    self.latest_angular = 0
                # 急停后等下一拍
                elapsed = time.time() - loop_start
                time.sleep(max(0.0, interval - elapsed))
                continue

            now = time.time()

            # ── 2. cmd_vel 超时停车 ───────────────────────────────────────
            if (last_t > 0
                    and now - last_t > self.CMD_TIMEOUT
                    and (sent_linear != 0 or sent_angular != 0)):
                self.get_logger().debug('[TX] cmd_vel 超时，自动停车')
                self._raw_write(0, 0)
                sent_linear = 0
                sent_angular = 0
                with self._lock:
                    self.latest_linear = 0
                    self.latest_angular = 0
                elapsed = time.time() - loop_start
                time.sleep(max(0.0, interval - elapsed))
                continue

            # ── 3. 正常发送 ───────────────────────────────────────────────
            if latest_v != 0 or latest_w != 0:
                self._raw_write(latest_v, latest_w)
                sent_linear = latest_v
                sent_angular = latest_w
            elif sent_linear != 0 or sent_angular != 0:
                # 目标刚归零：和急停一样补发多帧零速。
                # 一些电机驱动板会锁存上一速度；单帧 stop 丢失时会继续跑。
                for _ in range(self.ESTOP_REPEATS):
                    self._raw_write(0, 0)
                    time.sleep(0.02)
                sent_linear = 0
                sent_angular = 0
            # else: 持续零速，不重复刷串口

            elapsed = time.time() - loop_start
            time.sleep(max(0.0, interval - elapsed))

    def _raw_write(self, linear_vel: int, angular_vel: int):
        """直接写串口（仅在 _serial_write_thread 或析构时调用）"""
        cmd = self.build_control_cmd(linear_vel, angular_vel)
        try:
            self.serial.write(cmd)
            # 发布 debug topic：实际进入串口的整数速度
            try:
                tx_msg = Int32MultiArray()
                tx_msg.data = [int(linear_vel), int(angular_vel)]
                self.tx_cmd_pub.publish(tx_msg)
            except Exception:
                # 发布失败不影响串口主链路
                pass
            with self._lock:
                self._last_tx_time = time.time()
                self._last_tx_v = int(linear_vel)
                self._last_tx_w = int(angular_vel)
                self._tx_count += 1
            self.get_logger().debug(
                f'[TX] linear={linear_vel} mm/s, angular={angular_vel} mrad/s')
        except Exception as e:
            self.get_logger().error(f'[TX] 串口写入失败: {e}')

    # ────────────────────────────────────────────────────────────────────────
    # 1 Hz 可观测性日志
    # ────────────────────────────────────────────────────────────────────────
    def _observability_callback(self):
        """
        每秒打印一次：rx/tx 速率、最近 cmd_vel 入参、最近写串口值、急停锁状态。
        现场用这条日志可以快速区分三种"车不动"故障：
          - rx=0/s  → bridge 根本没收到 /cmd_vel（话题/QoS/重映射问题）
          - rx>0 但 last_rx 长时间为 0 → 上层在发零速（Nav2 失败/前端误发）
          - rx>0、last_rx 非零，但 tx=0/s → 入口被死区/急停/超时清零
          - rx>0、tx>0 但车不动 → 问题在串口下游（STM32/电机/odom）
        """
        now = time.time()
        with self._lock:
            rx_count = self._rx_count
            tx_count = self._tx_count
            last_rx_v = self._last_rx_v
            last_rx_w = self._last_rx_w
            last_rx_t = self._last_rx_time
            last_tx_v = self._last_tx_v
            last_tx_w = self._last_tx_w
            last_tx_t = self._last_tx_time
            latest_v = self.latest_linear
            latest_w = self.latest_angular
            estop_locked = now < self._estop_lock_until

        drx = rx_count - self._prev_rx_count
        dtx = tx_count - self._prev_tx_count
        self._prev_rx_count = rx_count
        self._prev_tx_count = tx_count

        rx_age = (now - last_rx_t) if last_rx_t > 0 else -1.0
        tx_age = (now - last_tx_t) if last_tx_t > 0 else -1.0

        self.get_logger().info(
            f'[OBS] rx={drx}/s(total={rx_count}) '
            f'last_rx=(v={last_rx_v}mm/s,w={last_rx_w}mrad/s,age={rx_age:.2f}s) | '
            f'tx={dtx}/s(total={tx_count}) '
            f'last_tx=(v={last_tx_v}mm/s,w={last_tx_w}mrad/s,age={tx_age:.2f}s) | '
            f'latest=(v={latest_v},w={latest_w}) '
            f'estop_lock={estop_locked}'
        )

    # ────────────────────────────────────────────────────────────────────────
    # 看门狗线程
    # ────────────────────────────────────────────────────────────────────────
    def _watchdog_loop(self):
        """
        最终安全兜底：每 100 ms 检查一次。
        若超过 watchdog_timeout 未收到新命令，且 latest_* 非零，
        则直接旁路写线程把零速怼到串口，与 STM32 自身超时形成双保险。
        """
        check_interval = 0.1

        while self.running:
            time.sleep(check_interval)

            with self._lock:
                last_t = self.last_cmd_time
                latest_v = self.latest_linear
                latest_w = self.latest_angular

            if last_t == 0.0:
                continue

            elapsed = time.time() - last_t

            if elapsed > self.WATCHDOG_TIMEOUT and (latest_v != 0 or latest_w != 0):
                self.get_logger().warn(
                    f'[WD] 超时 {elapsed:.2f}s 未收到 cmd_vel，强制停车')
                for _ in range(self.ESTOP_REPEATS):
                    try:
                        self.serial.write(self.build_control_cmd(0, 0))
                    except Exception:
                        pass
                    time.sleep(0.02)
                with self._lock:
                    self.latest_linear = 0
                    self.latest_angular = 0

    # ────────────────────────────────────────────────────────────────────────
    # 帧构造
    # ────────────────────────────────────────────────────────────────────────
    def build_control_cmd(self, linear_vel: int, angular_vel: int) -> bytes:
        """
        构造 10 字节控制帧：
          AA 55 01 <vx:int16 LE> <wz:int16 LE> 00 <cs> 0D
          checksum = sum(byte[2..6]) & 0xFF
        """
        data = bytearray([FRAME_HEADER_0, FRAME_HEADER_1, CMD_VELOCITY])
        data.extend(struct.pack('<h', linear_vel))
        data.extend(struct.pack('<h', angular_vel))
        data.append(0x00)
        checksum = sum(data[2:7]) & 0xFF
        data.append(checksum)
        data.append(FRAME_TAIL)
        return bytes(data)

    # ────────────────────────────────────────────────────────────────────────
    # 接收线程：解析 STM32 上行 odom 帧
    # ────────────────────────────────────────────────────────────────────────
    def _receive_thread(self):
        while self.running and rclpy.ok():
            try:
                data = self.serial.read(self.serial.in_waiting or 1)
                if data:
                    # ★ v6.5 关键：read() 一返回就立即记录到达时间。
                    # 后续 buffer 解析 / TF 广播无论花多久，odom 的 stamp
                    # 都锚定在这一刻，AMCL 才能把"激光观测时刻"和"odom 时刻"
                    # 对齐到同一物理瞬间。
                    self._last_serial_arrival_ns = (
                        self.get_clock().now().nanoseconds
                    )
                    self.rx_buffer.extend(data)
                    self._process_rx_buffer()
            except Exception as e:
                err_str = str(e)
                if 'returned no data' in err_str:
                    time.sleep(0.01)
                else:
                    self.get_logger().error(f'[RX] 接收数据错误: {e}')

    def _process_rx_buffer(self):
        """
        解析 20 字节里程计帧：
          BB 66 type x(int32) y(int32) yaw(int16) v(int16) w(int16) reserved cs 0D
          checksum = sum(byte[2..17]) & 0xFF
        """
        while len(self.rx_buffer) >= ODOM_FRAME_LEN:
            if self.rx_buffer[0] != ODOM_HEADER_0 or self.rx_buffer[1] != ODOM_HEADER_1:
                self.rx_buffer.pop(0)
                continue

            frame = self.rx_buffer[:ODOM_FRAME_LEN]

            if frame[19] != FRAME_TAIL:
                self.rx_buffer.pop(0)
                continue

            checksum_calc = sum(frame[2:18]) & 0xFF
            checksum_recv = frame[18]
            if checksum_calc != checksum_recv:
                self.get_logger().warn(
                    f'[RX] 校验和错误: 计算={checksum_calc}, 接收={checksum_recv}')
                self.rx_buffer.pop(0)
                continue

            data_type = frame[2]
            if data_type == DATA_TYPE_ODOM:
                self._parse_odom_data(frame)

            self.rx_buffer = self.rx_buffer[ODOM_FRAME_LEN:]

    def _parse_odom_data(self, frame):
        """
        解析 STM32 上行 odom 帧。

        v6.7：是否真正发布 /odom 与 TF 由 odom_source 决定：
          - 'stm32' / 'auto'  ：接收并发布
          - 'open_loop'        ：仅记录"STM32 是否仍在上行"作为参考，不发
          - 'disabled'         ：完全忽略

        'auto' 与开环定时器互斥：本函数收到帧时记录时间戳，开环定时器
        看到 odom_stm32_timeout 内有更新就主动让位。同时把 STM32 真实
        位姿同步到开环积分器里，避免后续 STM32 一掉线就发生位姿跳变。
        """
        # 不论是否发布，都先标记 STM32 仍在上行（'auto' 模式据此仲裁）
        self._last_stm32_odom_time = time.time()

        if self.odom_source in ('open_loop', 'disabled'):
            return

        if self.publish_tf and self.tf_broadcaster is not None:
            self.received_odom_data = True

        pos_x = struct.unpack('<i', frame[3:7])[0]
        pos_y = struct.unpack('<i', frame[7:11])[0]
        yaw = struct.unpack('<h', frame[11:13])[0]
        linear_vel = struct.unpack('<h', frame[13:15])[0]
        angular_vel = struct.unpack('<h', frame[15:17])[0]

        # ★ v6.5 诊断：每 ~1s 打印一次 STM32 原始整数，
        # 用来定位"/odom 一直是 0" 这类下位机故障。
        # 不依赖 logger 级别，直接 print 一行容易被现场看到。
        try:
            self._diag_counter += 1
        except AttributeError:
            self._diag_counter = 1
        if self._diag_counter % 10 == 0:  # STM32 10Hz → 每秒一行
            self.get_logger().info(
                f'[RX-RAW] pos_x={pos_x}mm pos_y={pos_y}mm '
                f'yaw={yaw}mrad v={linear_vel}mm/s w={angular_vel}mrad/s'
            )

        x = pos_x / 1000.0
        y = pos_y / 1000.0
        theta = yaw / 1000.0
        vx = linear_vel / 1000.0
        vth = angular_vel / 1000.0

        # ★ v6.5：以 read() 到达时刻作为测量时刻基准，再减去固定传输延迟。
        # 仅当接收线程已经成功读过至少一次串口才用 arrival 时间戳；
        # 解析中途异常退化时回落到 now()，保证 TF 链不断。
        arrival_ns = self._last_serial_arrival_ns
        if arrival_ns > 0:
            stamp_ns = max(0, arrival_ns + self.odom_stamp_offset_ns)
            stamp = RclpyTime(nanoseconds=stamp_ns).to_msg()
        else:
            stamp = self.get_clock().now().to_msg()

        cy = math.cos(theta / 2.0)
        sy = math.sin(theta / 2.0)

        if self.publish_tf:
            t = TransformStamped()
            t.header.stamp = stamp
            t.header.frame_id = 'odom'
            t.child_frame_id = 'base_link'
            t.transform.translation.x = x
            t.transform.translation.y = y
            t.transform.translation.z = 0.0
            t.transform.rotation.w = cy
            t.transform.rotation.x = 0.0
            t.transform.rotation.y = 0.0
            t.transform.rotation.z = sy
            self.tf_broadcaster.sendTransform(t)

        odom = Odometry()
        odom.header.stamp = stamp
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.w = cy
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = sy
        odom.twist.twist.linear.x = vx
        odom.twist.twist.linear.y = 0.0
        odom.twist.twist.angular.z = vth

        # ★ v6.5：补全 pose / twist 协方差。AMCL 内部不直接读这个值，
        # 但下游 robot_localization / EKF / RViz 显示都依赖；之前留空
        # 等价于"绝对确定"，下游融合会过度信任里程计，加剧漂移表象。
        # x, y, yaw 给 1cm / 1cm / 1°^2 量级噪声；vx, vth 同理。
        # 不影响 AMCL 的 alpha 噪声模型（那个还是看 amcl.alpha1..5）。
        odom.pose.covariance[0] = 1e-3       # x
        odom.pose.covariance[7] = 1e-3       # y
        odom.pose.covariance[14] = 1e6       # z (不可用)
        odom.pose.covariance[21] = 1e6       # roll (不可用)
        odom.pose.covariance[28] = 1e6       # pitch (不可用)
        odom.pose.covariance[35] = 3e-4      # yaw (~1°)
        odom.twist.covariance[0] = 1e-3      # vx
        odom.twist.covariance[7] = 1e6       # vy (阿克曼禁止)
        odom.twist.covariance[14] = 1e6
        odom.twist.covariance[21] = 1e6
        odom.twist.covariance[28] = 1e6
        odom.twist.covariance[35] = 3e-4     # vth

        self.odom_pub.publish(odom)

        # 同步开环积分器，保证 'auto' 模式下 STM32 帧丢失时切换到开环
        # 不会有位姿跳变。仅在 'auto' 模式下做，'stm32' 模式根本没开
        # 开环定时器，无所谓。
        if self.odom_source == 'auto':
            self._ol_x = x
            self._ol_y = y
            self._ol_yaw = theta
            self._ol_last_time = time.time()

        self.get_logger().debug(
            f'[RX] x={x:.3f}, y={y:.3f}, yaw={theta:.3f}, '
            f'vx={vx:.3f}, vth={vth:.3f}')

    # ────────────────────────────────────────────────────────────────────────
    # 清理
    # ────────────────────────────────────────────────────────────────────────
    def destroy_node(self):
        self.running = False
        # 强制写多帧零速，确保 STM32 收到
        for _ in range(self.ESTOP_REPEATS):
            try:
                self.serial.write(self.build_control_cmd(0, 0))
                time.sleep(0.02)
            except Exception:
                pass
        for t in [
            getattr(self, 'rx_thread', None),
            getattr(self, '_write_thread', None),
            getattr(self, '_watchdog_thread', None),
        ]:
            if t and t.is_alive():
                t.join(timeout=1.0)
        if hasattr(self, 'serial') and self.serial.is_open:
            self.serial.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = STM32Bridge()
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
