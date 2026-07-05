# LD14P → Livox Mid-360 切换方案

版本: 1.0  |  日期: 2026-05-23  |  状态: 待执行

---

## 一、差异速览

| 项目 | LD14P（当前） | Livox Mid-360（目标） |
|------|-------------|---------------------|
| 类型 | 2D 单线 | 3D 多线 |
| 连接方式 | USB 串口 | 以太网 |
| ROS2 消息 | `sensor_msgs/LaserScan` | `sensor_msgs/PointCloud2` |
| 默认 Topic | `/scan` | `/livox/lidar` |
| 量程 | 0.1 ~ 12m | 0.1 ~ 30m（@10%反射率） |
| FOV | 360° 水平 | 360° 水平 × 32° 垂直 |
| 点数/帧 | 360 | ~20,000（随时间累积） |
| 扫描模式 | 固定角度间隔 | 非重复花瓣扫描 |
| ROS2 驱动 | 自研 ldlidar_ros2 | livox_ros_driver2（官方） |
| SLAM | Cartographer 2D | FAST-LIO / Cartographer 3D |

---

## 二、硬件准备

### 2.1 网络连接

Livox Mid-360 通过以太网连接，需配置 RDK S100 网卡：

```bash
# 在 RDK S100 上，将连接雷达的网口配置为静态 IP
sudo ip addr add 192.168.1.50/24 dev eth1   # 假设 eth1 接雷达
# 或永久配置 /etc/network/interfaces
```

雷达默认 IP 为 `192.168.1.1xx`（具体见雷达底部标签）。

验证连通性：
```bash
ping 192.168.1.1xx
```

### 2.2 安装 Livox SDK2

```bash
git clone https://github.com/Livox-SDK/Livox-SDK2.git
cd Livox-SDK2 && mkdir build && cd build
cmake .. && make -j$(nproc)
sudo make install
```

### 2.3 安装 livox_ros_driver2

```bash
cd ~/rdks100_slam/ros2_ws/src
git clone https://github.com/Livox-SDK/livox_ros_driver2.git
cd ~/rdks100_slam/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select livox_ros_driver2
```

### 2.4 启动驱动并验证

```bash
source /opt/ros/humble/setup.bash
source ~/rdks100_slam/ros2_ws/install/setup.bash
ros2 launch livox_ros_driver2 msg_MID360_launch.py

# 另开终端验证
ros2 topic list          # 应看到 /livox/lidar
ros2 topic hz /livox/lidar   # 查看发布频率
ros2 topic echo /livox/lidar --once  # 查看一条消息结构
```

---

## 三、代码改动清单（共 6 文件）

### 3.1 `backend/app/core/config.py` — 雷达配置

```python
# ========== 改动 ==========

# Topic 名称
ROS2_TOPIC_SCAN = "/livox/lidar"      # 原 "/scan"

# 雷达参数
LIDAR_MAX_RANGE = 30.0                # 原 12.0
LIDAR_MIN_RANGE = 0.1                 # 不变
LIDAR_POINTS_PER_FRAME = 20000        # 新增：每帧最大点数（用于前端降采样）
LIDAR_VIEW_MODE = "2d"                # 新增："2d"=俯视投影 / "3d"=3D点云（预留）
```

### 3.2 `backend/app/services/ros2_bridge.py` — 订阅与解析

**订阅部分**（`_create_subscribers`）：

```python
# 原 LaserScan 订阅 → 改为 PointCloud2 订阅
from sensor_msgs.msg import PointCloud2

self._node.create_subscription(
    PointCloud2, ROS2_TOPIC_SCAN,
    lambda msg: self._dispatch("lidar", self._parse_pointcloud2(msg)), 10
)
```

**新增解析函数** `_parse_pointcloud2`：

```python
def _parse_pointcloud2(self, msg) -> dict:
    """解析 PointCloud2 → 前端可用 dict"""
    import struct
    import math

    # 解析 PointCloud2 的 field 结构
    # Livox 通常 fields: x(float32), y(float32), z(float32), intensity(float32)
    # 每个点通常是 16 bytes
    points = []
    point_step = msg.point_step
    data = msg.data

    # 预读 field offset
    offsets = {f.name: f.offset for f in msg.fields}

    for i in range(msg.width * msg.height):
        base = i * point_step
        x = struct.unpack_from('f', data, base + offsets['x'])[0]
        y = struct.unpack_from('f', data, base + offsets['y'])[0]
        z = struct.unpack_from('f', data, base + offsets['z'])[0]
        intensity = 0.0
        if 'intensity' in offsets:
            intensity = struct.unpack_from('f', data, base + offsets['intensity'])[0]

        # 过滤掉原点噪声
        dist = math.sqrt(x*x + y*y + z*z)
        if dist < 0.1:
            continue

        points.append([round(x, 4), round(y, 4), round(z, 4), round(intensity, 2)])

    # 计算障碍物信息（基于 2D 投影）
    xy_dists = [math.sqrt(p[0]**2 + p[1]**2) for p in points]
    return {
        "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
        "frame_id": msg.header.frame_id,
        "points": points,                    # [[x, y, z, intensity], ...]
        "point_count": len(points),
        "obstacle_count": sum(1 for d in xy_dists if d < 2.0),
        "min_distance": round(min(xy_dists, default=0), 3),
        "max_range": 30.0,
    }
```

### 3.3 `backend/app/services/data_pusher.py` — 推送逻辑

```python
# push_lidar() 中仅改一行：
data = ros2_bridge.get_latest("lidar")    # 原 "scan"
```

### 3.4 `backend/app/services/mock_data.py` — 模拟数据

`get_lidar_scan()` → 重构为生成 3D 模拟点云：

```python
def get_lidar_scan(self) -> dict:
    """生成模拟 3D 点云（模拟 Mid-360 的非重复扫描）"""
    t = self._elapsed()
    points = []

    # 模拟多层环形扫描（40 层 × 每层 360 点 ≈ 14400 点）
    num_rings = 40
    points_per_ring = 360
    for ring in range(num_rings):
        # 垂直角度：-16° ~ +16°
        v_angle = math.radians(-16 + 32 * ring / (num_rings - 1))
        v_offset = math.tan(v_angle)  # z 偏移

        for i in range(points_per_ring):
            h_angle = i * (2 * math.pi / points_per_ring)

            # 模拟障碍物距离
            base_range = 3.0 + 2.0 * math.sin(h_angle * 3 + t * 0.5 + ring * 0.1)
            noise = random.uniform(-0.05, 0.05)
            r = base_range + noise

            x = r * math.cos(h_angle)
            y = r * math.sin(h_angle)
            z = r * v_offset + random.uniform(-0.02, 0.02)
            intensity = random.uniform(0, 255)

            points.append([
                round(x, 4), round(y, 4), round(z, 4),
                round(intensity, 2)
            ])

    xy_dists = [math.sqrt(p[0]**2 + p[1]**2) for p in points]
    return {
        "timestamp": time.time(),
        "frame_id": "livox_frame",
        "points": points,
        "point_count": len(points),
        "obstacle_count": sum(1 for d in xy_dists if d < 2.0),
        "min_distance": round(min(xy_dists, default=0), 3),
        "max_range": 30.0,
    }
```

### 3.5 `frontend/src/views/lidar/LidarView.vue` — 前端渲染

**最小改动（2D 俯视投影，推荐先做）：**

```typescript
// drawLidar() 中，points 数据格式从 [x, y] 变为 [x, y, z, intensity]

for (const pt of lidarData.value.points) {
    const ptX = pt[0]  // x — 不变
    const ptY = pt[1]  // y — 不变
    // pt[2] 是 z（高度），用颜色表示
    // pt[3] 是 intensity（反射率）
    const px = cx + ptX * scale
    const py = cy - ptY * scale

    // 颜色按高度映射：低=蓝，高=红
    const zNorm = Math.min(Math.abs(pt[2]) / 3.0, 1)  // 3m 高度范围
    const r = Math.round(255 * zNorm)
    const b = Math.round(255 * (1 - zNorm))
    ctx.fillStyle = `rgb(${r},100,${b})`
    ctx.fillRect(px - 1, py - 1, 2, 2)
}
```

**后续升级（3D 点云，选做）：** 引入 Three.js，新增 `Lidar3DView.vue`

### 3.6 Cartographer 配置 — SLAM 切换（可后做）

两个选项：

| 选项 | 说明 | 难度 |
|------|------|------|
| Cartographer 3D | 设置 `MAP_BUILDER.use_trajectory_builder_2d = false`，配置 3D 参数 | ★★★★ |
| FAST-LIO | 专为 Livox 优化的 LiDAR-inertial odometry，建图质量更好 | ★★★★ |

**建议**：先打通数据显示，SLAM 独立立项。

---

## 四、执行步骤（按顺序）

```
□ 1. RDK S100 网口配置静态 IP（192.168.1.50）
□ 2. 安装 Livox-SDK2
□ 3. 克隆 livox_ros_driver2 到 ros2_ws/src/
□ 4. colcon build livox_ros_driver2
□ 5. 启动驱动，ros2 topic list 确认 /livox/lidar 有数据
□ 6. 改 config.py（topic + 参数）
□ 7. 改 ros2_bridge.py（PointCloud2 解析）
□ 8. 改 data_pusher.py（topic key）
□ 9. 改 mock_data.py（3D 模拟）
□ 10. 改 LidarView.vue（适配新格式）
□ 11. 联调：启动后端 → 前端查看点云
□ 12. Git commit: "feat: V3 切换 Livox Mid-360"
```

---

## 五、不动的部分

以下文件/目录 **不需要改动**：

- `ros2_ws/src/ldlidar_ros2/` — 保留不动，不影响 Livox 运行
- `deploy.sh` / `start.sh` — 现有逻辑兼容（自动检测 ROS2 环境）
- `build_ros2_ws.sh` — 新增 livox_ros_driver2 后需要重新 colcon build，脚本本身不变
- `backend/app/api/` — 无变化
- `backend/app/core/websocket_manager.py` — 无变化
- `frontend/src/stores/` / `frontend/src/router/` — 无变化

---

## 六、风险与注意事项

| 风险 | 应对 |
|------|------|
| Livox SDK 在 ARM 平台（RDK S100）编译失败 | 检查 cmake 依赖（PCL、Eigen），可能需要交叉编译 |
| PointCloud2 点数过多导致 WebSocket 带宽不足 | 前端降采样（每帧最多渲染 5000 点），或后端降采样后再推送 |
| Mid-360 非重复扫描，单帧点云稀疏 | 前端做帧间累积显示，或后端做 temporal accumulation |
| 雷达 IP 冲突 | 确认 RDK S100 上只有一个网口在 192.168.1.x 网段 |
