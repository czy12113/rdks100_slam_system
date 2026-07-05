<template>
  <div class="lidar-view">
    <el-row :gutter="12">
      <!-- 3D 点云视图 -->
      <el-col :xs="24" :sm="16">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Aim /></el-icon> 3D 点云（Livox Mid-360S）</span>
            <div class="actions">
              <el-tag size="small" type="info">Three.js</el-tag>
              <el-tag size="small" :type="lidarConnected ? 'success' : 'danger'">
                {{ lidarConnected ? '实时' : '离线' }}
              </el-tag>
              <el-tag size="small" type="warning" v-if="fps > 0">{{ fps }} fps</el-tag>
              <el-button size="small" text @click="resetCamera">复位视角</el-button>
            </div>
          </div>
          <div class="canvas-wrap" ref="containerRef">
            <canvas ref="threeCanvasRef" class="three-canvas"></canvas>

            <!-- 操作提示 -->
            <div class="hint-bar">
              <span>左键拖拽旋转</span>
              <span>右键拖拽平移</span>
              <span>滚轮缩放</span>
            </div>

            <!-- 高度色条图例 -->
            <div class="height-legend">
              <div class="legend-bar"></div>
              <div class="legend-labels">
                <span>{{ zDisplayMax.toFixed(1) }}m</span>
                <span>高度</span>
                <span>{{ zDisplayMin.toFixed(1) }}m</span>
              </div>
            </div>

            <!-- 点数统计 overlay -->
            <div class="stats-overlay">
              <span>{{ renderedPoints.toLocaleString() }} pts</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 信息面板 -->
      <el-col :xs="24" :sm="8">
        <div class="tech-card info-panel">
          <div class="card-header">
            <span class="card-title">扫描信息</span>
          </div>
          <div class="info-list">
            <div class="info-item">
              <span class="label">渲染点数</span>
              <span class="val mono">{{ renderedPoints.toLocaleString() }}</span>
            </div>
            <div class="info-item">
              <span class="label">原始点数</span>
              <span class="val mono">{{ lidarData?.total_points?.toLocaleString() ?? '--' }}</span>
            </div>
            <div class="info-item">
              <span class="label">最近障碍</span>
              <span class="val mono" :class="{ danger: (lidarData?.min_distance ?? 99) < 0.5 }">
                {{ lidarData?.min_distance?.toFixed(3) ?? '--' }} m
              </span>
            </div>
            <div class="info-item">
              <span class="label">障碍物数</span>
              <span class="val mono">{{ lidarData?.obstacle_count ?? 0 }}</span>
            </div>
            <div class="info-item">
              <span class="label">最大量程</span>
              <span class="val mono">{{ lidarData?.range_max?.toFixed(1) ?? '--' }} m</span>
            </div>
            <div class="info-item">
              <span class="label">高度范围</span>
              <span class="val mono">
                {{ lidarData?.z_min?.toFixed(2) ?? '--' }} ~ {{ lidarData?.z_max?.toFixed(2) ?? '--' }} m
              </span>
            </div>
            <div class="info-item">
              <span class="label">强度范围</span>
              <span class="val mono">
                {{ lidarData?.intensity_min ?? '--' }} ~ {{ lidarData?.intensity_max ?? '--' }}
              </span>
            </div>
            <div class="info-item">
              <span class="label">数据源</span>
              <span class="val mono" :class="{ 'text-success': lidarData?.is_3d }">
                {{ lidarData?.frame_id ?? 'mock' }}
              </span>
            </div>
          </div>

          <!-- 障碍物警告 -->
          <div v-if="(lidarData?.min_distance ?? 99) < 0.5" class="warn-box">
            <el-icon><Warning /></el-icon>
            <span>前方 {{ lidarData?.min_distance?.toFixed(2) }}m 有障碍物！</span>
          </div>

          <!-- 着色模式 -->
          <div class="ctrl-section">
            <div class="ctrl-title">着色模式</div>
            <el-radio-group v-model="colorMode" size="small">
              <el-radio-button value="height">高度</el-radio-button>
              <el-radio-button value="intensity">强度</el-radio-button>
              <el-radio-button value="distance">距离</el-radio-button>
            </el-radio-group>
          </div>

          <!-- 点大小控制 -->
          <div class="ctrl-section">
            <div class="ctrl-title">点大小 <span class="ctrl-val mono">{{ pointSize.toFixed(2) }}</span></div>
            <el-slider v-model="pointSize" :min="0.005" :max="0.15" :step="0.005" size="small" />
          </div>

          <!-- 高度过滤 -->
          <div class="ctrl-section">
            <div class="ctrl-title">高度过滤（Z 轴）</div>
            <div class="ctrl-row">
              <span class="ctrl-label">最小</span>
              <el-slider v-model="filterZMin" :min="-3" :max="5" :step="0.1" size="small" style="flex:1; margin: 0 8px;" />
              <span class="ctrl-val mono">{{ filterZMin.toFixed(1) }}m</span>
            </div>
            <div class="ctrl-row">
              <span class="ctrl-label">最大</span>
              <el-slider v-model="filterZMax" :min="-3" :max="5" :step="0.1" size="small" style="flex:1; margin: 0 8px;" />
              <span class="ctrl-val mono">{{ filterZMax.toFixed(1) }}m</span>
            </div>
          </div>

          <!-- 视角预设 -->
          <div class="ctrl-section">
            <div class="ctrl-title">视角预设</div>
            <div class="preset-btns">
              <el-button size="small" @click="setView('top')">俯视</el-button>
              <el-button size="small" @click="setView('front')">正视</el-button>
              <el-button size="small" @click="setView('side')">侧视</el-button>
              <el-button size="small" @click="setView('iso')">等轴</el-button>
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from 'vue'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { wsClient } from '@/api/websocket'
import { LIDAR_Z_MIN, LIDAR_Z_MAX } from '@/config'

// ─── DOM refs ───────────────────────────────────────────────────────────────
const containerRef = ref<HTMLDivElement>()
const threeCanvasRef = ref<HTMLCanvasElement>()

// ─── 状态 ────────────────────────────────────────────────────────────────────
const lidarConnected = ref(false)
const lidarData = ref<any>(null)
const pointSize = ref(0.03)
const filterZMin = ref(LIDAR_Z_MIN)
const filterZMax = ref(LIDAR_Z_MAX)
const colorMode = ref<'height' | 'intensity' | 'distance'>('height')
const renderedPoints = ref(0)
const fps = ref(0)

// 动态 Z 显示范围（跟随实际数据）
const zDisplayMin = computed(() => lidarData.value?.z_min ?? filterZMin.value)
const zDisplayMax = computed(() => lidarData.value?.z_max ?? filterZMax.value)

// ─── Three.js 对象 ───────────────────────────────────────────────────────────
let renderer: THREE.WebGLRenderer
let scene: THREE.Scene
let camera: THREE.PerspectiveCamera
let controls: OrbitControls
let pointCloud: THREE.Points | null = null
let animFrameId: number
let lastDataTime = 0
let offlineTimer: ReturnType<typeof setInterval> | null = null

// FPS 计数
let fpsFrameCount = 0
let fpsLastTime = performance.now()

// ─── 颜色映射 ─────────────────────────────────────────────────────────────────
// 5 段渐变色表（蓝→青→绿→黄→红），比单纯 HSL 更鲜明
const COLOR_STOPS = [
  new THREE.Color(0x0000ff), // 蓝
  new THREE.Color(0x00ffff), // 青
  new THREE.Color(0x00ff00), // 绿
  new THREE.Color(0xffff00), // 黄
  new THREE.Color(0xff0000), // 红
]

function lerpColor(t: number): THREE.Color {
  const clamped = Math.max(0, Math.min(1, t))
  const seg = clamped * (COLOR_STOPS.length - 1)
  const idx = Math.floor(seg)
  const frac = seg - idx
  if (idx >= COLOR_STOPS.length - 1) return COLOR_STOPS[COLOR_STOPS.length - 1].clone()
  return COLOR_STOPS[idx].clone().lerp(COLOR_STOPS[idx + 1], frac)
}

function getPointColor(
  x: number, y: number, z: number, intensity: number,
  zMin: number, zMax: number,
  intMin: number, intMax: number,
): THREE.Color {
  switch (colorMode.value) {
    case 'intensity': {
      const range = intMax - intMin || 1
      return lerpColor((intensity - intMin) / range)
    }
    case 'distance': {
      const dist = Math.sqrt(x * x + y * y)
      return lerpColor(Math.min(dist / 15.0, 1.0))
    }
    case 'height':
    default: {
      const range = zMax - zMin || 1
      return lerpColor((z - zMin) / range)
    }
  }
}

// ─── 初始化 Three.js ─────────────────────────────────────────────────────────
function initThree() {
  const canvas = threeCanvasRef.value!
  const container = containerRef.value!
  const W = container.clientWidth || 700
  const H = container.clientHeight || 480

  // Renderer：开启对数深度缓冲，改善远近点层叠
  renderer = new THREE.WebGLRenderer({
    canvas,
    antialias: false,   // 点云不需要抗锯齿，关闭节省 GPU
    alpha: false,
    powerPreference: 'high-performance',
  })
  renderer.setSize(W, H)
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2))
  renderer.setClearColor(0x050a14)

  // Scene
  scene = new THREE.Scene()
  scene.fog = new THREE.FogExp2(0x050a14, 0.012) // 远处轻雾，增加深度感

  // Camera
  camera = new THREE.PerspectiveCamera(55, W / H, 0.01, 300)
  camera.position.set(0, -10, 7)
  camera.lookAt(0, 0, 0)

  // OrbitControls
  controls = new OrbitControls(camera, canvas)
  controls.enableDamping = true
  controls.dampingFactor = 0.07
  controls.rotateSpeed = 0.55
  controls.panSpeed = 0.8
  controls.zoomSpeed = 1.1
  controls.minDistance = 0.3
  controls.maxDistance = 100
  controls.target.set(0, 0, 0)

  // 坐标轴辅助（X=红, Y=绿, Z=蓝）
  const axesHelper = new THREE.AxesHelper(1.5)
  scene.add(axesHelper)

  // 地面网格（两层：粗 + 细）
  const gridCoarse = new THREE.GridHelper(30, 15, 0x1a3a5c, 0x0d1f33)
  scene.add(gridCoarse)
  const gridFine = new THREE.GridHelper(10, 20, 0x1e3a5f, 0x0d1f33)
  scene.add(gridFine)

  // 机器人原点标记（十字线 + 圆球）
  const originGeo = new THREE.SphereGeometry(0.08, 8, 8)
  const originMat = new THREE.MeshBasicMaterial({ color: 0x00d4ff })
  scene.add(new THREE.Mesh(originGeo, originMat))

  // 动画循环
  function animate() {
    animFrameId = requestAnimationFrame(animate)
    controls.update()
    renderer.render(scene, camera)

    // FPS 统计
    fpsFrameCount++
    const now = performance.now()
    if (now - fpsLastTime >= 1000) {
      fps.value = fpsFrameCount
      fpsFrameCount = 0
      fpsLastTime = now
    }
  }
  animate()
}

// ─── 更新点云（复用 BufferGeometry 减少 GC）────────────────────────────────
// 预分配最大缓冲区，避免每帧重建
const MAX_RENDER_POINTS = 12000
let posBuffer: Float32Array | null = null
let colBuffer: Float32Array | null = null
let geomRef: THREE.BufferGeometry | null = null
let matRef: THREE.PointsMaterial | null = null

function updatePointCloud(data: any) {
  if (!scene) return

  const pts: any[] = data.points
  if (!pts || pts.length === 0) return

  const zMin = data.z_min ?? filterZMin.value
  const zMax = data.z_max ?? filterZMax.value
  const intMin = data.intensity_min ?? 0
  const intMax = data.intensity_max ?? 255

  // 首次创建缓冲区和 Points 对象
  if (!geomRef || !matRef || !pointCloud) {
    posBuffer = new Float32Array(MAX_RENDER_POINTS * 3)
    colBuffer = new Float32Array(MAX_RENDER_POINTS * 3)

    geomRef = new THREE.BufferGeometry()
    geomRef.setAttribute('position', new THREE.BufferAttribute(posBuffer, 3))
    geomRef.setAttribute('color', new THREE.BufferAttribute(colBuffer, 3))

    matRef = new THREE.PointsMaterial({
      size: pointSize.value,
      vertexColors: true,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.92,
      blending: THREE.AdditiveBlending,  // 叠加混合：密集区域更亮，增强立体感
      depthWrite: false,                  // 配合 AdditiveBlending 必须关闭深度写入
    })

    pointCloud = new THREE.Points(geomRef, matRef)
    scene.add(pointCloud)
  }

  // 填充缓冲区
  let count = 0
  for (const pt of pts) {
    if (count >= MAX_RENDER_POINTS) break

    let x: number, y: number, z: number, intensity: number
    if (Array.isArray(pt)) {
      x = pt[0]; y = pt[1]; z = pt[2] ?? 0; intensity = pt[3] ?? 128
    } else {
      x = pt.x; y = pt.y; z = pt.z ?? 0; intensity = pt.intensity ?? 128
    }

    // 高度过滤
    if (z < filterZMin.value || z > filterZMax.value) continue

    // ROS 坐标系（X前, Y左, Z上）→ Three.js（X右, Y上, Z后）
    posBuffer![count * 3]     = -y
    posBuffer![count * 3 + 1] = z
    posBuffer![count * 3 + 2] = -x

    const c = getPointColor(x, y, z, intensity, zMin, zMax, intMin, intMax)
    colBuffer![count * 3]     = c.r
    colBuffer![count * 3 + 1] = c.g
    colBuffer![count * 3 + 2] = c.b

    count++
  }

  // 更新 draw range，避免渲染空白区域
  geomRef.setDrawRange(0, count)
  geomRef.attributes.position.needsUpdate = true
  geomRef.attributes.color.needsUpdate = true
  geomRef.computeBoundingSphere()

  renderedPoints.value = count
}

// ─── 视角预设 ─────────────────────────────────────────────────────────────────
function setView(preset: 'top' | 'front' | 'side' | 'iso') {
  if (!camera || !controls) return
  const presets: Record<string, { pos: [number, number, number]; target: [number, number, number] }> = {
    top:   { pos: [0, 18, 0.01],  target: [0, 0, 0] },
    front: { pos: [0, -12, 2],    target: [0, 0, 0] },
    side:  { pos: [12, 0, 2],     target: [0, 0, 0] },
    iso:   { pos: [-7, -7, 7],    target: [0, 0, 0] },
  }
  const p = presets[preset]
  camera.position.set(...p.pos)
  controls.target.set(...p.target)
  controls.update()
}

function resetCamera() { setView('iso') }

// ─── 响应式调整大小 ───────────────────────────────────────────────────────────
function resizeRenderer() {
  const container = containerRef.value
  if (!container || !renderer || !camera) return
  const W = container.clientWidth
  const H = container.clientHeight
  if (W === 0 || H === 0) return
  renderer.setSize(W, H)
  camera.aspect = W / H
  camera.updateProjectionMatrix()
}

// ─── WebSocket 数据接收 ───────────────────────────────────────────────────────
const unsubLidar = wsClient.on('lidar', (data: any) => {
  lidarData.value = data
  lidarConnected.value = true
  lastDataTime = Date.now()
  updatePointCloud(data)
})

const unsubStatus = wsClient.onStatusChange((s) => {
  if (s === 'disconnected' || s === 'error') {
    lidarConnected.value = false
  }
})

// ─── 生命周期 ─────────────────────────────────────────────────────────────────
onMounted(() => {
  initThree()
  window.addEventListener('resize', resizeRenderer)
  offlineTimer = setInterval(() => {
    if (lidarConnected.value && Date.now() - lastDataTime > 2000) {
      lidarConnected.value = false
    }
  }, 1000)
})

onUnmounted(() => {
  unsubLidar()
  unsubStatus()
  if (offlineTimer) clearInterval(offlineTimer)
  cancelAnimationFrame(animFrameId)
  window.removeEventListener('resize', resizeRenderer)
  if (renderer) renderer.dispose()
  if (geomRef) geomRef.dispose()
  if (matRef) matRef.dispose()
})

// ─── 参数变化时重绘 ───────────────────────────────────────────────────────────
// 点大小：直接改 material，无需重建 geometry
watch(pointSize, (val: number) => {
  if (matRef) matRef.size = val
})

// 颜色模式 / Z 过滤：需要重新计算颜色或重新过滤点
watch([colorMode, filterZMin, filterZMax], () => {
  if (lidarData.value) updatePointCloud(lidarData.value)
})
</script>

<style lang="scss" scoped>
.lidar-view { display: flex; flex-direction: column; gap: 12px; }
.actions { display: flex; align-items: center; gap: 6px; }

.canvas-wrap {
  position: relative;
  background: #050a14;
  border-radius: 6px;
  overflow: hidden;
  height: 500px;

  .three-canvas {
    width: 100% !important;
    height: 100% !important;
    display: block;
  }

  .hint-bar {
    position: absolute;
    bottom: 10px;
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    gap: 16px;
    font-size: 10px;
    color: rgba(107, 122, 153, 0.6);
    pointer-events: none;
    white-space: nowrap;
  }

  .stats-overlay {
    position: absolute;
    top: 10px;
    left: 10px;
    font-size: 10px;
    font-family: monospace;
    color: rgba(0, 212, 255, 0.7);
    pointer-events: none;
  }

  .height-legend {
    position: absolute;
    top: 10px;
    right: 10px;
    display: flex;
    flex-direction: row;
    align-items: stretch;
    gap: 4px;
    height: 130px;

    .legend-bar {
      width: 10px;
      border-radius: 3px;
      background: linear-gradient(
        to bottom,
        #ff0000,
        #ffff00,
        #00ff00,
        #00ffff,
        #0000ff
      );
    }

    .legend-labels {
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      font-size: 9px;
      color: rgba(107, 122, 153, 0.8);
      font-family: monospace;
    }
  }
}

.info-panel {
  .info-list {
    .info-item {
      display: flex;
      justify-content: space-between;
      padding: 5px 0;
      border-bottom: 1px solid rgba(30, 58, 95, 0.4);

      .label { font-size: 11px; color: var(--color-text-muted); }
      .val { font-size: 12px; font-family: var(--font-mono); color: var(--color-text); }
      .danger { color: var(--color-danger) !important; }
      .text-success { color: var(--color-success, #00ff88) !important; }
    }
  }

  .warn-box {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-top: 10px;
    padding: 8px;
    background: rgba(255, 68, 68, 0.1);
    border: 1px solid var(--color-danger);
    border-radius: 6px;
    color: var(--color-danger);
    font-size: 12px;
    animation: pulse 1s infinite;
  }

  .ctrl-section {
    margin-top: 10px;
    padding-top: 8px;
    border-top: 1px solid rgba(30, 58, 95, 0.4);

    .ctrl-title {
      font-size: 11px;
      color: var(--color-text-muted);
      margin-bottom: 6px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }

    .ctrl-row {
      display: flex;
      align-items: center;
      margin-bottom: 4px;

      .ctrl-label {
        font-size: 10px;
        color: var(--color-text-muted);
        width: 28px;
        flex-shrink: 0;
      }

      .ctrl-val {
        font-size: 10px;
        color: var(--color-primary);
        width: 36px;
        text-align: right;
        flex-shrink: 0;
      }
    }

    .preset-btns {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
  }
}
</style>
