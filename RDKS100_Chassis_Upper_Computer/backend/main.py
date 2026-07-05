# =============================================================================
# FastAPI 后端主入口
# RDK S100 智能机器人上位机系统
# =============================================================================

import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.core.config import (
    DEVICE_HOST, DEVICE_PORT, DEVICE_NAME, DEVICE_VERSION,
    CORS_ORIGINS, LOG_LEVEL, MOCK_MODE, ROS2_ENABLED,
)
from app.core.websocket_manager import ws_manager
from app.services.data_pusher import start_all_push_tasks
from app.services.ros2_bridge import ros2_bridge
from app.services.safety_gate import safety_gate
from app.api import control, slam, navigation, device, vlm

# -----------------------------------------------------------------------------
# 日志配置
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# 后台任务句柄
# -----------------------------------------------------------------------------
_push_tasks: list = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理：启动时开启推送任务，关闭时清理"""
    logger.info("=" * 60)
    logger.info(f"  {DEVICE_NAME} v{DEVICE_VERSION} 启动中...")
    logger.info(f"  模拟模式: {'开启' if MOCK_MODE else '关闭'}")
    logger.info(f"  ROS2 接入: {'开启' if ROS2_ENABLED else '关闭'}")
    logger.info("=" * 60)

    global _push_tasks
    _push_tasks = await start_all_push_tasks()

    # 安全门 watchdog：绑定底层发布函数并启动后台线程
    safety_gate.bind_publisher(ros2_bridge.publish_cmd_vel)
    safety_gate.start_watchdog()

    yield  # 应用运行中

    # 关闭前主动发停车（双通道：cmd_vel + estop topic）
    try:
        if ros2_bridge.is_enabled:
            ros2_bridge.publish_cmd_vel(0.0, 0.0, 0.0)
            ros2_bridge.publish_estop()
    except Exception as e:
        logger.warning("[Main] 关闭前发送停车失败: %s", e)

    safety_gate.stop_watchdog()

    # 关闭时取消所有推送任务
    for task in _push_tasks:
        task.cancel()
    await asyncio.gather(*_push_tasks, return_exceptions=True)
    logger.info("[Main] 所有推送任务已停止")


# -----------------------------------------------------------------------------
# FastAPI 应用实例
# -----------------------------------------------------------------------------
app = FastAPI(
    title=f"{DEVICE_NAME} WebUI API",
    description="RDK S100 智能机器人上位机系统后端接口",
    version=DEVICE_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)

# -----------------------------------------------------------------------------
# CORS 中间件
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------------------------------
# 注册 REST API 路由
# -----------------------------------------------------------------------------
app.include_router(control.router)
app.include_router(slam.router)
app.include_router(navigation.router)
app.include_router(device.router)
app.include_router(vlm.router)


# -----------------------------------------------------------------------------
# WebSocket 端点
# -----------------------------------------------------------------------------
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    统一 WebSocket 入口
    客户端连接后默认订阅所有 topic
    支持通过消息动态订阅/取消订阅
    消息格式：
      订阅:   {"action": "subscribe",   "topic": "lidar"}
      取消:   {"action": "unsubscribe", "topic": "lidar"}
      心跳:   {"action": "ping", "ts": 1234567890}
    """
    connected = await ws_manager.connect(websocket)
    if not connected:
        return
    try:
        while True:
            raw = await websocket.receive_text()
            await ws_manager.handle_client_message(websocket, raw)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS] 连接异常断开: {e}")
    finally:
        await ws_manager.disconnect(websocket)


@app.websocket("/ws/{topics}")
async def websocket_topic_endpoint(websocket: WebSocket, topics: str):
    """
    按 topic 订阅的 WebSocket 端点
    例：/ws/lidar,imu  只接收激光雷达和 IMU 数据
    """
    topic_list = [t.strip() for t in topics.split(",") if t.strip()]
    connected = await ws_manager.connect(websocket, topic_list)
    if not connected:
        return
    try:
        while True:
            raw = await websocket.receive_text()
            await ws_manager.handle_client_message(websocket, raw)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"[WS] 连接异常断开: {e}")
    finally:
        await ws_manager.disconnect(websocket)


# -----------------------------------------------------------------------------
# REST API：系统状态
# -----------------------------------------------------------------------------
@app.get("/api/health", tags=["system"])
async def health_check():
    return {
        "status": "ok",
        "name": DEVICE_NAME,
        "version": DEVICE_VERSION,
        "mock_mode": MOCK_MODE,
        "ros2_enabled": ROS2_ENABLED,
        "ws_stats": ws_manager.stats,
    }


@app.get("/api/ws/stats", tags=["system"])
async def ws_stats():
    return ws_manager.stats


# -----------------------------------------------------------------------------
# 前端静态文件服务（生产模式）
# 前端 build 产物放在 backend/static/dist 目录
# -----------------------------------------------------------------------------
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static", "dist")
if os.path.exists(_STATIC_DIR):
    app.mount("/assets", StaticFiles(directory=os.path.join(_STATIC_DIR, "assets")), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_frontend(full_path: str):
        """所有非 API 路由返回前端 index.html（SPA 路由支持）"""
        index = os.path.join(_STATIC_DIR, "index.html")
        if os.path.exists(index):
            return FileResponse(index)
        return {"error": "前端文件未找到，请先执行 npm run build"}
else:
    @app.get("/", tags=["system"])
    async def root():
        return {
            "message": f"{DEVICE_NAME} 后端服务运行中",
            "api_docs": f"http://{DEVICE_HOST}:{DEVICE_PORT}/api/docs",
            "websocket": f"ws://{DEVICE_HOST}:{DEVICE_PORT}/ws",
            "note": "前端未构建，请在 frontend/ 目录执行 npm run build",
        }


# -----------------------------------------------------------------------------
# 直接运行入口
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host=DEVICE_HOST,
        port=DEVICE_PORT,
        reload=False,
        log_level=LOG_LEVEL.lower(),
        ws_ping_interval=20,
        ws_ping_timeout=10,
    )
