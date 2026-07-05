"""
detection.launch.py
-------------------
同时启动 D435i 相机节点 + YOLOv5 检测节点。

用法：
  # 仅启动检测（假设相机已由 d435i_bringup 启动）
  ros2 launch d435i_detection detection.launch.py camera:=false

  # 一键启动相机 + 检测
  ros2 launch d435i_detection detection.launch.py

  # 指定模型路径
  ros2 launch d435i_detection detection.launch.py \
      model_path:=/home/sunrise/rdks100_slam/d435i_ros2/d435i_ros2/weights/yolov5s.pt
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, LogInfo
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # ──────────────────────────────────────────────────────────────────
    # Launch 参数
    # ──────────────────────────────────────────────────────────────────
    camera_arg = DeclareLaunchArgument(
        "camera",
        default_value="true",
        description="是否同时启动相机节点（true/false）",
    )

    model_path_arg = DeclareLaunchArgument(
        "model_path",
        default_value="/home/sunrise/rdks100_slam/d435i_ros2/d435i_ros2/weights/yolov5s.pt",
        description="YOLOv5 模型路径（.pt 文件）",
    )

    conf_arg = DeclareLaunchArgument(
        "confidence_threshold",
        default_value="0.5",
        description="检测置信度阈值",
    )

    device_arg = DeclareLaunchArgument(
        "device",
        default_value="cpu",
        description="推理设备：cpu 或 cuda",
    )

    publish_annotated_arg = DeclareLaunchArgument(
        "publish_annotated",
        default_value="true",
        description="是否发布带标注图像（调试用）",
    )

    # ──────────────────────────────────────────────────────────────────
    # 可选：启动相机（依赖 d435i_bringup 包）
    # ──────────────────────────────────────────────────────────────────
    camera_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("d435i_bringup"),
                "launch",
                "d435i_camera.launch.py",
            ])
        ]),
        condition=IfCondition(LaunchConfiguration("camera")),
    )

    # ──────────────────────────────────────────────────────────────────
    # 参数文件
    # ──────────────────────────────────────────────────────────────────
    params_file = PathJoinSubstitution([
        FindPackageShare("d435i_detection"),
        "config",
        "detection_params.yaml",
    ])

    # ──────────────────────────────────────────────────────────────────
    # 注入 venv site-packages：ros2 run 用系统 Python shebang，
    # 找不到 venv 中的 torch，通过 PYTHONPATH 让子进程找到
    # ──────────────────────────────────────────────────────────────────
    _venv_sp = "/home/sunrise/rdks100_slam/backend/venv/lib/python3.10/site-packages"
    _sys_pp = os.environ.get("PYTHONPATH", "")
    _merged_pp = _venv_sp + (":" + _sys_pp if _sys_pp else "")

    # ──────────────────────────────────────────────────────────────────
    # 检测节点
    # ──────────────────────────────────────────────────────────────────
    detection_node = Node(
        package="d435i_detection",
        executable="detection_node",
        name="d435i_detection_node",
        parameters=[
            params_file,
            {
                # 命令行参数覆盖 yaml 配置
                "model_path":            LaunchConfiguration("model_path"),
                "confidence_threshold":  LaunchConfiguration("confidence_threshold"),
                "device":                LaunchConfiguration("device"),
                "publish_annotated":     LaunchConfiguration("publish_annotated"),
            },
        ],
        output="screen",
        emulate_tty=True,
        additional_env={"PYTHONPATH": _merged_pp},
    )

    return LaunchDescription([
        camera_arg,
        model_path_arg,
        conf_arg,
        device_arg,
        publish_annotated_arg,
        LogInfo(msg="[d435i_detection] 启动检测节点..."),
        camera_launch,
        detection_node,
    ])
