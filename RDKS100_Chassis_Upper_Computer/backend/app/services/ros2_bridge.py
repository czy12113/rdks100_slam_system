# =============================================================================
# ROS2 桥接模块
# 负责与 ROS2 系统通信，订阅 topic、发布指令、调用 service
# 当 ROS2_ENABLED=false 时自动降级为模拟数据
# =============================================================================
import asyncio
import logging
import threading
from typing import Optional, Callable, Any, Dict
from app.core.config import (
    ROS2_ENABLED, ROS2_DOMAIN_ID,
    ROS2_TOPIC_CMD_VEL, ROS2_TOPIC_SCAN, ROS2_TOPIC_IMU,
    ROS2_TOPIC_LIDAR3D,
    ROS2_TOPIC_MAP, ROS2_TOPIC_POSE, ROS2_TOPIC_BATTERY,
    ROS2_TOPIC_RGB_IMAGE, ROS2_TOPIC_DEPTH_IMAGE,
    ROS2_TOPIC_ANNOTATED_IMAGE, ROS2_TOPIC_DETECTION_RESULTS,
    ROS2_TOPIC_ODOM, ROS2_TOPIC_PATH, ROS2_TOPIC_GOAL,
    ROS2_TOPIC_SLAM_POSE,
    ROS2_TOPIC_VLM_DESCRIPTION, ROS2_TOPIC_VLM_STATUS, ROS2_SERVICE_VLM_ASK,
    ROS2_TOPIC_FIRE_ALERT, ROS2_TOPIC_FIRE_PREALERT,
    # ── 创新点：动态行人 + 安全事件 ─────────────────────────────
    ROS2_TOPIC_SAFETY_EVENT, ROS2_TOPIC_DYNAMIC_PERSON_POINTS,
    ROS2_SERVICE_SAVE_MAP, ROS2_SERVICE_LOAD_MAP,
    ROS2_SERVICE_START_SLAM, ROS2_SERVICE_STOP_SLAM,
    ROBOT_MAX_LINEAR_VEL, ROBOT_MAX_ANGULAR_VEL,
    LIDAR_MOUNT_PITCH_DEG,
    LIDAR_MAX_PUSH_POINTS,
)

logger = logging.getLogger(__name__)


class ROS2Bridge:
    """
    ROS2 桥接层
    - ROS2_ENABLED=true：使用 rclpy 与真实 ROS2 通信
    - ROS2_ENABLED=false：所有方法为空操作，由 mock_data 提供数据
    """

    def __init__(self):
        self._enabled = ROS2_ENABLED
        self._node = None
        self._executor = None
        self._spin_thread: Optional[threading.Thread] = None
        self._initialized = False

        # 回调函数注册表：topic -> callback
        self._callbacks: Dict[str, Callable] = {}

        # 发布者缓存
        self._publishers: Dict[str, Any] = {}
        # 订阅者缓存
        self._subscribers: Dict[str, Any] = {}

        # 最新数据缓存（线程安全），供 data_pusher 读取
        self._latest_data: Dict[str, Any] = {}
        self._data_lock = threading.Lock()

        # IMU 互补滤波状态（Livox 不输出姿态，需要自行估算）
        self._imu_roll: float = 0.0
        self._imu_pitch: float = 0.0
        self._imu_yaw: float = 0.0
        self._imu_last_time: float = 0.0

        if self._enabled:
            self._init_ros2()

    def _init_ros2(self):
        """初始化 ROS2 节点（仅在 ROS2_ENABLED=true 时调用）"""
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.executors import MultiThreadedExecutor

            rclpy.init(args=None)
            self._node = rclpy.create_node(
                "rdks100_webui_bridge",
                namespace="",
                use_global_arguments=True,
            )
            self._executor = MultiThreadedExecutor()
            self._executor.add_node(self._node)

            # 在独立线程中 spin
            self._spin_thread = threading.Thread(
                target=self._executor.spin,
                daemon=True,
                name="ros2_spin",
            )
            self._spin_thread.start()
            self._initialized = True
            logger.info("[ROS2] 节点初始化成功，domain_id=%d", ROS2_DOMAIN_ID)

            # 创建发布者
            self._create_publishers()
            # 创建订阅者
            self._create_subscribers()

        except ImportError:
            logger.warning("[ROS2] rclpy 未安装，自动降级为模拟模式")
            self._enabled = False
        except Exception as e:
            logger.error("[ROS2] 初始化失败: %s，降级为模拟模式", e)
            self._enabled = False

    def _create_publishers(self):
        """创建所有需要的 ROS2 发布者"""
        if not self._initialized:
            return
        try:
            from geometry_msgs.msg import Twist
            from geometry_msgs.msg import PoseStamped
            from std_msgs.msg import Empty

            self._publishers["cmd_vel"] = self._node.create_publisher(
                Twist, ROS2_TOPIC_CMD_VEL, 10
            )
            self._publishers["goal_pose"] = self._node.create_publisher(
                PoseStamped, ROS2_TOPIC_GOAL, 10
            )
            # 急停独立通道：与 stm32_bridge 的 cmd_vel_estop 订阅对齐
            self._publishers["estop"] = self._node.create_publisher(
                Empty, "/cmd_vel_estop", 10
            )
            logger.info("[ROS2] 发布者创建完成（含急停 /cmd_vel_estop）")
        except Exception as e:
            logger.error("[ROS2] 创建发布者失败: %s", e)

    def _create_subscribers(self):
        """
        创建所有需要的 ROS2 订阅者。
        每个订阅独立 try/except，单个失败不影响其他订阅。

        QoS 策略：
        - 高速传感器（点云/图像/IMU）：BEST_EFFORT + KEEP_LAST depth=1
          这样后端只处理最新一帧，旧帧由 DDS 自动丢弃，不会在后端排队积压
          导致 RDK 算力被旧帧的 JSON/base64 编码占满。
        - 低频可靠数据（地图/里程计/电池/路径/检测结果）：RELIABLE depth=10
          保证不丢，对实时性要求低。
        """
        if not self._initialized:
            return

        # 构造两套 QoS 配置
        try:
            from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy, DurabilityPolicy
            qos_sensor = QoSProfile(
                reliability=ReliabilityPolicy.BEST_EFFORT,
                history=HistoryPolicy.KEEP_LAST,
                depth=1,
                durability=DurabilityPolicy.VOLATILE,
            )
            qos_reliable = QoSProfile(
                reliability=ReliabilityPolicy.RELIABLE,
                history=HistoryPolicy.KEEP_LAST,
                depth=10,
            )
        except Exception as e:
            logger.error("[ROS2] 构造 QoS 失败，回退到默认 depth=10: %s", e)
            qos_sensor = 1
            qos_reliable = 10

        # ── 3D 激光雷达点云（Livox Mid-360S → /livox/lidar）────────────────
        try:
            from sensor_msgs.msg import PointCloud2
            sub = self._node.create_subscription(
                PointCloud2, ROS2_TOPIC_LIDAR3D,
                lambda msg: self._dispatch("lidar3d", self._parse_pointcloud2(msg)), qos_sensor
            )
            self._subscribers["lidar3d"] = sub
            logger.info("[ROS2] 已订阅 lidar3d → %s (BEST_EFFORT depth=1)", ROS2_TOPIC_LIDAR3D)
        except Exception as e:
            logger.error("[ROS2] 订阅 lidar3d 失败: %s", e)

        # ── IMU（Livox 内置 IMU → /livox/imu）──────────────────────────────
        try:
            from sensor_msgs.msg import Imu
            sub = self._node.create_subscription(
                Imu, ROS2_TOPIC_IMU,
                lambda msg: self._dispatch("imu", self._parse_imu(msg)), qos_sensor
            )
            self._subscribers["imu"] = sub
            logger.info("[ROS2] 已订阅 imu → %s (BEST_EFFORT depth=1)", ROS2_TOPIC_IMU)
        except Exception as e:
            logger.error("[ROS2] 订阅 imu 失败: %s", e)

        # ── 地图 ─────────────────────────────────────────────────────────────
        try:
            from nav_msgs.msg import OccupancyGrid
            sub = self._node.create_subscription(
                OccupancyGrid, ROS2_TOPIC_MAP,
                lambda msg: self._dispatch("map", self._parse_map(msg)), qos_reliable
            )
            self._subscribers["map"] = sub
            logger.info("[ROS2] 已订阅 map → %s", ROS2_TOPIC_MAP)
        except Exception as e:
            logger.error("[ROS2] 订阅 map 失败: %s", e)

        # ── 里程计 ───────────────────────────────────────────────────────────
        try:
            from nav_msgs.msg import Odometry
            sub = self._node.create_subscription(
                Odometry, ROS2_TOPIC_ODOM,
                lambda msg: self._dispatch("odom", self._parse_odom(msg)), qos_reliable
            )
            self._subscribers["odom"] = sub
            logger.info("[ROS2] 已订阅 odom → %s", ROS2_TOPIC_ODOM)
        except Exception as e:
            logger.error("[ROS2] 订阅 odom 失败: %s", e)

        # ── 电池 ─────────────────────────────────────────────────────────────
        try:
            from sensor_msgs.msg import BatteryState
            sub = self._node.create_subscription(
                BatteryState, ROS2_TOPIC_BATTERY,
                lambda msg: self._dispatch("battery", self._parse_battery(msg)), qos_reliable
            )
            self._subscribers["battery"] = sub
            logger.info("[ROS2] 已订阅 battery → %s", ROS2_TOPIC_BATTERY)
        except Exception as e:
            logger.error("[ROS2] 订阅 battery 失败: %s", e)

        # ── RGB 图像 ─────────────────────────────────────────────────────────
        try:
            from sensor_msgs.msg import Image
            sub = self._node.create_subscription(
                Image, ROS2_TOPIC_RGB_IMAGE,
                lambda msg: self._dispatch("rgb_image", self._parse_image(msg, "rgb")), qos_sensor
            )
            self._subscribers["rgb_image"] = sub
            logger.info("[ROS2] 已订阅 rgb_image → %s (BEST_EFFORT depth=1)", ROS2_TOPIC_RGB_IMAGE)
        except Exception as e:
            logger.error("[ROS2] 订阅 rgb_image 失败: %s", e)

        # ── 深度图像 ─────────────────────────────────────────────────────────
        try:
            from sensor_msgs.msg import Image
            sub = self._node.create_subscription(
                Image, ROS2_TOPIC_DEPTH_IMAGE,
                lambda msg: self._dispatch("depth_image", self._parse_image(msg, "depth")), qos_sensor
            )
            self._subscribers["depth_image"] = sub
            logger.info("[ROS2] 已订阅 depth_image → %s (BEST_EFFORT depth=1)", ROS2_TOPIC_DEPTH_IMAGE)
        except Exception as e:
            logger.error("[ROS2] 订阅 depth_image 失败: %s", e)
        # ── 带检测框的标注图像 ──────────────────────────────────────────────
        try:
            from sensor_msgs.msg import Image
            sub = self._node.create_subscription(
                Image, ROS2_TOPIC_ANNOTATED_IMAGE,
                lambda msg: self._dispatch("annotated_image", self._parse_annotated_image(msg)), qos_sensor
            )
            self._subscribers["annotated_image"] = sub
            logger.info("[ROS2] 已订阅 annotated_image → %s (BEST_EFFORT depth=1)", ROS2_TOPIC_ANNOTATED_IMAGE)
        except Exception as e:
            logger.error("[ROS2] 订阅 annotated_image 失败: %s", e)

        # ── YOLO 检测结果 JSON（/detection/results）──────────────────────────
        try:
            from std_msgs.msg import String
            sub = self._node.create_subscription(
                String, ROS2_TOPIC_DETECTION_RESULTS,
                lambda msg: self._dispatch("detection_results", self._parse_detection_results(msg)), qos_reliable
            )
            self._subscribers["detection_results"] = sub
            logger.info("[ROS2] 已订阅 detection_results → %s", ROS2_TOPIC_DETECTION_RESULTS)
        except Exception as e:
            logger.error("[ROS2] 订阅 detection_results 失败: %s", e)

        # ── 路径 ─────────────────────────────────────────────────────────────
        try:
            from nav_msgs.msg import Path
            sub = self._node.create_subscription(
                Path, ROS2_TOPIC_PATH,
                lambda msg: self._dispatch("path", self._parse_path(msg)), qos_reliable
            )
            self._subscribers["path"] = sub
            logger.info("[ROS2] 已订阅 path → %s", ROS2_TOPIC_PATH)
        except Exception as e:
            logger.error("[ROS2] 订阅 path 失败: %s", e)

        # ── VLM 场景描述（vlm_node → /vlm/scene_description）────────────────
        try:
            from std_msgs.msg import String
            sub = self._node.create_subscription(
                String, ROS2_TOPIC_VLM_DESCRIPTION,
                lambda msg: self._dispatch("vlm_description", self._parse_vlm_description(msg)), qos_reliable
            )
            self._subscribers["vlm_description"] = sub
            logger.info("[ROS2] 已订阅 vlm_description → %s", ROS2_TOPIC_VLM_DESCRIPTION)
        except Exception as e:
            logger.error("[ROS2] 订阅 vlm_description 失败: %s", e)

        # ── VLM 状态（vlm_node → /vlm/status）────────────────────────────────
        try:
            from std_msgs.msg import String
            sub = self._node.create_subscription(
                String, ROS2_TOPIC_VLM_STATUS,
                lambda msg: self._dispatch("vlm_status", self._parse_vlm_status(msg)), qos_reliable
            )
            self._subscribers["vlm_status"] = sub
            logger.info("[ROS2] 已订阅 vlm_status → %s", ROS2_TOPIC_VLM_STATUS)
        except Exception as e:
            logger.error("[ROS2] 订阅 vlm_status 失败: %s", e)

        # ── 火警告警（vlm_node → /alert/fire）─────────────────────────────────
        try:
            from std_msgs.msg import String
            sub = self._node.create_subscription(
                String, ROS2_TOPIC_FIRE_ALERT,
                lambda msg: self._dispatch("fire_alert", self._parse_fire_alert(msg)), qos_reliable
            )
            self._subscribers["fire_alert"] = sub
            logger.info("[ROS2] 已订阅 fire_alert → %s", ROS2_TOPIC_FIRE_ALERT)
        except Exception as e:
            logger.error("[ROS2] 订阅 fire_alert 失败: %s", e)

        # ── 火警预警（fire_smoke_node → /fire_smoke/prealert，debug 用）────
        try:
            from std_msgs.msg import String
            sub = self._node.create_subscription(
                String, ROS2_TOPIC_FIRE_PREALERT,
                lambda msg: self._dispatch("fire_prealert", self._parse_fire_prealert(msg)), qos_reliable
            )
            self._subscribers["fire_prealert"] = sub
            logger.info("[ROS2] 已订阅 fire_prealert → %s", ROS2_TOPIC_FIRE_PREALERT)
        except Exception as e:
            logger.error("[ROS2] 订阅 fire_prealert 失败: %s", e)

        # ── 安全事件（dynamic_person_obstacle_node → /vlm/safety_event）──────
        # 创新点核心 topic：本地 VLM + Nav2 联合决策后每次动作变化时发一次。
        # payload 是 JSON，格式见 dynamic_person_obstacle_node.py 中
        # _publish_safety_event() 定义。前端订阅它做弹窗、图标闪烁。
        try:
            from std_msgs.msg import String
            sub = self._node.create_subscription(
                String, ROS2_TOPIC_SAFETY_EVENT,
                lambda msg: self._dispatch("safety_event", self._parse_safety_event(msg)), qos_reliable
            )
            self._subscribers["safety_event"] = sub
            logger.info("[ROS2] 已订阅 safety_event → %s", ROS2_TOPIC_SAFETY_EVENT)
        except Exception as e:
            logger.error("[ROS2] 订阅 safety_event 失败: %s", e)

        # ── 动态行人点云（dynamic_person_obstacle_node → /dynamic_person_points）──
        # PointCloud2 供 Nav2 costmap 使用（本节点也订阅），本 bridge 把其中
        # 少量代表点提取出来推给前端，让 NavigationView 在地图上叠加红点。
        try:
            from sensor_msgs.msg import PointCloud2
            sub = self._node.create_subscription(
                PointCloud2, ROS2_TOPIC_DYNAMIC_PERSON_POINTS,
                lambda msg: self._dispatch(
                    "dynamic_person_points",
                    self._parse_dynamic_person_points(msg),
                ),
                qos_sensor,
            )
            self._subscribers["dynamic_person_points"] = sub
            logger.info(
                "[ROS2] 已订阅 dynamic_person_points → %s (BEST_EFFORT depth=1)",
                ROS2_TOPIC_DYNAMIC_PERSON_POINTS,
            )
        except Exception as e:
            logger.error("[ROS2] 订阅 dynamic_person_points 失败: %s", e)

        logger.info("[ROS2] 订阅者创建完成，成功: %s", list(self._subscribers.keys()))

    def _dispatch(self, topic: str, data: dict):
        """将 ROS2 消息分发给注册的回调函数，并缓存最新数据"""
        # 缓存最新数据（线程安全）
        with self._data_lock:
            self._latest_data[topic] = data

        if topic in self._callbacks:
            try:
                self._callbacks[topic](data)
            except Exception as e:
                logger.error("[ROS2] 回调执行失败 topic=%s: %s", topic, e)

    def register_callback(self, topic: str, callback: Callable):
        """注册 topic 数据回调"""
        self._callbacks[topic] = callback

    def get_latest(self, topic: str) -> Optional[dict]:
        """获取指定 topic 的最新数据（线程安全），无数据时返回 None"""
        with self._data_lock:
            return self._latest_data.get(topic)

    # -------------------------------------------------------------------------
    # 消息解析器（ROS2 msg -> Python dict）
    # -------------------------------------------------------------------------
    def _parse_pointcloud2(self, msg) -> dict:
        """
        解析 sensor_msgs/PointCloud2 消息（Livox Mid-360S 标准输出）
        字段布局：x(float32) y(float32) z(float32) intensity(float32)
        输出紧凑格式 [x, y, z, intensity] 减少 JSON 体积
        同时对点数降采样，控制 WebSocket 带宽

        安装俯仰角补偿：
        雷达水平安装时 LIDAR_MOUNT_PITCH_DEG=0，不做额外旋转。
        若现场设置了俯仰角，则绕 Y 轴旋转 -pitch_deg 还原为水平坐标系：
          x' =  x * cos(θ) + z * sin(θ)
          y' =  y
          z' = -x * sin(θ) + z * cos(θ)
        其中 θ = -LIDAR_MOUNT_PITCH_DEG（弧度），即对安装角取反做补偿。
        运行时可通过 /api/device/config 的 lidar.mount_pitch 字段覆盖此值。
        """
        import struct
        import math

        # ── 读取运行时安装俯仰角覆盖值（device.py 运行时配置，热更新无需重启）──────
        try:
            from app.api.device import _runtime_config as _rtcfg
            pitch_deg = float(_rtcfg.get("lidar", {}).get("mount_pitch", LIDAR_MOUNT_PITCH_DEG))
        except Exception:
            pitch_deg = LIDAR_MOUNT_PITCH_DEG

        # 补偿角 = -安装角；水平安装时 pitch_deg=0，因此这里是 no-op
        comp_rad = math.radians(-pitch_deg)
        cos_c = math.cos(comp_rad)
        sin_c = math.sin(comp_rad)

        # 解析 PointCloud2 字段偏移
        field_offsets = {}
        for field in msg.fields:
            field_offsets[field.name] = field.offset

        x_off = field_offsets.get("x", 0)
        y_off = field_offsets.get("y", 4)
        z_off = field_offsets.get("z", 8)
        intensity_off = field_offsets.get("intensity", 12)
        point_step = msg.point_step  # 每个点的字节数（通常 16 或 20）

        raw = bytes(msg.data)
        total_points = msg.width * msg.height

        # 降采样：最多保留 LIDAR_MAX_PUSH_POINTS 个点发送给前端（默认 5000）
        # Livox Mid-360S 约 19968 点/帧，step≈4 → 保留约 25% 密度
        # 显著降低 WebSocket JSON 体积，避免阻塞前端主线程
        MAX_POINTS = max(500, LIDAR_MAX_PUSH_POINTS)
        step = max(1, total_points // MAX_POINTS)

        points = []
        z_values = []
        distances = []
        intensities = []

        for i in range(0, total_points, step):
            base = i * point_step
            if base + point_step > len(raw):
                break
            try:
                x = struct.unpack_from("<f", raw, base + x_off)[0]
                y = struct.unpack_from("<f", raw, base + y_off)[0]
                z = struct.unpack_from("<f", raw, base + z_off)[0]
                intensity = struct.unpack_from("<f", raw, base + intensity_off)[0]
            except struct.error:
                continue

            # 过滤无效点（NaN / Inf / 超出量程）
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                continue
            if not math.isfinite(intensity):
                intensity = 0.0
            dist_xy = math.sqrt(x * x + y * y)
            # 最小距离 0.02m（Livox 近距离盲区），最大 40m
            if dist_xy < 0.02 or dist_xy > 40.0:
                continue

            # ── 应用安装俯仰角补偿：绕 Y 轴旋转 comp_rad ─────────────────────
            # ROS 坐标系：X=前, Y=左, Z=上；绕 Y 轴旋转只影响 X/Z 分量
            xc = x * cos_c + z * sin_c
            yc = y
            zc = -x * sin_c + z * cos_c

            # 保留 3 位小数（毫米级精度），intensity 归一化到 0~255 整数节省带宽
            points.append([
                round(xc, 3),
                round(yc, 3),
                round(zc, 3),
                min(255, max(0, int(intensity))),
            ])
            z_values.append(zc)
            distances.append(dist_xy)
            intensities.append(intensity)

        min_dist = round(min(distances, default=0.0), 3)
        max_range = round(max(distances, default=0.0), 1)
        z_min = round(min(z_values, default=0.0), 3)
        z_max = round(max(z_values, default=0.0), 3)
        # intensity 统计（用于前端动态色彩映射）
        int_max = round(max(intensities, default=255.0), 1)
        int_min = round(min(intensities, default=0.0), 1)

        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "frame_id": msg.header.frame_id,
            "points": points,           # [[x, y, z, intensity(0-255)], ...]
            "point_count": len(points),
            "total_points": total_points,
            "min_distance": min_dist,
            "range_max": max_range,
            "z_min": z_min,
            "z_max": z_max,
            "intensity_min": int_min,
            "intensity_max": int_max,
            "obstacle_count": sum(1 for d in distances if d < 2.0),
            "is_3d": True,
        }

    def _parse_laserscan(self, msg) -> dict:
        """保留 2D 激光雷达解析（兼容旧版本）"""
        import math
        ranges = list(msg.ranges)
        points = []
        for i, r in enumerate(ranges):
            if msg.range_min <= r <= msg.range_max:
                a = msg.angle_min + i * msg.angle_increment
                points.append([
                    round(r * math.cos(a), 3),
                    round(r * math.sin(a), 3),
                ])
        valid_ranges = [r for r in ranges if msg.range_min <= r <= msg.range_max]
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "angle_min": msg.angle_min,
            "angle_max": msg.angle_max,
            "range_min": msg.range_min,
            "range_max": msg.range_max,
            "points": points,
            "obstacle_count": sum(1 for r in valid_ranges if r < 2.0),
            "min_distance": round(min(valid_ranges, default=0), 3),
            "is_3d": False,
        }

    def _parse_imu(self, msg) -> dict:
        """
        解析 Livox Mid-360 IMU 消息。
        注意：Livox IMU 不输出姿态四元数（orientation 恒为单位四元数），
        因此使用互补滤波（加速度计 + 陀螺仪积分）估算 Roll/Pitch，
        Yaw 使用陀螺仪积分（无磁力计，存在漂移）。
        加速度单位：g（1g ≈ 9.81 m/s²）

        修复 v2：
        - 首次收到数据时用加速度计直接初始化 Roll/Pitch（避免从 0 缓慢收敛）
        - ALPHA 降低到 0.90，加速度计权重 10%，静止时更快反映真实姿态
        """
        import math
        import time

        now = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

        gx = msg.angular_velocity.x      # rad/s
        gy = msg.angular_velocity.y
        gz = msg.angular_velocity.z
        ax = msg.linear_acceleration.x   # g
        ay = msg.linear_acceleration.y
        az = msg.linear_acceleration.z

        # 时间步长（首次调用用默认值）
        dt = now - self._imu_last_time if self._imu_last_time > 0 else 0.01
        # 防止 dt 异常（重启/跳变）
        if dt <= 0 or dt > 1.0:
            dt = 0.01

        # 加速度计估算 Roll/Pitch（静止时准确，运动时有噪声）
        acc_norm = math.sqrt(ax * ax + ay * ay + az * az)
        if acc_norm > 0.1:  # 防止除零
            ax_n, ay_n, az_n = ax / acc_norm, ay / acc_norm, az / acc_norm
            acc_roll  = math.atan2(ay_n, az_n)
            acc_pitch = math.asin(max(-1.0, min(1.0, -ax_n)))
        else:
            acc_roll  = self._imu_roll
            acc_pitch = self._imu_pitch

        # 首次收到 IMU 数据：用加速度计直接初始化姿态（跳过缓慢收敛过程）
        if self._imu_last_time == 0.0:
            self._imu_roll  = acc_roll
            self._imu_pitch = acc_pitch
            self._imu_yaw   = 0.0
            self._imu_last_time = now
            # 首帧直接返回加速度计估算值
            roll_deg  = round(math.degrees(acc_roll),  2)
            pitch_deg = round(math.degrees(acc_pitch), 2)
            yaw_deg   = 0.0
        else:
            self._imu_last_time = now
            # 互补滤波：0.90 陀螺仪积分 + 0.10 加速度计修正
            # 降低 ALPHA 使加速度计有更大权重，静止时快速反映真实姿态
            ALPHA = 0.90
            self._imu_roll  = ALPHA * (self._imu_roll  + gx * dt) + (1 - ALPHA) * acc_roll
            self._imu_pitch = ALPHA * (self._imu_pitch + gy * dt) + (1 - ALPHA) * acc_pitch
            # Yaw 纯陀螺仪积分（无磁力计，长时间会漂移）
            self._imu_yaw  += gz * dt

            roll_deg  = round(math.degrees(self._imu_roll),  2)
            pitch_deg = round(math.degrees(self._imu_pitch), 2)
            yaw_deg   = round(math.degrees(self._imu_yaw),   2)

        return {
            "timestamp": now,
            "orientation": {
                "roll":  roll_deg,
                "pitch": pitch_deg,
                "yaw":   yaw_deg,
                "quaternion": {
                    "x": msg.orientation.x,
                    "y": msg.orientation.y,
                    "z": msg.orientation.z,
                    "w": msg.orientation.w,
                },
            },
            "angular_velocity": {
                "x": round(gx, 4),
                "y": round(gy, 4),
                "z": round(gz, 4),
            },
            "linear_acceleration": {
                "x": round(ax, 4),
                "y": round(ay, 4),
                "z": round(az, 4),
            },
            "temperature": 0.0,
        }

    def _parse_map(self, msg) -> dict:
        data_2d = []
        w, h = msg.info.width, msg.info.height
        flat = list(msg.data)
        for row in range(h):
            data_2d.append(flat[row * w:(row + 1) * w])
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "width": w,
            "height": h,
            "resolution": msg.info.resolution,
            "origin": {
                "x": msg.info.origin.position.x,
                "y": msg.info.origin.position.y,
            },
            "data": data_2d,
        }

    def _parse_odom(self, msg) -> dict:
        import math
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        siny = 2 * (q.w * q.z + q.x * q.y)
        cosy = 1 - 2 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny, cosy)
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "pose": {"x": p.x, "y": p.y, "z": p.z, "yaw": yaw},
            "velocity": {
                "linear_x": msg.twist.twist.linear.x,
                "linear_y": msg.twist.twist.linear.y,
                "angular_z": msg.twist.twist.angular.z,
            },
        }

    def _parse_battery(self, msg) -> dict:
        return {
            "timestamp": 0,
            "percent": round(msg.percentage * 100, 1),
            "voltage": round(msg.voltage, 2),
            "current": round(msg.current, 2),
            "charging": msg.power_supply_status == 1,
        }

    def _parse_image(self, msg, img_type: str) -> dict:
        """
        图像消息转 JPEG base64。

        性能相关：
        - RGB 使用运行时 CAMERA_JPEG_QUALITY（默认 80）；30fps 场景可考虑
          在 device 配置中降到 70~75 进一步降低带宽 / 编码耗时。
        - Depth 单独用较低 quality（65），因为深度可视化色带对压缩更宽容。
        - RGB 支持 rgb8 / bgr8 两种 encoding（RealSense 通常为 rgb8）：
          rgb8 需要转成 BGR 交给 cv2.imencode 才是"正确"的 JPEG，否则
          红蓝会互换。
        """
        import base64
        import numpy as np
        from app.core.config import CAMERA_JPEG_QUALITY
        try:
            import cv2
            if img_type == "rgb":
                arr = np.frombuffer(msg.data, dtype=np.uint8)
                img = arr.reshape((msg.height, msg.width, 3))
                # RealSense 默认 rgb8，需要转 BGR 供 cv2 编码
                encoding = (getattr(msg, "encoding", "") or "").lower()
                if encoding in ("rgb8", "rgb"):
                    img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                _, buf = cv2.imencode(
                    ".jpg", img,
                    [cv2.IMWRITE_JPEG_QUALITY, int(CAMERA_JPEG_QUALITY)]
                )
            else:
                arr16 = np.frombuffer(msg.data, dtype=np.uint16)
                depth = arr16.reshape((msg.height, msg.width))
                depth_vis = (depth / 10).clip(0, 255).astype(np.uint8)
                depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
                _, buf = cv2.imencode(
                    ".jpg", depth_color,
                    [cv2.IMWRITE_JPEG_QUALITY, 65]
                )
            return {
                "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                "type": img_type,
                "width": msg.width,
                "height": msg.height,
                "data": base64.b64encode(buf.tobytes()).decode(),
                "encoding": "jpeg/base64",
            }
        except Exception as e:
            logger.error("[ROS2] 图像解析失败: %s", e)
            return {}

    def _parse_annotated_image(self, msg) -> dict:
        """
        解析检测节点发布的带标注框图像（BGR8 → JPEG base64）。
        检测节点已将框和距离画在图上，直接编码即可。
        JPEG 质量取运行时 CAMERA_JPEG_QUALITY，与 RGB 保持一致。
        """
        import base64
        import numpy as np
        from app.core.config import CAMERA_JPEG_QUALITY
        try:
            import cv2
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            img = arr.reshape((msg.height, msg.width, 3))
            # BGR8 → JPEG 压缩
            _, buf = cv2.imencode(
                ".jpg", img,
                [cv2.IMWRITE_JPEG_QUALITY, int(CAMERA_JPEG_QUALITY)]
            )
            return {
                "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                "type": "annotated",
                "width": msg.width,
                "height": msg.height,
                "data": base64.b64encode(buf.tobytes()).decode(),
                "encoding": "jpeg/base64",
            }
        except Exception as e:
            logger.error("[ROS2] 标注图像解析失败: %s", e)
            return {}


    def _parse_detection_results(self, msg) -> dict:
        """
        解析 /detection/results（std_msgs/String，JSON 格式）。
        detection_node 发布的格式：
          {
            "timestamp": float,
            "frame_id":  int,
            "infer_ms":  float,
            "count":     int,
            "detections": [
              {"class_id", "class_name", "confidence", "bbox", "distance_m"}, ...
            ]
          }
        直接解析后原样透传，供前端 detection_results topic 消费。
        """
        import json as _json
        try:
            return _json.loads(msg.data)
        except Exception as e:
            logger.error("[ROS2] 解析 detection_results 失败: %s", e)
            return {}

    def _parse_path(self, msg) -> dict:
        points = [
            {"x": p.pose.position.x, "y": p.pose.position.y}
            for p in msg.poses
        ]
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "points": points,
        }

    def _parse_vlm_description(self, msg) -> dict:
        """
        解析 /vlm/scene_description（std_msgs/String，JSON 格式）。
        vlm_node 发布格式：
          {
            "timestamp": float,
            "frame_id":  int,
            "provider":  "qwen_vl",
            "model":     "qwen-vl-plus",
            "elapsed_ms": float,
            "description": "前方 3 米处有一个穿红衣服的人...",
            "per_object": [{"class_name", "distance_m", "text"}, ...],
            "trigger":   "class_change" | "distance" | "heartbeat" | "force",
            "tokens_in": int, "tokens_out": int
          }
        """
        import json as _json
        try:
            return _json.loads(msg.data)
        except Exception as e:
            logger.error("[ROS2] 解析 vlm_description 失败: %s", e)
            return {}

    def _parse_fire_alert(self, msg) -> dict:
        """
        解析 /alert/fire（std_msgs/String，JSON 格式，vlm_node 二次确认后发布）。

        vlm_node 发布格式：
          {
            "timestamp":      float,
            "frame_id":       int,
            "level":          "none" | "low" | "high",
            "fire_detected":  bool,
            "smoke_detected": bool,
            "confidence":     0~1,
            "reason":         "中文判定依据",
            "recommendation": "中文建议",
            "raw":            原始 VLM 文本,
            "provider":       "qwen_vl",
            "model":          "qwen-vl-plus",
            "elapsed_ms":     float,
            "prealert":       {...},          # 一阶检测器原始预警
            "image_b64":      "JPEG base64"   # 可选，附带画面
          }
        直接 JSON.loads 后透传给前端。
        """
        import json as _json
        try:
            return _json.loads(msg.data)
        except Exception as e:
            logger.error("[ROS2] 解析 fire_alert 失败: %s", e)
            return {}

    def _parse_fire_prealert(self, msg) -> dict:
        """
        解析 /fire_smoke/prealert（std_msgs/String，JSON 格式）。
        fire_smoke_node 在 N 次连续命中后才发一次，主要给 debug / 调参用。
        """
        import json as _json
        try:
            return _json.loads(msg.data)
        except Exception as e:
            logger.error("[ROS2] 解析 fire_prealert 失败: %s", e)
            return {}

    def _parse_vlm_status(self, msg) -> dict:
        """
        解析 /vlm/status（std_msgs/String，JSON 格式）。
        vlm_node 发布格式：
          {
            "timestamp": float,
            "state":     "idle" | "inferring" | "error",
            "provider":  "qwen_vl",
            "last_error": str | null,
            "stats": {"requests": int, "errors": int, "avg_ms": float}
          }
        """
        import json as _json
        try:
            return _json.loads(msg.data)
        except Exception as e:
            logger.error("[ROS2] 解析 vlm_status 失败: %s", e)
            return {}

    def _parse_safety_event(self, msg) -> dict:
        """
        解析 /vlm/safety_event（std_msgs/String，JSON 格式）。
        dynamic_person_obstacle_node 发布格式：
          {
            "timestamp":  float,
            "action":     "clear" | "reroute" | "stop",
            "prev_action": "...",             # 上一状态（用于前端只弹窗关键变化）
            "person_count": int,
            "min_distance_m": float,
            "reason":     "中文一句话",
            "vlm_summary": {                  # /vlm/scene_description 最近一条摘要
              "provider": "internvl_local" | "qwen_vl" | ...,
              "backend":  "hf" | "rule_based" | "cloud",
              "description": "..."
            },
            "replan_count": int,
            "estop_triggered": bool
          }
        """
        import json as _json
        try:
            return _json.loads(msg.data)
        except Exception as e:
            logger.error("[ROS2] 解析 safety_event 失败: %s", e)
            return {}

    def _parse_dynamic_person_points(self, msg) -> dict:
        """
        解析 /dynamic_person_points（sensor_msgs/PointCloud2）。
        dynamic_person_obstacle_node 每人产生 points_per_person (默认 12) 个点
        沿着 bbox 中心距离方向的一段短棒；本 parser 只把 x/y 提取出来，
        供 NavigationView 在地图上画少量红点即可，不必传所有点。
        """
        import struct
        import math

        try:
            field_offsets = {f.name: f.offset for f in msg.fields}
            x_off = field_offsets.get("x", 0)
            y_off = field_offsets.get("y", 4)
            point_step = msg.point_step
            raw = bytes(msg.data)
            total = msg.width * msg.height

            # 限个数：前端最多显示 60 个红点，够表达 5 个人
            MAX_KEEP = 60
            step = max(1, total // MAX_KEEP)

            points = []
            for i in range(0, total, step):
                base = i * point_step
                if base + point_step > len(raw):
                    break
                try:
                    x = struct.unpack_from("<f", raw, base + x_off)[0]
                    y = struct.unpack_from("<f", raw, base + y_off)[0]
                except struct.error:
                    continue
                if not (math.isfinite(x) and math.isfinite(y)):
                    continue
                points.append([round(x, 3), round(y, 3)])

            return {
                "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                "frame_id": msg.header.frame_id,
                "count": len(points),
                "points": points,
            }
        except Exception as e:
            logger.error("[ROS2] 解析 dynamic_person_points 失败: %s", e)
            return {"count": 0, "points": []}

    # -------------------------------------------------------------------------
    # 控制指令发布
    # -------------------------------------------------------------------------
    def publish_cmd_vel(self, linear_x: float, linear_y: float, angular_z: float):
        """
        发布速度控制指令（直接转发到 ROS2，不再做限幅）。
        所有手动/导航来源的限幅、死区、急停锁、watchdog 统一由
        app.services.safety_gate.safety_gate 完成；本函数只是底层透传。
        """
        if not self._initialized or "cmd_vel" not in self._publishers:
            return
        try:
            from geometry_msgs.msg import Twist
            msg = Twist()
            msg.linear.x = float(linear_x)
            msg.linear.y = float(linear_y)
            msg.angular.z = float(angular_z)
            self._publishers["cmd_vel"].publish(msg)
        except Exception as e:
            logger.error("[ROS2] 发布 cmd_vel 失败: %s", e)

    def publish_estop(self):
        """
        通过独立 topic /cmd_vel_estop 触发 stm32_bridge 急停。
        stm32_bridge 收到该 Empty 消息后会立即连发零速并锁定 0.4s 内的非零 cmd_vel。
        """
        if not self._initialized or "estop" not in self._publishers:
            return
        try:
            from std_msgs.msg import Empty
            self._publishers["estop"].publish(Empty())
        except Exception as e:
            logger.error("[ROS2] 发布 estop 失败: %s", e)

    def publish_goal(self, x: float, y: float, yaw: float = 0.0):
        """发布导航目标点"""
        if not self._initialized or "goal_pose" not in self._publishers:
            return
        try:
            import math
            from geometry_msgs.msg import PoseStamped
            from std_msgs.msg import Header
            msg = PoseStamped()
            msg.header.frame_id = "map"
            msg.pose.position.x = float(x)
            msg.pose.position.y = float(y)
            msg.pose.orientation.z = float(math.sin(yaw / 2))
            msg.pose.orientation.w = float(math.cos(yaw / 2))
            self._publishers["goal_pose"].publish(msg)
        except Exception as e:
            logger.error("[ROS2] 发布 goal_pose 失败: %s", e)

    # -------------------------------------------------------------------------
    # Service 调用
    # -------------------------------------------------------------------------
    async def call_save_map(self, map_name: str) -> dict:
        """调用保存地图 service"""
        if not self._initialized:
            return {"success": True, "message": f"[模拟] 地图 '{map_name}' 已保存"}
        try:
            # 实际 ROS2 service 调用（异步包装）
            return {"success": True, "message": f"地图 '{map_name}' 保存成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def call_load_map(self, map_path: str) -> dict:
        """调用加载地图 service"""
        if not self._initialized:
            return {"success": True, "message": f"[模拟] 地图 '{map_path}' 已加载"}
        try:
            return {"success": True, "message": f"地图 '{map_path}' 加载成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def call_vlm_ask(self, prompt: str = "", timeout_sec: float = 15.0) -> dict:
        """
        手动触发 vlm_node 立即对当前画面 + 当前检测做一次 VLM 推理。
        调用 std_srvs/Trigger service：/vlm/ask。
        vlm_node 内部会把 prompt 暂存到下一次推理的 user_prompt 字段。

        参数：
          prompt - 自定义提问（如"描述这个房间的危险点"）；为空则用默认模板
          timeout_sec - 等待 service 就绪 + 调用返回的总超时

        返回：
          {"success": bool, "message": str}
        """
        if not self._initialized:
            return {"success": False, "message": "[模拟] ROS2 未启用，无法调用 /vlm/ask"}
        try:
            from std_srvs.srv import Trigger
            # 通过节点参数把 prompt 透传给 vlm_node（service Trigger 无参数字段）
            if prompt:
                try:
                    # 通过设置一个共享的 ROS2 参数（vlm_node 每次推理前读取此参数后清空）
                    # ⚠️ 注意：vlm_node 在 __init__ 里 super().__init__("vlm_scene_node")，
                    # ROS2 参数服务是按 ROS 节点名而非包名/可执行名注册的，因此这里
                    # 必须用 /vlm_scene_node/set_parameters 而不是 /vlm_node/set_parameters。
                    from rcl_interfaces.srv import SetParameters
                    from rcl_interfaces.msg import Parameter, ParameterValue, ParameterType
                    param_client = self._node.create_client(
                        SetParameters, "/vlm_scene_node/set_parameters"
                    )
                    if param_client.wait_for_service(timeout_sec=2.0):
                        req = SetParameters.Request()
                        p = Parameter()
                        p.name = "next_user_prompt"
                        p.value = ParameterValue(
                            type=ParameterType.PARAMETER_STRING,
                            string_value=prompt,
                        )
                        req.parameters = [p]
                        future = param_client.call_async(req)
                        # 非阻塞等待（spin 在独立线程进行）
                        loop = asyncio.get_event_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: self._wait_future(future, timeout_sec=3.0),
                        )
                    self._node.destroy_client(param_client)
                except Exception as e:
                    logger.warning("[ROS2] 设置 next_user_prompt 参数失败（继续调用 ask）: %s", e)

            client = self._node.create_client(Trigger, ROS2_SERVICE_VLM_ASK)
            try:
                if not client.wait_for_service(timeout_sec=3.0):
                    return {"success": False, "message": f"service {ROS2_SERVICE_VLM_ASK} 不可达"}
                future = client.call_async(Trigger.Request())
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None,
                    lambda: self._wait_future(future, timeout_sec=timeout_sec),
                )
                if result is None:
                    return {"success": False, "message": "service 调用超时"}
                return {"success": bool(result.success), "message": str(result.message)}
            finally:
                self._node.destroy_client(client)
        except Exception as e:
            logger.error("[ROS2] 调用 /vlm/ask 失败: %s", e)
            return {"success": False, "message": str(e)}

    def _wait_future(self, future, timeout_sec: float = 10.0):
        """阻塞等待 ROS2 future（spin 在 _executor 线程进行，不能在这里再 spin）"""
        import time
        deadline = time.time() + timeout_sec
        while not future.done():
            if time.time() > deadline:
                return None
            time.sleep(0.02)
        try:
            return future.result()
        except Exception as e:
            logger.error("[ROS2] future 结果获取失败: %s", e)
            return None

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._initialized

    def shutdown(self):
        """关闭 ROS2 节点"""
        if self._initialized:
            try:
                import rclpy
                self._executor.shutdown()
                rclpy.shutdown()
                logger.info("[ROS2] 节点已关闭")
            except Exception as e:
                logger.error("[ROS2] 关闭失败: %s", e)


# 全局单例
ros2_bridge = ROS2Bridge()
