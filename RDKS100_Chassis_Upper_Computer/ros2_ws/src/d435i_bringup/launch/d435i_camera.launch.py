"""
d435i_camera.launch.py
----------------------
启动 Intel RealSense D435i 相机节点。

发布的关键 Topic（与 config.py 中保持一致）：
  /camera/color/image_raw          → sensor_msgs/Image (RGB8)
  /camera/depth/image_rect_raw     → sensor_msgs/Image (Z16)
  /camera/aligned_depth_to_color/image_raw  → 对齐深度（可选）
  /camera/imu                      → sensor_msgs/Imu

用法：
  ros2 launch d435i_bringup d435i_camera.launch.py
  ros2 launch d435i_bringup d435i_camera.launch.py serial_no:=<SN>
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # ──────────────────────────────────────────────────────────────
    # Launch 参数
    # ──────────────────────────────────────────────────────────────
    serial_no_arg = DeclareLaunchArgument(
        "serial_no",
        default_value="",
        description="D435i 序列号，留空自动选择第一个设备",
    )

    enable_pointcloud_arg = DeclareLaunchArgument(
        "enable_pointcloud",
        default_value="false",
        description="是否发布点云（true/false），默认关闭节省带宽",
    )

    align_depth_arg = DeclareLaunchArgument(
        "align_depth",
        default_value="true",
        description="是否将深度对齐到彩色帧（true/false）",
    )

    # ──────────────────────────────────────────────────────────────
    # 参数文件路径
    # ──────────────────────────────────────────────────────────────
    params_file = PathJoinSubstitution([
        FindPackageShare("d435i_bringup"),
        "config",
        "d435i_params.yaml",
    ])

    # ──────────────────────────────────────────────────────────────
    # realsense2_camera 节点
    # ──────────────────────────────────────────────────────────────
    realsense_node = Node(
        package="realsense2_camera",
        executable="realsense2_camera_node",
        name="camera",
        namespace="camera",
        parameters=[
            params_file,
            {
                # 运行时覆盖 yaml，支持命令行传参
                "serial_no":          LaunchConfiguration("serial_no"),
                "enable_pointcloud":  LaunchConfiguration("enable_pointcloud"),
                "align_depth.enable": LaunchConfiguration("align_depth"),
            },
        ],
        remappings=[
            # 把 realsense 默认的深度对齐 topic 重映射到 config.py 期望的名字
            # config.py: ROS2_TOPIC_DEPTH_IMAGE = "/camera/depth/image_raw"
            # realsense2_camera 实际发布: /camera/aligned_depth_to_color/image_raw
            ("/camera/aligned_depth_to_color/image_raw", "/camera/depth/image_raw"),
        ],
        output="screen",
        emulate_tty=True,
    )

    return LaunchDescription([
        serial_no_arg,
        enable_pointcloud_arg,
        align_depth_arg,
        LogInfo(msg="[d435i_bringup] 启动 RealSense D435i 相机节点..."),
        realsense_node,
    ])
