<template>
  <div class="nav-view">
    <el-row :gutter="12">
      <!-- 地图导航区域 -->
      <el-col :xs="24" :sm="16">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Position /></el-icon> 导航地图</span>
            <div class="actions">
              <el-tag size="small" :type="navStatus.active ? 'success' : 'info'">
                {{ navStatus.active ? '导航中' : '空闲' }}
              </el-tag>
              <!-- 安全动作徽标（clear/reroute/stop） -->
              <el-tag size="small" :type="safetyTagType(currentAction)" effect="dark">
                {{ safetyActionLabel(currentAction) }}
              </el-tag>
            </div>
          </div>
          <div class="nav-map-area">
            <!-- 动态障碍可视化：机器人为原点，前方 x 轴，左右 y 轴（相机坐标系）-->
            <svg
              class="obstacle-canvas"
              viewBox="-3 -3 6 6"
              preserveAspectRatio="xMidYMid meet"
            >
              <!-- 网格 -->
              <g class="grid">
                <line v-for="d in gridLines" :key="'v'+d"
                      :x1="d" :y1="-3" :x2="d" :y2="3" />
                <line v-for="d in gridLines" :key="'h'+d"
                      :x1="-3" :y1="d" :x2="3" :y2="d" />
              </g>
              <!-- 距离环 -->
              <circle cx="0" cy="0" r="0.8" fill="none"
                      stroke="#ff4d4f" stroke-dasharray="0.05 0.05"
                      stroke-width="0.02" />
              <circle cx="0" cy="0" r="1.2" fill="none"
                      stroke="#faad14" stroke-dasharray="0.05 0.05"
                      stroke-width="0.02" />
              <circle cx="0" cy="0" r="2.5" fill="none"
                      stroke="#1890ff" stroke-dasharray="0.05 0.05"
                      stroke-width="0.02" />
              <!-- 相机视锥 (87°) -->
              <path d="M0,0 L2.85,-2.85 L2.85,2.85 Z"
                    fill="rgba(30,144,255,0.05)" stroke="none" />
              <!-- 机器人 -->
              <g class="robot">
                <circle cx="0" cy="0" r="0.15"
                        fill="#00d4ff" stroke="#fff" stroke-width="0.03" />
                <line x1="0" y1="0" x2="0.3" y2="0"
                      stroke="#00d4ff" stroke-width="0.05" />
              </g>
              <!-- 动态障碍点（红点，注意 SVG y 轴向下所以 y 需要取反） -->
              <g class="obstacles">
                <circle
                  v-for="(pt, idx) in obstaclePointsView"
                  :key="idx"
                  :cx="pt.x"
                  :cy="-pt.y"
                  r="0.08"
                  fill="#ff4d4f"
                  fill-opacity="0.85"
                />
              </g>
            </svg>

            <!-- 图例 -->
            <div class="canvas-legend">
              <span class="lg-item"><span class="dot robot"></span>机器人</span>
              <span class="lg-item"><span class="dot obs"></span>动态障碍点</span>
              <span class="lg-item"><span class="ring stop"></span>停车 0.8m</span>
              <span class="lg-item"><span class="ring warn"></span>绕行 1.2m</span>
              <span class="lg-item"><span class="ring far"></span>感知 2.5m</span>
            </div>

            <!-- 空态提示 -->
            <div
              v-if="obstaclePointsView.length === 0 && currentAction === 'clear'"
              class="canvas-hint"
            >
              <el-icon><MapLocation /></el-icon>
              暂无动态障碍。放置行人后此处会出现红点。
            </div>
          </div>
        </div>
      </el-col>

      <!-- 右侧控制 + 状态 -->
      <el-col :xs="24" :sm="8">
        <!-- 安全状态面板 -->
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title">
              <el-icon><WarningFilled /></el-icon> 动态行人避障
            </span>
            <el-tag size="small" :type="safetyTagType(currentAction)" effect="dark">
              {{ safetyActionLabel(currentAction) }}
            </el-tag>
          </div>
          <div class="status-section">
            <div class="status-item">
              <span class="label">最近距离</span>
              <span class="val mono" :class="{ danger: nearest !== null && nearest < 0.8 }">
                {{ nearest != null ? nearest.toFixed(2) + ' m' : '--' }}
              </span>
            </div>
            <div class="status-item">
              <span class="label">障碍点数</span>
              <span class="val mono">{{ obstaclePointsView.length }}</span>
            </div>
            <div class="status-item">
              <span class="label">人数（VLM）</span>
              <span class="val mono">{{ latest?.person_count ?? '--' }}</span>
            </div>
            <div class="status-item">
              <span class="label">累计绕行</span>
              <span class="val mono warn">{{ counters.reroute }}</span>
            </div>
            <div class="status-item">
              <span class="label">累计停车</span>
              <span class="val mono danger">{{ counters.stop }}</span>
            </div>
            <div class="status-item">
              <span class="label">急停触发</span>
              <span class="val mono danger">{{ counters.estop }}</span>
            </div>
            <div class="status-item">
              <span class="label">重规划</span>
              <span class="val mono">{{ latest?.replan_count ?? 0 }}</span>
            </div>
            <div class="status-item">
              <span class="label">推理后端</span>
              <span class="val" :class="isLocal ? 'ok' : 'warn'">
                {{ currentBackendLabel }}
              </span>
            </div>
          </div>
          <div v-if="latest?.reason" class="reason-box">
            <div class="reason-title">最近判定</div>
            <div class="reason-text">{{ latest.reason }}</div>
          </div>
        </div>

        <!-- 导航控制 -->
        <div class="tech-card mt8">
          <div class="card-header"><span class="card-title">导航控制</span></div>

          <!-- 算法选择 -->
          <div class="ctrl-section">
            <div class="ctrl-label">规划算法</div>
            <el-select v-model="selectedAlgo" size="small" class="full-width">
              <el-option v-for="a in algorithms" :key="a" :label="a" :value="a" />
            </el-select>
          </div>

          <!-- 目标点设置 -->
          <div class="ctrl-section">
            <div class="ctrl-label">目标点坐标</div>
            <el-row :gutter="6">
              <el-col :span="8">
                <el-input v-model.number="goalX" size="small" placeholder="X" />
              </el-col>
              <el-col :span="8">
                <el-input v-model.number="goalY" size="small" placeholder="Y" />
              </el-col>
              <el-col :span="8">
                <el-input v-model.number="goalYaw" size="small" placeholder="Yaw" />
              </el-col>
            </el-row>
          </div>

          <div class="ctrl-section btn-group">
            <el-button type="primary" size="small" @click="sendGoal">
              <el-icon><Position /></el-icon> 开始导航
            </el-button>
            <el-button type="danger" size="small" @click="cancelNav">
              <el-icon><Close /></el-icon> 取消
            </el-button>
          </div>

          <!-- 导航状态 -->
          <div class="status-section">
            <div class="status-item">
              <span class="label">状态</span>
              <span class="val">{{ navStatus.status }}</span>
            </div>
            <div class="status-item">
              <span class="label">剩余距离</span>
              <span class="val mono">{{ navStatus.distance_to_goal?.toFixed(2) ?? '--' }} m</span>
            </div>
            <div class="status-item">
              <span class="label">算法</span>
              <span class="val">{{ navStatus.algorithm ?? '--' }}</span>
            </div>
          </div>
        </div>

        <!-- 多点巡航 -->
        <div class="tech-card mt8">
          <div class="card-header">
            <span class="card-title">多点巡航（预留）</span>
          </div>
          <div class="waypoint-area">
            <div v-for="(wp, i) in waypoints" :key="i" class="wp-item">
              <span class="wp-idx">#{{ i + 1 }}</span>
              <span class="wp-coord">X:{{ wp.x }} Y:{{ wp.y }}</span>
              <el-button size="small" text type="danger" @click="waypoints.splice(i, 1)">×</el-button>
            </div>
            <el-button size="small" text @click="addWaypoint">+ 添加巡航点</el-button>
          </div>
          <el-button size="small" type="primary" :disabled="waypoints.length < 2" @click="startPatrol" class="mt8">
            开始巡航
          </el-button>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { wsClient } from '@/api/websocket'
import { navigationApi } from '@/api/http'
import { ElMessage } from 'element-plus'
import { useSafetyEvent, type SafetyAction } from '@/composables/useSafetyEvent'
import { useVlmProvider } from '@/composables/useVlmProvider'

// ── 原有导航状态 ─────────────────────────────────────────────────────────────
const algorithms   = ref(['nav2_default', 'a_star', 'rrt', 'dwa', 'teb'])
const selectedAlgo = ref('nav2_default')
const goalX   = ref(1.0)
const goalY   = ref(0.0)
const goalYaw = ref(0.0)
const navStatus = ref<any>({
  active: false, status: 'idle', distance_to_goal: 0, algorithm: '',
})
const waypoints = ref<Array<{ x: number; y: number }>>([])

const unsubNav = wsClient.on('navigation', (data: any) => {
  navStatus.value = data
})

// ── 安全事件（本地/云端 VLM 通用）─────────────────────────────────────────
const {
  latest,
  counters,
  currentBackendLabel,
} = useSafetyEvent()

const currentAction = computed<SafetyAction>(() => {
  const a = latest.value?.action
  if (a === 'stop' || a === 'reroute' || a === 'clear') return a
  return 'clear'
})

const { isLocal } = useVlmProvider()

// ── 动态障碍点云 (来自 dynamic_person_obstacle_node) ────────────────────
// backend/data_pusher 会把 PointCloud2 拆成 {points: [{x,y}, ...], count}
interface ObsPoint { x: number; y: number }
const obstaclePoints = ref<ObsPoint[]>([])

const unsubDyn = wsClient.on('dynamic_person_points', (data: any) => {
  if (!data) return
  const pts = Array.isArray(data.points) ? data.points : []
  obstaclePoints.value = pts
    .filter((p: any) => typeof p?.x === 'number' && typeof p?.y === 'number')
    .map((p: any) => ({ x: p.x, y: p.y }))
})

// 只画机器人 3m 内的点
const obstaclePointsView = computed<ObsPoint[]>(() => {
  return obstaclePoints.value.filter(p => {
    const d = Math.hypot(p.x, p.y)
    return d <= 3.0
  })
})

const nearest = computed<number | null>(() => {
  const pts = obstaclePointsView.value
  if (!pts.length) return latest.value?.min_distance_m ?? null
  let m = Infinity
  for (const p of pts) {
    const d = Math.hypot(p.x, p.y)
    if (d < m) m = d
  }
  return isFinite(m) ? m : null
})

const gridLines = [-3, -2, -1, 0, 1, 2, 3]

function safetyActionLabel(a: string): string {
  switch (a) {
    case 'stop':    return '🛑 停车'
    case 'reroute': return '🚧 绕行'
    case 'clear':   return '✅ 通畅'
    default:        return a || '-'
  }
}
function safetyTagType(a: string) {
  switch (a) {
    case 'stop':    return 'danger'
    case 'reroute': return 'warning'
    case 'clear':   return 'success'
    default:        return 'info'
  }
}

// ── 原有导航操作 ─────────────────────────────────────────────────────────────
async function sendGoal() {
  try {
    await navigationApi.setGoal(goalX.value, goalY.value, goalYaw.value)
    ElMessage.success('导航目标已设置')
  } catch { ElMessage.error('设置失败') }
}

async function cancelNav() {
  try {
    await navigationApi.cancel()
    ElMessage.info('导航已取消')
  } catch { ElMessage.error('取消失败') }
}

function addWaypoint() {
  waypoints.value.push({
    x: Math.round(Math.random() * 4 * 10) / 10,
    y: Math.round(Math.random() * 4 * 10) / 10,
  })
}

async function startPatrol() {
  try {
    await navigationApi.setWaypoints(waypoints.value)
    ElMessage.success(`已设置 ${waypoints.value.length} 个巡航点`)
  } catch { ElMessage.error('巡航设置失败') }
}

// ── 生命周期 ────────────────────────────────────────────────────────────────
onMounted(() => {
  navigationApi.getStatus()
    .then((r: any) => { navStatus.value = r })
    .catch(() => {})
})
onUnmounted(() => {
  unsubNav()
  unsubDyn()
})
</script>

<style lang="scss" scoped>
.nav-view { display: flex; flex-direction: column; gap: 12px; }
.mt8 { margin-top: 12px; }
.actions { display: flex; align-items: center; gap: 6px; }
.full-width { width: 100%; }

// ── 障碍可视化 ──────────────────────────────────────────────────────────────
.nav-map-area {
  position: relative;
  height: 420px;
  background: #050a14;
  border-radius: 6px;
  overflow: hidden;
}

.obstacle-canvas {
  width: 100%;
  height: 100%;
  display: block;

  .grid line {
    stroke: rgba(30, 144, 255, 0.15);
    stroke-width: 0.005;
  }
  .robot circle {
    filter: drop-shadow(0 0 4px #00d4ff);
  }
  .obstacles circle {
    filter: drop-shadow(0 0 3px #ff4d4f);
    animation: obs-pulse 1.4s ease-in-out infinite;
  }
}

@keyframes obs-pulse {
  0%, 100% { fill-opacity: 0.85; }
  50%      { fill-opacity: 0.4; }
}

.canvas-legend {
  position: absolute;
  top: 8px;
  left: 10px;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 11px;
  color: var(--color-text-muted);
  pointer-events: none;

  .lg-item {
    display: inline-flex;
    align-items: center;
    gap: 4px;
  }
  .dot {
    width: 8px; height: 8px; border-radius: 50%;
    display: inline-block;
    &.robot { background: #00d4ff; box-shadow: 0 0 6px #00d4ff; }
    &.obs   { background: #ff4d4f; box-shadow: 0 0 6px #ff4d4f; }
  }
  .ring {
    width: 10px; height: 10px; border-radius: 50%;
    display: inline-block; border: 1px dashed;
    &.stop { border-color: #ff4d4f; }
    &.warn { border-color: #faad14; }
    &.far  { border-color: #1890ff; }
  }
}

.canvas-hint {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(0, 0, 0, 0.55);
  color: var(--color-text-muted);
  font-size: 12px;
  border-radius: 20px;
  border: 1px solid rgba(30, 144, 255, 0.2);
  pointer-events: none;
}

.ctrl-section {
  margin-bottom: 12px;
  .ctrl-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 6px; }
  &.btn-group { display: flex; gap: 8px; }
}

.status-section {
  margin-top: 12px;
  .status-item {
    display: flex; justify-content: space-between; padding: 5px 0;
    border-bottom: 1px solid rgba(30,58,95,0.4);
    .label { font-size: 11px; color: var(--color-text-muted); }
    .val { font-size: 12px; color: var(--color-text); }
    .mono { font-family: var(--font-mono); }
    .danger { color: var(--color-danger, #ff4d4f); font-weight: 600; }
    .warn   { color: var(--color-warning, #faad14); font-weight: 600; }
    .ok     { color: var(--color-success, #22c55e); font-weight: 600; }
  }
}

.reason-box {
  margin-top: 10px;
  padding: 8px 10px;
  background: rgba(30, 58, 95, 0.35);
  border: 1px solid rgba(30, 58, 95, 0.6);
  border-radius: 6px;
  .reason-title {
    font-size: 10px;
    color: var(--color-text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .reason-text {
    font-size: 12px;
    line-height: 1.5;
    color: var(--color-text);
    word-break: break-word;
  }
}

.waypoint-area {
  .wp-item {
    display: flex; align-items: center; gap: 8px; padding: 4px 0;
    border-bottom: 1px solid rgba(30,58,95,0.3);
    .wp-idx { font-size: 11px; color: var(--color-primary); font-weight: 600; }
    .wp-coord { font-size: 11px; font-family: var(--font-mono); color: var(--color-text); flex: 1; }
  }
}
</style>
