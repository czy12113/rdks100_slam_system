# RDK S100 + Livox Mid-360S 激光雷达 SLAM 建图指南

## 硬件配置
- **主控**: 地瓜机器人 RDK S100 (ROS2 Humble)
- **激光雷达**: LD14P (USB 连接)
- **底盘**: STM32F103C8T6 + 四路电机驱动 (暂不使用)

## 前置准备

### 1. 安装必要的 ROS2 包

在 RDK S100 上执行：

```bash
# 安装 SLAM Toolbox
sudo apt update
sudo apt install ros-humble-slam-toolbox

# 安装 RViz2（如果还没有）
sudo apt install ros-humble-rviz2

# 安装 TF2 工具
sudo apt install ros-humble-tf2-ros ros-humble-tf2-tools
```

### 2. 安装 LD14P 雷达驱动

你已经有了 `ldlidar_ros2` 驱动包，只需要编译即可：

```bash
cd ~/ros2_ws  # 你的工作空间路径
colcon build --packages-select ldlidar
source install/setup.bash
```

驱动包信息：
- **包名**: `ldlidar`
- **可执行文件**: `ldlidar`
- **默认设备**: `/dev/ttyCH343USB0` (CH343 USB转串口芯片)
- **话题名称**: `/scan`
- **Frame ID**: `base_laser`

### 3. 检查雷达设备

连接 LD14P 到 RDK S100 的 USB 口后：

```bash
# 查看设备（RDK S100 使用 CH343 芯片）
ls -l /dev/ttyCH343USB*

# 应该看到类似：
# crw-rw---- 1 root dialout 166, 0 Apr  1 10:00 /dev/ttyCH343USB0

# 如果权限不足，给予权限
sudo chmod 666 /dev/ttyCH343USB0

# 永久解决权限问题
sudo usermod -aG dialout $USER
# 然后重新登录
```

### 4. 测试雷达驱动

```bash
# 单独启动雷达驱动测试
ros2 run ldlidar_stl_ros2 ldlidar_stl_ros2_node

# 在另一个终端查看雷达数据
ros2 topic echo /scan
```

如果能看到数据输出，说明雷达驱动正常。

## 使用步骤

### 1. 编译项目

```bash
cd ~/ros2_ws  # 或你的工作空间路径
colcon build --packages-select czybot_navigation2
source install/setup.bash
```

### 2. 启动 SLAM 建图

```bash
ros2 launch czybot_navigation2 slam_ld14p.launch.py
```

这个命令会启动：
- LD14P 雷达驱动
- SLAM Toolbox 建图节点
- 必要的 TF 变换
- RViz2 可视化界面

### 3. 开始建图

1. **RViz2 界面**：启动后会自动打开 RViz2，你应该能看到：
   - 红色的激光扫描点云
   - 逐渐生成的灰色地图

2. **手动推动机器人**：
   - 缓慢推动机器人在环境中移动
   - 尽量让机器人旋转，以便扫描周围环境
   - 建议速度：步行速度，不要太快
   - 建议路径：沿着房间边缘走一圈，然后穿过中间

3. **建图技巧**：
   - 移动要平稳，避免突然加速或急转弯
   - 确保环境中有足够的特征（墙壁、家具等）
   - 尽量让新扫描区域与已建图区域有重叠
   - 可以多次经过同一区域以提高精度

### 4. 保存地图

建图完成后，在新终端执行：

```bash
# 保存地图到指定位置
ros2 run nav2_map_server map_saver_cli -f ~/my_map

# 或者保存到项目的 maps 目录
ros2 run nav2_map_server map_saver_cli -f ~/ros2_ws/src/czybot_navigation2/maps/my_room
```

这会生成两个文件：
- `my_map.pgm` - 地图图像
- `my_map.yaml` - 地图配置文件

## 配置调整

### 修改雷达驱动参数

编辑 `slam_ld14p.launch.py`，找到 `ld14p_node` 部分：

```python
ld14p_node = Node(
    package='ldlidar_stl_ros2',  # 你的驱动包名称
    executable='ldlidar_stl_ros2_node',  # 可执行文件名
    parameters=[{
        'port_name': '/dev/ttyUSB0',  # 如果是 ttyUSB1，改成 '/dev/ttyUSB1'
        # 其他参数...
    }]
)
```

### 调整雷达安装位置

如果雷达不是安装在底盘正中心上方 10cm 处，需要修改 TF：

编辑 `slam_ld14p.launch.py`，找到 `static_tf_laser`：

```python
static_tf_laser = Node(
    # ...
    arguments=[
        '0.0', '0.0', '0.1',  # 修改这三个值：x(前后), y(左右), z(上下)
        '0', '0', '0',  # 旋转角度，一般不需要改
        'base_link',
        'laser_link'
    ],
)
```

### 调整 SLAM 参数

如果建图效果不好，可以编辑 `slam_toolbox_params.yaml`：

- `resolution: 0.05` - 地图分辨率，越小越精细但计算量越大
- `minimum_travel_distance: 0.2` - 移动多少距离才更新地图
- `max_laser_range: 12.0` - 雷达最大有效距离

## 常见问题

### 1. 雷达没有数据

```bash
# 检查雷达话题
ros2 topic list | grep scan

# 查看雷达数据
ros2 topic echo /scan

# 检查设备权限
ls -l /dev/ttyUSB0
```

### 2. RViz2 中看不到激光数据

- 检查 Fixed Frame 是否设置为 `map`
- 检查 LaserScan 话题是否为 `/scan`
- 检查 TF 树是否完整：`ros2 run tf2_tools view_frames`

### 3. 地图质量差

- 降低移动速度
- 确保环境光线充足（虽然激光雷达不受光线影响，但便于你观察）
- 增加重叠区域
- 调整 `slam_toolbox_params.yaml` 中的参数

### 4. 找不到雷达驱动包

如果你的驱动包名称不同，需要：
1. 查看驱动包名称：`ros2 pkg list | grep lidar`
2. 查看可执行文件：`ros2 pkg executables <包名>`
3. 修改 launch 文件中的 package 和 executable 参数

## 下一步

建图完成后，你可以：
1. 使用这个地图进行定位和导航
2. 集成底盘控制，实现自主导航
3. 添加更多传感器（摄像头、IMU 等）

## 参考资料

- [SLAM Toolbox 文档](https://github.com/SteveMacenski/slam_toolbox)
- [LD14P 雷达文档](https://www.ldrobot.com/product/en/98)
- [ROS2 Navigation2 教程](https://navigation.ros.org/)
