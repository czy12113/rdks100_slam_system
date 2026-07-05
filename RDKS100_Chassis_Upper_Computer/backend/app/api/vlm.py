# =============================================================================
# API 路由：VLM 场景理解
#
# /api/vlm/status        GET   节点状态 + provider 信息
# /api/vlm/latest        GET   最新一条 VLM 场景描述
# /api/vlm/history       GET   最近 N 条历史描述（后端内存环形缓冲）
# /api/vlm/ask           POST  手动触发一次 VLM 推理（可带自定义 prompt）
#
# 设计原则：
# - 后端不直接调用 VLM API（避免 RDK 算力 / Key 暴露给 HTTP 客户端）。
# - 所有推理都由 ROS2 节点 vlm_node 完成，REST 仅做转发 + 历史聚合。
# - 历史缓冲在 backend 内存中（默认 50 条），重启即清空，足够前端展示。
# =============================================================================

import time
import asyncio
import logging
from collections import deque
from threading import Lock
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.ros2_bridge import ros2_bridge

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/vlm", tags=["vlm"])

# -----------------------------------------------------------------------------
# 内存历史缓冲（线程安全）
# -----------------------------------------------------------------------------
_HISTORY_MAX = 50
_history: "deque[Dict[str, Any]]" = deque(maxlen=_HISTORY_MAX)
_history_lock = Lock()
_last_seen_ts: float = 0.0


def _ingest_history():
    """从 ros2_bridge 拉取最新 vlm_description，若 timestamp 更新则入队。"""
    global _last_seen_ts
    if not ros2_bridge.is_enabled:
        return
    data = ros2_bridge.get_latest("vlm_description")
    if not data:
        return
    ts = float(data.get("timestamp", 0.0))
    if ts <= _last_seen_ts:
        return
    with _history_lock:
        _last_seen_ts = ts
        _history.append(data)


# -----------------------------------------------------------------------------
# 数据模型
# -----------------------------------------------------------------------------
class VLMAskCmd(BaseModel):
    prompt: str = Field(
        "",
        description="自定义提问，例如 '描述前方场景的潜在危险'；留空则用 vlm_node 默认 prompt",
        max_length=500,
    )
    timeout_sec: float = Field(15.0, ge=1.0, le=60.0, description="等待 VLM 响应的总超时")


# -----------------------------------------------------------------------------
# 路由
# -----------------------------------------------------------------------------
@router.get("/status", summary="获取 VLM 节点状态")
async def get_vlm_status():
    """
    返回 vlm_node 最近一次发布的状态（provider/统计/错误）。
    若 vlm_node 未启动，返回 enabled=False。
    """
    enabled = ros2_bridge.is_enabled
    status = ros2_bridge.get_latest("vlm_status") if enabled else None
    return {
        "enabled": enabled,
        "ros2_bridge": enabled,
        "status": status or {
            "state": "unknown",
            "provider": None,
            "last_error": None,
            "stats": {},
            "timestamp": 0.0,
        },
    }


@router.get("/latest", summary="获取最新一条 VLM 场景描述")
async def get_latest_description():
    """
    返回 vlm_node 最近一次发布的场景描述（关键帧触发结果）。
    """
    _ingest_history()
    data = ros2_bridge.get_latest("vlm_description") if ros2_bridge.is_enabled else None
    if not data:
        return {"available": False, "description": "", "data": None}
    return {"available": True, "description": data.get("description", ""), "data": data}


@router.get("/history", summary="获取 VLM 历史描述")
async def get_history(
    limit: int = Query(20, ge=1, le=_HISTORY_MAX, description="返回最近 N 条"),
):
    """
    返回内存中保存的 VLM 历史记录（按时间升序，最新在末尾）。
    历史在后端进程内存中维护，重启即清空。
    """
    _ingest_history()
    with _history_lock:
        items = list(_history)[-limit:]
    return {"count": len(items), "max": _HISTORY_MAX, "items": items}


@router.post("/ask", summary="手动触发一次 VLM 推理")
async def ask_vlm(cmd: VLMAskCmd):
    """
    手动让 vlm_node 立即对当前画面 + 检测结果做一次 VLM 推理。
    可附带自定义 prompt 改变描述角度（例如"描述前方危险"、"识别这是什么物体"）。

    成功后 vlm_node 会发布新结果到 /vlm/scene_description，前端可通过
    WebSocket 的 vlm_description topic 实时收到，或调用 /api/vlm/latest 拉取。
    """
    if not ros2_bridge.is_enabled:
        raise HTTPException(status_code=503, detail="ROS2 桥接未启用，无法调用 vlm_node")
    result = await ros2_bridge.call_vlm_ask(prompt=cmd.prompt, timeout_sec=cmd.timeout_sec)
    if not result.get("success"):
        raise HTTPException(status_code=502, detail=result.get("message", "VLM 调用失败"))
    # 调用成功后 vlm_node 已发布新结果，等一小段时间让 bridge 更新缓存再返回
    await asyncio.sleep(0.2)
    _ingest_history()
    latest = ros2_bridge.get_latest("vlm_description")
    return {
        "success": True,
        "message": result.get("message", ""),
        "latest": latest,
    }
