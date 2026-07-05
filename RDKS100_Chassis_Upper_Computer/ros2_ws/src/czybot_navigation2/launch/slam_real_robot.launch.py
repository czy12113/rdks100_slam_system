#!/usr/bin/env python3
"""
真实小车SLAM建图启动文件
硬件配置：RDK S100 + Livox Mid-360S激光雷达 + STM32底盘
功能：启动雷达驱动、STM32通信（真实里程计）、键盘控制和SLAM建图
使用方法：ros2 launch czybot_navigation2 slam_real_robot.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, TimerAction, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # 参数声明
    use_sim_time = LaunchConfiguration('use_sim_time')
    slam_params_file = LaunchConfiguration('slam_params_file')
    lidar_port = LaunchConfiguration('lidar_port')
    stm32_port = LaunchConfiguration('stm32_port')
    stm32_baudrate = LaunchConfiguration('stm32_baudrate')
    use_rviz = LaunchConfiguration('use_rviz')
    
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation time'
    )
    
    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Launch RViz2 (set to false if not needed)'
    )
    
    declare_stm32_baudrate = DeclareLaunchArgument(
        'stm32_baudrate',
        default_value='115200',
        description='STM32 serial baudrate (9600 or 115200)'
    )
    
    declare_slam_params_file = DeclareLaunchArgument(
        'slam_params_file',
        default_value=PathJoinSubstitution([
            FindPackageShare('czybot_navigation2'),
            'config',
            'slam_toolbox_params.yaml'
        ]),
        description='Full path to the SLAM parameters file'
    )
    
    declare_lidar_port = DeclareLaunchArgument(
        'lidar_port',
        default_value='/dev/ttyCH343USB0',
        description='LD14P laser serial port'
    )
    
    declare_stm32_port = DeclareLaunchArgument(
        'stm32_port',
        default_value='/dev/ttyUSB0',
        description='STM32 serial port'
    )
    
    # 1. STM32串口通信桥接节点（先启动，确保TF就绪）
    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        parameters=[{
            'port': stm32_port,
            'baudrate': stm32_baudrate,
            'publish_tf': True,  # 使用真实里程计发布TF
        }]
    )
    
    # 2. LD14P 雷达驱动（使用ldlidar官方launch，包含雷达节点和静态TF）
    # 延迟启动激光雷达，确保STM32的TF已经发布
    ldlidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ldlidar'),
                'launch',
                'ld14p.launch.py'
            ])
        ]),
        launch_arguments={
            'port_name': lidar_port,
        }.items()
    )
    
    ld14p_delayed = TimerAction(
        period=5.0,  # 延迟5秒（STM32需要时间接收底盘数据）
        actions=[ldlidar_launch]
    )
    
    # 3. 键盘控制节点（可选）
    teleop_node = Node(
        package='czybot_navigation2',
        executable='teleop_key',
        name='teleop_key',
        output='screen',
        prefix='xterm -e',  # 在新终端中运行
    )
    
    # 4. SLAM Toolbox 建图节点
    slam_toolbox_node = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[
            slam_params_file,
            {'use_sim_time': use_sim_time}
        ]
    )
    
    # 5. RViz2 可视化（可选）
    rviz_config = PathJoinSubstitution([
        FindPackageShare('czybot_navigation2'),
        'config',
        'slam_rviz.rviz'
    ])
    
    # 条件启动RViz2
    from launch.conditions import IfCondition
    
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen',
        condition=IfCondition(use_rviz)
    )
    
    return LaunchDescription([
        declare_use_sim_time,
        declare_use_rviz,
        declare_slam_params_file,
        declare_lidar_port,
        declare_stm32_port,
        declare_stm32_baudrate,
        stm32_bridge_node,  # 先启动STM32
        ld14p_delayed,  # 延迟5秒启动雷达（包含雷达节点和静态TF）
        slam_toolbox_node,
        rviz_node,
        # teleop_node,  # 如果需要键盘控制，取消注释
    ])
