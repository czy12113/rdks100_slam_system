# =============================================================================
# 数据推送服务
# 后台异步任务，定时从数据源获取数据并通过 WebSocket 广播给前端
# =============================================================================

import asyncio
import logging
import time
import base64
import random
from app.core.config import (
    MOCK_MODE,
    PUSH_RATE_SYSTEM_INFO, PUSH_RATE_ROBOT_STATUS,
    PUSH_RATE_LIDAR, PUSH_RATE_IMU, PUSH_RATE_SLAM_MAP,
    PUSH_RATE_LOG, PUSH_RATE_VIDEO, PUSH_VIDEO_POLL,
    CAMERA_JPEG_QUALITY,
)
from app.core.websocket_manager import ws_manager
from app.services.mock_data import mock_generator
from app.services.ros2_bridge import ros2_bridge

# 里程计推送间隔（秒，10Hz）
PUSH_RATE_ODOM: float = 0.1

logger = logging.getLogger(__name__)


async def _push_loop(topic: str, interval: float, data_fn):
    """通用推送循环"""
    while True:
        try:
            data = data_fn()
            await ws_manager.broadcast(topic, data)
        except Exception as e:
            logger.error("[PUSH] topic=%s 推送失败: %s", topic, e)
        await asyncio.sleep(interval)


async def push_system_info():
    await _push_loop("system", PUSH_RATE_SYSTEM_INFO, mock_generator.get_system_info)


async def push_robot_status():
    await _push_loop("robot_status", PUSH_RATE_ROBOT_STATUS, mock_generator.get_robot_status)


async def push_lidar():
    """推送 3D 激光雷达点云数据（Livox Mid-360S → /livox/lidar）

    优化：若没有任何客户端订阅 lidar topic，则跳过本帧（不生成 mock，
          也不访问 ROS2 缓存），完全把 CPU 让给视频/检测等正在被观看的 topic。
    """
    _last_source = None   # 上一次数据源，用于检测切换
    _log_counter = 0      # 每 50 次打一次诊断日志（约 5 秒）
    while True:
        try:
            # 没人订阅时直接 short-circuit
            if not ws_manager.has_subscribers("lidar"):
                await asyncio.sleep(PUSH_RATE_LIDAR)
                continue

            # 优先使用 ROS2 桥接的真实 3D 点云数据
            data = None
            source = "mock"
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("lidar3d")
                if data is not None:
                    source = "ros2_3d"
                else:
                    source = "ros2_no_data"  # ROS2 已启用但尚无数据

            if data is None:
                data = mock_generator.get_lidar3d_scan()

            _log_counter += 1
            # 数据源切换时立即打日志；否则每 50 次（约 5s）打一次
            if source != _last_source or _log_counter >= 50:
                logger.info(
                    "[PUSH] lidar3d 数据源: %s | ros2_bridge.is_enabled=%s | 点数: %d",
                    source, ros2_bridge.is_enabled, len(data.get('points', []))
                )
                _last_source = source
                _log_counter = 0

            await ws_manager.broadcast("lidar", data)
        except Exception as e:
            logger.error("[PUSH] topic=lidar 推送失败: %s", e)
        await asyncio.sleep(PUSH_RATE_LIDAR)


async def push_imu():
    """推送 IMU 数据（Livox Mid-360 内置 IMU → /livox/imu）
    优先使用真实 ROS2 IMU 数据，不可用时降级为模拟数据
    推送频率 20Hz（PUSH_RATE_IMU=0.05s），与 Livox IMU 200Hz 原始频率匹配
    """
    _last_source = None
    _log_counter = 0
    _last_ts = 0.0   # 上一帧时间戳，用于检测是否有新数据
    while True:
        try:
            data = None
            source = "mock"
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("imu")
                if data is not None:
                    source = "ros2"
                else:
                    source = "ros2_no_data"

            if data is None:
                data = mock_generator.get_imu_data()

            # 每 200 次（约 10s）打一次诊断日志，减少 I/O 开销
            _log_counter += 1
            if source != _last_source or _log_counter >= 200:
                cur_ts = data.get("timestamp", 0)
                logger.info(
                    "[PUSH] imu 数据源: %s | ros2_bridge.is_enabled=%s | ts=%.3f",
                    source, ros2_bridge.is_enabled, cur_ts
                )
                _last_source = source
                _log_counter = 0

            await ws_manager.broadcast("imu", data)
        except Exception as e:
            logger.error("[PUSH] topic=imu 推送失败: %s", e)
        await asyncio.sleep(PUSH_RATE_IMU)


async def push_odom():
    """推送里程计数据（优先使用 ROS2 真实数据，降级为模拟数据）"""
    while True:
        try:
            data = None
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("odom")
            if data is None:
                # 从 mock_generator 的机器人状态中提取里程计数据
                status = mock_generator.get_robot_status()
                data = {
                    "timestamp": status["timestamp"],
                    "pose": {
                        "x": status["pose"]["x"],
                        "y": status["pose"]["y"],
                        "z": status["pose"]["z"],
                        "yaw": status["pose"]["yaw"],
                    },
                    "velocity": {
                        "linear_x": status["velocity"]["linear_x"],
                        "linear_y": status["velocity"]["linear_y"],
                        "angular_z": status["velocity"]["angular_z"],
                    },
                    "odometry": status.get("odometry", {}),
                }
            await ws_manager.broadcast("odom", data)
        except Exception as e:
            logger.error("[PUSH] topic=odom 推送失败: %s", e)
        await asyncio.sleep(PUSH_RATE_ODOM)


async def push_slam_map():
    """SLAM 地图：地图数据量大，没人看时跳过生成"""
    while True:
        try:
            if ws_manager.has_subscribers("slam_map"):
                data = mock_generator.get_slam_map()
                await ws_manager.broadcast("slam_map", data)
        except Exception as e:
            logger.error("[PUSH] topic=slam_map 推送失败: %s", e)
        await asyncio.sleep(PUSH_RATE_SLAM_MAP)


async def push_log():
    await _push_loop("log", PUSH_RATE_LOG, mock_generator.get_log_entry)


async def push_video():
    """
    推送视频帧（RGB / Annotated / Depth）。

    ── 事件驱动 + timestamp 去重策略（提升到 30fps 的关键）─────────────────
    以前的实现是"固定 sleep 66ms → 15fps 上限"。这里改为：
      1. 短 sleep 轮询（PUSH_VIDEO_POLL，默认 8ms / 125Hz）
      2. 每个 topic 独立维护 last_pushed_ts，只有 ros2_bridge 缓存里出现
         新 timestamp 时才推送 → 不会重复推同一帧、也不会落后源头帧率
      3. 相邻推送最少间隔 PUSH_RATE_VIDEO（默认 33ms / 30fps 上限）
         防止极端情况下的过度推送

    优先级：
      1. ROS2 真实数据  ← realsense2_camera 发布的 /camera/camera/color/image_raw
                          和 /camera/camera/aligned_depth_to_color/image_raw（经 d435i_bringup 重映射）
      2. 模拟占位帧     ← 纯色渐变 PNG，用于无相机时前端不空白
         为避免占位帧占满 CPU，Mock 场景下节流到 ~10fps。
    """
    import struct
    import zlib

    def _make_fallback_png(width: int, height: int, r: int, g: int, b: int) -> str:
        """生成最小占位 PNG 并返回 base64 字符串（仅无真实数据时使用）"""
        def chunk(name: bytes, data: bytes) -> bytes:
            c = name + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        raw = b""
        for y in range(height):
            raw += b"\x00"
            for x in range(width):
                raw += bytes([
                    (r + x * 2) % 256,
                    (g + y * 2) % 256,
                    (b + (x + y)) % 256,
                ])
        compressed = zlib.compress(raw)
        ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", ihdr_data)
        png += chunk(b"IDAT", compressed)
        png += chunk(b"IEND", b"")
        return base64.b64encode(png).decode()

    frame_count = 0
    _last_rgb_source = None
    _log_counter = 0

    # 每 topic 独立的 last-pushed timestamp / send-time，用于去重 + 节流
    last_ts:   dict = {"video_rgb": 0.0, "video_annotated": 0.0, "video_depth": 0.0}
    last_sent: dict = {"video_rgb": 0.0, "video_annotated": 0.0, "video_depth": 0.0}
    # mock 帧节流（避免没有真实相机时占位帧被 125Hz 无脑刷）
    MOCK_MIN_INTERVAL = 0.1  # 10fps

    # ── FPS 采样：每 2 秒打一次实际推送帧率，方便判断源头/后端瓶颈 ─────
    fps_sample_start = time.time()
    fps_sample_count = {"video_rgb": 0, "video_annotated": 0, "video_depth": 0}
    # 源头到达帧率（realsense 直接送到 ros2_bridge 缓存的帧频）
    src_last_ts = {"rgb_image": 0.0, "depth_image": 0.0, "annotated_image": 0.0}
    src_count   = {"rgb_image": 0,   "depth_image": 0,   "annotated_image": 0}

    while True:
        try:
            # 三个视频 topic 任一被订阅时才推送，否则整轮跳过节省 CPU
            want_rgb   = ws_manager.has_subscribers("video_rgb")
            want_anno  = ws_manager.has_subscribers("video_annotated")
            want_depth = ws_manager.has_subscribers("video_depth")
            if not (want_rgb or want_anno or want_depth):
                await asyncio.sleep(PUSH_RATE_VIDEO)
                continue

            now = time.time()
            pushed_any = False

            # ── RGB 原图帧 ──────────────────────────────────────────────
            rgb_source = _last_rgb_source or "mock"
            if want_rgb and (now - last_sent["video_rgb"]) >= PUSH_RATE_VIDEO:
                rgb_data = ros2_bridge.get_latest("rgb_image") if ros2_bridge.is_enabled else None
                if rgb_data and rgb_data.get("data"):
                    ts = float(rgb_data.get("timestamp") or 0.0)
                    # 只有源头出现新 timestamp 才推送（避免重复推同一帧）
                    if ts > last_ts["video_rgb"]:
                        rgb_source = "ros2"
                        frame_count += 1
                        last_ts["video_rgb"]   = ts
                        last_sent["video_rgb"] = now
                        pushed_any = True
                        await ws_manager.broadcast("video_rgb", {
                            "type": "rgb",
                            "width":     rgb_data.get("width", 640),
                            "height":    rgb_data.get("height", 480),
                            "data":      rgb_data["data"],
                            "encoding":  rgb_data.get("encoding", "jpeg/base64"),
                            "timestamp": ts or now,
                            "frame_id":  frame_count,
                            "source":    "realsense_d435i",
                        })
                elif (now - last_sent["video_rgb"]) >= MOCK_MIN_INTERVAL:
                    rgb_source = "mock"
                    frame_count += 1
                    last_sent["video_rgb"] = now
                    t = frame_count % 256
                    await ws_manager.broadcast("video_rgb", {
                        "type": "rgb",
                        "width": 160, "height": 120,
                        "data": _make_fallback_png(160, 120, t, 100, 200 - t),
                        "encoding": "png/base64",
                        "timestamp": now,
                        "frame_id": frame_count,
                        "source": "mock",
                    })

            # ── AI 标注图像帧（仅检测节点运行时推送，无 mock 兜底）───────
            if want_anno and (now - last_sent["video_annotated"]) >= PUSH_RATE_VIDEO:
                annotated = ros2_bridge.get_latest("annotated_image") if ros2_bridge.is_enabled else None
                if annotated and annotated.get("data"):
                    ts = float(annotated.get("timestamp") or 0.0)
                    if ts > last_ts["video_annotated"]:
                        last_ts["video_annotated"]   = ts
                        last_sent["video_annotated"] = now
                        pushed_any = True
                        await ws_manager.broadcast("video_annotated", {
                            "type": "annotated",
                            "width":     annotated.get("width", 640),
                            "height":    annotated.get("height", 480),
                            "data":      annotated["data"],
                            "encoding":  annotated.get("encoding", "jpeg/base64"),
                            "timestamp": ts or now,
                            "frame_id":  frame_count,
                            "source":    "realsense_d435i",
                        })

            # ── Depth 帧 ────────────────────────────────────────────────
            if want_depth and (now - last_sent["video_depth"]) >= PUSH_RATE_VIDEO:
                depth_data = ros2_bridge.get_latest("depth_image") if ros2_bridge.is_enabled else None
                if depth_data and depth_data.get("data"):
                    ts = float(depth_data.get("timestamp") or 0.0)
                    if ts > last_ts["video_depth"]:
                        last_ts["video_depth"]   = ts
                        last_sent["video_depth"] = now
                        pushed_any = True
                        await ws_manager.broadcast("video_depth", {
                            "type": "depth",
                            "width":    depth_data.get("width", 640),
                            "height":   depth_data.get("height", 480),
                            "data":     depth_data["data"],
                            "encoding": depth_data.get("encoding", "jpeg/base64"),
                            "timestamp": ts or now,
                            "frame_id": frame_count,
                            "source":   "realsense_d435i",
                        })
                elif (now - last_sent["video_depth"]) >= MOCK_MIN_INTERVAL:
                    last_sent["video_depth"] = now
                    t = frame_count % 256
                    await ws_manager.broadcast("video_depth", {
                        "type": "depth",
                        "width": 160, "height": 120,
                        "data": _make_fallback_png(160, 120, 0, t, 255 - t),
                        "encoding": "png/base64",
                        "timestamp": now,
                        "frame_id": frame_count,
                        "source": "mock",
                    })

            # ── 诊断日志（数据源切换时 + 每 300 帧打一次，减少 I/O 干扰）─
            if pushed_any:
                _log_counter += 1
                if rgb_source != _last_rgb_source or _log_counter >= 300:
                    logger.info(
                        "[PUSH] video 数据源: %s | ros2_bridge.is_enabled=%s | frame=%d",
                        rgb_source, ros2_bridge.is_enabled, frame_count,
                    )
                    _last_rgb_source = rgb_source
                    _log_counter = 0

            # ── FPS 汇总：分别统计"源头到达帧率"与"后端推送帧率"─────────
            # 前者反映 realsense/detection 节点的实际发帧速度；
            # 后者反映 backend push_video 的实际吞吐。
            # 每 2 秒打一次，方便一眼看出是哪一环卡住。
            if ros2_bridge.is_enabled:
                for src_topic in ("rgb_image", "depth_image", "annotated_image"):
                    latest = ros2_bridge.get_latest(src_topic)
                    if latest:
                        ts_src = float(latest.get("timestamp") or 0.0)
                        if ts_src > src_last_ts[src_topic]:
                            src_last_ts[src_topic] = ts_src
                            src_count[src_topic] += 1

            # 更新推送计数（本轮真正推了才计数）
            if pushed_any:
                if want_rgb   and last_sent["video_rgb"]       == now: fps_sample_count["video_rgb"] += 1
                if want_anno  and last_sent["video_annotated"] == now: fps_sample_count["video_annotated"] += 1
                if want_depth and last_sent["video_depth"]     == now: fps_sample_count["video_depth"] += 1

            elapsed = time.time() - fps_sample_start
            if elapsed >= 2.0:
                logger.info(
                    "[PUSH] video FPS 采样 (%.1fs): "
                    "源头 rgb=%.1f depth=%.1f anno=%.1f | "
                    "推送 rgb=%.1f depth=%.1f anno=%.1f",
                    elapsed,
                    src_count["rgb_image"]        / elapsed,
                    src_count["depth_image"]      / elapsed,
                    src_count["annotated_image"]  / elapsed,
                    fps_sample_count["video_rgb"]       / elapsed,
                    fps_sample_count["video_depth"]     / elapsed,
                    fps_sample_count["video_annotated"] / elapsed,
                )
                fps_sample_start = time.time()
                for k in fps_sample_count: fps_sample_count[k] = 0
                for k in src_count:        src_count[k] = 0

        except Exception as e:
            logger.error("[PUSH] video 推送失败: %s", e)

        # 短 sleep 轮询：真实相机 30fps，轮询 125Hz 足够不漏帧且不吃 CPU
        await asyncio.sleep(PUSH_VIDEO_POLL)


async def push_detection_results():
    """
    推送 YOLO 检测结果 JSON（/detection/results → detection_results topic）。

    detection_node 每帧推理后发布一次，backend 通过 ROS2 bridge 缓存最新结果并
    以 10Hz 向前端推送（与标注图像帧率解耦，避免结果丢失）。
    无真实数据时不发送（无需 mock 占位）。
    """
    _last_frame_id = -1
    while True:
        try:
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("detection_results")
                # 只在有新帧时推送（避免重复推送同一帧）
                if data and data.get("frame_id", -1) != _last_frame_id:
                    _last_frame_id = data["frame_id"]
                    await ws_manager.broadcast("detection_results", data)
        except Exception as e:
            logger.error("[PUSH] topic=detection_results 推送失败: %s", e)
        await asyncio.sleep(0.1)   # 10Hz，与标注图像帧率解耦


async def push_vlm_description():
    """
    推送 VLM 场景描述（/vlm/scene_description → vlm_description topic）。

    vlm_node 在关键帧触发时才发布（节流：默认 3 秒冷却 + 类别/距离变化触发），
    backend 仅在收到新 timestamp 时转发一次给前端，避免重复推送。
    无真实数据时静默等待。
    """
    _last_ts = 0.0
    while True:
        try:
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("vlm_description")
                ts = float(data.get("timestamp", 0.0)) if data else 0.0
                if data and ts > _last_ts:
                    _last_ts = ts
                    await ws_manager.broadcast("vlm_description", data)
        except Exception as e:
            logger.error("[PUSH] topic=vlm_description 推送失败: %s", e)
        await asyncio.sleep(0.5)   # 2Hz 轮询：VLM 触发频率本身就低


async def push_vlm_status():
    """
    推送 VLM 节点状态（/vlm/status → vlm_status topic）。
    心跳级别，1Hz 即可。
    """
    _last_ts = 0.0
    while True:
        try:
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("vlm_status")
                ts = float(data.get("timestamp", 0.0)) if data else 0.0
                if data and ts > _last_ts:
                    _last_ts = ts
                    await ws_manager.broadcast("vlm_status", data)
        except Exception as e:
            logger.error("[PUSH] topic=vlm_status 推送失败: %s", e)
        await asyncio.sleep(1.0)


async def push_fire_alert():
    """
    推送火警告警（/alert/fire → fire_alert topic）。

    vlm_node 完成二次确认后才会发布，频率非常低（默认 15s 冷却），
    backend 仅在 timestamp 推进时转发一次，前端据此弹窗 / 横幅 / 播放报警音。
    无论是否真火警都转发（level=none 表示二次确认认定为误报，前端可选择忽略）。
    """
    _last_ts = 0.0
    while True:
        try:
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("fire_alert")
                ts = float(data.get("timestamp", 0.0)) if data else 0.0
                if data and ts > _last_ts:
                    _last_ts = ts
                    await ws_manager.broadcast("fire_alert", data)
                    logger.warning(
                        "[PUSH] fire_alert 已转发 level=%s fire=%s smoke=%s conf=%.2f",
                        data.get("level"), data.get("fire_detected"),
                        data.get("smoke_detected"),
                        float(data.get("confidence", 0.0) or 0.0),
                    )
        except Exception as e:
            logger.error("[PUSH] topic=fire_alert 推送失败: %s", e)
        # 0.5s 轮询，火警告警发出频率本来就低，不会浪费 CPU
        await asyncio.sleep(0.5)


async def push_safety_event():
    """
    推送安全事件（/vlm/safety_event → safety_event topic）。

    dynamic_person_obstacle_node 每次动作状态变化（clear/reroute/stop 切换）
    时会推一次事件；backend 仅在 timestamp 前进时转发，前端据此显示：
      - 状态图标（绿/黄/红）
      - stop 时弹窗
      - reroute 时高亮"绕行中"
      - 汇报当前本地/云端 provider（vlm_summary.backend）
    这是本次创新点最直接对外可见的信号，因此单独一个 push 任务，1Hz 足够。
    """
    _last_ts = 0.0
    while True:
        try:
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("safety_event")
                ts = float(data.get("timestamp", 0.0)) if data else 0.0
                if data and ts > _last_ts:
                    _last_ts = ts
                    await ws_manager.broadcast("safety_event", data)
                    action = data.get("action")
                    if action in ("stop", "reroute"):
                        logger.warning(
                            "[PUSH] safety_event action=%s dist=%.2fm reason=%s",
                            action,
                            float(data.get("min_distance_m", 0.0) or 0.0),
                            data.get("reason", ""),
                        )
        except Exception as e:
            logger.error("[PUSH] topic=safety_event 推送失败: %s", e)
        await asyncio.sleep(0.5)


async def push_dynamic_person_points():
    """
    推送动态行人点云简化版（/dynamic_person_points → dynamic_person_points topic）。

    仅在有订阅者时才广播（has_subscribers 判定），避免没人看时也把序列化 CPU 花掉。
    Nav2 costmap 是另一个 ROS2 内部消费者，这里的推送只面向前端 NavigationView。
    """
    _last_ts = 0.0
    while True:
        try:
            if not ws_manager.has_subscribers("dynamic_person_points"):
                await asyncio.sleep(0.5)
                continue
            if ros2_bridge.is_enabled:
                data = ros2_bridge.get_latest("dynamic_person_points")
                ts = float(data.get("timestamp", 0.0)) if data else 0.0
                if data and ts > _last_ts:
                    _last_ts = ts
                    await ws_manager.broadcast("dynamic_person_points", data)
        except Exception as e:
            logger.error("[PUSH] topic=dynamic_person_points 推送失败: %s", e)
        # 5Hz：跟随 dynamic_person_obstacle_node 的 publish_rate_hz
        await asyncio.sleep(0.2)


async def start_all_push_tasks():
    """启动所有后台推送任务"""
    tasks = [
        asyncio.create_task(push_system_info(), name="push_system"),
        asyncio.create_task(push_robot_status(), name="push_robot"),
        asyncio.create_task(push_lidar(), name="push_lidar"),
        asyncio.create_task(push_imu(), name="push_imu"),
        asyncio.create_task(push_odom(), name="push_odom"),
        asyncio.create_task(push_slam_map(), name="push_slam"),
        asyncio.create_task(push_log(), name="push_log"),
        asyncio.create_task(push_video(), name="push_video"),            # 真实相机 + 降级模拟
        asyncio.create_task(push_detection_results(), name="push_det"),  # YOLO 检测结果
        asyncio.create_task(push_vlm_description(), name="push_vlm"),    # VLM 场景描述
        asyncio.create_task(push_vlm_status(), name="push_vlm_status"),  # VLM 节点状态
        asyncio.create_task(push_fire_alert(), name="push_fire_alert"),  # 火警二次确认结果
        # ── 创新点：动态行人 + 本地 VLM + Nav2 联合决策 ──
        asyncio.create_task(push_safety_event(), name="push_safety_event"),
        asyncio.create_task(push_dynamic_person_points(), name="push_dyn_person"),
    ]
    logger.info("[PUSH] 所有数据推送任务已启动，共 %d 个", len(tasks))
    return tasks
