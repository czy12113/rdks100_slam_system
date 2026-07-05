#!/usr/bin/env python3
"""
GMapping SLAM建图Launch文件
使用经典的GMapping算法进行2D SLAM
专为手持激光雷达优化，稳定可靠
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch.conditions import IfCondition
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.launch_description_sources import PythonLaunchDescriptionSource
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():
    
    # RViz配置文件路径
    rviz_config_file = PathJoinSubstitution([
        FindPackageShare('ldlidar'),
        'rviz2',
        'slam_mapping.rviz'
    ])
    
    # 声明launch参数
    use_sim_time_arg = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation clock if true'
    )
    
    port_name_arg = DeclareLaunchArgument(
        'port_name',
        default_value='/dev/ttyCH343USB0',
        description='LD14P serial port'
    )
    
    use_rviz_arg = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='Whether to start RViz2'
    )
    
    # 启动LD14P雷达驱动
    ldlidar_launch = IncludeLaunchDescription(
        PythonLaunchDescriptionSource([
            PathJoinSubstitution([
                FindPackageShare('ldlidar'),
                'launch',
                'ld14p.launch.py'
            ])
        ]),
        launch_arguments={
            'port_name': LaunchConfiguration('port_name')
        }.items()
    )
    
    # 启动GMapping SLAM节点
    gmapping_node = Node(
        package='slam_gmapping',
        executable='slam_gmapping',
        name='slam_gmapping',
        output='screen',
        parameters=[
            {'use_sim_time': LaunchConfiguration('use_sim_time')},
            
            # 坐标系配置
            {'map_frame': 'map'},
            {'odom_frame': 'odom'},
            {'base_frame': 'base_link'},
            
            # 地图参数
            {'map_update_interval': 1.0},  # 1秒更新一次地图
            {'maxUrange': 11.9},  # LD14P最大有效距离（略小于12m）
            {'maxRange': 12.0},  # LD14P最大距离
            {'sigma': 0.05},
            {'kernelSize': 1},
            {'lstep': 0.05},  # 线性步长
            {'astep': 0.05},  # 角度步长
            {'iterations': 5},
            {'lsigma': 0.075},
            {'ogain': 3.0},
            {'lskip': 0},  # 处理每一帧扫描
            
            # 粒子滤波器参数 - 关键！
            {'particles': 30},  # 粒子数（降低以节省资源）
            
            # 运动模型参数 - 针对手持优化
            {'srr': 0.01},  # 平移-平移噪声
            {'srt': 0.02},  # 平移-旋转噪声
            {'str': 0.01},  # 旋转-平移噪声
            {'stt': 0.02},  # 旋转-旋转噪声
            
            # 更新阈值 - 降低以便更灵敏
            {'linearUpdate': 0.1},  # 10cm移动就更新
            {'angularUpdate': 0.1},  # 5.7度旋转就更新
            {'temporalUpdate': 0.5},  # 0.5秒强制更新
            
            # 重采样阈值
            {'resampleThreshold': 0.5},
            
            # 地图大小和分辨率
            {'xmin': -50.0},
            {'ymin': -50.0},
            {'xmax': 50.0},
            {'ymax': 50.0},
            {'delta': 0.05},  # 5cm分辨率
            
            # 似然参数
            {'llsamplerange': 0.01},
            {'llsamplestep': 0.01},
            {'lasamplerange': 0.005},
            {'lasamplestep': 0.005},
            
            # TF相关
            {'transform_publish_period': 0.05},  # 20Hz发布TF
            {'occ_thresh': 0.25},
            {'minimumScore': 0.0},  # 降低最小分数要求
        ],
        remappings=[
            ('scan', '/scan'),
        ]
    )
    
    # 发布odom到base_link的静态变换
    # GMapping需要odom坐标系，但我们没有里程计，所以创建一个静态的
    odom_to_base_link_tf = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='odom_to_base_link',
        arguments=['0', '0', '0', '0', '0', '0', 'odom', 'base_link']
    )
    
    # 启动RViz2可视化
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config_file],
        parameters=[{'use_sim_time': LaunchConfiguration('use_sim_time')}],
        condition=IfCondition(LaunchConfiguration('use_rviz'))
    )
    
    # 组装LaunchDescription
    ld = LaunchDescription()
    
    # 添加参数声明
    ld.add_action(use_sim_time_arg)
    ld.add_action(port_name_arg)
    ld.add_action(use_rviz_arg)
    
    # 添加节点
    ld.add_action(ldlidar_launch)
    ld.add_action(odom_to_base_link_tf)
    ld.add_action(gmapping_node)
    ld.add_action(rviz_node)
    
    return ld
