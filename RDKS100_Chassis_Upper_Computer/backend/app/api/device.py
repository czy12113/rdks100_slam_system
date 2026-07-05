# =============================================================================
# API 路由：设备管理与参数配置
# =============================================================================

import json
import os
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict
from app.core.config import (
    MOCK_MODE, ROS2_ENABLED, DEVICE_NAME, DEVICE_VERSION,
    CAMERA_RGB_WIDTH, CAMERA_RGB_HEIGHT, CAMERA_FPS, CAMERA_JPEG_QUALITY,
    LIDAR_MAX_RANGE, LIDAR_MIN_RANGE, LIDAR_POINTS_PER_SCAN, LIDAR_MOUNT_PITCH_DEG,
    IMU_SAMPLE_RATE, IMU_ACCEL_RANGE, IMU_GYRO_RANGE,
    ROS2_TOPIC_LIDAR3D, ROS2_TOPIC_IMU,
)
from app.services.mock_data import mock_generator

router = APIRouter(prefix="/api/device", tags=["device"])

# 参数配置文件路径（持久化存储）
_CONFIG_FILE = os.path.join(os.path.dirname(__file__), "../../config_runtime.json")

# 运行时参数缓存（内存）
_runtime_config: Dict[str, Any] = {}


def _load_runtime_config() -> Dict[str, Any]:
    global _runtime_config
    if os.path.exists(_CONFIG_FILE):
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                _runtime_config = json.load(f)
        except Exception:
            _runtime_config = {}
    return _runtime_config


def _save_runtime_config(cfg: Dict[str, Any]):
    global _runtime_config
    _runtime_config.update(cfg)
    try:
        os.makedirs(os.path.dirname(_CONFIG_FILE), exist_ok=True)
        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(_runtime_config, f, ensure_ascii=False, indent=2)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"配置保存失败: {e}")


# 初始化加载
_load_runtime_config()


class DeviceConfigUpdate(BaseModel):
    config: Dict[str, Any] = Field(..., description="要更新的配置键值对")


@router.get("/info", summary="获取设备基本信息")
async def get_device_info():
    return {
        "name": DEVICE_NAME,
        "version": DEVICE_VERSION,
        "mock_mode": MOCK_MODE,
        "ros2_enabled": ROS2_ENABLED,
        "platform": "RDK S100",
        "cpu": "Cortex-A78AE + R52 + BPU",
        "os": "Ubuntu 22.04 (RDK Linux)",
    }


@router.get("/status", summary="获取所有设备状态")
async def get_device_status():
    return mock_generator.get_device_status()


@router.get("/config", summary="获取当前运行时配置")
async def get_config():
    default_cfg = {
        "camera": {
            "rgb_width": CAMERA_RGB_WIDTH,
            "rgb_height": CAMERA_RGB_HEIGHT,
            "fps": CAMERA_FPS,
            "jpeg_quality": CAMERA_JPEG_QUALITY,
        },
        "lidar": {
            "max_range": LIDAR_MAX_RANGE,
            "min_range": LIDAR_MIN_RANGE,
            "points_per_scan": LIDAR_POINTS_PER_SCAN,
            # 安装俯仰角（度）：水平安装为 0，前倾为负，后仰为正
            # 默认水平安装，不对原始点云做额外俯仰补偿
            "mount_pitch": LIDAR_MOUNT_PITCH_DEG,
        },
        "imu": {
            "sample_rate": IMU_SAMPLE_RATE,
            "accel_range": IMU_ACCEL_RANGE,
            "gyro_range": IMU_GYRO_RANGE,
        },
    }
    # 合并运行时覆盖配置
    merged = {**default_cfg, **_runtime_config}
    return merged


@router.post("/config", summary="更新运行时配置")
async def update_config(body: DeviceConfigUpdate):
    _save_runtime_config(body.config)
    return {"success": True, "message": "配置已保存", "updated": body.config}


@router.post("/config/reset", summary="重置为默认配置")
async def reset_config():
    global _runtime_config
    _runtime_config = {}
    if os.path.exists(_CONFIG_FILE):
        os.remove(_CONFIG_FILE)
    return {"success": True, "message": "配置已重置为默认值"}


@router.get("/sensors", summary="获取传感器详细状态")
async def get_sensors():
    """
    获取传感器状态。
    ROS2 已启用时，根据 bridge 订阅者和最新数据判断真实在线状态；
    否则返回模拟数据。
    """
    from app.services.ros2_bridge import ros2_bridge

    mock_status = mock_generator.get_device_status()
    devices = mock_status["devices"]

    if ros2_bridge.is_enabled:
        # 激光雷达：有 lidar3d 订阅者且收到数据
        lidar_data = ros2_bridge.get_latest("lidar3d")
        devices["lidar"]["connected"] = lidar_data is not None
        devices["lidar"]["status"] = "normal" if lidar_data is not None else "offline"
        devices["lidar"]["topic"] = "/livox/lidar"
        devices["lidar"]["name"] = "Livox Mid-360S"

        # IMU：有 imu 订阅者且收到数据
        imu_data = ros2_bridge.get_latest("imu")
        devices["imu"]["connected"] = imu_data is not None
        devices["imu"]["status"] = "normal" if imu_data is not None else "offline"
        devices["imu"]["topic"] = "/livox/imu"

        # 里程计：有 odom 数据
        odom_data = ros2_bridge.get_latest("odom")
        devices["motor"]["connected"] = odom_data is not None
        devices["motor"]["status"] = "normal" if odom_data is not None else "offline"

        # 相机：有 rgb_image 数据
        rgb_data = ros2_bridge.get_latest("rgb_image")
        devices["camera"]["connected"] = rgb_data is not None
        devices["camera"]["status"] = "normal" if rgb_data is not None else "offline"

        # 电池：有 battery 数据
        battery_data = ros2_bridge.get_latest("battery")
        if battery_data:
            devices["battery"] = {
                "name": "电池管理系统",
                "connected": True,
                "status": "normal",
                "topic": "/battery_state",
                "percent": battery_data.get("percent", 0),
                "voltage": battery_data.get("voltage", 0),
                "charging": battery_data.get("charging", False),
            }
        else:
            devices.setdefault("battery", {
                "name": "电池管理系统",
                "connected": False,
                "status": "offline",
                "topic": "/battery_state",
            })

    # 统一格式：前端期望 sensors 数组
    sensor_list = []
    name_map = {
        "lidar": "激光雷达 (LiDAR)",
        "camera": "RGB 摄像头",
        "imu": "IMU 惯性测量单元",
        "motor": "驱动电机 / 里程计",
        "battery": "电池管理系统",
    }
    for key, info in devices.items():
        sensor_list.append({
            "key": key,
            "name": name_map.get(key, info.get("name", key)),
            "status": "online" if info.get("connected") else "offline",
            "topic": info.get("topic", ""),
            "detail": info,
        })

    return {"sensors": sensor_list, "devices": devices}


@router.post("/reboot", summary="重启设备（预留）")
async def reboot_device():
    # 实际部署时可调用 os.system("sudo reboot")
    return {"success": True, "message": "[预留] 重启指令已发送，设备将在 5 秒后重启"}


@router.get("/ros2/diag", summary="ROS2 桥接诊断（排查真实数据问题）")
async def ros2_diag():
    """
    返回 ROS2 桥接的详细状态，用于排查为何显示模拟数据而非真实数据。
    访问：GET /api/device/ros2/diag
    """
    from app.services.ros2_bridge import ros2_bridge
    import os

    latest_lidar = ros2_bridge.get_latest("lidar3d")
    latest_imu   = ros2_bridge.get_latest("imu")

    return {
        "config": {
            "ROS2_ENABLED_env":  os.getenv("ROS2_ENABLED", "(not set)"),
            "ROS2_ENABLED_cfg":  ROS2_ENABLED,
            "lidar3d_topic":     ROS2_TOPIC_LIDAR3D,
            "imu_topic":         ROS2_TOPIC_IMU,
        },
        "bridge": {
            "is_enabled":        ros2_bridge.is_enabled,
            "_enabled":          ros2_bridge._enabled,
            "_initialized":      ros2_bridge._initialized,
            "subscribers":       list(ros2_bridge._subscribers.keys()),
            "latest_topics":     list(ros2_bridge._latest_data.keys()),
        },
        "latest_lidar3d": {
            "received":          latest_lidar is not None,
            "point_count":       latest_lidar.get("point_count", 0) if latest_lidar else 0,
            "timestamp":         latest_lidar.get("timestamp", 0) if latest_lidar else 0,
        },
        "latest_imu": {
            "received":          latest_imu is not None,
        },
        "diagnosis": _diagnose_ros2(ros2_bridge, latest_lidar),
    }


def _diagnose_ros2(bridge, latest_lidar) -> str:
    """根据桥接状态给出人类可读的诊断结论"""
    if not bridge._enabled:
        return "❌ ROS2_ENABLED=false，后端以模拟模式运行。请确认环境变量或 config.py 默认值。"
    if not bridge._initialized:
        return "❌ ROS2_ENABLED=true 但节点初始化失败（rclpy 导入错误或 ROS2 环境未 source）。"
    if not bridge._subscribers:
        return "❌ 节点已初始化但订阅者列表为空，创建订阅者时可能出错，请查看后端日志。"
    if latest_lidar is None:
        return "⚠️ 节点已初始化且订阅者已创建，但尚未收到 /livox/lidar 数据。请确认雷达驱动已启动并发布该 topic。"
    return "✅ ROS2 桥接正常，已收到真实点云数据。"
