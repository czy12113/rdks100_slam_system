# =============================================================================
# 模拟数据生成器
# 硬件未就绪时提供仿真数据，保证前端可正常调试
# 所有数据格式与真实 ROS2 数据保持一致，切换时只需关闭 MOCK_MODE
# =============================================================================

import math
import random
import time
from typing import List, Dict, Any


class MockDataGenerator:
    """模拟数据生成器，所有方法返回与真实传感器相同格式的数据"""

    def __init__(self):
        self._start_time = time.time()
        self._robot_x: float = 0.0
        self._robot_y: float = 0.0
        self._robot_yaw: float = 0.0
        self._robot_vx: float = 0.0
        self._robot_vy: float = 0.0
        self._robot_wz: float = 0.0
        self._battery: float = 85.0
        self._imu_roll: float = 0.0
        self._imu_pitch: float = 0.0
        self._imu_yaw: float = 0.0
        self._slam_running: bool = False
        self._slam_algorithm: str = "cartographer"
        self._map_data: List[List[int]] = []
        self._trajectory: List[Dict] = []
        self._log_index: int = 0
        self._nav_active: bool = False
        self._nav_goal: Dict = {}

        # 预生成模拟地图（100x100 占用栅格）
        self._generate_mock_map()

    def _elapsed(self) -> float:
        return time.time() - self._start_time

    def _generate_mock_map(self):
        """生成一个简单的模拟占用栅格地图"""
        size = 100
        self._map_data = [[0] * size for _ in range(size)]
        # 外墙
        for i in range(size):
            self._map_data[0][i] = 100
            self._map_data[size - 1][i] = 100
            self._map_data[i][0] = 100
            self._map_data[i][size - 1] = 100
        # 内部障碍物
        obstacles = [
            (20, 20, 5, 15), (60, 10, 8, 5), (30, 60, 3, 20),
            (70, 50, 10, 3), (15, 80, 20, 4), (80, 75, 5, 12),
        ]
        for ox, oy, w, h in obstacles:
            for dy in range(h):
                for dx in range(w):
                    nx, ny = ox + dx, oy + dy
                    if 0 < nx < size and 0 < ny < size:
                        self._map_data[ny][nx] = 100
        # 未知区域（-1 -> 用 255 表示）
        for y in range(40, 60):
            for x in range(40, 60):
                self._map_data[y][x] = -1

    # -------------------------------------------------------------------------
    # 系统信息
    # -------------------------------------------------------------------------
    def get_system_info(self) -> Dict[str, Any]:
        t = self._elapsed()
        cpu_base = 35.0 + 15.0 * math.sin(t * 0.1)
        return {
            "timestamp": time.time(),
            "cpu": {
                "usage": round(cpu_base + random.uniform(-3, 3), 1),
                "cores": [
                    round(cpu_base + random.uniform(-10, 10), 1)
                    for _ in range(8)
                ],
                "frequency": round(1800 + random.uniform(-100, 200), 0),
            },
            "memory": {
                "total": 8192,
                "used": round(3200 + 200 * math.sin(t * 0.05) + random.uniform(-50, 50), 0),
                "percent": round(40.0 + 5.0 * math.sin(t * 0.05) + random.uniform(-1, 1), 1),
            },
            "temperature": {
                "cpu": round(52.0 + 8.0 * math.sin(t * 0.08) + random.uniform(-1, 1), 1),
                "board": round(45.0 + 5.0 * math.sin(t * 0.06) + random.uniform(-1, 1), 1),
                "bpu": round(48.0 + 6.0 * math.sin(t * 0.07) + random.uniform(-1, 1), 1),
            },
            "network": {
                "interface": "eth0",
                "ip": "10.21.1.145",
                "rx_bytes": int(1024 * 1024 * (10 + t * 0.5)),
                "tx_bytes": int(1024 * 512 * (5 + t * 0.2)),
                "rx_rate": round(random.uniform(100, 500), 1),
                "tx_rate": round(random.uniform(50, 200), 1),
                "connected": True,
            },
            "disk": {
                "total": 32768,
                "used": 12800,
                "percent": 39.1,
            },
            "uptime": int(t),
        }

    # -------------------------------------------------------------------------
    # 机器人状态
    # -------------------------------------------------------------------------
    def get_robot_status(self) -> Dict[str, Any]:
        t = self._elapsed()
        # 模拟机器人缓慢移动
        self._robot_x += self._robot_vx * 0.1
        self._robot_y += self._robot_vy * 0.1
        self._robot_yaw += self._robot_wz * 0.1
        # 电量缓慢下降
        self._battery = max(0.0, self._battery - 0.001)

        return {
            "timestamp": time.time(),
            "online": True,
            "name": "RDK-S100-001",
            "mode": "manual",
            "battery": {
                "percent": round(self._battery, 1),
                "voltage": round(11.1 + (self._battery / 100) * 1.5, 2),
                "current": round(random.uniform(0.5, 2.0), 2),
                "charging": False,
            },
            "pose": {
                "x": round(self._robot_x, 3),
                "y": round(self._robot_y, 3),
                "z": 0.0,
                "roll": round(self._imu_roll, 4),
                "pitch": round(self._imu_pitch, 4),
                "yaw": round(self._robot_yaw, 4),
            },
            "velocity": {
                "linear_x": round(self._robot_vx, 3),
                "linear_y": round(self._robot_vy, 3),
                "angular_z": round(self._robot_wz, 3),
            },
            "odometry": {
                "distance": round(math.sqrt(self._robot_x**2 + self._robot_y**2), 3),
                "total_distance": round(abs(self._robot_x) + abs(self._robot_y) + t * 0.01, 2),
            },
            "emergency_stop": False,
            "errors": [],
        }

    def set_velocity(self, linear_x: float, linear_y: float, angular_z: float):
        """设置机器人速度（模拟控制）"""
        self._robot_vx = linear_x
        self._robot_vy = linear_y
        self._robot_wz = angular_z

    def emergency_stop(self):
        """急停"""
        self._robot_vx = 0.0
        self._robot_vy = 0.0
        self._robot_wz = 0.0

    # -------------------------------------------------------------------------
    # 激光雷达数据（3D，Livox Mid-360S 模拟）
    # -------------------------------------------------------------------------
    def get_lidar3d_scan(self) -> Dict[str, Any]:
        """
        模拟 Livox Mid-360S 3D 点云数据
        输出格式与 _parse_pointcloud2 一致：[[x, y, z, intensity], ...]
        模拟场景：地面 + 四周墙壁 + 几个障碍物柱体
        约 2000 个点，覆盖 360° 水平 + 多层垂直扫描
        """
        t = self._elapsed()
        points = []
        distances = []

        # 水平层数（模拟 Livox 非重复扫描的多层效果）
        # 垂直角度范围：-7° ~ +52°（Mid-360S 规格）
        v_angles_deg = [-7, -3, 0, 3, 7, 12, 18, 25, 35, 45, 52]
        h_steps = 180  # 每层水平采样数

        # 障碍物：(中心角度rad, 距离m, 半径m, 高度m)
        obstacles = [
            (0.5,  1.2, 0.15, 1.5),
            (1.8,  2.0, 0.20, 1.2),
            (3.5,  1.5, 0.15, 1.8),
            (5.0,  1.8, 0.18, 1.0),
            (2.8,  3.0, 0.25, 2.0),
        ]

        for v_deg in v_angles_deg:
            v_rad = math.radians(v_deg)
            cos_v = math.cos(v_rad)
            sin_v = math.sin(v_rad)

            for hi in range(h_steps):
                h_rad = hi * (2 * math.pi / h_steps) + t * 0.05  # 缓慢旋转模拟非重复扫描

                # 基础距离（模拟墙壁）
                base_r = 4.0 + 1.5 * math.sin(h_rad * 2 + t * 0.3)
                noise = random.uniform(-0.03, 0.03)

                # 检查是否命中障碍物
                hit_r = base_r + noise
                for obs_h, obs_d, obs_radius, obs_height in obstacles:
                    angle_diff = abs((h_rad - obs_h + math.pi) % (2 * math.pi) - math.pi)
                    if angle_diff < obs_radius / obs_d:
                        # 命中障碍物，计算实际距离
                        candidate = obs_d + random.uniform(-0.02, 0.02)
                        # 只有在障碍物高度范围内才命中
                        z_at_candidate = candidate * sin_v
                        if -0.05 <= z_at_candidate <= obs_height:
                            hit_r = min(hit_r, candidate)

                # 地面点（v_deg < 0 时会扫到地面）
                if v_deg < 0 and cos_v > 0:
                    ground_r = abs(-0.3 / sin_v) if sin_v < 0 else hit_r  # 传感器高度约 0.3m
                    hit_r = min(hit_r, ground_r)

                # 过滤超出量程的点
                if hit_r > 20.0 or hit_r < 0.05:
                    continue

                x = round(hit_r * cos_v * math.cos(h_rad), 3)
                y = round(hit_r * cos_v * math.sin(h_rad), 3)
                z = round(hit_r * sin_v, 3)
                intensity = round(random.uniform(50, 200), 1)

                points.append([x, y, z, intensity])
                distances.append(math.sqrt(x * x + y * y))

        z_vals = [p[2] for p in points]
        return {
            "timestamp": time.time(),
            "frame_id": "livox_frame",
            "points": points,
            "point_count": len(points),
            "total_points": len(points),
            "min_distance": round(min(distances, default=0.0), 3),
            "range_max": round(max(distances, default=0.0), 1),
            "z_min": round(min(z_vals, default=0.0), 3),
            "z_max": round(max(z_vals, default=0.0), 3),
            "obstacle_count": sum(1 for d in distances if d < 2.0),
            "is_3d": True,
        }

    def get_lidar_scan(self) -> Dict[str, Any]:
        """保留 2D 激光雷达模拟（兼容旧版本）"""
        t = self._elapsed()
        num_points = 360
        angles = [i * (2 * math.pi / num_points) for i in range(num_points)]
        ranges = []
        for a in angles:
            base_range = 3.0 + 1.5 * math.sin(a * 3 + t * 0.5)
            noise = random.uniform(-0.05, 0.05)
            obstacle_dist = 10.0
            for obs_angle, obs_dist in [(0.5, 1.2), (1.8, 2.0), (3.5, 1.5), (5.0, 1.8)]:
                if abs(a - obs_angle) < 0.1:
                    obstacle_dist = min(obstacle_dist, obs_dist + random.uniform(-0.02, 0.02))
            r = min(base_range + noise, obstacle_dist)
            ranges.append(round(max(0.1, min(r, 12.0)), 3))

        points = []
        for i, (a, r) in enumerate(zip(angles, ranges)):
            if r < 12.0:
                points.append({
                    "x": round(r * math.cos(a), 3),
                    "y": round(r * math.sin(a), 3),
                    "r": r,
                    "a": round(math.degrees(a), 1),
                })

        return {
            "timestamp": time.time(),
            "angle_min": -math.pi,
            "angle_max": math.pi,
            "angle_increment": 2 * math.pi / num_points,
            "range_min": 0.1,
            "range_max": 12.0,
            "ranges": ranges,
            "points": points,
            "obstacle_count": sum(1 for r in ranges if r < 2.0),
            "min_distance": round(min(ranges), 3),
            "is_3d": False,
        }

    # -------------------------------------------------------------------------
    # IMU 数据
    # -------------------------------------------------------------------------
    def get_imu_data(self) -> Dict[str, Any]:
        t = self._elapsed()
        self._imu_roll = 0.05 * math.sin(t * 0.3) + random.uniform(-0.002, 0.002)
        self._imu_pitch = 0.03 * math.cos(t * 0.2) + random.uniform(-0.002, 0.002)
        self._imu_yaw += self._robot_wz * 0.05 + random.uniform(-0.001, 0.001)

        return {
            "timestamp": time.time(),
            "orientation": {
                "roll": round(math.degrees(self._imu_roll), 3),
                "pitch": round(math.degrees(self._imu_pitch), 3),
                "yaw": round(math.degrees(self._imu_yaw), 3),
                "quaternion": {
                    "x": round(math.sin(self._imu_roll / 2), 6),
                    "y": round(math.sin(self._imu_pitch / 2), 6),
                    "z": round(math.sin(self._imu_yaw / 2), 6),
                    "w": round(math.cos(self._imu_yaw / 2), 6),
                },
            },
            "angular_velocity": {
                "x": round(self._robot_wz * 0.1 + random.uniform(-0.01, 0.01), 4),
                "y": round(random.uniform(-0.005, 0.005), 4),
                "z": round(self._robot_wz + random.uniform(-0.01, 0.01), 4),
            },
            "linear_acceleration": {
                "x": round(self._robot_vx * 0.5 + random.uniform(-0.05, 0.05), 4),
                "y": round(self._robot_vy * 0.5 + random.uniform(-0.05, 0.05), 4),
                "z": round(9.81 + random.uniform(-0.02, 0.02), 4),
            },
            "temperature": round(35.0 + random.uniform(-0.5, 0.5), 1),
        }

    # -------------------------------------------------------------------------
    # SLAM 数据
    # -------------------------------------------------------------------------
    def get_slam_status(self) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "running": self._slam_running,
            "algorithm": self._slam_algorithm,
            "map_ready": self._slam_running,
            "pose": {
                "x": round(self._robot_x, 3),
                "y": round(self._robot_y, 3),
                "yaw": round(self._robot_yaw, 3),
            },
            "trajectory_length": len(self._trajectory),
            "map_info": {
                "width": 100,
                "height": 100,
                "resolution": 0.05,
                "origin_x": -2.5,
                "origin_y": -2.5,
            },
        }

    def get_slam_map(self) -> Dict[str, Any]:
        """返回 SLAM 地图数据"""
        if self._slam_running:
            # 动态更新轨迹
            self._trajectory.append({
                "x": round(self._robot_x, 3),
                "y": round(self._robot_y, 3),
            })
            if len(self._trajectory) > 500:
                self._trajectory = self._trajectory[-500:]

        return {
            "timestamp": time.time(),
            "width": 100,
            "height": 100,
            "resolution": 0.05,
            "origin": {"x": -2.5, "y": -2.5},
            "data": self._map_data,
            "robot_pose": {
                "x": round(self._robot_x, 3),
                "y": round(self._robot_y, 3),
                "yaw": round(self._robot_yaw, 3),
            },
            "trajectory": self._trajectory[-100:],  # 只传最近100个点
        }

    def start_slam(self, algorithm: str = "cartographer"):
        self._slam_running = True
        self._slam_algorithm = algorithm
        self._trajectory = []

    def stop_slam(self):
        self._slam_running = False

    # -------------------------------------------------------------------------
    # 导航数据
    # -------------------------------------------------------------------------
    def get_navigation_status(self) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "active": self._nav_active,
            "goal": self._nav_goal,
            "status": "idle" if not self._nav_active else "navigating",
            "distance_to_goal": round(random.uniform(0.5, 3.0), 2) if self._nav_active else 0.0,
            "path_points": [],
            "algorithm": "nav2_default",
        }

    def set_nav_goal(self, x: float, y: float, yaw: float = 0.0):
        self._nav_active = True
        self._nav_goal = {"x": x, "y": y, "yaw": yaw}

    def cancel_navigation(self):
        self._nav_active = False
        self._nav_goal = {}

    # -------------------------------------------------------------------------
    # 日志数据
    # -------------------------------------------------------------------------
    _LOG_TEMPLATES = [
        ("[INFO] [slam_node] 地图更新完成，分辨率: 0.05m", "info"),
        ("[INFO] [lidar_driver] 激光雷达数据正常，点数: 360", "info"),
        ("[INFO] [imu_driver] IMU 校准完成", "info"),
        ("[WARN] [battery_monitor] 电池电量低于 20%，请及时充电", "warn"),
        ("[INFO] [nav2] 路径规划完成，距离: 2.34m", "info"),
        ("[INFO] [camera_driver] 深度相机连接正常", "info"),
        ("[DEBUG] [robot_controller] 速度指令: vx=0.3, wz=0.0", "debug"),
        ("[INFO] [slam_node] 检测到回环，优化位姿图", "info"),
        ("[WARN] [lidar_driver] 激光雷达信号弱，请检查环境", "warn"),
        ("[INFO] [system_monitor] CPU 温度: 52°C，状态正常", "info"),
        ("[ERROR] [nav2] 路径规划失败，目标点不可达", "error"),
        ("[INFO] [robot_controller] 急停指令已执行", "info"),
    ]

    def get_log_entry(self) -> Dict[str, Any]:
        self._log_index = (self._log_index + 1) % len(self._LOG_TEMPLATES)
        msg, level = self._LOG_TEMPLATES[self._log_index]
        return {
            "timestamp": time.time(),
            "level": level,
            "message": msg,
            "source": "mock",
        }

    # -------------------------------------------------------------------------
    # 设备状态
    # -------------------------------------------------------------------------
    def get_device_status(self) -> Dict[str, Any]:
        return {
            "timestamp": time.time(),
            "devices": {
                "lidar": {
                    "name": "LD LiDAR",
                    "connected": True,
                    "status": "normal",
                    "topic": "/scan",
                    "frequency": round(10.0 + random.uniform(-0.5, 0.5), 1),
                },
                "camera": {
                    "name": "RealSense D435",
                    "connected": True,
                    "status": "normal",
                    "topic": "/camera/camera/color/image_raw",
                    "resolution": "640x480",
                    "fps": 30,
                },
                "imu": {
                    "name": "BMI088",
                    "connected": True,
                    "status": "normal",
                    "topic": "/imu/data",
                    "frequency": 200,
                },
                "motor": {
                    "name": "驱动电机",
                    "connected": True,
                    "status": "normal",
                    "left_rpm": round(random.uniform(-10, 10), 1),
                    "right_rpm": round(random.uniform(-10, 10), 1),
                },
            }
        }


# 全局单例
mock_generator = MockDataGenerator()
