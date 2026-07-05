-- Copyright 2016 The Cartographer Authors
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--      http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Cartographer 3D SLAM 配置
-- 硬件：RDK S100 + Livox Mid-360S（直接输入PointCloud2）
-- 特点：利用360S内置IMU + 里程计，生成3D地图和高精度2D投影地图
-- 适合：复杂室内/室外环境，有坡度的场景
--
-- 雷达水平安装说明：
--   base_link→livox_frame 的静态TF仅包含安装高度，四元数为单位旋转。
--   3D模式下 Cartographer 直接消费 /livox/lidar（livox_frame坐标系），
--   TF树会将点云和IMU数据变换到 tracking_frame(base_link)。

include "map_builder.lua"
include "trajectory_builder.lua"

options = {
  map_builder = MAP_BUILDER,
  trajectory_builder = TRAJECTORY_BUILDER,
  map_frame = "map",
  tracking_frame = "base_link",      -- 跟踪坐标系
  published_frame = "odom",          -- STM32提供odom->base_link TF
  odom_frame = "odom",
  provide_odom_frame = false,        -- STM32已提供odom帧
  publish_frame_projected_to_2d = false,
  use_pose_extrapolator = true,
  use_odometry = true,               -- 使用STM32里程计
  use_nav_sat = false,
  use_landmarks = false,
  num_laser_scans = 0,               -- 3D模式不使用2D激光
  num_multi_echo_laser_scans = 0,
  num_subdivisions_per_laser_scan = 1,
  num_point_clouds = 1,              -- 1个点云输入（360S）
  lookup_transform_timeout_sec = 0.3,
  submap_publish_period_sec = 0.3,
  pose_publish_period_sec = 5e-3,
  trajectory_publish_period_sec = 30e-3,
  rangefinder_sampling_ratio = 1.,
  odometry_sampling_ratio = 1.,
  fixed_frame_pose_sampling_ratio = 1.,
  imu_sampling_ratio = 1.,
  landmarks_sampling_ratio = 1.,
}

-- 3D SLAM
MAP_BUILDER.use_trajectory_builder_3d = true
MAP_BUILDER.num_background_threads = 4  -- RDK S100多核优化

-- ============================================================
-- 轨迹构建器 3D 参数
-- Livox Mid-360S 规格：
--   点频约200,000点/秒，水平360°全覆盖
--   内置IMU：加速度计 + 陀螺仪，200Hz
--   测量范围：0.1m ~ 40m
-- ============================================================
TRAJECTORY_BUILDER_3D.min_range = 0.1
TRAJECTORY_BUILDER_3D.max_range = 25.0
TRAJECTORY_BUILDER_3D.num_accumulated_range_data = 1  -- 每帧点云直接处理

-- IMU配置（360S内置IMU可用）
TRAJECTORY_BUILDER_3D.imu_gravity_time_constant = 10.

-- 高分辨率子图（近距离精细特征）
TRAJECTORY_BUILDER_3D.high_resolution_adaptive_voxel_filter.max_length = 0.5
TRAJECTORY_BUILDER_3D.high_resolution_adaptive_voxel_filter.min_num_points = 150
TRAJECTORY_BUILDER_3D.high_resolution_adaptive_voxel_filter.max_range = 15.

-- 低分辨率子图（远距离全局约束）
TRAJECTORY_BUILDER_3D.low_resolution_adaptive_voxel_filter.max_length = 0.9
TRAJECTORY_BUILDER_3D.low_resolution_adaptive_voxel_filter.min_num_points = 100
TRAJECTORY_BUILDER_3D.low_resolution_adaptive_voxel_filter.max_range = 25.

-- 实时相关性扫描匹配
TRAJECTORY_BUILDER_3D.use_online_correlative_scan_matching = false  -- 3D下计算量大，默认关闭

-- Ceres扫描匹配
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.occupied_space_weight_0 = 1.
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.occupied_space_weight_1 = 6.
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.translation_weight = 5.
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.rotation_weight = 4e2
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.only_optimize_yaw = false
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = false
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 12
TRAJECTORY_BUILDER_3D.ceres_scan_matcher.ceres_solver_options.num_threads = 2

-- 运动滤波器
TRAJECTORY_BUILDER_3D.motion_filter.max_time_seconds = 0.5
TRAJECTORY_BUILDER_3D.motion_filter.max_distance_meters = 0.1
TRAJECTORY_BUILDER_3D.motion_filter.max_angle_radians = 0.004

-- 子图配置（3D子图分辨率）
TRAJECTORY_BUILDER_3D.submaps.high_resolution = 0.10  -- 10cm高分辨率层
TRAJECTORY_BUILDER_3D.submaps.high_resolution_max_range = 20.
TRAJECTORY_BUILDER_3D.submaps.low_resolution = 0.45   -- 45cm低分辨率层
TRAJECTORY_BUILDER_3D.submaps.num_range_data = 160
TRAJECTORY_BUILDER_3D.submaps.range_data_inserter.hit_probability = 0.55
TRAJECTORY_BUILDER_3D.submaps.range_data_inserter.miss_probability = 0.49
TRAJECTORY_BUILDER_3D.submaps.range_data_inserter.num_free_space_voxels = 2

-- ============================================================
-- 位姿图优化 (3D)
-- ============================================================
POSE_GRAPH.optimize_every_n_nodes = 80
POSE_GRAPH.constraint_builder.sampling_ratio = 0.28
POSE_GRAPH.constraint_builder.max_constraint_distance = 15.
POSE_GRAPH.constraint_builder.min_score = 0.55
POSE_GRAPH.constraint_builder.global_localization_min_score = 0.60
POSE_GRAPH.constraint_builder.loop_closure_translation_weight = 1.1e4
POSE_GRAPH.constraint_builder.loop_closure_rotation_weight = 1e5
POSE_GRAPH.constraint_builder.log_matches = true
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher_3d.branch_and_bound_depth = 8
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher_3d.full_resolution_depth = 3
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher_3d.min_rotational_score = 0.77
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher_3d.min_low_resolution_score = 0.55
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher_3d.linear_xy_search_window = 5.
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher_3d.linear_z_search_window = 1.
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher_3d.angular_search_window = math.rad(15.)
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.occupied_space_weight_0 = 5.
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.occupied_space_weight_1 = 30.
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.translation_weight = 10.
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.rotation_weight = 1.
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.only_optimize_yaw = false
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.ceres_solver_options.use_nonmonotonic_steps = false
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.ceres_solver_options.max_num_iterations = 10
POSE_GRAPH.constraint_builder.ceres_scan_matcher_3d.ceres_solver_options.num_threads = 2
POSE_GRAPH.optimization_problem.huber_scale = 5e2
POSE_GRAPH.optimization_problem.acceleration_weight = 1e3
POSE_GRAPH.optimization_problem.rotation_weight = 3e5
POSE_GRAPH.optimization_problem.local_slam_pose_translation_weight = 1e5
POSE_GRAPH.optimization_problem.local_slam_pose_rotation_weight = 1e5
POSE_GRAPH.optimization_problem.odometry_translation_weight = 1e5
POSE_GRAPH.optimization_problem.odometry_rotation_weight = 1e5
POSE_GRAPH.optimization_problem.fixed_frame_pose_translation_weight = 1e1
POSE_GRAPH.optimization_problem.fixed_frame_pose_rotation_weight = 1e2
POSE_GRAPH.optimization_problem.log_solver_summary = false
POSE_GRAPH.optimization_problem.ceres_solver_options.use_nonmonotonic_steps = false
POSE_GRAPH.optimization_problem.ceres_solver_options.max_num_iterations = 50
POSE_GRAPH.optimization_problem.ceres_solver_options.num_threads = 4
POSE_GRAPH.max_num_final_iterations = 200
POSE_GRAPH.global_sampling_ratio = 0.003
POSE_GRAPH.log_residual_histograms = true
POSE_GRAPH.global_constraint_search_after_n_seconds = 10.

return options
