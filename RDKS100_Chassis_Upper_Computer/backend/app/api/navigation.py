# =============================================================================
# API 路由：导航与路径规划
# =============================================================================

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.config import NAV_ALGORITHMS, NAV_DEFAULT_ALGORITHM, NAV_GOAL_TOLERANCE
from app.services.mock_data import mock_generator
from app.services.ros2_bridge import ros2_bridge

router = APIRouter(prefix="/api/navigation", tags=["navigation"])


class NavGoalCmd(BaseModel):
    x: float = Field(..., description="目标点 X 坐标（地图坐标系，米）")
    y: float = Field(..., description="目标点 Y 坐标（地图坐标系，米）")
    yaw: float = Field(0.0, description="目标朝向（弧度）")


class WaypointList(BaseModel):
    waypoints: list = Field(..., description="途经点列表 [{x, y, yaw}]")


@router.get("/algorithms", summary="获取支持的导航算法")
async def get_nav_algorithms():
    return {"algorithms": NAV_ALGORITHMS, "default": NAV_DEFAULT_ALGORITHM}


@router.post("/goal", summary="设置导航目标点")
async def set_goal(cmd: NavGoalCmd):
    mock_generator.set_nav_goal(cmd.x, cmd.y, cmd.yaw)
    if ros2_bridge.is_enabled:
        ros2_bridge.publish_goal(cmd.x, cmd.y, cmd.yaw)
    return {"success": True, "goal": cmd.dict(), "message": "导航目标已设置"}


@router.post("/cancel", summary="取消导航")
async def cancel_navigation():
    mock_generator.cancel_navigation()
    return {"success": True, "message": "导航已取消"}


@router.get("/status", summary="获取导航状态")
async def get_nav_status():
    return mock_generator.get_navigation_status()


@router.post("/waypoints", summary="多点巡航")
async def set_waypoints(cmd: WaypointList):
    if not cmd.waypoints:
        raise HTTPException(status_code=400, detail="途经点列表不能为空")
    return {
        "success": True,
        "waypoint_count": len(cmd.waypoints),
        "message": f"已设置 {len(cmd.waypoints)} 个巡航点",
    }


@router.get("/params", summary="获取导航参数")
async def get_nav_params():
    return {
        "goal_tolerance": NAV_GOAL_TOLERANCE,
        "default_algorithm": NAV_DEFAULT_ALGORITHM,
    }
