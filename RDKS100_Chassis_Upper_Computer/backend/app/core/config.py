# =============================================================================
# RDK S100 智能机器人上位机系统 - 全局配置（宏定义）
# 所有可变参数集中在此文件，方便后续按需修改
# =============================================================================

from typing import List
import os

# -----------------------------------------------------------------------------
# 设备基础配置
# -----------------------------------------------------------------------------
DEVICE_HOST: str = os.getenv("DEVICE_HOST", "0.0.0.0")   # 后端监听地址，0.0.0.0 表示监听所有网卡
DEVICE_PORT: int = int(os.getenv("DEVICE_PORT", "8000"))  # 后端服务端口
DEVICE_NAME: str = "RDK S100 智能机器人"                   # 设备名称
DEVICE_VERSION: str = "1.0.0"                              # 系统版本

# -----------------------------------------------------------------------------
# CORS 跨域配置（前端开发时需要）
# -----------------------------------------------------------------------------
CORS_ORIGINS: List[str] = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "*",  # 局域网访问，生产环境可改为具体IP段
]

# -----------------------------------------------------------------------------
# WebSocket 配置
# -----------------------------------------------------------------------------
WS_HEARTBEAT_INTERVAL: float = 5.0    # WebSocket 心跳间隔（秒）
WS_MAX_CONNECTIONS: int = 50           # 最大 WebSocket 连接数
WS_MESSAGE_QUEUE_SIZE: int = 100       # 消息队列大小

# -----------------------------------------------------------------------------
# 数据推送频率配置（Hz -> 秒间隔）
#
# ⚠️ 重型 topic（lidar/video/imu）的频率直接影响 WebSocket 带宽和前端解析负担。
#    点云已从 10Hz/10000 点 → 5Hz/5000 点。
#    视频推送改为"事件驱动 + 短 sleep 轮询 + timestamp 去重"策略：
#      - PUSH_RATE_VIDEO 现在作为"上限节流"，即两帧之间最少间隔
#        （0.033s ≈ 30fps，与 RealSense 原生帧率对齐）
#      - PUSH_VIDEO_POLL 是轮询新帧的短间隔（比 30fps 更快，保证不漏帧）
#    如果设备性能富余且前端不卡，可逐步调高。
# -----------------------------------------------------------------------------
PUSH_RATE_SYSTEM_INFO: float = 1.0     # 系统信息推送间隔（秒）
PUSH_RATE_ROBOT_STATUS: float = 0.1    # 机器人状态推送间隔（秒，10Hz）
PUSH_RATE_LIDAR: float = 0.2           # 激光雷达数据推送间隔（秒，5Hz）
PUSH_RATE_IMU: float = 0.05            # IMU 数据推送间隔（秒，20Hz）
PUSH_RATE_SLAM_MAP: float = 0.5        # SLAM 地图推送间隔（秒，2Hz）
PUSH_RATE_VIDEO: float = 0.033         # 视频帧推送上限节流（秒，~30fps）
PUSH_VIDEO_POLL: float = 0.008         # 视频帧轮询间隔（秒，125Hz 轮询，> 帧率保证不漏帧）
PUSH_RATE_LOG: float = 0.5             # 日志推送间隔（秒）

# 点云降采样上限：每帧最多发送给前端的点数（19968 点 → 5000 点约 25%）
LIDAR_MAX_PUSH_POINTS: int = 5000

# -----------------------------------------------------------------------------
# ROS2 配置
# -----------------------------------------------------------------------------
# ROS2_ENABLED 默认 true：只要 rclpy 可导入就启用真实数据；
# 若 rclpy 不存在，ros2_bridge 内部会自动捕获 ImportError 并降级为模拟模式。
# 如需强制模拟模式，设置环境变量 ROS2_ENABLED=false
ROS2_ENABLED: bool = os.getenv("ROS2_ENABLED", "true").lower() == "true"
ROS2_DOMAIN_ID: int = int(os.getenv("ROS_DOMAIN_ID", "0"))

# ROS2 Topic 名称（标准命名，可按实际修改）
ROS2_TOPIC_CMD_VEL: str = "/cmd_vel"                        # 速度控制
ROS2_TOPIC_ODOM: str = "/odom"                              # 里程计
ROS2_TOPIC_SCAN: str = "/scan"                              # 2D 激光雷达扫描（已弃用，保留兼容）
ROS2_TOPIC_LIDAR3D: str = "/livox/lidar"                    # 3D 激光雷达点云（Livox Mid-360S）
ROS2_TOPIC_IMU: str = "/livox/imu"                          # IMU 数据（Livox 内置 IMU）
ROS2_TOPIC_MAP: str = "/map"                                # SLAM 地图
ROS2_TOPIC_POSE: str = "/robot_pose"                        # 机器人位姿
ROS2_TOPIC_BATTERY: str = "/battery_state"                  # 电池状态
ROS2_TOPIC_RGB_IMAGE: str = "/camera/camera/color/image_raw"       # RGB 图像（RealSense 实际 topic）
ROS2_TOPIC_DEPTH_IMAGE: str = "/camera/camera/aligned_depth_to_color/image_raw"  # 对齐到 RGB 的深度图像
ROS2_TOPIC_ANNOTATED_IMAGE: str = "/detection/annotated_image"   # 带检测框+距离标注的 RGB 图像（BGR8）
ROS2_TOPIC_DETECTION_RESULTS: str = "/detection/results"          # YOLO 检测结果 JSON（std_msgs/String）
ROS2_TOPIC_CAMERA_INFO: str = "/camera/camera/color/camera_info"   # 相机信息
ROS2_TOPIC_POINTCLOUD: str = "/livox/lidar"                 # 3D 点云数据（与 LIDAR3D 同源）
ROS2_TOPIC_SLAM_POSE: str = "/slam/pose"                    # SLAM 位姿
ROS2_TOPIC_PATH: str = "/plan"                              # 规划路径
ROS2_TOPIC_GOAL: str = "/goal_pose"                         # 导航目标点
ROS2_TOPIC_DIAGNOSTICS: str = "/diagnostics"                # 诊断信息

# ── VLM 场景理解（vlm_scene 节点）─────────────────────────────────────────────
# vlm_node 接收检测框 + 关键帧，调用通义千问 VL（或其它 provider）输出自然语言。
# backend 仅订阅这两个 topic 做转发，不会自己再发起 VLM 请求，避免 RDK 算力浪费。
ROS2_TOPIC_VLM_DESCRIPTION: str = "/vlm/scene_description"
ROS2_TOPIC_VLM_STATUS: str = "/vlm/status"
ROS2_SERVICE_VLM_ASK: str = "/vlm/ask"

# ── 火警告警（fire_smoke_node + vlm_node 协同） ─────────────────────────────
# fire_smoke_node 用 YOLOv5 做一阶火/烟检测 → /fire_smoke/prealert
# vlm_node 二次确认 → /alert/fire（严格 JSON：level/fire_detected/...）
# backend 仅订阅 /alert/fire 并直接 WS 转发给前端。
ROS2_TOPIC_FIRE_ALERT: str = "/alert/fire"
ROS2_TOPIC_FIRE_PREALERT: str = "/fire_smoke/prealert"     # 可选订阅（debug 用）
ROS2_TOPIC_FIRE_RESULTS: str = "/fire_smoke/results"       # 可选订阅（每帧检测结果，debug 用）

# ── 动态行人安全事件（创新点：本地 VLM + Nav2 联合决策）─────────────────────
# dynamic_person_obstacle_node 每次做出 stop / reroute / clear 决策时，
# 会发布结构化 JSON 到 /vlm/safety_event，供前端弹窗、图标闪烁、状态显示。
# 前端 NavigationView 还会订阅 /dynamic_person_points（可视化红点）。
ROS2_TOPIC_SAFETY_EVENT: str = "/vlm/safety_event"
ROS2_TOPIC_DYNAMIC_PERSON_POINTS: str = "/dynamic_person_points"

# ROS2 Service 名称
ROS2_SERVICE_SAVE_MAP: str = "/slam/save_map"               # 保存地图
ROS2_SERVICE_LOAD_MAP: str = "/map_server/load_map"         # 加载地图
ROS2_SERVICE_START_SLAM: str = "/slam/start"                # 启动 SLAM
ROS2_SERVICE_STOP_SLAM: str = "/slam/stop"                  # 停止 SLAM
ROS2_SERVICE_CLEAR_COSTMAP: str = "/clear_costmaps"         # 清除代价地图

# -----------------------------------------------------------------------------
# 机器人运动参数
# 数值与 STM32 USER/ChassisParams.h 一致：
#   MAX_LINEAR_SPEED  = 0.60 m/s
#   MAX_ANGULAR_SPEED = 1.20 rad/s
#   LINEAR_DEADBAND   = 0.02 m/s
#   ANGULAR_DEADBAND  = 0.03 rad/s
# 上位机的死区取得比下位机更小（ROBOT_LINEAR_DEADBAND/ROBOT_ANGULAR_DEADBAND），
# 让 STM32 做最终判定，避免 RDK 把"非零但很小"的指令长期发给电机引起抖动。
# -----------------------------------------------------------------------------
ROBOT_MAX_LINEAR_VEL: float = float(os.getenv("ROBOT_MAX_LINEAR_VEL", "0.60"))
ROBOT_MAX_ANGULAR_VEL: float = float(os.getenv("ROBOT_MAX_ANGULAR_VEL", "1.20"))
ROBOT_DEFAULT_LINEAR_VEL: float = float(os.getenv("ROBOT_DEFAULT_LINEAR_VEL", "0.25"))
ROBOT_DEFAULT_ANGULAR_VEL: float = float(os.getenv("ROBOT_DEFAULT_ANGULAR_VEL", "0.50"))
ROBOT_LINEAR_DEADBAND: float = float(os.getenv("ROBOT_LINEAR_DEADBAND", "0.005"))
ROBOT_ANGULAR_DEADBAND: float = float(os.getenv("ROBOT_ANGULAR_DEADBAND", "0.010"))
ROBOT_EMERGENCY_STOP_DECEL: float = 2.0  # 急停减速度（m/s²，仅用于显示）
# 急停锁定时长（s）：触发急停后，本时长内忽略任何非零速请求
ROBOT_ESTOP_LOCK_SECONDS: float = float(os.getenv("ROBOT_ESTOP_LOCK_SECONDS", "0.5"))
# 后端 watchdog：超过此时长未收到任何手动 cmd_vel/estop 调用，主动把零速发到 ROS2
ROBOT_CMD_WATCHDOG_SECONDS: float = float(os.getenv("ROBOT_CMD_WATCHDOG_SECONDS", "0.4"))

# -----------------------------------------------------------------------------
# 激光雷达配置
# -----------------------------------------------------------------------------
LIDAR_MAX_RANGE: float = 12.0          # 最大测距范围（米）
LIDAR_MIN_RANGE: float = 0.1           # 最小测距范围（米）
LIDAR_ANGLE_MIN: float = -3.14159      # 最小角度（rad）
LIDAR_ANGLE_MAX: float = 3.14159       # 最大角度（rad）
LIDAR_POINTS_PER_SCAN: int = 360       # 每圈点数
# 激光雷达安装俯仰角（度）：水平安装为 0.0；前倾为负值，后仰为正值
# 默认按水平安装处理，不对前端点云做额外俯仰补偿
LIDAR_MOUNT_PITCH_DEG: float = float(os.getenv("LIDAR_MOUNT_PITCH_DEG", "0.0"))

# -----------------------------------------------------------------------------
# 相机配置
# -----------------------------------------------------------------------------
CAMERA_RGB_WIDTH: int = 640            # RGB 图像宽度
CAMERA_RGB_HEIGHT: int = 480           # RGB 图像高度
CAMERA_DEPTH_WIDTH: int = 640          # 深度图像宽度
CAMERA_DEPTH_HEIGHT: int = 480         # 深度图像高度
CAMERA_FPS: int = 30                   # 帧率
CAMERA_JPEG_QUALITY: int = 80          # JPEG 压缩质量（0-100）

# -----------------------------------------------------------------------------
# IMU 配置
# -----------------------------------------------------------------------------
IMU_SAMPLE_RATE: int = 200             # IMU 采样率（Hz）
IMU_ACCEL_RANGE: float = 16.0          # 加速度计量程（g）
IMU_GYRO_RANGE: float = 2000.0         # 陀螺仪量程（°/s）

# -----------------------------------------------------------------------------
# SLAM 配置
# -----------------------------------------------------------------------------
SLAM_ALGORITHMS: list = [
    "cartographer",   # Google Cartographer（激光SLAM）
    "rtab_map",       # RTAB-Map（视觉/融合SLAM）
    "orb_slam3",      # ORB-SLAM3（视觉SLAM）
    "lego_loam",      # LeGO-LOAM（激光SLAM）
    "lio_sam",        # LIO-SAM（融合SLAM）
]
SLAM_DEFAULT_ALGORITHM: str = "cartographer"
# 地图保存路径：save_map.sh 会把 pgm/yaml 落到 ~/rdks100_slam/my_map/
# 允许通过环境变量覆盖，便于开发机（kkk）与部署机（sunrise）共用一份代码
SLAM_MAP_SAVE_PATH: str = os.getenv(
    "SLAM_MAP_SAVE_PATH",
    os.path.expanduser("~/rdks100_slam/my_map"),
)
# 障碍物标注文件后缀（与地图同名 + .annotations.json）
SLAM_MAP_ANNOTATION_SUFFIX: str = ".annotations.json"
SLAM_MAP_RESOLUTION: float = 0.05       # 地图分辨率（米/像素）
SLAM_MAP_MAX_SIZE: int = 1000           # 地图最大尺寸（像素）

# -----------------------------------------------------------------------------
# 导航配置
# -----------------------------------------------------------------------------
NAV_ALGORITHMS: list = [
    "nav2_default",   # Nav2 默认
    "a_star",         # A* 算法
    "rrt",            # RRT 算法
    "dwa",            # DWA 局部规划
    "teb",            # TEB 局部规划
]
NAV_DEFAULT_ALGORITHM: str = "nav2_default"
NAV_GOAL_TOLERANCE: float = 0.1        # 到达目标点容差（米）
NAV_WAYPOINT_TOLERANCE: float = 0.2    # 途经点容差（米）

# -----------------------------------------------------------------------------
# 系统监控配置
# -----------------------------------------------------------------------------
SYS_CPU_WARN_THRESHOLD: float = 80.0   # CPU 使用率警告阈值（%）
SYS_MEM_WARN_THRESHOLD: float = 85.0   # 内存使用率警告阈值（%）
SYS_TEMP_WARN_THRESHOLD: float = 75.0  # 温度警告阈值（°C）
SYS_TEMP_CRITICAL_THRESHOLD: float = 90.0  # 温度危险阈值（°C）
SYS_BATTERY_WARN_THRESHOLD: float = 20.0   # 电池电量警告阈值（%）
SYS_BATTERY_CRITICAL_THRESHOLD: float = 10.0  # 电池电量危险阈值（%）

# -----------------------------------------------------------------------------
# 日志配置
# -----------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_LINES: int = 500               # 前端日志最大显示行数
LOG_FILE_PATH: str = "/home/sunrise/logs/rdks100_webui.log"  # 日志文件路径

# -----------------------------------------------------------------------------
# 模拟数据配置（硬件未就绪时使用）
# -----------------------------------------------------------------------------
MOCK_MODE: bool = os.getenv("MOCK_MODE", "true").lower() == "true"  # 模拟模式开关
MOCK_ROBOT_NAME: str = "RDK-S100-001"
