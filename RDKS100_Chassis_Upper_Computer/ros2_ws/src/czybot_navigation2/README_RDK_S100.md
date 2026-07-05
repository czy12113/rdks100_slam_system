# RDK S100 + Livox Mid-360S 快速使用指南

## 硬件连接

1. **Livox Mid-360S 雷达**：通过网口连接到 RDK S100
2. **设备名称**：通常为 `/dev/ttyCH343USB0` 或 `/dev/ttyCH343USB1`

## 快速开始

### 1. 检查雷达连接

```bash
# 查看串口设备
ls -l /dev/ttyCH343USB*

# 应该看到类似：
# crw-rw---- 1 root dialout 166, 0 Apr  1 10:00 /dev/ttyCH343USB0

# 如果权限不足，添加用户到 dialout 组
sudo usermod -aG dialout $USER
# 然后重新登录或重启
```

### 2. 编译项目

```bash
cd ~/ros2_ws  # 你的工作空间路径

# 编译所有包（包括雷达驱动）
colcon build

# 或者只编译需要的包
colcon build --packages-select ldlidar czybot_navigation2

# 加载环境
source install/setup.bash
```

### 3. 测试雷达

先单独测试雷达是否正常工作：

```bash
# 启动雷达驱动
ros2 launch ldlidar ld14p.launch.py

# 在另一个终端查看雷达数据
ros2 topic echo /scan --once

# 或者查看雷达话题
ros2 topic hz /scan
```

如果能看到数据输出，说明雷达工作正常！

### 4. 启动 SLAM 建图

```bash
# 确保已经 source 环境
source ~/ros2_ws/install/setup.bash

# 启动 SLAM 建图（会自动启动雷达驱动）
ros2 launch czybot_navigation2 slam_ld14p.launch.py

# 如果设备不是 /dev/ttyCH343USB0，可以指定：
ros2 launch czybot_navigation2 slam_ld14p.launch.py port_name:=/dev/ttyCH343USB1
```

启动后会自动打开 RViz2，你应该能看到：
- 红色的激光扫描点云
- 逐渐生成的灰色地图

### 5. 开始建图

1. **手动推动机器人**：缓慢推动机器人在房间内移动
2. **建图技巧**：
   - 速度要慢，类似正常走路的速度
   - 让机器人旋转，扫描周围环境
   - 沿着房间边缘走一圈
   - 确保新区域与已建图区域有重叠

3. **观察 RViz2**：
   - 红色点云应该实时更新
   - 灰色地图会逐渐扩展
   - 黑色表示障碍物，白色表示可通行区域

### 6. 保存地图

建图完成后，在新终端执行：

```bash
# 保存到当前目录
ros2 run nav2_map_server map_saver_cli -f my_map

# 或保存到指定位置
ros2 run nav2_map_server map_saver_cli -f ~/maps/room_map
```

会生成两个文件：
- `my_map.pgm` - 地图图像
- `my_map.yaml` - 地图配置

## 常见问题

### 1. 找不到设备 /dev/ttyCH343USB0

```bash
# 查看所有串口设备
ls -l /dev/tty*

# 可能的设备名：
# /dev/ttyCH343USB0, /dev/ttyCH343USB1
# /dev/ttyUSB0, /dev/ttyUSB1
# /dev/ttyACM0

# 使用正确的设备名启动
ros2 launch czybot_navigation2 slam_ld14p.launch.py port_name:=/dev/ttyUSB0
```

### 2. 权限被拒绝

```bash
# 临时解决
sudo chmod 666 /dev/ttyCH343USB0

# 永久解决
sudo usermod -aG dialout $USER
# 重新登录
```

### 3. RViz2 中看不到激光数据

检查话题：
```bash
# 查看是否有 /scan 话题
ros2 topic list | grep scan

# 查看 /scan 数据
ros2 topic echo /scan --once

# 查看 TF 树
ros2 run tf2_tools view_frames
# 会生成 frames.pdf，检查 TF 关系是否正确
```

在 RViz2 中：
- 确保 Fixed Frame 设置为 `map`
- 确保 LaserScan 话题设置为 `/scan`
- 检查 LaserScan 是否勾选启用

### 4. 地图质量不好

调整建图参数，编辑 `config/slam_toolbox_params.yaml`：

```yaml
# 降低更新阈值，更频繁地更新地图
minimum_travel_distance: 0.1  # 从 0.2 改为 0.1
minimum_travel_heading: 0.1   # 从 0.2 改为 0.1

# 提高地图分辨率
resolution: 0.03  # 从 0.05 改为 0.03（更精细但计算量更大）
```

### 5. 雷达安装位置不对

如果雷达不是安装在底盘中心正上方 10cm 处，需要修改 TF：

编辑 `launch/slam_ld14p.launch.py`，找到 `static_tf_laser` 部分：

```python
arguments=[
    '0.0',   # x: 前后方向，向前为正（米）
    '0.0',   # y: 左右方向，向左为正（米）
    '0.1',   # z: 上下方向，向上为正（米）
    '0', '0', '0',  # 旋转角度，一般不需要改
    'base_link',
    'base_laser'
],
```

例如，如果雷达安装在底盘前方 5cm、上方 15cm：
```python
arguments=['0.05', '0.0', '0.15', '0', '0', '0', 'base_link', 'base_laser'],
```

## 调试命令

```bash
# 查看所有话题
ros2 topic list

# 查看雷达数据频率
ros2 topic hz /scan

# 查看 TF 变换
ros2 run tf2_ros tf2_echo map base_link

# 查看节点信息
ros2 node list
ros2 node info /slam_toolbox

# 查看参数
ros2 param list /slam_toolbox
```

## 下一步

建图完成后，你可以：
1. 使用地图进行定位
2. 集成底盘控制实现自主导航
3. 添加更多传感器（摄像头、IMU）
4. 实现路径规划和避障

## 技术支持

如果遇到问题：
1. 检查雷达连接和权限
2. 确认 ROS2 环境已正确 source
3. 查看终端错误信息
4. 使用 `ros2 topic` 和 `ros2 node` 命令调试
