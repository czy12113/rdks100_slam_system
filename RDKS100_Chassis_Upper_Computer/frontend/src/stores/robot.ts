// =============================================================================
// Pinia Store：全局机器人状态
// =============================================================================

import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { wsClient } from '@/api/websocket'
import { BATTERY_WARN, BATTERY_CRITICAL, SYS_CPU_WARN, SYS_TEMP_WARN, SYS_TEMP_CRITICAL } from '@/config'

// ---- 类型定义 ----
export interface RobotStatus {
  online: boolean
  name: string
  mode: string
  battery: { percent: number; voltage: number; current: number; charging: boolean }
  pose: { x: number; y: number; z: number; roll: number; pitch: number; yaw: number }
  velocity: { linear_x: number; linear_y: number; angular_z: number }
  odometry?: { distance: number; total_distance: number }
  emergency_stop: boolean
  errors: string[]
}

export interface OdomData {
  timestamp: number
  pose: { x: number; y: number; z: number; yaw: number }
  velocity: { linear_x: number; linear_y: number; angular_z: number }
  odometry?: { distance: number; total_distance: number }
}

export interface SystemInfo {
  cpu: { usage: number; cores: number[]; frequency: number }
  memory: { total: number; used: number; percent: number }
  temperature: { cpu: number; board: number; bpu: number }
  network: { ip: string; connected: boolean; rx_rate: number; tx_rate: number }
  disk: { total: number; used: number; percent: number }
  uptime: number
}

export interface LogEntry {
  timestamp: number
  level: 'info' | 'warn' | 'error' | 'debug'
  message: string
  source: string
}

export const useRobotStore = defineStore('robot', () => {
  // ---- 状态 ----
  const wsStatus = ref<'connecting' | 'connected' | 'disconnected' | 'error'>('disconnected')
  const robotStatus = ref<RobotStatus | null>(null)
  const odomData = ref<OdomData | null>(null)
  const systemInfo = ref<SystemInfo | null>(null)
  const logs = ref<LogEntry[]>([])
  const maxLogs = 500

  // ---- 计算属性 ----
  const isOnline = computed(() => robotStatus.value?.online ?? false)
  const batteryPercent = computed(() => robotStatus.value?.battery.percent ?? 0)
  const batteryLevel = computed(() => {
    const p = batteryPercent.value
    if (p <= BATTERY_CRITICAL) return 'critical'
    if (p <= BATTERY_WARN) return 'warn'
    return 'normal'
  })
  const cpuUsage = computed(() => systemInfo.value?.cpu.usage ?? 0)
  const cpuLevel = computed(() => cpuUsage.value >= SYS_CPU_WARN ? 'warn' : 'normal')
  const temperature = computed(() => systemInfo.value?.temperature.cpu ?? 0)
  const tempLevel = computed(() => {
    const t = temperature.value
    if (t >= SYS_TEMP_CRITICAL) return 'critical'
    if (t >= SYS_TEMP_WARN) return 'warn'
    return 'normal'
  })

  // 当前速度（优先使用里程计真实速度，降级使用 robotStatus）
  const currentVelocity = computed(() => {
    if (odomData.value) return odomData.value.velocity
    return robotStatus.value?.velocity ?? { linear_x: 0, linear_y: 0, angular_z: 0 }
  })

  // 当前位姿（优先使用里程计）
  const currentPose = computed(() => {
    if (odomData.value) return odomData.value.pose
    const p = robotStatus.value?.pose
    return p ? { x: p.x, y: p.y, z: p.z, yaw: p.yaw } : { x: 0, y: 0, z: 0, yaw: 0 }
  })

  // ---- Actions ----
  function initWebSocket() {
    wsClient.connect()
    wsClient.onStatusChange((s) => { wsStatus.value = s })
    wsClient.on('robot_status', (data) => { robotStatus.value = data as RobotStatus })
    wsClient.on('system', (data) => { systemInfo.value = data as SystemInfo })
    wsClient.on('odom', (data) => { odomData.value = data as OdomData })
    wsClient.on('log', (data) => {
      logs.value.push(data as LogEntry)
      if (logs.value.length > maxLogs) logs.value.shift()
    })
  }

  function clearLogs() { logs.value = [] }

  return {
    wsStatus, robotStatus, odomData, systemInfo, logs,
    isOnline, batteryPercent, batteryLevel,
    cpuUsage, cpuLevel, temperature, tempLevel,
    currentVelocity, currentPose,
    initWebSocket, clearLogs,
  }
})
