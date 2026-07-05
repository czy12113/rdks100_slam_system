// =============================================================================
// HTTP API 封装（axios）
// =============================================================================

import axios from 'axios'
import { API_BASE_URL } from '@/config'

// 通用请求实例（较长超时，用于非实时接口）
const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// 急停专用实例：适中超时（800ms），急停必须送达，不能太短
// 注意：速度控制已迁移到 WebSocket 通道，不再需要 ctrlHttp 发速度
const stopHttp = axios.create({
  baseURL: API_BASE_URL,
  timeout: 800,
  headers: { 'Content-Type': 'application/json' },
})

// 响应拦截器（通用）
http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    console.error('[API]', err.response?.data || err.message)
    return Promise.reject(err)
  },
)

// 响应拦截器（急停专用，静默失败但记录警告）
stopHttp.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (axios.isCancel(err)) return Promise.reject(err)
    console.warn('[ESTOP]', err.response?.data || err.message)
    return Promise.reject(err)
  },
)

// =============================================================================
// 急停请求
// 速度控制已通过 WebSocket 通道发送（wsClient.sendCmdVel），HTTP 只保留急停。
// 急停独立通道，不受 WebSocket 速度消息影响。
// =============================================================================
function sendStopRequest() {
  return stopHttp.post('/api/control/stop')
}

// =============================================================================
// HTTP fallback 速度请求（WebSocket 不可用时使用）
// 零速（停车）帧不使用 AbortController，确保不被后续请求取消
// =============================================================================
let _velAbortController: AbortController | null = null

function sendVelocityRequest(linear_x: number, linear_y: number, angular_z: number) {
  const isStop = linear_x === 0 && linear_y === 0 && angular_z === 0

  if (isStop) {
    // 零速帧：独立请求，不参与 abort 链，确保停车必然到达
    if (_velAbortController) {
      _velAbortController.abort()
      _velAbortController = null
    }
    return http.post('/api/control/velocity', { linear_x: 0, linear_y: 0, angular_z: 0 })
  }

  // 非零速：取消上一个还未完成的速度请求，防止请求堆积
  if (_velAbortController) {
    _velAbortController.abort()
  }
  _velAbortController = new AbortController()

  return http.post(
    '/api/control/velocity',
    { linear_x, linear_y, angular_z },
    { signal: _velAbortController.signal, timeout: 400 },
  )
}

// =============================================================================
// 控制 API
// =============================================================================
export const controlApi = {
  /** 急停（HTTP 独立通道，始终可靠送达） */
  stop: sendStopRequest,
  /** HTTP fallback 速度控制（正常情况用 wsClient.sendCmdVel） */
  setVelocity: sendVelocityRequest,
  setMode: (mode: string) => http.post('/api/control/mode', { mode }),
  getParams: () => http.get('/api/control/params'),
}

// =============================================================================
// SLAM API
// =============================================================================
export interface SavedMap {
  name: string
  yaml_path: string
  pgm_path: string
  size: number
  modified: number
  has_annotations: boolean
}

export interface MapGrid {
  name: string
  width: number
  height: number
  resolution: number
  origin: { x: number; y: number; theta: number }
  occupied_thresh: number
  free_thresh: number
  negate: number
  /** base64 编码的三态占据栅格 bytes：0=空闲 / 100=障碍 / 255=未知，行主序 */
  cells_base64: string
}

export interface MapAnnotation {
  row: number
  col: number
  text: string
  color?: string | null
  /** 批量标注分组 id：同一障碍物的多个栅格共享同一 group_id；单格标注为 null */
  group_id?: string | null
  created?: number
}

export const slamApi = {
  getAlgorithms: () => http.get('/api/slam/algorithms'),
  start: (algorithm: string) => http.post('/api/slam/start', { algorithm }),
  stop: () => http.post('/api/slam/stop'),
  getStatus: () => http.get('/api/slam/status'),
  saveMap: (name: string) => http.post('/api/slam/map/save', { name }),
  loadMap: (path: string) => http.post('/api/slam/map/load', { path }),
  listMaps: () => http.get<any, { maps: SavedMap[]; dir: string }>('/api/slam/map/list'),
  deleteMap: (name: string) => http.delete(`/api/slam/map/${name}`),
  /** 读取地图并栅格化为占据栅格（前端 Canvas 渲染） */
  getMapGrid: (name: string) =>
    http.get<any, MapGrid>('/api/slam/map/grid', { params: { name } }),
  /** 获取该地图的全部障碍物栅格标注 */
  getAnnotations: (name: string) =>
    http.get<any, { name: string; annotations: MapAnnotation[] }>(
      '/api/slam/map/annotations',
      { params: { name } },
    ),
  /** 新增/更新单个栅格标注（text 为空则删除该格） */
  upsertAnnotation: (name: string, row: number, col: number, text: string, color?: string) =>
    http.post<any, { success: boolean; count: number; annotations: MapAnnotation[] }>(
      '/api/slam/map/annotations',
      { name, row, col, text, color },
    ),
  /** 删除单个栅格标注 */
  deleteAnnotation: (name: string, row: number, col: number) =>
    http.delete('/api/slam/map/annotations', { params: { name, row, col } }),
  /** 批量替换某地图的全部标注 */
  putAnnotations: (name: string, annotations: MapAnnotation[]) =>
    http.put('/api/slam/map/annotations', { name, annotations }),
  /** 批量标注一组栅格为同一障碍物（一键标注），返回 group_id */
  batchAnnotate: (
    name: string,
    cells: Array<{ row: number; col: number }>,
    text: string,
    color?: string,
  ) =>
    http.post<any, {
      success: boolean
      group_id: string
      added: number
      count: number
      annotations: MapAnnotation[]
    }>('/api/slam/map/annotations/batch', { name, cells, text, color }),
  /** 按 group_id 一键删除整组标注 */
  deleteAnnotationGroup: (name: string, group_id: string) =>
    http.delete<any, {
      success: boolean
      removed: number
      count: number
      annotations: MapAnnotation[]
    }>('/api/slam/map/annotations/group', { params: { name, group_id } }),
}

// =============================================================================
// 导航 API
// =============================================================================
export const navigationApi = {
  getAlgorithms: () => http.get('/api/navigation/algorithms'),
  setGoal: (x: number, y: number, yaw: number = 0) =>
    http.post('/api/navigation/goal', { x, y, yaw }),
  cancel: () => http.post('/api/navigation/cancel'),
  getStatus: () => http.get('/api/navigation/status'),
  setWaypoints: (waypoints: Array<{ x: number; y: number; yaw?: number }>) =>
    http.post('/api/navigation/waypoints', { waypoints }),
  getParams: () => http.get('/api/navigation/params'),
}

// =============================================================================
// 设备 API
// =============================================================================
export const deviceApi = {
  getInfo: () => http.get('/api/device/info'),
  getStatus: () => http.get('/api/device/status'),
  getConfig: () => http.get('/api/device/config'),
  updateConfig: (config: Record<string, unknown>) =>
    http.post('/api/device/config', { config }),
  resetConfig: () => http.post('/api/device/config/reset'),
  getSensors: () => http.get('/api/device/sensors'),
  reboot: () => http.post('/api/device/reboot'),
  ros2Diag: () => http.get('/api/device/ros2/diag'),
}

// =============================================================================
// VLM 场景理解 API
// vlm_node（ROS2 节点）会订阅 D435i 相机帧 + DOSOD/YOLO 检测框，按关键帧策略
// 调用 Qwen-VL / DeepSeek-Text 等 Provider 输出自然语言描述。
// 后端只做转发与历史聚合，所有推理在 ROS2 节点内完成。
// =============================================================================
export const vlmApi = {
  /** 获取 VLM 节点状态（provider、统计、最近错误） */
  getStatus: () => http.get('/api/vlm/status'),
  /** 获取最新一条场景描述 */
  getLatest: () => http.get('/api/vlm/latest'),
  /** 获取历史描述（默认 20 条，最多 50） */
  getHistory: (limit: number = 20) => http.get(`/api/vlm/history?limit=${limit}`),
  /** 手动触发一次 VLM 推理（可选自定义 prompt） */
  ask: (prompt: string = '', timeout_sec: number = 15) =>
    http.post('/api/vlm/ask', { prompt, timeout_sec }, { timeout: (timeout_sec + 5) * 1000 }),
}

// =============================================================================
// 系统 API
// =============================================================================
export const systemApi = {
  health: () => http.get('/api/health'),
  wsStats: () => http.get('/api/ws/stats'),
}

export default http
