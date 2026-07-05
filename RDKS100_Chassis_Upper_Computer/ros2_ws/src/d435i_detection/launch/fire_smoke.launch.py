"""
fire_smoke.launch.py
--------------------
独立启动 火/烟 YOLOv5 检测节点。

用法：
  # 假定相机已由 d435i_bringup 启动
  ros2 launch d435i_detection fire_smoke.launch.py

  # 一键启动相机 + 火/烟检测
  ros2 launch d435i_detection fire_smoke.launch.py camera:=true

  # 自定义权重 / 阈值
  ros2 launch d435i_detection fire_smoke.launch.py \
       weights_path:=/abs/path/best.pt \
       confidence_threshold:=0.55

为什么不和 detection.launch.py 合并：
  - 通用 BPU 检测和火/烟 CPU 检测可独立启停，互不影响。
  - 让用户在前端"火警模式"切换时只重启一个节点。
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # ── 参数 ──────────────────────────────────────────────────────────────
    camera_arg = DeclareLaunchArgument(
        "camera",
        default_value="false",
        description="是否同时启动 D435i 相机节点（默认 false：假定相机已起）",
    )

    weights_arg = DeclareLaunchArgument(
        "weights_path",
        default_value="/home/sunrise/rdks100_slam/ros2_ws/src/d435i_detection/weights/fire_smoke_best.pt",
        description="火/烟 YOLOv5 权重路径（.pt）",
    )

    yolov5_src_arg = DeclareLaunchArgument(
        "yolov5_src_dir",
        default_value="/home/sunrise/rdks100_slam/fire-smoke-detect-yolov5/yolov5",
        description="YOLOv5 源码目录（torch.load 反序列化必需）",
    )

    conf_arg = DeclareLaunchArgument(
        "confidence_threshold",
        default_value="0.45",
        description="置信度阈值（0~1）。误报多→调高，漏报多→调低",
    )

    publish_anno_arg = DeclareLaunchArgument(
        "publish_annotated",
        default_value="true",
        description="是否发布带红框标注的图像（关掉可省 CPU）",
    )

    # ── 可选：启动相机 ──────────────────────────────────────────────────────
    camera_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare("d435i_bringup"),
                "launch", "d435i_camera.launch.py",
            ])
        ]),
        condition=IfCondition(LaunchConfiguration("camera")),
    )

    # ── 参数文件 ────────────────────────────────────────────────────────────
    params_file = PathJoinSubstitution([
        FindPackageShare("d435i_detection"),
        "config", "fire_smoke_params.yaml",
    ])

    # ── 节点 ────────────────────────────────────────────────────────────────
    fire_smoke_node = Node(
        package="d435i_detection",
        executable="fire_smoke_node",
        name="fire_smoke_detection_node",
        output="screen",
        parameters=[
            params_file,
            {
                "weights_path":         LaunchConfiguration("weights_path"),
                "yolov5_src_dir":       LaunchConfiguration("yolov5_src_dir"),
                "confidence_threshold": LaunchConfiguration("confidence_threshold"),
                "publish_annotated":    LaunchConfiguration("publish_annotated"),
            },
        ],
    )

    return LaunchDescription([
        camera_arg,
        weights_arg,
        yolov5_src_arg,
        conf_arg,
        publish_anno_arg,
        camera_launch,
        fire_smoke_node,
    ])
