# =============================================================================
# API 路由：SLAM 建图
#
# 主要能力：
#   1. SLAM 启停 / 状态（保留原逻辑）
#   2. 地图列表：扫描 SLAM_MAP_SAVE_PATH 下的 *.yaml，与 pgm 配对
#   3. 栅格化：读取 pgm + yaml，返回三态占据栅格（0 空闲 / 100 障碍 / 255 未知）
#      → 前端可直接绘制 Canvas，并按栅格坐标做点击标注
#   4. 障碍物栅格标注：每张地图对应一个 <name>.annotations.json 存储用户标注
#      - 支持单格标注 / 批量把多个栅格标为同一个障碍物（同一 group_id）
# =============================================================================

import os
import glob
import json
import base64
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.config import (
    SLAM_ALGORITHMS, SLAM_DEFAULT_ALGORITHM, SLAM_MAP_SAVE_PATH,
    SLAM_MAP_ANNOTATION_SUFFIX,
)
from app.services.mock_data import mock_generator
from app.services.ros2_bridge import ros2_bridge


router = APIRouter(prefix="/api/slam", tags=["slam"])


# -----------------------------------------------------------------------------
# 请求模型
# -----------------------------------------------------------------------------
class SlamStartCmd(BaseModel):
    algorithm: str = Field(SLAM_DEFAULT_ALGORITHM, description="SLAM 算法名称")


class MapSaveCmd(BaseModel):
    name: str = Field(..., description="地图名称")


class MapLoadCmd(BaseModel):
    path: str = Field(..., description="地图文件路径")


class AnnotationItem(BaseModel):
    """单个栅格标注：row/col 为地图像素坐标（左上角为 0,0），text 为标注文本"""
    row: int = Field(..., ge=0, description="栅格行索引（像素）")
    col: int = Field(..., ge=0, description="栅格列索引（像素）")
    text: str = Field("", description="标注文本")
    color: Optional[str] = Field(None, description="标注颜色（可选，前端用于区分类别）")
    group_id: Optional[str] = Field(None, description="批量标注分组 id，同一障碍物的多个栅格共享同一 group_id")


class AnnotationBulk(BaseModel):
    """全量替换某张地图的标注"""
    name: str = Field(..., description="地图名称（不含扩展名）")
    annotations: List[AnnotationItem] = Field(default_factory=list)


class AnnotationSingle(BaseModel):
    """新增/更新单个栅格标注（按 row/col 唯一）"""
    name: str = Field(..., description="地图名称（不含扩展名）")
    row: int = Field(..., ge=0)
    col: int = Field(..., ge=0)
    text: str = Field("", description="标注文本，空字符串等同于删除")
    color: Optional[str] = None


class CellPos(BaseModel):
    row: int = Field(..., ge=0)
    col: int = Field(..., ge=0)


class AnnotationBatchAdd(BaseModel):
    """
    一次性把多个栅格标注为「同一个障碍物」：
      - cells: [{row,col}, ...] 多个栅格坐标
      - text/color 为共同标签
      - 生成一个 group_id，所有子栅格共享，便于以「组」为单位管理
    """
    name: str = Field(..., description="地图名称（不含扩展名）")
    cells: List[CellPos] = Field(..., min_length=1, description="障碍物覆盖的栅格集合")
    text: str = Field(..., min_length=1, description="共同标注文本")
    color: Optional[str] = None


class AnnotationGroupDelete(BaseModel):
    name: str = Field(..., description="地图名称（不含扩展名）")
    group_id: str = Field(..., min_length=1)


# -----------------------------------------------------------------------------
# 内部工具
# -----------------------------------------------------------------------------
def _safe_map_name(name: str) -> str:
    """避免路径穿越：只保留 basename + 去掉扩展名"""
    base = os.path.basename(name)
    stem, _ = os.path.splitext(base)
    if not stem or stem.startswith("."):
        raise HTTPException(status_code=400, detail="非法地图名称")
    return stem


def _yaml_path(stem: str) -> str:
    return os.path.join(SLAM_MAP_SAVE_PATH, f"{stem}.yaml")


def _pgm_path(stem: str) -> str:
    return os.path.join(SLAM_MAP_SAVE_PATH, f"{stem}.pgm")


def _annotation_path(stem: str) -> str:
    return os.path.join(SLAM_MAP_SAVE_PATH, f"{stem}{SLAM_MAP_ANNOTATION_SUFFIX}")


def _parse_map_yaml(yaml_path: str) -> dict:
    """
    极简 YAML 解析（nav2 map yaml 格式固定，无需引入 PyYAML）：
      image: my_map.pgm
      resolution: 0.05
      origin: [x, y, theta]
      negate: 0
      occupied_thresh: 0.65
      free_thresh: 0.196
    """
    meta = {
        "image": "",
        "resolution": 0.05,
        "origin": [0.0, 0.0, 0.0],
        "negate": 0,
        "occupied_thresh": 0.65,
        "free_thresh": 0.196,
    }
    with open(yaml_path, "r", encoding="utf-8") as fp:
        for raw in fp:
            line = raw.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key == "image":
                meta["image"] = val
            elif key == "resolution":
                meta["resolution"] = float(val)
            elif key == "origin":
                # 形如 [x, y, theta]
                inside = val.strip("[]")
                parts = [p.strip() for p in inside.split(",") if p.strip()]
                if len(parts) >= 3:
                    meta["origin"] = [float(parts[0]), float(parts[1]), float(parts[2])]
            elif key == "negate":
                meta["negate"] = int(val)
            elif key == "occupied_thresh":
                meta["occupied_thresh"] = float(val)
            elif key == "free_thresh":
                meta["free_thresh"] = float(val)
    return meta


def _read_pgm_binary(pgm_path: str):
    """
    读取 P5 二进制灰度 PGM，返回 (width, height, maxval, bytes_data)。
    ROS map_saver_cli 输出的都是 P5 格式。
    """
    with open(pgm_path, "rb") as fp:
        # magic
        magic = fp.readline().strip()
        if magic != b"P5":
            raise HTTPException(status_code=500, detail=f"不支持的 PGM 格式: {magic!r}，仅支持 P5")

        # 跳过注释行，读取 width height maxval
        def _next_token():
            token = b""
            while True:
                b = fp.read(1)
                if not b:
                    return token
                if b in (b" ", b"\t", b"\r", b"\n"):
                    if token:
                        return token
                    continue
                if b == b"#":
                    # 注释直到行末
                    fp.readline()
                    continue
                token += b

        try:
            width = int(_next_token())
            height = int(_next_token())
            maxval = int(_next_token())
        except ValueError:
            raise HTTPException(status_code=500, detail="PGM 头解析失败")

        data = fp.read(width * height)
        if len(data) < width * height:
            raise HTTPException(status_code=500, detail="PGM 像素数据不完整")
        return width, height, maxval, data


def _rasterize(meta: dict, width: int, height: int, maxval: int, pixels: bytes) -> bytes:
    """
    将灰度像素按 nav2 阈值规则转成三态占据栅格：
      p = (maxval - gray) / maxval   若 negate == 0 （黑=占据、白=空闲）
      p = gray / maxval              若 negate == 1
      p > occupied_thresh → 100 障碍
      p < free_thresh     → 0   空闲
      其它                 → 255 未知（前端约定用 255 代表未知）
    返回 bytes 长度 = width * height
    """
    negate = meta.get("negate", 0)
    occ_th = meta.get("occupied_thresh", 0.65)
    free_th = meta.get("free_thresh", 0.196)
    mv = max(1, maxval)

    out = bytearray(width * height)
    for i, g in enumerate(pixels):
        if negate:
            p = g / mv
        else:
            p = (mv - g) / mv
        if p >= occ_th:
            out[i] = 100
        elif p <= free_th:
            out[i] = 0
        else:
            out[i] = 255
    return bytes(out)


def _load_annotations(stem: str) -> List[dict]:
    path = _annotation_path(stem)
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if isinstance(data, dict) and "annotations" in data:
            return list(data["annotations"])
        if isinstance(data, list):
            return data
    except Exception:
        return []
    return []


def _save_annotations(stem: str, annotations: List[dict]) -> str:
    os.makedirs(SLAM_MAP_SAVE_PATH, exist_ok=True)
    path = _annotation_path(stem)
    payload = {
        "name": stem,
        "updated": time.time(),
        "annotations": annotations,
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
    return path


# -----------------------------------------------------------------------------
# SLAM 启停 / 状态（保留原有逻辑）
# -----------------------------------------------------------------------------
@router.get("/algorithms", summary="获取支持的 SLAM 算法列表")
async def get_algorithms():
    return {"algorithms": SLAM_ALGORITHMS, "default": SLAM_DEFAULT_ALGORITHM}


@router.post("/start", summary="启动 SLAM")
async def start_slam(cmd: SlamStartCmd):
    if cmd.algorithm not in SLAM_ALGORITHMS:
        raise HTTPException(status_code=400, detail=f"不支持的算法: {cmd.algorithm}")
    mock_generator.start_slam(cmd.algorithm)
    return {"success": True, "algorithm": cmd.algorithm, "message": f"SLAM [{cmd.algorithm}] 已启动"}


@router.post("/stop", summary="停止 SLAM")
async def stop_slam():
    mock_generator.stop_slam()
    return {"success": True, "message": "SLAM 已停止"}


@router.get("/status", summary="获取 SLAM 状态")
async def get_slam_status():
    return mock_generator.get_slam_status()


@router.post("/map/save", summary="保存当前地图")
async def save_map(cmd: MapSaveCmd):
    result = await ros2_bridge.call_save_map(cmd.name)
    return result


@router.post("/map/load", summary="加载地图")
async def load_map(cmd: MapLoadCmd):
    result = await ros2_bridge.call_load_map(cmd.path)
    return result


# -----------------------------------------------------------------------------
# 地图列表 / 栅格化 / 障碍物标注（核心新功能）
# -----------------------------------------------------------------------------
@router.get("/map/list", summary="获取已保存地图列表")
async def list_maps():
    """
    扫描 SLAM_MAP_SAVE_PATH 下的 *.yaml，找出配对的 pgm，返回给前端下拉框。
    响应字段：
      maps: [{ name, yaml_path, pgm_path, size, modified, has_annotations }]
      dir:  当前扫描目录
    """
    maps = []
    if os.path.isdir(SLAM_MAP_SAVE_PATH):
        for yaml_file in sorted(glob.glob(os.path.join(SLAM_MAP_SAVE_PATH, "*.yaml"))):
            stem = os.path.splitext(os.path.basename(yaml_file))[0]
            pgm_file = _pgm_path(stem)
            if not os.path.exists(pgm_file):
                continue
            stat = os.stat(yaml_file)
            maps.append({
                "name": stem,
                "yaml_path": yaml_file,
                "pgm_path": pgm_file,
                "size": os.path.getsize(pgm_file),
                "modified": stat.st_mtime,
                "has_annotations": os.path.exists(_annotation_path(stem)),
            })
        # 按修改时间倒序（最新的地图优先）
        maps.sort(key=lambda m: m["modified"], reverse=True)
    return {"maps": maps, "dir": SLAM_MAP_SAVE_PATH}


@router.get("/map/grid", summary="读取地图并栅格化为占据栅格")
async def get_map_grid(name: str = Query(..., description="地图名称（不含扩展名）")):
    """
    返回三态占据栅格（0 空闲 / 100 障碍 / 255 未知），供前端 Canvas 直接绘制。
    响应：
      name, width, height, resolution, origin{x,y,theta},
      occupied_thresh, free_thresh, negate,
      cells_base64  (bytes 长度=width*height，值域 {0,100,255})
    """
    stem = _safe_map_name(name)
    yaml_file = _yaml_path(stem)
    pgm_file = _pgm_path(stem)

    if not os.path.exists(yaml_file):
        raise HTTPException(status_code=404, detail=f"地图 yaml 不存在: {stem}.yaml")
    if not os.path.exists(pgm_file):
        raise HTTPException(status_code=404, detail=f"地图 pgm 不存在: {stem}.pgm")

    meta = _parse_map_yaml(yaml_file)
    width, height, maxval, pixels = _read_pgm_binary(pgm_file)
    cells = _rasterize(meta, width, height, maxval, pixels)

    ox, oy, otheta = meta["origin"]
    return {
        "name": stem,
        "width": width,
        "height": height,
        "resolution": meta["resolution"],
        "origin": {"x": ox, "y": oy, "theta": otheta},
        "occupied_thresh": meta["occupied_thresh"],
        "free_thresh": meta["free_thresh"],
        "negate": meta["negate"],
        # 前端约定：cells 数组按行主序（row-major），左上角为 (0,0)，
        # 与 PGM 像素顺序一致，方便直接与 Canvas 像素索引对齐。
        "cells_base64": base64.b64encode(cells).decode("ascii"),
    }


@router.get("/map/annotations", summary="读取地图的障碍物栅格标注")
async def get_annotations(name: str = Query(..., description="地图名称（不含扩展名）")):
    stem = _safe_map_name(name)
    return {"name": stem, "annotations": _load_annotations(stem)}


@router.put("/map/annotations", summary="批量替换某地图的标注")
async def put_annotations(payload: AnnotationBulk):
    stem = _safe_map_name(payload.name)
    ann = [a.model_dump() for a in payload.annotations]
    for a in ann:
        a.setdefault("created", time.time())
    path = _save_annotations(stem, ann)
    return {"success": True, "count": len(ann), "path": path}


@router.post("/map/annotations", summary="新增或更新单个栅格标注")
async def upsert_annotation(payload: AnnotationSingle):
    """
    以 (row, col) 作为唯一键：
      - text 非空 → 新增或更新
      - text 为空 → 删除该栅格标注
    """
    stem = _safe_map_name(payload.name)
    annotations = _load_annotations(stem)
    now = time.time()

    # 剔除同坐标旧标注
    annotations = [a for a in annotations if not (a.get("row") == payload.row and a.get("col") == payload.col)]

    if payload.text.strip():
        annotations.append({
            "row": payload.row,
            "col": payload.col,
            "text": payload.text,
            "color": payload.color,
            "group_id": None,  # 单格标注默认不属于任何 group
            "created": now,
        })

    path = _save_annotations(stem, annotations)
    return {
        "success": True,
        "count": len(annotations),
        "path": path,
        "annotations": annotations,
    }


@router.delete("/map/annotations", summary="删除某个栅格标注")
async def delete_annotation(
    name: str = Query(..., description="地图名称"),
    row: int = Query(..., ge=0),
    col: int = Query(..., ge=0),
):
    stem = _safe_map_name(name)
    annotations = _load_annotations(stem)
    new_ann = [a for a in annotations if not (a.get("row") == row and a.get("col") == col)]
    _save_annotations(stem, new_ann)
    return {"success": True, "removed": len(annotations) - len(new_ann), "count": len(new_ann)}


@router.post("/map/annotations/batch", summary="批量把多个栅格标注为同一障碍物")
async def batch_add_annotations(payload: AnnotationBatchAdd):
    """
    将 cells 中所有栅格视为同一个障碍物：
      - 生成新的 group_id，所有栅格共享同 text/color/group_id
      - 若某栅格已有旧标注，按 (row,col) 唯一键覆盖
      - 返回本次生成的 group_id 与更新后的全量列表
    """
    stem = _safe_map_name(payload.name)
    if not payload.cells:
        raise HTTPException(status_code=400, detail="cells 不能为空")

    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="text 不能为空")

    group_id = uuid.uuid4().hex[:12]
    now = time.time()
    annotations = _load_annotations(stem)

    # 剔除同坐标旧标注，保证 (row,col) 唯一
    keys = {(c.row, c.col) for c in payload.cells}
    annotations = [a for a in annotations if (a.get("row"), a.get("col")) not in keys]

    for c in payload.cells:
        annotations.append({
            "row": c.row,
            "col": c.col,
            "text": text,
            "color": payload.color,
            "group_id": group_id,
            "created": now,
        })

    _save_annotations(stem, annotations)
    return {
        "success": True,
        "group_id": group_id,
        "added": len(payload.cells),
        "count": len(annotations),
        "annotations": annotations,
    }


@router.delete("/map/annotations/group", summary="按 group_id 一键删除整组标注")
async def delete_annotation_group(
    name: str = Query(..., description="地图名称"),
    group_id: str = Query(..., min_length=1),
):
    stem = _safe_map_name(name)
    annotations = _load_annotations(stem)
    new_ann = [a for a in annotations if a.get("group_id") != group_id]
    removed = len(annotations) - len(new_ann)
    _save_annotations(stem, new_ann)
    return {
        "success": True,
        "removed": removed,
        "count": len(new_ann),
        "annotations": new_ann,
    }


@router.delete("/map/{map_name}", summary="删除地图（pgm/yaml/标注）")
async def delete_map(map_name: str):
    stem = _safe_map_name(map_name)
    targets = [_yaml_path(stem), _pgm_path(stem), _annotation_path(stem)]
    deleted = []
    for p in targets:
        if os.path.exists(p):
            os.remove(p)
            deleted.append(p)
    return {"success": True, "deleted": deleted, "message": f"地图 '{stem}' 已删除"}
