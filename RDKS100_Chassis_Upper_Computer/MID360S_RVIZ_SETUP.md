# Livox Mid-360S 远程可视化配置指南

> 版本: 1.0 | 日期: 2026-05-26 | 状态: ✅ 已验证

---

## 最终架构

```
┌─────────────────────────────────────────────────────┐
│  RDK S100 (10.21.1.145)                              │
│                                                     │
│  Mid-360S ──eth1──▶ livox_ros_driver2_node          │
│  192.168.1.138      xfer_format=0 (PointCloud2)     │
│                     10Hz → /livox/lidar              │
│                         │                           │
│                         ▼                           │
│                      RViz2 ←── X11 Forwarding ──┐   │
└─────────────────────────────────────────────────│───┘
                                                  │
  Windows (VcXsrv X Server) ◄─────────────────────┘
```

---

## 关键配置一览

| 项目 | 值 |
|------|-----|
| 雷达型号 | Livox Mid-360S |
| 雷达 IP | `192.168.1.138` |
| RDK 雷达口 (eth1) | `192.168.1.50/24` |
| RDK Wi-Fi | `10.21.1.145/16` |
| ROS2 版本 | Humble (RDK ARM64) |
| 数据格式 | `sensor_msgs/PointCloud2` |
| 发布频率 | 10 Hz |
| Frame ID | `livox_frame` |
| 显示方式 | RViz2 通过 SSH X11 转发到 Windows |

---

## 一次性环境准备

### Windows 端：安装 VcXsrv

1. 下载 [VcXsrv](https://sourceforge.net/projects/vcxsrv/)
2. 安装后启动，配置：
   - 选 **Multiple Windows**
   - **Start no client**
   - 勾选 **Disable access control**
3. 任务栏右下角出现 X 图标即表示运行中

### RDK 端：安装 RViz2

```bash
sudo apt update
sudo apt install -y ros-humble-rviz2
```

---

## 日常启动（每次需要 2 个 SSH 终端）

### 终端 A：启动雷达驱动

```bash
ssh sunrise@10.21.1.145

source /opt/ros/humble/setup.bash
source ~/rdks100_slam/ros2_ws/install/setup.bash

ros2 run livox_ros_driver2 livox_ros_driver2_node --ros-args \
  -p xfer_format:=0 \
  -p data_src:=0 \
  -p publish_freq:=10.0 \
  -p frame_id:=livox_frame \
  -p user_config_path:=$(ros2 pkg prefix livox_ros_driver2 --share)/config/MID360s_config.json
```

看到 `[INFO]` 日志输出表示驱动正常运行。

### 终端 B：启动 RViz2（带 X11 转发）

```bash
ssh -X sunrise@10.21.1.145

source /opt/ros/humble/setup.bash
rviz2
```

> ⚠️ 注意 `-X` 参数，这是 X11 转发的关键。

---

## RViz2 首次配置

1. **Fixed Frame**：左侧面板 → Global Options → Fixed Frame → 输入 `livox_frame`
2. **添加点云**：左下角 Add → By topic → 选 `/livox/lidar` (PointCloud2)
3. **调显示效果**（展开 PointCloud2 条目）：
   - Style: `Points` 或 `Flat Squares`
   - Size (m): `0.03`
   - Color Transformer: `Intensity`（按反射强度着色）
4. **保存配置**：File → Save Config As → 存为 `livox_mid360s.rviz`

之后可用 `rviz2 -d livox_mid360s.rviz` 直接加载配置。

---

## 踩过的坑

| 问题 | 原因 | 解决 |
|------|------|------|
| Livox Viewer segfault (139) | WSL Vulkan 兼容性差 | 换 RViz2 |
| Livox Viewer 搜不到雷达 | UDP 广播过不了 NAT | 换 RViz2 |
| CustomMsg RViz2 不识别 | `xfer_format=1` 输出自定义格式 | 改为 `xfer_format=0` 输出 PointCloud2 |
| `xfer_format:=0` launch 参数不生效 | launch 文件是 Python 变量非 ROS2 参数 | 改用 `ros2 run` 直接传参 |
| WSL 看不到 RDK 的 ROS2 topic | CycloneDDS + 跨子网组播不可达 | RDK 本机跑 RViz2 + X11 转发到 Windows |

---

## 故障排查

```bash
# 检查雷达连通性（RDK 上）
ping 192.168.1.138

# 检查雷达数据是否在发布（RDK 上）
source /opt/ros/humble/setup.bash
ros2 topic hz /livox/lidar

# 检查 topic 类型是否为 PointCloud2
ros2 topic info /livox/lidar

# 杀旧驱动进程
pkill -f livox_ros_driver2_node

# 确认 X11 转发正常（登录 RDK 后）
echo $DISPLAY  # 应显示类似 localhost:10.0
```
