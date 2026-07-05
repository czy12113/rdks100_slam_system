<template>
  <div class="control-view">
    <el-row :gutter="12">
      <!-- 左列：摇杆 + 方向按钮 + 键盘提示 -->
      <el-col :xs="24" :sm="10">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Promotion /></el-icon> 运动控制</span>
            <div style="display:flex;align-items:center;gap:8px;">
              <el-tooltip :content="tapMode ? '点按模式：每次按键递增/递减速度，空格急停' : '长按模式：松开按键自动停车'" placement="bottom">
                <el-button
                  size="small"
                  :type="tapMode ? 'warning' : 'primary'"
                  @click="toggleMode"
                  style="font-size:11px;padding:4px 8px;"
                >
                  <el-icon style="margin-right:3px;"><component :is="tapMode ? 'Pointer' : 'Aim'" /></el-icon>
                  {{ tapMode ? '点按' : '长按' }}
                </el-button>
              </el-tooltip>
              <el-tag size="small" :type="robotStore.isOnline ? 'success' : 'danger'">
                {{ robotStore.isOnline ? '在线' : '离线' }}
              </el-tag>
            </div>
          </div>

          <!-- 虚拟摇杆区域 -->
          <div class="joystick-area">
            <div ref="joystickRef" class="joystick-zone"></div>
            <div class="joystick-hint">拖动摇杆控制移动</div>
          </div>

          <!-- 方向按钮 -->
          <div class="dpad-area">
            <div class="dpad-row">
              <button
                class="dpad-btn"
                :class="{ active: keys.w }"
                @pointerdown="(e) => onDpadDown(e, 'w')"
                @pointerup="onDpadUp('w')"
                @pointercancel="onDpadUp('w')"
              >
                <el-icon><ArrowUp /></el-icon>
              </button>
            </div>
            <div class="dpad-row">
              <button
                class="dpad-btn"
                :class="{ active: keys.a }"
                @pointerdown="(e) => onDpadDown(e, 'a')"
                @pointerup="onDpadUp('a')"
                @pointercancel="onDpadUp('a')"
              >
                <el-icon><ArrowLeft /></el-icon>
              </button>
              <button
                class="dpad-btn stop-btn"
                @pointerdown.prevent="emergencyStop"
              >
                <el-icon><VideoPause /></el-icon>
              </button>
              <button
                class="dpad-btn"
                :class="{ active: keys.d }"
                @pointerdown="(e) => onDpadDown(e, 'd')"
                @pointerup="onDpadUp('d')"
                @pointercancel="onDpadUp('d')"
              >
                <el-icon><ArrowRight /></el-icon>
              </button>
            </div>
            <div class="dpad-row">
              <button
                class="dpad-btn"
                :class="{ active: keys.s }"
                @pointerdown="(e) => onDpadDown(e, 's')"
                @pointerup="onDpadUp('s')"
                @pointercancel="onDpadUp('s')"
              >
                <el-icon><ArrowDown /></el-icon>
              </button>
            </div>
          </div>

          <!-- 点按模式速度显示 -->
          <div v-if="tapMode" class="tap-vel-display">
            <div class="tap-vel-item">
              <span class="tap-label">线速度</span>
              <span class="tap-val mono" :class="tapVx > 0 ? 'pos' : tapVx < 0 ? 'neg' : ''">
                {{ tapVx >= 0 ? '+' : '' }}{{ tapVx.toFixed(2) }} <span class="unit">m/s</span>
              </span>
            </div>
            <div class="tap-vel-item">
              <span class="tap-label">角速度</span>
              <span class="tap-val mono" :class="tapWz > 0 ? 'pos' : tapWz < 0 ? 'neg' : ''">
                {{ tapWz >= 0 ? '+' : '' }}{{ tapWz.toFixed(2) }} <span class="unit">rad/s</span>
              </span>
            </div>
          </div>

          <!-- WASD 键盘提示 -->
          <div class="keyboard-hint">
            <div class="key-row"><div class="key" :class="{ active: keys.w }">W</div></div>
            <div class="key-row">
              <div class="key" :class="{ active: keys.a }">A</div>
              <div class="key" :class="{ active: keys.s }">S</div>
              <div class="key" :class="{ active: keys.d }">D</div>
            </div>
            <div class="key-desc" v-if="!tapMode">前进 / 左转 / 后退 / 右转 &nbsp;|&nbsp; 空格键急停</div>
            <div class="key-desc" v-else>每次按键递增/递减速度 &nbsp;|&nbsp; 空格键急停归零</div>
          </div>
        </div>
      </el-col>

      <!-- 右列 -->
      <el-col :xs="24" :sm="14">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title">速度参数</span>
          </div>
          <div class="speed-control">
            <div class="speed-row">
              <span class="label">线速度</span>
              <el-slider v-model="linearSpeed" :min="0.05" :max="ROBOT_MAX_LINEAR_VEL" :step="0.05" show-input size="small" class="slider" />
              <span class="unit">m/s</span>
            </div>
            <div class="speed-row">
              <span class="label">角速度</span>
              <el-slider v-model="angularSpeed" :min="0.05" :max="ROBOT_MAX_ANGULAR_VEL" :step="0.05" show-input size="small" class="slider" />
              <span class="unit">rad/s</span>
            </div>
          </div>

          <!-- 实时速度仪表盘 -->
          <div class="vel-dashboard">
            <div class="vel-gauge">
              <div class="gauge-label">线速度</div>
              <div class="gauge-bar-wrap">
                <div
                  class="gauge-bar"
                  :class="velBarClass(displayVx)"
                  :style="{ width: velBarWidth(displayVx, ROBOT_MAX_LINEAR_VEL), marginLeft: displayVx < 0 ? 'auto' : '0' }"
                ></div>
              </div>
              <div class="gauge-val mono">{{ displayVx.toFixed(3) }} <span class="unit">m/s</span></div>
            </div>
            <div class="vel-gauge">
              <div class="gauge-label">角速度</div>
              <div class="gauge-bar-wrap">
                <div
                  class="gauge-bar angular"
                  :class="velBarClass(displayWz)"
                  :style="{ width: velBarWidth(displayWz, ROBOT_MAX_ANGULAR_VEL), marginLeft: displayWz < 0 ? 'auto' : '0' }"
                ></div>
              </div>
              <div class="gauge-val mono">{{ displayWz.toFixed(3) }} <span class="unit">rad/s</span></div>
            </div>
          </div>

          <!-- 急停按钮 -->
          <el-button
            type="danger"
            size="large"
            class="estop-btn"
            @pointerdown.prevent="emergencyStop"
          >
            <el-icon><VideoPause /></el-icon>
            紧急停止 (Space)
          </el-button>
        </div>

        <!-- 里程计卡片 -->
        <div class="tech-card" style="margin-top: 12px;">
          <div class="card-header">
            <span class="card-title"><el-icon><Position /></el-icon> 里程计 / 位姿</span>
            <el-button size="small" text @click="resetOdom">重置</el-button>
          </div>
          <div class="odom-grid">
            <div class="odom-item">
              <span class="odom-label">X 坐标</span>
              <span class="odom-val mono">{{ displayPose.x.toFixed(3) }} <span class="unit">m</span></span>
            </div>
            <div class="odom-item">
              <span class="odom-label">Y 坐标</span>
              <span class="odom-val mono">{{ displayPose.y.toFixed(3) }} <span class="unit">m</span></span>
            </div>
            <div class="odom-item">
              <span class="odom-label">朝向角</span>
              <span class="odom-val mono">{{ (displayPose.yaw * 180 / Math.PI).toFixed(1) }} <span class="unit">°</span></span>
            </div>
            <div class="odom-item">
              <span class="odom-label">累计距离</span>
              <span class="odom-val mono">{{ totalDistance.toFixed(2) }} <span class="unit">m</span></span>
            </div>
          </div>
        </div>

        <!-- 控制日志 -->
        <div class="tech-card" style="margin-top: 12px;">
          <div class="card-header">
            <span class="card-title"><el-icon><Document /></el-icon> 控制日志</span>
            <el-button size="small" text @click="controlLogs = []">清空</el-button>
          </div>
          <div ref="logRef" class="ctrl-log-area">
            <div
              v-for="(log, i) in controlLogs.slice(-50)"
              :key="i"
              class="ctrl-log-line"
              :class="`log-${log.level}`"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-msg">{{ log.msg }}</span>
            </div>
            <div v-if="controlLogs.length === 0" class="log-empty">暂无控制日志</div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import nipplejs from 'nipplejs'
import { controlApi } from '@/api/http'
import { wsClient } from '@/api/websocket'
import { useRobotStore } from '@/stores/robot'
import {
  ROBOT_MAX_LINEAR_VEL, ROBOT_MAX_ANGULAR_VEL,
  ROBOT_DEFAULT_LINEAR_VEL, ROBOT_DEFAULT_ANGULAR_VEL,
} from '@/config'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'

const robotStore = useRobotStore()
const joystickRef = ref<HTMLElement>()
const logRef = ref<HTMLElement>()

const linearSpeed  = ref(ROBOT_DEFAULT_LINEAR_VEL)
const angularSpeed = ref(ROBOT_DEFAULT_ANGULAR_VEL)

// 本地显示用速度（WebSocket 有实际里程计数据时会覆盖）
const cmdVx = ref(0)
const cmdWz = ref(0)
const displayCmdUntil = ref(0)
let displayCmdTimer: ReturnType<typeof setTimeout> | null = null

// v11.2: 当 STM32 端 ODOMETRY_READ_ENCODER=0 时底盘反馈速度恒为 0，
// 用一段较长的兜底窗口在 odom 速度为 0 但近期下发过非零命令时显示命令值。
const STALE_VELOCITY_FALLBACK_MS = 1500
const lastNonZeroCmdAt = ref(0)

const odomOffsetX   = ref(0)
const odomOffsetY   = ref(0)
const odomOffsetYaw = ref(0)

interface CtrlLog { time: string; msg: string; level: 'info' | 'warn' | 'error' }
const controlLogs = ref<CtrlLog[]>([])

const keys = ref({ w: false, a: false, s: false, d: false })

// ── 控制模式 ──────────────────────────────────────────────────────────
const tapMode = ref(false)
const tapVx   = ref(0)
const tapWz   = ref(0)

/**
 * v11.1 防锁死修复：
 * tapMode 步长不再写死。直接使用 linearSpeed / angularSpeed（速度滑条）作为
 * 单次按键的增量，这样：
 *   1. 滑条调小 → 点按一次的速度变化也变小，"调速滑条对点按生效"。
 *   2. 滑条调大 → 点按一次直接到目标速度，避免连按累加到危险高速。
 * 同时保留最大不超过 ROBOT_MAX_* 的硬上限。
 */
function getTapVxStep(): number {
  return Math.min(Math.max(linearSpeed.value, 0.01), ROBOT_MAX_LINEAR_VEL)
}
function getTapWzStep(): number {
  return Math.min(Math.max(angularSpeed.value, 0.01), ROBOT_MAX_ANGULAR_VEL)
}

/**
 * v11.1 防锁死修复：tapMode 自动清零定时器
 *
 * 现象：点按一次"前进"后 tapVx 保持非零，sendLoop 每 50ms 持续向后端发非零
 *       /cmd_vel，导致小车一直走（"按一下就锁死"）。
 * 修复：每次 tapStep 调用都重启一个 TAP_AUTO_ZERO_MS 倒计时；倒计时到期且
 *       tapVx/tapWz 仍非零则强制归零并发零速。等价于"3 秒内没新点按 → 停车"。
 *       3000ms 是经验值：足够 Ackermann 完成一个小直线机动，又远小于人类
 *       "忘了在控制车"的反应时间。
 */
const TAP_AUTO_ZERO_MS = 3000
let tapAutoZeroTimer: ReturnType<typeof setTimeout> | null = null

function clearTapAutoZeroTimer() {
  if (tapAutoZeroTimer) {
    clearTimeout(tapAutoZeroTimer)
    tapAutoZeroTimer = null
  }
}

function scheduleTapAutoZero() {
  clearTapAutoZeroTimer()
  tapAutoZeroTimer = setTimeout(() => {
    tapAutoZeroTimer = null
    if (tapMode.value && (tapVx.value !== 0 || tapWz.value !== 0)) {
      tapVx.value = 0
      tapWz.value = 0
      targetVx = 0
      targetWz = 0
      sendVelNow(0, 0)
      addLog(`点按模式 ${TAP_AUTO_ZERO_MS / 1000}s 无新操作，自动归零`, 'warn')
    }
  }, TAP_AUTO_ZERO_MS)
}

function toggleMode() {
  tapMode.value = !tapMode.value
  tapVx.value = 0
  tapWz.value = 0
  targetVx = 0
  targetWz = 0
  keys.value = { w: false, a: false, s: false, d: false }
  clearTapAutoZeroTimer()
  // 切换模式时立即发一次零速
  sendVelNow(0, 0)
  addLog(`已切换到${tapMode.value ? '点按' : '长按'}模式`, 'info')
}

let joystick: ReturnType<typeof nipplejs.create> | null = null
let unsubOdom: (() => void) | null = null

// ── 计算属性 ──────────────────────────────────────────────────────────
const DISPLAY_CMD_HOLD_MS = 300
const isDisplayingCommandVelocity = computed(() => displayCmdUntil.value > Date.now())
// 兜底：odom 速度 ≈ 0 且最近 STALE_VELOCITY_FALLBACK_MS 内下发过非零命令时，
// 用命令值代替反馈值显示。一旦 odom 出现非零反馈立刻让位给真实数据。
function shouldFallbackToCmd(odomVal: number): boolean {
  if (Math.abs(odomVal) > 1e-3) return false
  return Date.now() - lastNonZeroCmdAt.value < STALE_VELOCITY_FALLBACK_MS
}
const displayVx = computed(() => {
  if (isDisplayingCommandVelocity.value) return cmdVx.value
  const v = robotStore.currentVelocity.linear_x
  if (shouldFallbackToCmd(v)) return cmdVx.value
  return v
})
const displayWz = computed(() => {
  if (isDisplayingCommandVelocity.value) return cmdWz.value
  const w = robotStore.currentVelocity.angular_z
  if (shouldFallbackToCmd(w)) return cmdWz.value
  return w
})
const displayPose = computed(() => {
  const p = robotStore.currentPose
  return { x: p.x - odomOffsetX.value, y: p.y - odomOffsetY.value, yaw: p.yaw - odomOffsetYaw.value }
})
const totalDistance = computed(() => {
  return robotStore.odomData?.odometry?.total_distance ?? robotStore.robotStatus?.odometry?.total_distance ?? 0
})
function velBarClass(val: number) {
  const abs = Math.abs(val)
  if (abs > 0.6) return 'high'
  if (abs > 0.2) return 'mid'
  return 'low'
}
function velBarWidth(val: number, max: number) {
  return Math.min(Math.abs(val) / max * 100, 100) + '%'
}

function updateCommandDisplay(vx: number, wz: number) {
  cmdVx.value = vx
  cmdWz.value = wz
  displayCmdUntil.value = Date.now() + DISPLAY_CMD_HOLD_MS

  // 记录最近一次"实际下发"的非零命令时间，给 STALE_VELOCITY_FALLBACK_MS 兜底窗口提供基准
  if (Math.abs(vx) > 1e-3 || Math.abs(wz) > 1e-3) {
    lastNonZeroCmdAt.value = Date.now()
  }

  if (displayCmdTimer) clearTimeout(displayCmdTimer)
  displayCmdTimer = setTimeout(() => {
    displayCmdTimer = null
    if (Date.now() >= displayCmdUntil.value) {
      displayCmdUntil.value = 0
    }
  }, DISPLAY_CMD_HOLD_MS)
}

// ── 控制参数 ──────────────────────────────────────────────────────────
const JOYSTICK_DEADZONE = 0.08
const JOYSTICK_SIZE     = 140
/**
 * v11.0：摇杆轴吸附阈值（±15°）
 *
 * 现象：触屏 / 鼠标拖摇杆几乎无法精准对准 90°，几度偏角就给出一个
 * 稳定的小 angular.z（如 ~0.07 rad/s），导致 Ackermann 底盘"前进时
 * 持续小角度转弯"走圈。
 *
 * 修复：靠近 0 / π/2 / π / 3π/2（即 D-pad 四方向）时，强制吸附到
 * 正交轴。允许的有效角度区间是 [c-15°, c+15°]，超出阈值才按真实
 * 角度计算 vx / wz 分量。
 *
 * 15° 是用户体验经验值：太小（< 10°）用户感觉"摇杆失灵"，
 * 太大（> 20°）会失去斜向运动能力。
 */
const JOYSTICK_SNAP_RAD = Math.PI / 12   // 15°
const JOYSTICK_CARDINALS = [
  0,                  // 右（纯右转）
  Math.PI / 2,        // 上（纯前进）
  Math.PI,            // 左（纯左转）
  3 * Math.PI / 2,    // 下（纯后退）
  2 * Math.PI,        // 右（跨周回环，等价于 0）
]
/**
 * 发送间隔 50ms（20Hz）
 * stm32_bridge CMD_TIMEOUT=0.5s，50ms 轮询远小于超时阈值，不会触发误停车
 */
const SEND_INTERVAL_MS  = 50
const DIAGONAL_SCALE    = 0.707

// 目标速度（由键盘/摇杆写入，由 sendLoop 读取）
let targetVx = 0
let targetWz = 0
let sendTimer: ReturnType<typeof setInterval> | null = null
let joystickActive = false

// 上一帧已发送的速度，用于"到达零速后不再重复发零"优化
let _sentVx = 0
let _sentWz = 0

// 急停状态标志：true 时 sendLoop 跳过，防止定时器覆盖急停
let _estopActive = false

/**
 * v11.1 防锁死修复：用户最近一次有效输入时间戳 + 硬超时
 *
 * 现象：tapMode 或长按模式下，sendLoop 每 50ms 把 targetVx/Wz 持续发往后端，
 *       一旦上层逻辑因 bug（如 pointer 丢失、按键卡住）忘了归零，
 *       小车就会持续运动直到撞到东西或人按急停。
 * 修复：每次"用户主动输入"刷新 lastUserInputTs；sendLoop 每帧检查，
 *       若处于非零速且距上次输入超过 SEND_HARD_TIMEOUT_MS（5 秒），
 *       无条件归零并发零速。
 */
const SEND_HARD_TIMEOUT_MS = 5000
let lastUserInputTs = 0
function markUserInput() {
  lastUserInputTs = Date.now()
}

// ── 核心发送函数 ──────────────────────────────────────────────────────
/**
 * 立即发送速度（主通道：WebSocket；fallback：HTTP）
 * WebSocket 无网络往返延迟，不会有请求堆积问题。
 * 只有 WebSocket 断开时才 fallback 到 HTTP。
 */
function sendVelNow(vx: number, wz: number) {
  updateCommandDisplay(vx, wz)
  _sentVx = vx
  _sentWz = wz

  // 优先走 WebSocket（低延迟，无堆积）
  const sent = wsClient.sendCmdVel(vx, 0, wz)
  if (!sent) {
    // WebSocket 未连接：fallback 到 HTTP（静默失败）
    controlApi.setVelocity(vx, 0, wz).catch(() => {})
  }
}

/**
 * 急停：双通道并行发送（WebSocket + HTTP），确保必然送达
 * 不再额外调用 setVelocity(0,0,0)，避免竞态覆盖
 */
function doForceStop() {
  updateCommandDisplay(0, 0)
  _sentVx = 0
  _sentWz = 0
  targetVx = 0
  targetWz = 0

  // WebSocket 通道：后端发 5 帧零速
  wsClient.sendEstop()
  // HTTP 通道：独立请求，不受 WebSocket 状态影响（双保险）
  controlApi.stop().catch(() => {})
}

// ── 摇杆 ─────────────────────────────────────────────────────────────
function initJoystick() {
  if (!joystickRef.value) return
  joystick = nipplejs.create({
    zone: joystickRef.value,
    mode: 'static',
    position: { left: '50%', top: '50%' },
    color: '#00d4ff',
    size: JOYSTICK_SIZE,
    restOpacity: 0.6,
    fadeTime: 100,
  })

  joystick.on('start', () => {
    joystickActive = true
    _estopActive = false
    markUserInput()
  })

  joystick.on('move', (_evt: any, data: any) => {
    if (_estopActive) return
    markUserInput()
    const force = Math.min(data.force, 1)
    if (force < JOYSTICK_DEADZONE) {
      targetVx = 0
      targetWz = 0
      return
    }
    const mappedForce = (force - JOYSTICK_DEADZONE) / (1 - JOYSTICK_DEADZONE)
    let angle = data.angle.radian

    // v11.0：四方向轴吸附（±15°）
    // 靠近 0 / π/2 / π / 3π/2 时强制贴到正交轴，杜绝
    // 触屏拖摇杆时几度偏角导致的"前进时持续微转弯"走圈。
    for (const c of JOYSTICK_CARDINALS) {
      if (Math.abs(angle - c) <= JOYSTICK_SNAP_RAD) {
        angle = c
        break
      }
    }

    targetVx =  Math.sin(angle) * mappedForce * linearSpeed.value
    targetWz = -Math.cos(angle) * mappedForce * angularSpeed.value
  })

  joystick.on('end', () => {
    joystickActive = false
    targetVx = 0
    targetWz = 0
    // 摇杆松开：立即发零速，不等定时器下一拍
    if (!_estopActive) {
      sendVelNow(0, 0)
    }
  })
}

// ── 方向按钮 ─────────────────────────────────────────────────────────
function onDpadDown(e: PointerEvent, key: 'w' | 'a' | 's' | 'd') {
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  if (_estopActive) return
  markUserInput()
  if (tapMode.value) {
    tapStep(key)
  } else {
    keys.value[key] = true
  }
}

function onDpadUp(key: 'w' | 'a' | 's' | 'd') {
  if (!tapMode.value) {
    keys.value[key] = false
    if (!keys.value.w && !keys.value.a && !keys.value.s && !keys.value.d && !joystickActive) {
      targetVx = 0
      targetWz = 0
      // 松键立即发零速，不等定时器
      if (!_estopActive) {
        sendVelNow(0, 0)
      }
    }
  }
}

function tapStep(key: 'w' | 'a' | 's' | 'd') {
  if (_estopActive) return
  markUserInput()
  const maxVx = ROBOT_MAX_LINEAR_VEL
  const maxWz = ROBOT_MAX_ANGULAR_VEL
  // v11.1：步长来源于滑条而不是常量，滑条调速对点按生效
  const stepVx = getTapVxStep()
  const stepWz = getTapWzStep()
  if (key === 'w') tapVx.value = Math.min(tapVx.value + stepVx, maxVx)
  if (key === 's') tapVx.value = Math.max(tapVx.value - stepVx, -maxVx)
  if (key === 'a') tapWz.value = Math.min(tapWz.value + stepWz, maxWz)
  if (key === 'd') tapWz.value = Math.max(tapWz.value - stepWz, -maxWz)
  targetVx = tapVx.value
  targetWz = tapWz.value
  // v11.1：每次点按都重启自动归零倒计时，TAP_AUTO_ZERO_MS 秒无新操作 → 自动停车
  scheduleTapAutoZero()
  addLog(`点按 ${key.toUpperCase()}: vx=${tapVx.value.toFixed(2)}, wz=${tapWz.value.toFixed(2)}`, 'info')
}

// ── 键盘 ─────────────────────────────────────────────────────────────
function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const k = e.key.toLowerCase()
  if (k === ' ') { emergencyStop(); e.preventDefault(); return }

  if (_estopActive) return  // 急停状态下屏蔽其他按键

  if (tapMode.value) {
    if (e.repeat) return
    if (k === 'w' || k === 'arrowup')    { tapStep('w'); e.preventDefault() }
    if (k === 'a' || k === 'arrowleft')  { tapStep('a'); e.preventDefault() }
    if (k === 's' || k === 'arrowdown')  { tapStep('s'); e.preventDefault() }
    if (k === 'd' || k === 'arrowright') { tapStep('d'); e.preventDefault() }
  } else {
    let hit = false
    if (k === 'w' || k === 'arrowup')    { keys.value.w = true; hit = true; e.preventDefault() }
    if (k === 'a' || k === 'arrowleft')  { keys.value.a = true; hit = true; e.preventDefault() }
    if (k === 's' || k === 'arrowdown')  { keys.value.s = true; hit = true; e.preventDefault() }
    if (k === 'd' || k === 'arrowright') { keys.value.d = true; hit = true; e.preventDefault() }
    if (hit) markUserInput()
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (tapMode.value) return
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const k = e.key.toLowerCase()
  if (k === 'w' || k === 'arrowup')    keys.value.w = false
  if (k === 'a' || k === 'arrowleft')  keys.value.a = false
  if (k === 's' || k === 'arrowdown')  keys.value.s = false
  if (k === 'd' || k === 'arrowright') keys.value.d = false

  if (!keys.value.w && !keys.value.a && !keys.value.s && !keys.value.d && !joystickActive) {
    targetVx = 0
    targetWz = 0
    if (!_estopActive) {
      sendVelNow(0, 0)
    }
  }
}

function calcKeyTarget(): { vx: number; wz: number } {
  let vx = 0, wz = 0
  if (keys.value.w) vx += linearSpeed.value
  if (keys.value.s) vx -= linearSpeed.value
  if (keys.value.a) wz += angularSpeed.value
  if (keys.value.d) wz -= angularSpeed.value
  if (vx !== 0 && wz !== 0) {
    vx *= DIAGONAL_SCALE
    wz *= DIAGONAL_SCALE
  }
  return { vx, wz }
}

// ── 发送循环 ─────────────────────────────────────────────────────────
/**
 * 50ms 定时发送（20Hz），核心设计原则：
 *
 * 1. 急停状态（_estopActive=true）直接跳过，防止定时器覆盖急停指令
 * 2. 非零速时每帧都发：stm32_bridge 需要持续收到指令才能保持运动
 *    （CMD_TIMEOUT=0.3s，50ms 远小于超时阈值）
 * 3. 零速状态：只在"上一帧刚从非零变为零"时发一次，之后不再重复发零
 *    （防止大量零速帧刷串口）
 * 4. 通过 WebSocket 发送（无 HTTP 往返延迟，无请求堆积）
 */
function startSendLoop() {
  sendTimer = setInterval(() => {
    // 急停状态：跳过，防止覆盖急停指令
    if (_estopActive) return

    // 更新目标速度（键盘/tap 模式）
    if (!joystickActive) {
      if (!tapMode.value) {
        const kt = calcKeyTarget()
        targetVx = kt.vx
        targetWz = kt.wz
      }
      // tap 模式：targetVx/Wz 由 tapStep 直接写入
    }

    // v11.1 防锁死硬超时兜底：连续非零速且距上次用户输入超 SEND_HARD_TIMEOUT_MS 强制归零
    // 这是最后一道防线，即使 tapStep 自动归零定时器 / pointer 事件全部失效，
    // SEND_HARD_TIMEOUT_MS 秒后仍能保证不会持续向小车发送非零速度。
    if (targetVx !== 0 || targetWz !== 0) {
      if (lastUserInputTs > 0 && Date.now() - lastUserInputTs > SEND_HARD_TIMEOUT_MS) {
        targetVx = 0
        targetWz = 0
        tapVx.value = 0
        tapWz.value = 0
        keys.value = { w: false, a: false, s: false, d: false }
        clearTapAutoZeroTimer()
        sendVelNow(0, 0)
        addLog(`前端硬超时：${SEND_HARD_TIMEOUT_MS / 1000}s 无新输入，自动停车`, 'warn')
        return
      }
      // 非零速：每帧都发，保持电机持续运转
      sendVelNow(targetVx, targetWz)
    } else {
      // 目标归零：只在"刚归零"时发一次，避免重复刷零速
      if (_sentVx !== 0 || _sentWz !== 0) {
        sendVelNow(0, 0)
      }
      // 否则：已是零速，不重复发
    }
  }, SEND_INTERVAL_MS)
}

// ── 急停 ─────────────────────────────────────────────────────────────
/**
 * 急停：
 * 1. 设置 _estopActive 标志，阻止 sendLoop 和其他控制路径覆盖
 * 2. 双通道并行：WebSocket（低延迟） + HTTP（可靠）
 * 3. 300ms 后自动解除急停标志（允许下次操作）
 *    比 stm32_bridge 看门狗超时(0.6s)短，但足够让停车帧到达
 */
function emergencyStop() {
  _estopActive = true

  // 清零所有控制状态
  keys.value = { w: false, a: false, s: false, d: false }
  tapVx.value = 0
  tapWz.value = 0
  joystickActive = false
  clearTapAutoZeroTimer()

  // 双通道发送急停
  doForceStop()

  // 300ms 后解除急停锁定（允许重新操作）
  setTimeout(() => { _estopActive = false }, 300)

  addLog('急停已触发', 'warn')
  ElMessage.warning('急停已执行')
}

function resetOdom() {
  const p = robotStore.currentPose
  odomOffsetX.value   = p.x
  odomOffsetY.value   = p.y
  odomOffsetYaw.value = p.yaw
  addLog('里程计已重置', 'info')
  ElMessage.success('里程计已重置')
}

function addLog(msg: string, level: 'info' | 'warn' | 'error' = 'info') {
  controlLogs.value.push({ time: dayjs().format('HH:mm:ss'), msg, level })
  if (controlLogs.value.length > 200) controlLogs.value.shift()
}

watch(() => controlLogs.value.length, async () => {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
})

// ── 安全保护：失焦/可见性/断连/卸载 → 自动停车 ───────────────────────
let unsubWsStatus: (() => void) | null = null

/**
 * 安全停车（不强制激活急停锁，只把目标速度归零并发零速）。
 * 用于失焦/鼠标离开等"轻量"场景：避免用户回来时被锁住操作。
 */
function safeStopOnly(reason: string) {
  keys.value = { w: false, a: false, s: false, d: false }
  tapVx.value = 0
  tapWz.value = 0
  joystickActive = false
  targetVx = 0
  targetWz = 0
  clearTapAutoZeroTimer()
  // 直接发零速（双通道：WS + HTTP fallback）
  sendVelNow(0, 0)
  controlApi.setVelocity(0, 0, 0).catch(() => {})
  addLog(`安全停车：${reason}`, 'warn')
}

/**
 * 强急停（触发后端 SafetyGate 急停锁）。
 * 用于断开连接、页面卸载等不可逆场景。
 */
function hardEstop(reason: string) {
  _estopActive = true
  clearTapAutoZeroTimer()
  doForceStop()
  setTimeout(() => { _estopActive = false }, 300)
  addLog(`强制急停：${reason}`, 'error')
}

// ── v11.2 修复"按下 W/S 电机转一会停一会"问题 ───────────────────────
// 现象：用户长按 W 时，会下意识把鼠标移到浏览器窗口外去看小车，
//   或者快速切窗口/Alt+Tab，导致 onMouseLeave / onWindowBlur 触发
//   safeStopOnly → keys 被清空 → 必须松开重按才能继续走。
// 修复策略：
//   1. 完全移除 onMouseLeave 监听（鼠标飘出窗口属于正常使用场景）。
//   2. onWindowBlur 添加 800ms 抖动窗口：失焦后等 800ms 再判定是否
//      仍处于失焦状态，避免瞬时切窗口造成误停。
//   3. visibilitychange（页面真正进入后台/最小化）保持原逻辑立即停。
let blurStopTimer: ReturnType<typeof setTimeout> | null = null
const BLUR_STOP_DEBOUNCE_MS = 800

function clearBlurStopTimer() {
  if (blurStopTimer) {
    clearTimeout(blurStopTimer)
    blurStopTimer = null
  }
}

function onVisibilityChange() {
  if (document.visibilityState === 'hidden') {
    // 页面真正被隐藏（切到后台/最小化）才立即停
    clearBlurStopTimer()
    safeStopOnly('页面隐藏')
  } else {
    // 回到前台：取消还在排队的 blur 停车
    clearBlurStopTimer()
  }
}
function onWindowBlur() {
  // 失焦后启动 800ms 抖动窗口：期间若 focus 回来则取消停车
  clearBlurStopTimer()
  blurStopTimer = setTimeout(() => {
    blurStopTimer = null
    // 只在仍处于失焦状态时执行停车
    if (!document.hasFocus()) {
      safeStopOnly('窗口失焦')
    }
  }, BLUR_STOP_DEBOUNCE_MS)
}
function onWindowFocus() {
  // 用户回到窗口：取消任何正在排队的 blur 停车
  clearBlurStopTimer()
}
function onPageHide()    { hardEstop('页面卸载/导航离开') }
function onBeforeUnload(){
  hardEstop('浏览器关闭')
  // 浏览器关闭时 WebSocket 大概率已无法发出，靠 sendBeacon 兜底
  wsClient.beaconEstop('/api/control/stop')
}

onMounted(() => {
  initJoystick()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)

  // ── 失焦/可见性/卸载安全钩子 ──
  // v11.2：移除 document.mouseleave（鼠标飘出浏览器属于正常操作）
  //         window.blur 加抖动 + focus 撤销，避免瞬时切窗口误停车
  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('blur', onWindowBlur)
  window.addEventListener('focus', onWindowFocus)
  window.addEventListener('pagehide', onPageHide)
  window.addEventListener('beforeunload', onBeforeUnload)

  // ── WebSocket 状态变化：断开 → 立即发 HTTP 停车 + 标记急停 ──
  unsubWsStatus = wsClient.onStatusChange((s) => {
    if (s === 'disconnected' || s === 'error') {
      hardEstop(`WebSocket ${s}`)
    }
  })

  startSendLoop()
  unsubOdom = wsClient.on('odom', () => {})

  // 进入页面立即同步一帧零速，确保后端 SafetyGate 状态干净
  sendVelNow(0, 0)

  addLog('控制界面已就绪（WebSocket 控制通道，含失焦/断连保护）', 'info')
  addLog('WASD/方向键/摇杆控制，空格键急停', 'info')
})

onUnmounted(() => {
  joystick?.destroy()
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  document.removeEventListener('visibilitychange', onVisibilityChange)
  window.removeEventListener('blur', onWindowBlur)
  window.removeEventListener('focus', onWindowFocus)
  window.removeEventListener('pagehide', onPageHide)
  window.removeEventListener('beforeunload', onBeforeUnload)
  clearBlurStopTimer()
  if (sendTimer) clearInterval(sendTimer)
  clearTapAutoZeroTimer()
  if (displayCmdTimer) clearTimeout(displayCmdTimer)
  if (unsubOdom) unsubOdom()
  if (unsubWsStatus) unsubWsStatus()
  // 离开/切换路由：双通道发送停车（含 SafetyGate 急停锁）
  wsClient.sendEstop()
  controlApi.stop().catch(() => {})
})
</script>

<style lang="scss" scoped>
.control-view { display: flex; flex-direction: column; gap: 12px; }

.joystick-area {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  .joystick-zone {
    width: 180px; height: 180px; background: rgba(0,212,255,0.05);
    border: 2px solid var(--color-border); border-radius: 50%; position: relative;
  }
  .joystick-hint { font-size: 11px; color: var(--color-text-muted); }
}

.dpad-area {
  display: flex; flex-direction: column; align-items: center; gap: 4px; margin: 12px 0;
  .dpad-row { display: flex; gap: 4px; }
}

.dpad-btn {
  width: 44px; height: 44px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-muted);
  font-size: 18px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.1s;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
  &:hover { border-color: var(--color-primary); color: var(--color-primary); }
  &.active {
    background: rgba(0,212,255,0.15);
    border-color: var(--color-primary);
    color: var(--color-primary);
    transform: scale(0.95);
  }
  &.stop-btn {
    background: rgba(255,68,68,0.1);
    border-color: var(--color-danger);
    color: var(--color-danger);
    &:hover { background: rgba(255,68,68,0.2); }
    &:active { transform: scale(0.95); }
  }
}

.keyboard-hint {
  display: flex; flex-direction: column; align-items: center; gap: 4px; margin-top: 4px;
  .key-row { display: flex; gap: 4px; }
  .key {
    width: 28px; height: 28px; border: 1px solid var(--color-border);
    border-radius: 4px; display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 600; color: var(--color-text-muted);
    background: var(--color-bg-panel); transition: all 0.1s;
    &.active { background: rgba(0,212,255,0.2); border-color: var(--color-primary); color: var(--color-primary); }
  }
  .key-desc { font-size: 10px; color: var(--color-text-muted); margin-top: 4px; }
}

.speed-control {
  display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px;
  .speed-row {
    display: flex; align-items: center; gap: 10px;
    .label { font-size: 12px; color: var(--color-text-muted); min-width: 50px; }
    .slider { flex: 1; }
    .unit { font-size: 11px; color: var(--color-text-muted); min-width: 36px; }
  }
}

.vel-dashboard { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }

.vel-gauge {
  display: flex; align-items: center; gap: 10px;
  .gauge-label { font-size: 11px; color: var(--color-text-muted); min-width: 44px; }
  .gauge-bar-wrap {
    flex: 1; height: 8px; background: rgba(255,255,255,0.05);
    border-radius: 4px; overflow: hidden; position: relative;
    display: flex; align-items: center;
  }
  .gauge-bar {
    height: 100%; border-radius: 4px; transition: width 0.1s ease;
    background: var(--color-success);
    &.mid { background: var(--color-warning); }
    &.high { background: var(--color-danger); }
  }
  .gauge-val {
    font-family: var(--font-mono); font-size: 12px; color: var(--color-primary);
    min-width: 80px; text-align: right;
    .unit { font-size: 10px; color: var(--color-text-muted); }
  }
}

.estop-btn {
  width: 100%; height: 44px; font-size: 14px; font-weight: 700;
  background: rgba(255,68,68,0.1) !important;
  border: 2px solid var(--color-danger) !important;
  color: var(--color-danger) !important;
  &:hover { background: rgba(255,68,68,0.2) !important; }
  &:active { transform: scale(0.98); }
}

.odom-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
  .odom-item {
    display: flex; flex-direction: column; gap: 2px;
    padding: 8px; background: rgba(0,212,255,0.03);
    border: 1px solid rgba(30,58,95,0.5); border-radius: 6px;
    .odom-label { font-size: 11px; color: var(--color-text-muted); }
    .odom-val {
      font-family: var(--font-mono); font-size: 14px; color: var(--color-primary);
      .unit { font-size: 10px; color: var(--color-text-muted); }
    }
  }
}

.ctrl-log-area {
  height: 120px; overflow-y: auto; font-family: var(--font-mono); font-size: 11px;
  .ctrl-log-line {
    padding: 2px 0; border-bottom: 1px solid rgba(30,58,95,0.3);
    display: flex; gap: 8px;
    .log-time { color: var(--color-text-muted); flex-shrink: 0; }
    .log-msg { color: var(--color-text); }
    &.log-warn .log-msg { color: var(--color-warning); }
    &.log-error .log-msg { color: var(--color-danger); }
    &.log-info .log-msg { color: var(--color-text); }
  }
  .log-empty { color: var(--color-text-muted); font-size: 11px; padding: 8px 0; }
}

.mono { font-family: var(--font-mono); }
.unit { font-size: 10px; color: var(--color-text-muted); }

.tap-vel-display {
  display: flex; gap: 12px; margin: 8px 0 4px;
  padding: 8px 12px;
  background: rgba(255,170,0,0.06);
  border: 1px solid rgba(255,170,0,0.3);
  border-radius: 8px;
  .tap-vel-item {
    display: flex; flex-direction: column; gap: 2px; flex: 1;
    .tap-label { font-size: 10px; color: var(--color-text-muted); }
    .tap-val {
      font-family: var(--font-mono); font-size: 15px; font-weight: 600;
      color: var(--color-text);
      &.pos { color: var(--color-success); }
      &.neg { color: var(--color-danger); }
      .unit { font-size: 10px; color: var(--color-text-muted); font-weight: 400; }
    }
  }
}
</style>
