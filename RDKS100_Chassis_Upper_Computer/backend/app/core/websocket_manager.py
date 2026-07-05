# =============================================================================
# WebSocket 连接管理器
# 统一管理所有 WebSocket 连接，支持分组广播
# =============================================================================

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import WS_MAX_CONNECTIONS, WS_HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)


class ConnectionGroup:
    """WebSocket 连接分组，每个 topic 对应一个分组"""

    def __init__(self, name: str):
        self.name = name
        self.connections: Set[WebSocket] = set()

    async def add(self, ws: WebSocket):
        self.connections.add(ws)
        logger.debug(f"[WS] 客户端加入分组 '{self.name}'，当前连接数: {len(self.connections)}")

    async def remove(self, ws: WebSocket):
        self.connections.discard(ws)
        logger.debug(f"[WS] 客户端离开分组 '{self.name}'，当前连接数: {len(self.connections)}")

    async def broadcast(self, message: dict):
        """向分组内所有连接广播消息
        JSON 序列化在线程池中执行，避免大数据（如点云）阻塞 asyncio 事件循环
        """
        if not self.connections:
            return
        loop = asyncio.get_event_loop()
        # 点云等大数据的 JSON 序列化放到线程池，不阻塞事件循环
        data = await loop.run_in_executor(
            None, lambda: json.dumps(message, ensure_ascii=False)
        )
        dead: List[WebSocket] = []
        for ws in list(self.connections):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self.connections)


class WebSocketManager:
    """
    全局 WebSocket 管理器（单例）
    支持按 topic 分组订阅，客户端可订阅多个 topic
    """

    # 预定义 topic 列表
    TOPICS = {
        "system",             # 系统信息（CPU/内存/温度/网络）
        "robot_status",       # 机器人状态（电量/速度/模式）
        "lidar",              # 激光雷达数据
        "imu",                # IMU 姿态数据
        "odom",               # 里程计
        "slam_map",           # SLAM 地图数据
        "slam_pose",          # SLAM 位姿
        "video_rgb",          # RGB 原始视频帧（无标注）
        "video_annotated",    # AI 检测标注图像（带框）
        "video_depth",        # 深度视频帧
        "detection_results",  # YOLO 检测结果 JSON（目标框 + 距离）
        "vlm_description",    # VLM 场景自然语言描述（关键帧触发）
        "vlm_status",         # VLM 节点状态（provider/统计/错误）
        "fire_alert",         # 火警告警（vlm_node 二次确认结果，所有页面常驻）
        # ── 创新点：动态行人 + 本地 VLM + Nav2 联合决策产生的安全事件 ──
        # dynamic_person_obstacle_node 每次做出 stop / reroute / clear 决策时
        # 发布结构化 JSON。前端所有页面都需要能弹告警，因此列为默认订阅。
        "safety_event",
        # 动态行人 3D 红点（PointCloud2 简化后）供 NavigationView 覆盖到地图上
        "dynamic_person_points",
        "navigation",         # 导航状态
        "log",                # 实时日志
        "heartbeat",          # 心跳
    }

    # 轻量 topic：连接建立时自动订阅（数据量小，不影响性能）
    # 重型 topic（lidar/video_*/slam_map）由前端按页面显式 subscribe
    # fire_alert / safety_event 列为默认订阅：安全事件必须能弹窗
    # vlm_status 也列为默认：前端 VideoView 需要立即知道当前 provider
    # 是本地还是云端（用于渲染"本地离线 / 云端增强"标签）
    DEFAULT_TOPICS = {
        "system",
        "robot_status",
        "heartbeat",
        "log",
        "odom",
        "fire_alert",
        "safety_event",
        "vlm_status",
    }

    def __init__(self):
        # topic -> ConnectionGroup
        self._groups: Dict[str, ConnectionGroup] = {
            topic: ConnectionGroup(topic) for topic in self.TOPICS
        }
        # ws -> 已订阅的 topic 集合
        self._client_topics: Dict[WebSocket, Set[str]] = {}
        self._total_connections: int = 0
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, topics: Optional[List[str]] = None):
        """
        接受新连接并订阅指定 topic。

        - 若 topics 显式传入（如 /ws/lidar,imu）：按列表订阅；
        - 否则：只订阅轻量 DEFAULT_TOPICS。重型 topic（lidar/video_*/slam_map）
          需要前端进入对应页面时主动 subscribe，离开时 unsubscribe。
          这样浏览器空闲页面不会被点云/视频 JSON 灌满。
        """
        async with self._lock:
            if self._total_connections >= WS_MAX_CONNECTIONS:
                await ws.close(code=1008, reason="连接数已达上限")
                return False
            await ws.accept()
            self._total_connections += 1
            self._client_topics[ws] = set()

        subscribe_list = topics if topics else list(self.DEFAULT_TOPICS)
        for topic in subscribe_list:
            await self.subscribe(ws, topic)

        logger.info(
            f"[WS] 新连接，总连接数: {self._total_connections}，订阅: {subscribe_list}"
        )
        return True

    async def disconnect(self, ws: WebSocket):
        """
        断开连接，清理所有订阅。
        若断开的是最后一个客户端，自动触发急停 —— 防止前端
        浏览器关闭、网络中断、组件卸载时小车继续运动。
        """
        async with self._lock:
            topics = self._client_topics.pop(ws, set())
            self._total_connections = max(0, self._total_connections - 1)
            remaining = self._total_connections

        for topic in topics:
            if topic in self._groups:
                await self._groups[topic].remove(ws)

        logger.info(f"[WS] 连接断开，总连接数: {remaining}")

        # 最后一个客户端断开 → 主动急停
        if remaining == 0:
            try:
                await self._handle_estop(source="ws_disconnect_last")
            except Exception as e:
                logger.warning(f"[WS] 断开后自动急停失败: {e}")

    async def subscribe(self, ws: WebSocket, topic: str):
        """订阅指定 topic"""
        if topic not in self._groups:
            self._groups[topic] = ConnectionGroup(topic)
        await self._groups[topic].add(ws)
        if ws in self._client_topics:
            self._client_topics[ws].add(topic)

    async def unsubscribe(self, ws: WebSocket, topic: str):
        """取消订阅指定 topic"""
        if topic in self._groups:
            await self._groups[topic].remove(ws)
        if ws in self._client_topics:
            self._client_topics[ws].discard(topic)

    async def broadcast(self, topic: str, data: dict):
        """向指定 topic 的所有订阅者广播消息

        ⚠️ 当 topic 无任何订阅者时直接返回，避免后端在没人观看的情况下
           继续 dump 重型数据（点云/视频）。data_pusher 中重型推送任务
           应该先调用 has_subscribers() 判断后再生成数据，进一步避免
           上游 JSON/base64 编码的 CPU 浪费。
        """
        if topic not in self._groups:
            return
        group = self._groups[topic]
        if not group.connections:
            return
        message = {"topic": topic, "data": data}
        await group.broadcast(message)

    def has_subscribers(self, topic: str) -> bool:
        """是否有任意客户端订阅了该 topic（供 data_pusher 提前 short-circuit）"""
        group = self._groups.get(topic)
        return bool(group and group.connections)

    async def send_to(self, ws: WebSocket, topic: str, data: dict):
        """向单个连接发送消息"""
        try:
            message = {"topic": topic, "data": data}
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[WS] 发送消息失败: {e}")

    async def handle_client_message(self, ws: WebSocket, raw: str):
        """
        处理客户端发来的消息（订阅/取消订阅/控制指令）

        支持 action 类型：
          subscribe   - 订阅 topic
          unsubscribe - 取消订阅 topic
          ping        - 心跳
          cmd_vel     - 速度控制（直接转发到 ros2_bridge，零延迟）
          estop       - 急停（发多次零速，优先级最高）
        """
        try:
            msg = json.loads(raw)
            action = msg.get("action")
            topic = msg.get("topic")

            if action == "subscribe" and topic:
                await self.subscribe(ws, topic)
                await self.send_to(ws, "system", {"type": "ack", "action": "subscribe", "topic": topic})

            elif action == "unsubscribe" and topic:
                await self.unsubscribe(ws, topic)
                await self.send_to(ws, "system", {"type": "ack", "action": "unsubscribe", "topic": topic})

            elif action == "ping":
                await self.send_to(ws, "heartbeat", {"type": "pong", "ts": msg.get("ts")})

            elif action == "cmd_vel":
                # 速度控制：从 WebSocket 直接驱动 ros2_bridge，避免 HTTP 往返延迟
                # 格式: {"action": "cmd_vel", "vx": float, "vy": float, "wz": float}
                await self._handle_cmd_vel(msg)

            elif action == "estop":
                # 急停：连续发送零速，优先级最高
                await self._handle_estop()

        except json.JSONDecodeError:
            logger.warning(f"[WS] 收到非法消息: {raw[:100]}")
        except Exception as e:
            logger.error(f"[WS] 处理消息异常: {e}")

    async def _handle_cmd_vel(self, msg: dict):
        """
        处理速度控制消息：经 SafetyGate 统一限速/死区/急停锁后发布到 ROS2。
        SafetyGate 也会刷新 last_cmd_time，使后端 watchdog 不会在持续控制中误触发。
        """
        from app.services.ros2_bridge import ros2_bridge
        from app.services.safety_gate import safety_gate
        from app.services.mock_data import mock_generator

        try:
            vx, vy, wz, allowed = safety_gate.filter(
                float(msg.get("vx", 0.0)),
                float(msg.get("vy", 0.0)),
                float(msg.get("wz", 0.0)),
            )
            if not allowed:
                # 急停锁中：丢弃该帧；STM32 也会被 estop topic 锁住
                return

            if ros2_bridge.is_enabled:
                ros2_bridge.publish_cmd_vel(vx, vy, wz)
            mock_generator.set_velocity(vx, vy, wz)

        except (ValueError, TypeError) as e:
            logger.warning(f"[WS] cmd_vel 参数非法: {e}")

    async def _handle_estop(self, source: str = "ws:estop"):
        """
        急停处理：
          1. SafetyGate 进入急停锁（一段时间内拒绝任何非零速）
          2. 通过独立 topic /cmd_vel_estop 触发 stm32_bridge 急停
          3. 同时连续发 5 帧零速兜底（每 20ms 一帧）
        """
        from app.services.ros2_bridge import ros2_bridge
        from app.services.safety_gate import safety_gate
        from app.services.mock_data import mock_generator

        safety_gate.trigger_estop(source)
        mock_generator.emergency_stop()

        if ros2_bridge.is_enabled:
            loop = asyncio.get_event_loop()

            def _send_stop():
                import time
                try:
                    ros2_bridge.publish_estop()
                except Exception as e:
                    logger.warning(f"[WS] publish_estop 失败: {e}")
                for _ in range(5):
                    try:
                        ros2_bridge.publish_cmd_vel(0.0, 0.0, 0.0)
                    except Exception:
                        pass
                    time.sleep(0.02)

            await loop.run_in_executor(None, _send_stop)
        logger.info(f"[WS] 急停已执行 source={source}（estop topic + 5 帧零速）")

    @property
    def stats(self) -> dict:
        """返回连接统计信息"""
        return {
            "total_connections": self._total_connections,
            "groups": {
                topic: group.count
                for topic, group in self._groups.items()
            }
        }


# 全局单例
ws_manager = WebSocketManager()
