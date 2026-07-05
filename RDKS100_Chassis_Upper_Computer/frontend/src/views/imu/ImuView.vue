<template>
  <div class="imu-view">
    <el-row :gutter="12">
      <!-- 三维姿态模型 -->
      <el-col :xs="24" :sm="10">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Compass /></el-icon> 三维姿态</span>
            <el-tag size="small" :type="imuConnected ? 'success' : 'danger'">{{ imuConnected ? '实时' : '离线' }}</el-tag>
          </div>
          <div ref="threeRef" class="three-container"></div>
          <div class="euler-display">
            <div class="euler-item">
              <span class="axis roll">Roll</span>
              <span class="val">{{ imuData?.orientation?.roll?.toFixed(2) ?? '0.00' }}°</span>
            </div>
            <div class="euler-item">
              <span class="axis pitch">Pitch</span>
              <span class="val">{{ imuData?.orientation?.pitch?.toFixed(2) ?? '0.00' }}°</span>
            </div>
            <div class="euler-item">
              <span class="axis yaw">Yaw</span>
              <span class="val">{{ imuData?.orientation?.yaw?.toFixed(2) ?? '0.00' }}°</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 数值面板 -->
      <el-col :xs="24" :sm="14">
        <el-row :gutter="12">
          <el-col :span="24">
            <div class="tech-card">
              <div class="card-header">
                <span class="card-title">加速度计 (g)</span>
                <el-tooltip content="Livox Mid-360 IMU 加速度单位为 g（1g ≈ 9.81 m/s²），量程 ±8g" placement="top">
                  <el-icon style="color:#6b7a99;cursor:help;margin-left:4px"><InfoFilled /></el-icon>
                </el-tooltip>
              </div>
              <div class="sensor-grid">
                <div class="sensor-item" v-for="axis in ['x','y','z']" :key="'acc'+axis">
                  <span class="axis-label" :class="axis">{{ axis.toUpperCase() }}</span>
                  <span class="sensor-val">{{ imuData?.linear_acceleration?.[axis]?.toFixed(4) ?? '0.0000' }}</span>
                  <div class="mini-bar">
                    <!-- 量程 ±8g，bar 按 8g 满量程显示 -->
                    <div class="bar-fill" :style="{ width: Math.min(Math.abs(imuData?.linear_acceleration?.[axis] ?? 0) / 8 * 100, 100) + '%', background: axisColor(axis) }"></div>
                  </div>
                </div>
              </div>
            </div>
          </el-col>
          <el-col :span="24" class="mt8">
            <div class="tech-card">
              <div class="card-header"><span class="card-title">陀螺仪 (rad/s)</span></div>
              <div class="sensor-grid">
                <div class="sensor-item" v-for="axis in ['x','y','z']" :key="'gyro'+axis">
                  <span class="axis-label" :class="axis">{{ axis.toUpperCase() }}</span>
                  <span class="sensor-val">{{ imuData?.angular_velocity?.[axis]?.toFixed(4) ?? '0.0000' }}</span>
                  <div class="mini-bar">
                    <div class="bar-fill" :style="{ width: Math.min(Math.abs(imuData?.angular_velocity?.[axis] ?? 0) / 5 * 100, 100) + '%', background: axisColor(axis) }"></div>
                  </div>
                </div>
              </div>
            </div>
          </el-col>
        </el-row>
      </el-col>
    </el-row>

    <!-- 数据曲线 -->
    <el-row :gutter="12" class="mt8">
      <el-col :span="24">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><TrendCharts /></el-icon> 姿态角曲线</span>
          </div>
          <div ref="chartRef" class="chart-area"></div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import * as THREE from 'three'
import * as echarts from 'echarts'
import { wsClient } from '@/api/websocket'
import { CHART_MAX_POINTS } from '@/config'

const threeRef = ref<HTMLElement>()
const chartRef = ref<HTMLElement>()
const imuConnected = ref(false)
const imuData = ref<any>(null)

// Three.js
let renderer: THREE.WebGLRenderer | null = null
let scene: THREE.Scene | null = null
let camera: THREE.PerspectiveCamera | null = null
let robotMesh: THREE.Mesh | null = null
let animId: number

function initThree() {
  if (!threeRef.value) return
  const W = threeRef.value.clientWidth, H = 200
  renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true })
  renderer.setSize(W, H)
  renderer.setClearColor(0x050a14, 1)
  threeRef.value.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(45, W / H, 0.1, 100)
  camera.position.set(3, 2, 3)
  camera.lookAt(0, 0, 0)

  // 坐标轴
  scene.add(new THREE.AxesHelper(1.5))

  // 机器人模型（简化为长方体）
  const geo = new THREE.BoxGeometry(1.2, 0.4, 0.8)
  const mat = new THREE.MeshPhongMaterial({ color: 0x00d4ff, transparent: true, opacity: 0.85, wireframe: false })
  robotMesh = new THREE.Mesh(geo, mat)
  scene.add(robotMesh)

  // 前向箭头
  const arrowGeo = new THREE.ConeGeometry(0.1, 0.4, 8)
  const arrowMat = new THREE.MeshPhongMaterial({ color: 0x00ff88 })
  const arrow = new THREE.Mesh(arrowGeo, arrowMat)
  arrow.position.set(0.8, 0, 0)
  arrow.rotation.z = -Math.PI / 2
  robotMesh.add(arrow)

  // 网格地面
  const grid = new THREE.GridHelper(4, 8, 0x1e3a5f, 0x1e3a5f)
  scene.add(grid)

  // 光照
  scene.add(new THREE.AmbientLight(0x404040, 2))
  const dirLight = new THREE.DirectionalLight(0x00d4ff, 1)
  dirLight.position.set(5, 5, 5)
  scene.add(dirLight)

  const animate = () => {
    animId = requestAnimationFrame(animate)
    renderer!.render(scene!, camera!)
  }
  animate()
}

function updateThree() {
  if (!robotMesh || !imuData.value) return
  const { roll, pitch, yaw } = imuData.value.orientation
  robotMesh.rotation.x = pitch * Math.PI / 180
  robotMesh.rotation.y = -yaw * Math.PI / 180
  robotMesh.rotation.z = roll * Math.PI / 180
}

function axisColor(axis: string) {
  return axis === 'x' ? '#ff4444' : axis === 'y' ? '#00ff88' : '#00d4ff'
}

// ECharts 曲线
let chart: echarts.ECharts | null = null
const rollData: number[] = [], pitchData: number[] = [], yawData: number[] = [], timeData: string[] = []

function initChart() {
  if (!chartRef.value) return
  chart = echarts.init(chartRef.value, 'dark')
  chart.setOption({
    backgroundColor: 'transparent',
    grid: { top: 30, right: 20, bottom: 30, left: 50 },
    tooltip: { trigger: 'axis' },
    legend: { data: ['Roll', 'Pitch', 'Yaw'], textStyle: { color: '#6b7a99' }, top: 0 },
    xAxis: { type: 'category', data: timeData, axisLabel: { color: '#6b7a99', fontSize: 10 }, axisLine: { lineStyle: { color: '#1e3a5f' } } },
    yAxis: { type: 'value', axisLabel: { color: '#6b7a99', fontSize: 10 }, splitLine: { lineStyle: { color: '#1e3a5f' } } },
    series: [
      { name: 'Roll', type: 'line', data: rollData, smooth: true, symbol: 'none', lineStyle: { color: '#ff4444', width: 1.5 } },
      { name: 'Pitch', type: 'line', data: pitchData, smooth: true, symbol: 'none', lineStyle: { color: '#00ff88', width: 1.5 } },
      { name: 'Yaw', type: 'line', data: yawData, smooth: true, symbol: 'none', lineStyle: { color: '#00d4ff', width: 1.5 } },
    ],
  })
}

function updateChart() {
  if (!chart || !imuData.value) return
  const now = new Date().toLocaleTimeString('zh', { hour12: false })
  timeData.push(now); rollData.push(imuData.value.orientation.roll)
  pitchData.push(imuData.value.orientation.pitch); yawData.push(imuData.value.orientation.yaw)
  if (timeData.length > CHART_MAX_POINTS) { timeData.shift(); rollData.shift(); pitchData.shift(); yawData.shift() }
  chart.setOption({ xAxis: { data: timeData }, series: [{ data: rollData }, { data: pitchData }, { data: yawData }] })
}

const unsubImu = wsClient.on('imu', (data: any) => {
  imuData.value = data; imuConnected.value = true
  updateThree(); updateChart()
})

onMounted(() => {
  initThree(); initChart()
  window.addEventListener('resize', () => { chart?.resize() })
})

onUnmounted(() => {
  unsubImu()
  cancelAnimationFrame(animId)
  renderer?.dispose()
  chart?.dispose()
})
</script>

<style lang="scss" scoped>
.imu-view { display: flex; flex-direction: column; gap: 12px; }
.mt8 { margin-top: 0; }

.three-container {
  height: 200px; background: #050a14; border-radius: 6px; overflow: hidden;
  :deep(canvas) { width: 100% !important; }
}

.euler-display {
  display: flex; justify-content: space-around; margin-top: 10px;
  .euler-item {
    display: flex; flex-direction: column; align-items: center; gap: 4px;
    .axis { font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 3px;
      &.roll  { background: rgba(255,68,68,0.15); color: #ff4444; }
      &.pitch { background: rgba(0,255,136,0.15); color: #00ff88; }
      &.yaw   { background: rgba(0,212,255,0.15); color: #00d4ff; }
    }
    .val { font-family: var(--font-mono); font-size: 14px; color: var(--color-text); }
  }
}

.sensor-grid {
  display: flex; flex-direction: column; gap: 8px;
  .sensor-item {
    display: grid; grid-template-columns: 24px 1fr 80px; align-items: center; gap: 8px;
    .axis-label {
      font-size: 11px; font-weight: 700; text-align: center;
      &.x { color: #ff4444; } &.y { color: #00ff88; } &.z { color: #00d4ff; }
    }
    .sensor-val { font-family: var(--font-mono); font-size: 12px; color: var(--color-text); }
    .mini-bar { height: 4px; background: var(--color-border); border-radius: 2px; overflow: hidden;
      .bar-fill { height: 100%; border-radius: 2px; transition: width 0.1s; }
    }
  }
}

.chart-area { height: 180px; }
</style>
