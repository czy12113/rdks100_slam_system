# 🔥 火灾/烟雾检测 · 小白上手指南

> 给"第一次跑火警链路"的同学看的傻瓜版手册。
> 跟着每一步 **复制 → 粘贴 → 回车**，10 分钟就能在前端看到红色横幅。

---

## 0. 整体架构（一图看懂）

```
D435i 相机
   │ /camera/.../color/image_raw（彩色帧）
   │ /camera/.../aligned_depth_to_color/image_raw（对齐深度）
   ▼
[ 节点 1 ] fire_smoke_node       —— CPU YOLOv5 一阶筛查（轻量、可能误报）
   │ /fire_smoke/prealert         —— 连续 N 次命中后才发一条预警 JSON
   ▼
[ 节点 2 ] vlm_node              —— Qwen-VL 二次确认（看图说话，给出 level / reason）
   │ /alert/fire                  —— 结构化 JSON 警告（含画面、判定依据、处置建议）
   ▼
[ 后端 ] FastAPI ros2_bridge     —— 订阅 /alert/fire，转 WebSocket 推到前端
   │ topic = "fire_alert"
   ▼
[ 前端 ] Vue3 全局 Overlay
   ├── 高危：顶部红色脉冲横幅 + 自动弹窗（带画面）+ 4 声警报音
   ├── 疑似：右下角黄色小条
   └── 用户点"我已知晓"才会消失
```

**两段式检测的好处：** YOLOv5 跑得快但常把"晚霞 / 红衣服 / 暖光灯"当成 fire。
VLM（Qwen-VL）只在 YOLOv5 触发后才被调一次，靠**视觉常识**过滤误报，
同时给出"为什么是火 / 不是火"的人类可读理由。**单次推理大约 ¥0.01。**

---

## 1. 一次性准备（只做一次）

### 1.1 检查权重文件

```bash
ls -lh /home/sunrise/rdks100_slam/ros2_ws/src/d435i_detection/weights/fire_smoke_best.pt
```

看到 `~14M` 左右就 OK。没有的话从开源仓库复制：

```bash
cp /home/sunrise/rdks100_slam/fire-smoke-detect-yolov5/yolov5/best.pt \
   /home/sunrise/rdks100_slam/ros2_ws/src/d435i_detection/weights/fire_smoke_best.pt
```

### 1.2 检查 DASHSCOPE_API_KEY（已硬编码，一般不用动）

本项目的 DashScope Key 已经写死在 [`keys.py`](ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py:24) 第 24 行的 `DASHSCOPE_API_KEY` 常量里。

读取优先级：**构造参数 > 环境变量 `DASHSCOPE_API_KEY` > keys.py 常量**。

```bash
# 想确认当前用的是哪一份，可以临时设环境变量覆盖：
# export DASHSCOPE_API_KEY=sk-另一个key
# 或者直接编辑 keys.py 第 24 行，重启 vlm_node 生效
grep -n DASHSCOPE_API_KEY /home/sunrise/rdks100_slam/ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py
```

> ⚠️ keys.py 含明文 Key，**不要 push 到公开仓库**，建议加 `.gitignore`。
>   生产环境推荐方式：keys.py 里留空字符串，用 systemd 的 `Environment=DASHSCOPE_API_KEY=...` 注入。

### 1.3 编译 ROS2 工作空间

```bash
cd /home/sunrise/rdks100_slam/ros2_ws
colcon build --symlink-install --packages-select d435i_detection vlm_scene
source install/setup.bash
```

> `--symlink-install` 让 Python 改完不用重编。第一次编可能要 1~2 分钟。
> 看到 `Summary: 2 packages finished` 就成功了。

---

## 2. 启动顺序（每次开机都要做）

为了好定位问题，**先开下游、后开上游**。每条命令独占一个终端。

### 终端 A —— ROS2 环境 + D435i 相机

```bash
source /opt/ros/humble/setup.bash    # 或 foxy/iron，看你装的版本
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash
ros2 launch realsense2_camera rs_launch.py \
     enable_color:=true enable_depth:=true align_depth.enable:=true
```

> 终端不停滚 `/camera/.../color/image_raw` 帧率信息就是好的。
> 新开一个终端验证：`ros2 topic hz /camera/camera/color/image_raw` 应该看到 ~30 Hz。

### 终端 B —— BPU 通用目标检测（已有的那个，可选）

如果你想同时跑常规目标检测就开它，**不开也不影响火警**。

```bash
source /opt/ros/humble/setup.bash
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash
ros2 run d435i_detection detection_node_bpu
```

> ⚠️ 不要加 `--params-file detection_params.yaml`。
>   BPU 节点内部已经硬编码了正确的 hbm 模型路径，YAML 里若 `weights_path` 不一致会覆盖内部默认值，导致 `RuntimeError: The input hbm model ... does not exist.`。

### 终端 C —— 火/烟一阶检测（新加的，CPU YOLOv5）

```bash
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash
ros2 launch d435i_detection fire_smoke.launch.py
```

**验证它在工作：**

```bash
ros2 node list | grep fire                                # 应该看到 /fire_smoke_detection_node
ros2 node info /fire_smoke_detection_node | head -30      # 看 publishers / subscribers 是否齐全
ros2 topic hz /fire_smoke/results                         # 持续打印帧率 = 推理在跑
ros2 topic echo /fire_smoke/prealert                      # 手机播放火焰视频对准相机，命中 3 次后会刷一条 JSON
```

⚠️ 节点真实名字是 **`/fire_smoke_detection_node`**（不是 `/fire_smoke_node`）。
   如果 `ros2 topic hz /fire_smoke/results` 始终为空、但 `ros2 node list` 又能看到节点，
   通常是 **模型加载失败**或**没收到 RGB 帧**。看终端 C 的日志最快定位，常见三种：

   - `[FIRE] PyTorch 不可用` → 装 torch：`pip3 install --user torch==2.0.1 torchvision==0.15.2`（或用 sudo）
   - `[FIRE] 模型文件不存在` → 检查 `fire_smoke_params.yaml` 的 `weights_path`
   - `[FIRE] YOLOv5 源码目录不存在` → 检查 `yolov5_src_dir` 必须包含 `models/` 和 `utils/`

### 终端 D —— VLM 二次确认

```bash
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash
ros2 launch vlm_scene vlm.launch.py
```

启动日志里能看到：

```
[VLM] provider=qwen_vl model=qwen-vl-plus
[VLM] 订阅火警预警：/fire_smoke/prealert → /alert/fire
```

**验证：**

```bash
ros2 topic echo /alert/fire
# 一阶检测到火警 → VLM 二次推理 → 这里刷出 level/reason/recommendation JSON
```

### 终端 E —— 后端 + 前端（一条命令搞定）

项目自带启动脚本会自动完成：venv 装依赖 → `npm run build` 编译前端到 `backend/static/dist/` → source ROS2 humble + 工作空间 → 启动 `python3 main.py`，最终监听 `0.0.0.0:8000`。

```bash
cd /home/sunrise/rdks100_slam
./start.sh prod
```

首次跑要约 30~60 秒（pip 装依赖 + vite build）；之后再启动只要 10 秒左右。

启动日志会看到：

```
[INFO] Python: ...
[INFO] 已加载 ROS2 环境: /opt/ros/humble/setup.bash
[INFO] 已加载雷达 ROS2 工作空间，ROS2_ENABLED=true
[ROS2] 订阅 fire_alert: /alert/fire
[PUSH] task=push_fire_alert started
[INFO] 前端访问地址: http://<本机IP>:8000
```

浏览器打开 **`http://机器人IP:8000`**（生产模式下前端是后端 8000 端口托管的静态资源，**不是 5173**）。进任意页面（默认综合监控）即可。

> 想热重载前端开发：另开一个终端跑 `./start.sh frontend`，访问 `http://机器人IP:5173`。
> 想只跑后端、用已构建好的前端产物：`./start.sh backend`。

### 不想用 start.sh？降级方案

如果脚本因为什么原因不能用，手动跑也行：

```bash
# 终端 E1 —— 后端（确保系统装了 uvicorn 和后端依赖）
cd /home/sunrise/rdks100_slam/backend
source venv/bin/activate                                # 或 pip install -r requirements.txt
source /opt/ros/humble/setup.bash
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash
export ROS2_ENABLED=true
python3 main.py                                          # 不要用 uvicorn，main.py 里已经包了

# 终端 E2 —— 前端开发服务器（仅 dev 用）
cd /home/sunrise/rdks100_slam/frontend
npm run dev                                              # → http://机器人IP:5173
```

---

## 3. 联调测试

### 最快的测法（推荐）

1. 找一段 **火焰视频**（B 站 / YouTube 搜 "fire 4k" 一抓一大把）。
2. 在手机上**全屏播放**，把手机举到 D435i 镜头前 30~80cm。
3. 等 **2~5 秒**：
   - 终端 C 滚出 "`[FIRE] 预警发出 hits=3`"
   - 终端 D 滚出 "`[FIRE] 调 VLM 二次确认`" → "`[FIRE] 二次确认结果 level=high`"
   - 终端 E 滚出 "`[PUSH] fire_alert level=high`"
4. 前端 **顶部红色横幅闪烁** + 中央弹窗自动弹出 + 听到 4 声 880Hz 警报音。

### 浏览器没声音？

浏览器要求**用户先点击页面任意位置**才允许播放音频。
随便点一下页面（侧边栏 / 标题都行），下次告警就有声音了。

### 误报太多？

调高 [`fire_smoke_params.yaml`](ros2_ws/src/d435i_detection/config/fire_smoke_params.yaml:1) 的 `confidence_threshold`，
从 `0.45` 提到 `0.55` 或 `0.65`，重启终端 C 即可。

### 漏报太多？

反过来调低 `confidence_threshold` 到 `0.35`，并把 `consecutive_hits` 从 `3` 改成 `2`。

### 想省 VLM 钱？

[`vlm_params.yaml`](ros2_ws/src/vlm_scene/config/vlm_params.yaml:1) 里把 `fire_alert_cooldown_sec` 拉大（默认 30s），
连续命中也只会每 N 秒调一次 Qwen。

---

## 4. 常见报错对照表

| 报错信息 | 原因 | 处理 |
|----------|------|------|
| `ModuleNotFoundError: No module named 'models'` (终端 C) | YOLOv5 源码路径不对 | 检查 `fire_smoke_params.yaml` 的 `yolov5_src_dir` 必须是包含 `models/` 和 `utils/` 的那一层 |
| `[FireSmoke] 模型加载失败: No module named 'tqdm'`（或 seaborn / pandas / requests / matplotlib / scipy）| YOLOv5 源码依赖未装 | `pip3 install --user tqdm seaborn pandas requests matplotlib scipy pyyaml`，然后重启终端 C |
| `[FIRE] provider 未就绪` (终端 D) | DASHSCOPE_API_KEY 没读到 | 在**启动 vlm_node 的终端**里执行 `export DASHSCOPE_API_KEY=...` 后再 launch |
| `[ROS2] 解析 fire_alert 失败` (终端 E) | vlm_node 输出 JSON 不合法（罕见） | 看终端 D 里 `[FIRE] 二次确认结果` 的 raw 字段是否被 VLM 加了多余文本 |
| 前端没有横幅，但终端 D 有 level=high | WS 没连上 / 后端 fire_alert 任务没起 | 浏览器 F12 → Network → WS → 看 fire_alert topic 有没有 frame；或在后端日志搜 `push_fire_alert started` |
| 前端横幅来回闪 | 同一帧的告警没 dismiss 又来了新的 | 点"我已知晓"或"忽略"，或把 `fire_alert_cooldown_sec` 拉大 |

---

## 5. 关键文件速查

| 角色 | 文件 |
|------|------|
| 一阶检测节点 | [`ros2_ws/src/d435i_detection/d435i_detection/fire_smoke_node.py`](ros2_ws/src/d435i_detection/d435i_detection/fire_smoke_node.py:1) |
| 一阶检测配置 | [`ros2_ws/src/d435i_detection/config/fire_smoke_params.yaml`](ros2_ws/src/d435i_detection/config/fire_smoke_params.yaml:1) |
| 一阶检测启动 | [`ros2_ws/src/d435i_detection/launch/fire_smoke.launch.py`](ros2_ws/src/d435i_detection/launch/fire_smoke.launch.py:1) |
| VLM 二次确认 | [`ros2_ws/src/vlm_scene/vlm_scene/vlm_node.py`](ros2_ws/src/vlm_scene/vlm_scene/vlm_node.py:1) |
| VLM 配置（火警段） | [`ros2_ws/src/vlm_scene/config/vlm_params.yaml`](ros2_ws/src/vlm_scene/config/vlm_params.yaml:1) |
| 后端 WS 桥 | [`backend/app/services/ros2_bridge.py`](backend/app/services/ros2_bridge.py:740) |
| 后端推送任务 | [`backend/app/services/data_pusher.py`](backend/app/services/data_pusher.py:388) |
| 前端 composable | [`frontend/src/composables/useFireAlert.ts`](frontend/src/composables/useFireAlert.ts:1) |
| 前端告警 UI | [`frontend/src/components/FireAlertOverlay.vue`](frontend/src/components/FireAlertOverlay.vue:1) |

---

## 6. 一键调参速查表

```yaml
# 误报多 → confidence_threshold ↑（0.55 ~ 0.65）
# 漏报多 → confidence_threshold ↓（0.35 ~ 0.40）+ consecutive_hits 改 2

# VLM 调用太频繁 → fire_alert_cooldown_sec ↑（默认 30，可拉到 60~120）
# VLM 反应太慢 → fire_alert_cooldown_sec ↓（最低 5）

# 想看更准但慢 → infer_width/height = 640
# 想看更快但糙 → infer_width/height = 320
```

---

## 7. 关掉火警功能（不影响其他系统）

只需**停掉终端 C 的 `fire_smoke_node`** 即可。
vlm_node 收不到 prealert 就不会调用 Qwen，前端也不会有任何弹窗。
后端的 ros2_bridge 即便订阅了 `/alert/fire` 也只是空跑，几乎零开销。

---

跑通后欢迎在前端"综合监控"页面拿手机直怼试一下，**第一次看到红色脉冲横幅 + 听到嘀嘀嘀的瞬间还挺爽的。** 🎯
