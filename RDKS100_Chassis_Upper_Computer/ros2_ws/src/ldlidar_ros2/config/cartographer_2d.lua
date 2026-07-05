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

-- Cartographer 2D配置 - 手持LD14P雷达建图
-- 纯激光SLAM，不依赖里程计

include "map_builder.lua"
include "trajectory_builder.lua"

options = {
  map_builder = MAP_BUILDER,
  trajectory_builder = TRAJECTORY_BUILDER,
  map_frame = "map",
  tracking_frame = "base_link",  -- 跟踪坐标系
  published_frame = "base_link",  -- 发布坐标系
  odom_frame = "odom",
  provide_odom_frame = true,  -- Cartographer提供odom
  publish_frame_projected_to_2d = false,
  use_pose_extrapolator = true,
  use_odometry = false,  -- 不使用里程计
  use_nav_sat = false,
  use_landmarks = false,
  num_laser_scans = 1,  -- 单个激光雷达
  num_multi_echo_laser_scans = 0,
  num_subdivisions_per_laser_scan = 1,
  num_point_clouds = 0,
  lookup_transform_timeout_sec = 0.2,
  submap_publish_period_sec = 0.3,
  pose_publish_period_sec = 5e-3,  -- 200Hz发布位姿
  trajectory_publish_period_sec = 30e-3,
  rangefinder_sampling_ratio = 1.,
  odometry_sampling_ratio = 1.,
  fixed_frame_pose_sampling_ratio = 1.,
  imu_sampling_ratio = 1.,
  landmarks_sampling_ratio = 1.,
}

-- 2D SLAM配置
MAP_BUILDER.use_trajectory_builder_2d = true

-- 纯激光SLAM配置
TRAJECTORY_BUILDER_2D.use_imu_data = false  -- 不使用IMU
TRAJECTORY_BUILDER_2D.min_range = 0.1  -- LD14P最小距离
TRAJECTORY_BUILDER_2D.max_range = 12.0  -- LD14P最大距离12米
TRAJECTORY_BUILDER_2D.missing_data_ray_length = 5.0
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = true  -- 启用在线扫描匹配
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.15  -- 线性搜索窗口
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.angular_search_window = math.rad(35.)  -- 角度搜索窗口
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.translation_delta_cost_weight = 10.
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.rotation_delta_cost_weight = 1e-1

-- Ceres扫描匹配器配置
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.occupied_space_weight = 1.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 10.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.rotation_weight = 40.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = false
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 20
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.num_threads = 1

-- 运动滤波器 - 降低阈值以便更容易检测移动
TRAJECTORY_BUILDER_2D.motion_filter.max_time_seconds = 0.2
TRAJECTORY_BUILDER_2D.motion_filter.max_distance_meters = 0.05  -- 5cm移动就处理
TRAJECTORY_BUILDER_2D.motion_filter.max_angle_radians = math.rad(5.)  -- 5度旋转就处理

-- 子图配置
TRAJECTORY_BUILDER_2D.submaps.num_range_data = 90  -- 每个子图的扫描数
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.grid_type = "PROBABILITY_GRID"
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.resolution = 0.05  -- 5cm分辨率
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.insert_free_space = true
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.hit_probability = 0.55
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.miss_probability = 0.49

-- 位姿图优化
POSE_GRAPH.optimize_every_n_nodes = 90  -- 每90个节点优化一次
POSE_GRAPH.constraint_builder.min_score = 0.55  -- 约束最小分数
POSE_GRAPH.constraint_builder.global_localization_min_score = 0.6
POSE_GRAPH.optimization_problem.huber_scale = 1e1
POSE_GRAPH.optimization_problem.acceleration_weight = 1e3
POSE_GRAPH.optimization_problem.rotation_weight = 3e5
POSE_GRAPH.constraint_builder.max_constraint_distance = 15.  -- 最大约束距离
POSE_GRAPH.constraint_builder.sampling_ratio = 0.3
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.linear_search_window = 7.
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.angular_search_window = math.rad(30.)
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.branch_and_bound_depth = 7
POSE_GRAPH.constraint_builder.ceres_scan_matcher.occupied_space_weight = 20.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.translation_weight = 10.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.rotation_weight = 1.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = true
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 10
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.num_threads = 1

return options
