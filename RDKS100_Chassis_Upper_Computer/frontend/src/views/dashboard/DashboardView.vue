<template>
  <div class="dashboard">
    <!-- 第一行：系统状态卡片 -->
    <el-row :gutter="12" class="row">
      <el-col :xs="12" :sm="6">
        <div class="tech-card metric-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Cpu /></el-icon> CPU</span>
            <span class="badge" :class="robotStore.cpuLevel">{{ robotStore.cpuUsage.toFixed(1) }}%</span>
          </div>
          <div class="metric-value">{{ robotStore.cpuUsage.toFixed(1) }}<span class="metric-unit">%</span></div>
          <div class="tech-progress mt8">
            <div class="bar" :class="robotStore.cpuLevel" :style="{ width: robotStore.cpuUsage + '%' }"></div>
          </div>
          <div class="sub-info">{{ systemInfo?.cpu.frequency?.toFixed(0) ?? '--' }} MHz</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="tech-card metric-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Coin /></el-icon> 内存</span>
            <span class="badge">{{ systemInfo?.memory.percent?.toFixed(1) ?? '--' }}%</span>
          </div>
          <div class="metric-value">{{ memUsedGB }}<span class="metric-unit">GB</span></div>
          <div class="tech-progress mt8">
            <div class="bar" :style="{ width: (systemInfo?.memory.percent ?? 0) + '%' }"></div>
          </div>
          <div class="sub-info">共 {{ memTotalGB }} GB</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="tech-card metric-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Odometer /></el-icon> 温度</span>
            <span class="badge" :class="robotStore.tempLevel">{{ systemInfo?.temperature.cpu?.toFixed(1) ?? '--' }}°C</span>
          </div>
          <div class="metric-value">{{ systemInfo?.temperature.cpu?.toFixed(1) ?? '--' }}<span class="metric-unit">°C</span></div>
          <div class="tech-progress mt8">
            <div class="bar" :class="robotStore.tempLevel" :style="{ width: Math.min((systemInfo?.temperature.cpu ?? 0) / 100 * 100, 100) + '%' }"></div>
          </div>
          <div class="sub-info">BPU: {{ systemInfo?.temperature.bpu?.toFixed(1) ?? '--' }}°C</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="6">
        <div class="tech-card metric-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Connection /></el-icon> 网络</span>
            <span class="status-dot" :class="systemInfo?.network.connected ? 'online' : 'offline'"></span>
          </div>
          <div class="metric-value" style="font-size:14px">{{ systemInfo?.network.ip ?? '--' }}</div>
          <div class="sub-info mt8">↓ {{ systemInfo?.network.rx_rate?.toFixed(0) ?? '--' }} KB/s</div>
          <div class="sub-info">↑ {{ systemInfo?.network.tx_rate?.toFixed(0) ?? '--' }} KB/s</div>
        </div>
      </el-col>
    </el-row>

    <!-- 第二行：机器人状态 + 电量 + 速度 -->
    <el-row :gutter="12" class="row">
      <el-col :xs="24" :sm="8">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Avatar /></el-icon> 机器人状态</span>
            <span class="status-dot" :class="robotStore.isOnline ? 'online pulse' : 'offline'"></span>
          </div>
          <div class="robot-info">
            <div class="info-row"><span class="label">名称</span><span class="val">{{ robotStatus?.name ?? '--' }}</span></div>
            <div class="info-row"><span class="label">模式</span><span class="val mode-badge">{{ robotStatus?.mode ?? '--' }}</span></div>
            <div class="info-row"><span class="label">位置</span><span class="val mono">X:{{ robotStatus?.pose.x.toFixed(2) ?? '--' }} Y:{{ robotStatus?.pose.y.toFixed(2) ?? '--' }}</span></div>
            <div class="info-row"><span class="label">朝向</span><span class="val mono">{{ robotStatus ? (robotStatus.pose.yaw * 180 / Math.PI).toFixed(1) : '--' }}°</span></div>
            <div class="info-row"><span class="label">急停</span><span class="val" :style="{ color: robotStatus?.emergency_stop ? 'var(--color-danger)' : 'var(--color-success)' }">{{ robotStatus?.emergency_stop ? '已触发' : '正常' }}</span></div>
          </div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Lightning /></el-icon> 电池</span>
            <span class="badge" :class="robotStore.batteryLevel">{{ robotStore.batteryPercent.toFixed(0) }}%</span>
          </div>
          <div class="battery-visual">
            <div class="battery-body">
              <div class="battery-fill" :class="robotStore.batteryLevel" :style="{ width: robotStore.batteryPercent + '%' }"></div>
            </div>
            <div class="battery-tip"></div>
          </div>
          <div class="metric-value mt8">{{ robotStore.batteryPercent.toFixed(0) }}<span class="metric-unit">%</span></div>
          <div class="sub-info">{{ robotStatus?.battery.voltage?.toFixed(2) ?? '--' }} V / {{ robotStatus?.battery.current?.toFixed(2) ?? '--' }} A</div>
          <div class="sub-info" v-if="robotStatus?.battery.charging" style="color:var(--color-success)">⚡ 充电中</div>
        </div>
      </el-col>
      <el-col :xs="12" :sm="8">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Odometer /></el-icon> 速度</span>
          </div>
          <div class="speed-grid">
            <div class="speed-item">
              <div class="speed-label">线速度 X</div>
              <div class="metric-value" style="font-size:18px">{{ robotStatus?.velocity.linear_x.toFixed(3) ?? '0.000' }}<span class="metric-unit">m/s</span></div>
            </div>
            <div class="speed-item">
              <div class="speed-label">线速度 Y</div>
              <div class="metric-value" style="font-size:18px">{{ robotStatus?.velocity.linear_y.toFixed(3) ?? '0.000' }}<span class="metric-unit">m/s</span></div>
            </div>
            <div class="speed-item">
              <div class="speed-label">角速度 Z</div>
              <div class="metric-value" style="font-size:18px">{{ robotStatus?.velocity.angular_z.toFixed(3) ?? '0.000' }}<span class="metric-unit">rad/s</span></div>
            </div>
            <div class="speed-item">
              <div class="speed-label">运行时间</div>
              <div class="metric-value" style="font-size:18px">{{ uptimeStr }}</div>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第三行：CPU 曲线 + 实时日志 -->
    <el-row :gutter="12" class="row">
      <el-col :xs="24" :sm="14">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><TrendCharts /></el-icon> 系统性能曲线</span>
          </div>
          <div ref="chartRef" class="chart-area"></div>
        </div>
      </el-col>
      <el-col :xs="24" :sm="10">
        <div class="tech-card log-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Document /></el-icon> 实时日志</span>
            <el-button size="small" text @click="robotStore.clearLogs()">清空</el-button>
          </div>
          <div ref="logRef" class="log-area">
            <div
              v-for="(log, i) in robotStore.logs.slice(-100)"
              :key="i"
              class="log-line"
              :class="`log-${log.level}`"
            >
              <span class="log-time">{{ formatTime(log.timestamp) }}</span>
              <span class="log-msg">{{ log.message }}</span>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useRobotStore } from '@/stores/robot'
import { wsClient } from '@/api/websocket'
import { CHART_MAX_POINTS } from '@/config'
import dayjs from 'dayjs'

const robotStore = useRobotStore()
const chartRef = ref<HTMLElement>()
const logRef = ref<HTMLElement>()

const robotStatus = computed(() => robotStore.robotStatus)
const systemInfo = computed(() => robotStore.systemInfo)

const memUsedGB = computed(() => ((systemInfo.value?.memory.used ?? 0) / 1024).toFixed(1))
const memTotalGB = computed(() => ((systemInfo.value?.memory.total ?? 0) / 1024).toFixed(1))

const uptimeStr = computed(() => {
  const s = systemInfo.value?.uptime ?? 0
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h${m}m`
})

function formatTime(ts: number) {
  return dayjs(ts * 1000).format('HH:mm:ss')
}

// ---- ECharts 性能曲线 ----
let chart: echarts.ECharts | null = null
const cpuData: number[] = []
const memData: number[] = []
const timeData: string[] = []

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, 'dark')
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 30, right: 20, bottom: 30, left: 50 },
    tooltip: { trigger: 'axis' },
    legend: { data: ['CPU %', '内存 %'], textStyle: { color: '#6b7a99' }, top: 0 },
    xAxis: { type: 'category', data: timeData, axisLabel: { color: '#6b7a99', fontSize: 10 }, axisLine: { lineStyle: { color: '#1e3a5f' } } },
    yAxis: { type: 'value', min: 0, max: 100, axisLabel: { color: '#6b7a99', fontSize: 10 }, splitLine: { lineStyle: { color: '#1e3a5f' } } },
    series: [
      { name: 'CPU %', type: 'line', data: cpuData, smooth: true, symbol: 'none', lineStyle: { color: '#00d4ff', width: 2 }, areaStyle: { color: 'rgba(0,212,255,0.08)' } },
      { name: '内存 %', type: 'line', data: memData, smooth: true, symbol: 'none', lineStyle: { color: '#00ff88', width: 2 }, areaStyle: { color: 'rgba(0,255,136,0.06)' } },
    ],
  })
}

function updateChart() {
  if (!chart || !systemInfo.value) return
  const now = dayjs().format('HH:mm:ss')
  timeData.push(now)
  cpuData.push(systemInfo.value.cpu.usage)
  memData.push(systemInfo.value.memory.percent)
  if (timeData.length > CHART_MAX_POINTS) {
    timeData.shift(); cpuData.shift(); memData.shift()
  }
  chart.setOption({ xAxis: { data: timeData }, series: [{ data: cpuData }, { data: memData }] })
}

// 自动滚动日志
watch(() => robotStore.logs.length, async () => {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
})

// 监听系统数据更新图表
const unsubSys = wsClient.on('system', () => updateChart())

onMounted(() => {
  initChart()
  window.addEventListener('resize', () => chart?.resize())
})

onUnmounted(() => {
  unsubSys()
  chart?.dispose()
})
</script>

<style lang="scss" scoped>
.dashboard { display: flex; flex-direction: column; gap: 12px; }
.row { margin-bottom: 0 !important; }
.mt8 { margin-top: 8px; }

.metric-card {
  .sub-info { font-size: 11px; color: var(--color-text-muted); margin-top: 4px; }
}

.badge {
  font-size: 11px; font-family: var(--font-mono);
  padding: 2px 6px; border-radius: 4px;
  background: rgba(0,212,255,0.1); color: var(--color-primary);
  &.warn { background: rgba(255,170,0,0.1); color: var(--color-warning); }
  &.critical { background: rgba(255,68,68,0.1); color: var(--color-danger); }
}

.robot-info {
  .info-row {
    display: flex; justify-content: space-between; align-items: center;
    padding: 5px 0; border-bottom: 1px solid rgba(30,58,95,0.5);
    &:last-child { border-bottom: none; }
    .label { font-size: 11px; color: var(--color-text-muted); }
    .val { font-size: 12px; color: var(--color-text); }
    .mono { font-family: var(--font-mono); font-size: 11px; }
    .mode-badge {
      background: rgba(0,212,255,0.1); color: var(--color-primary);
      padding: 1px 6px; border-radius: 3px; font-size: 11px;
    }
  }
}

.battery-visual {
  display: flex; align-items: center; margin-top: 8px;
  .battery-body {
    flex: 1; height: 20px; border: 2px solid var(--color-border);
    border-radius: 4px; overflow: hidden; position: relative;
    .battery-fill {
      height: 100%; transition: width 0.5s ease;
      background: linear-gradient(90deg, var(--color-success), #00aa55);
      &.warn { background: linear-gradient(90deg, var(--color-warning), #cc7700); }
      &.critical { background: linear-gradient(90deg, var(--color-danger), #aa0000); }
    }
  }
  .battery-tip {
    width: 6px; height: 10px; background: var(--color-border);
    border-radius: 0 2px 2px 0; margin-left: 2px;
  }
}

.speed-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
  .speed-item { .speed-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 2px; } }
}

.chart-area { height: 200px; }

.log-card { display: flex; flex-direction: column; }
.log-area {
  height: 200px; overflow-y: auto; font-family: var(--font-mono); font-size: 11px;
  .log-line {
    padding: 2px 0; border-bottom: 1px solid rgba(30,58,95,0.3);
    .log-time { color: var(--color-text-muted); margin-right: 8px; }
  }
}
</style>
