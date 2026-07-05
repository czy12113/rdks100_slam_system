<template>
  <div class="video-view">
    <!-- 第一行：RGB 原图 + 深度图 -->
    <el-row :gutter="12">
      <!-- RGB 原图 -->
      <el-col :xs="24" :sm="12">
        <div class="tech-card video-card">
          <div class="card-header">
            <span class="card-title"><el-icon><VideoCamera /></el-icon> RGB 图像</span>
            <div class="actions">
              <el-tag size="small" :type="rgbConnected ? 'success' : 'danger'">
                {{ rgbConnected ? '实时' : '离线' }}
              </el-tag>
              <el-button size="small" text @click="screenshot('rgb')"><el-icon><Camera /></el-icon></el-button>
              <el-button size="small" text @click="openFullscreen(rgbSrc)"><el-icon><FullScreen /></el-icon></el-button>
            </div>
          </div>
          <div class="video-container" ref="rgbContainer">
            <img v-if="rgbSrc" :src="rgbSrc" class="video-frame" alt="RGB" />
            <div v-else class="video-placeholder">
              <el-icon size="48"><VideoCamera /></el-icon>
              <p>等待 RGB 图像...</p>
            </div>
            <div class="video-overlay">
              <span class="fps-badge">{{ rgbFps }} fps</span>
              <span class="res-badge">{{ rgbWidth }}×{{ rgbHeight }}</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 深度图像 -->
      <el-col :xs="24" :sm="12">
        <div class="tech-card video-card">
          <div class="card-header">
            <span class="card-title"><el-icon><View /></el-icon> 深度图像</span>
            <div class="actions">
              <el-tag size="small" :type="depthConnected ? 'success' : 'danger'">
                {{ depthConnected ? '实时' : '离线' }}
              </el-tag>
              <el-button size="small" text @click="screenshot('depth')"><el-icon><Camera /></el-icon></el-button>
              <el-button size="small" text @click="openFullscreen(depthSrc)"><el-icon><FullScreen /></el-icon></el-button>
            </div>
          </div>
          <div class="video-container" ref="depthContainer">
            <img v-if="depthSrc" :src="depthSrc" class="video-frame" alt="Depth" />
            <div v-else class="video-placeholder">
              <el-icon size="48"><View /></el-icon>
              <p>等待深度图像...</p>
            </div>
            <div class="video-overlay">
              <span class="fps-badge">{{ depthFps }} fps</span>
            </div>
          </div>
          <div class="depth-legend">
            <span class="legend-label">近</span>
            <div class="legend-bar"></div>
            <span class="legend-label">远</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第二行：AI 标注图像 + 识别结果列表 -->
    <el-row :gutter="12" class="mt12">
      <!-- 带标注框的 AI 检测图像 -->
      <el-col :xs="24" :sm="14">
        <div class="tech-card video-card">
          <div class="card-header">
            <span class="card-title">
              <el-icon><MagicStick /></el-icon> AI 目标检测
            </span>
            <div class="actions">
              <el-tag size="small" :type="annoConnected ? 'success' : 'info'">
                {{ annoConnected ? '检测中' : '未启动' }}
              </el-tag>
              <span class="det-badge">{{ detections.length }} 目标</span>
              <el-button size="small" text @click="openFullscreen(annoSrc)"><el-icon><FullScreen /></el-icon></el-button>
            </div>
          </div>
          <div class="video-container">
            <img v-if="annoSrc" :src="annoSrc" class="video-frame" alt="Annotated" />
            <div v-else class="video-placeholder">
              <el-icon size="48"><MagicStick /></el-icon>
              <p>等待检测节点发布图像...</p>
              <p class="hint">ros2 launch d435i_detection detection.launch.py</p>
            </div>
            <div class="video-overlay">
              <span class="fps-badge">{{ annoFps }} fps</span>
              <span class="infer-badge" v-if="lastInferMs > 0">{{ lastInferMs }}ms</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 识别结果列表 -->
      <el-col :xs="24" :sm="10">
        <div class="tech-card det-panel">
          <div class="card-header">
            <span class="card-title"><el-icon><List /></el-icon> 识别结果</span>
            <div class="actions">
              <span class="det-count">共 {{ detections.length }} 个</span>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="detections.length === 0" class="det-empty">
            <el-icon size="32"><Search /></el-icon>
            <p>暂未检测到目标</p>
          </div>

          <!-- 检测结果列表 -->
          <div v-else class="det-list">
            <div
              v-for="(det, idx) in detections"
              :key="idx"
              class="det-item"
            >
              <div class="det-row">
                <span class="det-cls" :style="{ color: classColor(det.class_id) }">
                  {{ det.class_name }}
                </span>
                <span class="det-dist" v-if="det.distance_m > 0">
                  {{ det.distance_m.toFixed(2) }} m
                </span>
                <span class="det-dist dist-unknown" v-else>--</span>
              </div>
              <div class="det-row">
                <div class="conf-bar-wrap">
                  <div
                    class="conf-bar"
                    :style="{
                      width: (det.confidence * 100).toFixed(0) + '%',
                      background: confColor(det.confidence),
                    }"
                  ></div>
                </div>
                <span class="conf-val">{{ (det.confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>

          <!-- 帧统计 -->
          <div class="det-footer">
            <span>frame #{{ lastFrameId }}</span>
            <span>{{ lastDetCount }} det</span>
            <span>{{ lastInferMs }} ms</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第三行：VLM 场景理解（AI 自然语言描述） -->
    <el-row :gutter="12" class="mt12">
      <el-col :span="24">
        <div class="tech-card vlm-card">
          <div class="card-header">
            <span class="card-title">
              <el-icon><MagicStick /></el-icon> 场景理解
              <!-- 本地 / 云端 模式徽标（来自 useVlmProvider） -->
              <span
                class="mode-badge"
                :style="{
                  color: modeColor,
                  borderColor: modeColor,
                  background: modeColor + '22',
                }"
                :title="isLocal ? '本地推理 · 无需公网' : '云端推理 · 依赖公网'"
              >
                <span class="mode-dot" :style="{ background: modeColor }" />
                {{ modeLabel }}
              </span>
              <span class="vlm-provider" v-if="vlmProvider">
                {{ vlmProvider }} / {{ vlmModel }}
              </span>
            </span>
            <div class="actions">
              <el-tag size="small" :type="vlmReady ? 'success' : 'info'">
                {{ vlmReady ? '在线' : '未启动' }}
              </el-tag>
              <el-tag size="small" type="warning" v-if="vlmLastMs > 0">
                {{ vlmLastMs }} ms
              </el-tag>
              <el-tag
                size="small"
                :type="isLocal ? 'success' : 'primary'"
                effect="plain"
                v-if="avgLatencyMs != null && avgLatencyMs > 0"
              >
                均 {{ avgLatencyMs!.toFixed(0) }} ms
              </el-tag>
              <el-button
                size="small"
                type="primary"
                :loading="vlmAsking"
                @click="askVlm()"
              >
                <el-icon><Refresh /></el-icon> 立即分析
              </el-button>
            </div>
          </div>

          <!-- 最新描述 -->
          <div class="vlm-latest">
            <div v-if="vlmLatest" class="vlm-text">{{ vlmLatest }}</div>
            <div v-else class="vlm-empty">
              <el-icon size="24"><MagicStick /></el-icon>
              <p>等待 VLM 节点输出场景描述...</p>
              <p class="hint">ros2 launch vlm_scene vlm.launch.py</p>
            </div>
            <div class="vlm-meta" v-if="vlmLatestTs">
              <span>{{ formatTs(vlmLatestTs) }}</span>
              <span v-if="vlmDetCount >= 0">· {{ vlmDetCount }} 个目标</span>
            </div>
          </div>

          <!-- 手动 prompt -->
          <div class="vlm-prompt-bar">
            <el-input
              v-model="vlmPrompt"
              placeholder="可选：自定义提问（留空走默认场景描述）"
              size="small"
              clearable
              @keyup.enter="askVlm(vlmPrompt)"
            />
            <el-button size="small" @click="askVlm(vlmPrompt)" :loading="vlmAsking">
              提问
            </el-button>
          </div>

          <!-- 历史折叠 -->
          <el-collapse v-model="vlmHistoryOpen" class="vlm-history">
            <el-collapse-item title="历史描述" name="history">
              <div v-if="vlmHistory.length === 0" class="vlm-history-empty">暂无历史</div>
              <div
                v-else
                v-for="(item, idx) in vlmHistory"
                :key="idx"
                class="vlm-history-item"
              >
                <span class="hist-ts">{{ formatTs(item.timestamp) }}</span>
                <span class="hist-text">{{ item.description }}</span>
              </div>
            </el-collapse-item>
          </el-collapse>
        </div>
      </el-col>
    </el-row>

    <!-- 第四行：相机参数 -->
    <el-row :gutter="12" class="mt12">
      <el-col :span="24">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Setting /></el-icon> 相机参数</span>
          </div>
          <el-row :gutter="16">
            <el-col :xs="12" :sm="6" v-for="item in cameraParams" :key="item.label">
              <div class="param-item">
                <span class="param-label">{{ item.label }}</span>
                <span class="param-value">{{ item.value }}</span>
              </div>
            </el-col>
          </el-row>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { wsClient } from '@/api/websocket'
import { vlmApi } from '@/api/http'
import { ElMessage } from 'element-plus'
import { useVlmProvider } from '@/composables/useVlmProvider'

// ── 本地 / 云端 模式（来自 useVlmProvider 单例）─────────────────────────────
const {
  isLocal,
  modeLabel,
  modeColor,
  avgLatencyMs,
} = useVlmProvider()

// ── 图像流状态 ────────────────────────────────────────────────────────────────
const rgbSrc      = ref('')
const depthSrc    = ref('')
const annoSrc     = ref('')        // 带标注框的 AI 检测图像
const rgbConnected   = ref(false)
const depthConnected = ref(false)
const annoConnected  = ref(false)

const rgbFps    = ref(0)
const depthFps  = ref(0)
const annoFps   = ref(0)
const rgbWidth  = ref(640)
const rgbHeight = ref(480)

let rgbFrameCount   = 0
let depthFrameCount = 0
let annoFrameCount  = 0
let fpsTimer: ReturnType<typeof setInterval>

// ── Blob URL 缓存：避免 base64 data:URL 的解码开销 ─────────────────────────────
// data:URL 每次赋给 <img> 时浏览器都要 base64 decode + JPEG decode，30fps 时
// 明显吃渲染线程。改用 blob:URL 后：base64 只解一次，浏览器可 GPU 加速解码。
// 每次替换新 URL 后必须 revokeObjectURL 释放旧的，避免内存泄漏。
let rgbBlobUrl:   string | null = null
let depthBlobUrl: string | null = null
let annoBlobUrl:  string | null = null

/**
 * base64 → Uint8Array（比 fetch(data:URL).blob() 快，也不阻塞事件循环）
 */
function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64)
  const len = bin.length
  const bytes = new Uint8Array(len)
  for (let i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i)
  return bytes
}

/**
 * 用 base64 + 编码类型生成新的 blob:URL，返回后立刻释放旧 URL。
 * encoding 为 'png/base64' 时也走 image/jpeg 的 MIME 影响不大（浏览器按内容识别）。
 */
function makeBlobUrl(b64: string, encoding: string): string {
  const mime = encoding && encoding.startsWith('png') ? 'image/png' : 'image/jpeg'
  const bytes = base64ToBytes(b64)
  // TS 5.7+ 中 Uint8Array.buffer 的类型是 ArrayBufferLike，直接传入 BlobPart
  // 会因为可能是 SharedArrayBuffer 报错；这里明确断言为 ArrayBuffer 安全传入。
  const blob = new Blob([bytes.buffer as ArrayBuffer], { type: mime })
  return URL.createObjectURL(blob)
}

// ── 检测结果状态 ──────────────────────────────────────────────────────────────
interface Detection {
  class_id:   number
  class_name: string
  confidence: number
  bbox: { x1: number; y1: number; x2: number; y2: number }
  distance_m: number
}

const detections   = ref<Detection[]>([])
const lastFrameId  = ref(0)
const lastInferMs  = ref(0)
const lastDetCount = ref(0)

// ── 颜色映射（按类别 ID 生成固定色，视觉区分度高）────────────────────────────
const CLASS_PALETTE = [
  '#00d4ff', '#00ff88', '#ffaa00', '#ff6b6b', '#a78bfa',
  '#34d399', '#fbbf24', '#f472b6', '#60a5fa', '#4ade80',
]
function classColor(cls_id: number): string {
  return CLASS_PALETTE[cls_id % CLASS_PALETTE.length]
}
function confColor(conf: number): string {
  if (conf >= 0.7) return '#00ff88'
  if (conf >= 0.5) return '#ffaa00'
  return '#ff6b6b'
}

// ── WebSocket 订阅 ────────────────────────────────────────────────────────────

// RGB 原图帧
const unsubRgb = wsClient.on('video_rgb', (data: any) => {
  if (!data?.data) return
  try {
    const url = makeBlobUrl(data.data, data.encoding || 'jpeg/base64')
    if (rgbBlobUrl) URL.revokeObjectURL(rgbBlobUrl)
    rgbBlobUrl       = url
    rgbSrc.value     = url
    rgbConnected.value = true
    rgbWidth.value   = data.width  ?? 640
    rgbHeight.value  = data.height ?? 480
    rgbFrameCount++
  } catch (e) {
    console.warn('[VideoView] RGB 帧解码失败', e)
  }
})

// 深度图帧
const unsubDepth = wsClient.on('video_depth', (data: any) => {
  if (!data?.data) return
  try {
    const url = makeBlobUrl(data.data, data.encoding || 'jpeg/base64')
    if (depthBlobUrl) URL.revokeObjectURL(depthBlobUrl)
    depthBlobUrl        = url
    depthSrc.value      = url
    depthConnected.value = true
    depthFrameCount++
  } catch (e) {
    console.warn('[VideoView] Depth 帧解码失败', e)
  }
})

// 带标注框的 AI 检测图像（detection_node 发布 /detection/annotated_image
// → backend 以 video_annotated topic 推送，与 video_rgb 纯原图完全分离）
const unsubAnno = wsClient.on('video_annotated', (data: any) => {
  if (!data?.data) return
  try {
    const url = makeBlobUrl(data.data, data.encoding || 'jpeg/base64')
    if (annoBlobUrl) URL.revokeObjectURL(annoBlobUrl)
    annoBlobUrl         = url
    annoSrc.value       = url
    annoConnected.value = true
    annoFrameCount++
  } catch (e) {
    console.warn('[VideoView] Annotated 帧解码失败', e)
  }
})

// 纯 JSON 检测结果（/detection/results → backend 可选转发）
// 目前 backend 尚未单独推送此 topic，通过 annotated_image 的配套结果推送：
// 若后续 backend 增加 'detection_results' topic 推送，在此处接收
const unsubResults = wsClient.on('detection_results', (data: any) => {
  if (!data) return
  detections.value   = data.detections   ?? []
  lastFrameId.value  = data.frame_id     ?? 0
  lastInferMs.value  = data.infer_ms     ?? 0
  lastDetCount.value = data.count        ?? 0
})

// ── VLM 场景理解 ──────────────────────────────────────────────────────────────
interface VlmRecord {
  description: string
  timestamp:   number
  provider?:   string
  model?:      string
  det_count?:  number
  elapsed_ms?: number
}

const vlmLatest      = ref<string>('')
const vlmLatestTs    = ref<number>(0)
const vlmProvider    = ref<string>('')
const vlmModel       = ref<string>('')
const vlmLastMs      = ref<number>(0)
const vlmDetCount    = ref<number>(-1)
const vlmReady       = ref<boolean>(false)
const vlmHistory     = ref<VlmRecord[]>([])
const vlmHistoryOpen = ref<string[]>([])
const vlmPrompt      = ref<string>('')
const vlmAsking      = ref<boolean>(false)

// WebSocket: 实时场景描述
const unsubVlmDesc = wsClient.on('vlm_description', (data: any) => {
  if (!data?.description) return
  vlmLatest.value   = data.description
  vlmLatestTs.value = data.timestamp ?? (Date.now() / 1000)
  vlmProvider.value = data.provider ?? vlmProvider.value
  vlmModel.value    = data.model    ?? vlmModel.value
  vlmLastMs.value   = Math.round(data.elapsed_ms ?? 0)
  vlmDetCount.value = data.det_count ?? -1
  vlmReady.value    = true
  // 推入历史前面，限制 50 条
  vlmHistory.value.unshift({
    description: data.description,
    timestamp:   vlmLatestTs.value,
    provider:    data.provider,
    model:       data.model,
    det_count:   data.det_count,
    elapsed_ms:  data.elapsed_ms,
  })
  if (vlmHistory.value.length > 50) vlmHistory.value.length = 50
})

// WebSocket: 节点状态/心跳
const unsubVlmStatus = wsClient.on('vlm_status', (data: any) => {
  if (!data) return
  vlmReady.value    = !!data.ready
  vlmProvider.value = data.provider ?? vlmProvider.value
  vlmModel.value    = data.model    ?? vlmModel.value
})

// 手动触发推理
async function askVlm(prompt: string = '') {
  if (vlmAsking.value) return
  vlmAsking.value = true
  try {
    const res: any = await vlmApi.ask(prompt || '', 15)
    if (res?.description) {
      vlmLatest.value   = res.description
      vlmLatestTs.value = res.timestamp ?? (Date.now() / 1000)
      vlmLastMs.value   = Math.round(res.elapsed_ms ?? 0)
      ElMessage.success('VLM 推理完成')
    } else if (res?.error) {
      ElMessage.error(`VLM 失败: ${res.error}`)
    }
  } catch (e: any) {
    ElMessage.error(`VLM 请求失败: ${e.message || e}`)
  } finally {
    vlmAsking.value = false
  }
}

// 时间戳格式化
function formatTs(ts: number): string {
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  const ss = String(d.getSeconds()).padStart(2, '0')
  return `${hh}:${mm}:${ss}`
}

// 启动时拉一次历史（防止刷新页面后空白）
async function loadVlmHistory() {
  try {
    const res: any = await vlmApi.getHistory(20)
    if (Array.isArray(res?.items)) {
      vlmHistory.value = res.items
      if (res.items.length > 0) {
        vlmLatest.value   = res.items[0].description
        vlmLatestTs.value = res.items[0].timestamp
      }
    }
    const st: any = await vlmApi.getStatus()
    if (st) {
      vlmProvider.value = st.provider ?? ''
      vlmModel.value    = st.model    ?? ''
      vlmReady.value    = !!st.ready
    }
  } catch (_e) {
    // 后端可能未启动 VLM 路由，静默
  }
}

// ── FPS 计算 ─────────────────────────────────────────────────────────────────
const cameraParams = computed(() => [
  { label: 'RGB 分辨率', value: `${rgbWidth.value}×${rgbHeight.value}` },
  { label: 'RGB FPS',   value: `${rgbFps.value}` },
  { label: '深度范围',  value: '0.1 ~ 10.0 m' },
  { label: '视场角',   value: '87° × 58°' },
])

// ── 工具函数 ─────────────────────────────────────────────────────────────────
function screenshot(type: 'rgb' | 'depth') {
  const src = type === 'rgb' ? rgbSrc.value : depthSrc.value
  if (!src) { ElMessage.warning('暂无图像'); return }
  const a = document.createElement('a')
  a.href     = src
  a.download = `${type}_${Date.now()}.jpg`
  a.click()
  ElMessage.success('截图已保存')
}

function openFullscreen(src: string) {
  if (!src) return
  const win = window.open('', '_blank')
  if (win) {
    win.document.write(
      `<html><body style="margin:0;background:#000">` +
      `<img src="${src}" style="max-width:100%;max-height:100vh">` +
      `</body></html>`
    )
  }
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
onMounted(() => {
  fpsTimer = setInterval(() => {
    rgbFps.value    = rgbFrameCount
    depthFps.value  = depthFrameCount
    annoFps.value   = annoFrameCount
    rgbFrameCount   = 0
    depthFrameCount = 0
    annoFrameCount  = 0
  }, 1000)
  loadVlmHistory()
})

onUnmounted(() => {
  unsubRgb()
  unsubDepth()
  unsubAnno()
  unsubResults()
  unsubVlmDesc()
  unsubVlmStatus()
  clearInterval(fpsTimer)
  // 释放所有 blob:URL，避免内存泄漏
  if (rgbBlobUrl)   { URL.revokeObjectURL(rgbBlobUrl);   rgbBlobUrl   = null }
  if (depthBlobUrl) { URL.revokeObjectURL(depthBlobUrl); depthBlobUrl = null }
  if (annoBlobUrl)  { URL.revokeObjectURL(annoBlobUrl);  annoBlobUrl  = null }
})
</script>

<style lang="scss" scoped>
.video-view { display: flex; flex-direction: column; gap: 12px; }
.mt12 { margin-top: 0; }

// ── 视频卡片 ──────────────────────────────────────────────────────────────────
.video-card {
  .actions { display: flex; align-items: center; gap: 4px; }
}

.video-container {
  position: relative; background: #000; border-radius: 6px;
  overflow: hidden; aspect-ratio: 4/3;

  .video-frame {
    width: 100%; height: 100%; object-fit: contain; display: block;
  }
  .video-placeholder {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100%; color: var(--color-text-muted); gap: 8px;
    p { font-size: 12px; margin: 0; }
    .hint { font-size: 10px; font-family: var(--font-mono); color: var(--color-primary); opacity: 0.6; }
  }
  .video-overlay {
    position: absolute; bottom: 6px; left: 6px; display: flex; gap: 6px;
    .fps-badge, .res-badge, .infer-badge {
      background: rgba(0,0,0,0.65); color: var(--color-primary);
      font-size: 10px; font-family: var(--font-mono);
      padding: 2px 6px; border-radius: 3px;
    }
    .infer-badge { color: var(--color-warning); }
  }
}

// ── AI 检测面板标题徽章 ───────────────────────────────────────────────────────
.det-badge {
  font-size: 11px; font-family: var(--font-mono);
  color: var(--color-success);
  background: rgba(0, 255, 136, 0.1);
  padding: 1px 7px; border-radius: 10px;
  border: 1px solid rgba(0, 255, 136, 0.3);
}

// ── 识别结果面板 ──────────────────────────────────────────────────────────────
.det-panel {
  display: flex; flex-direction: column; height: 100%;

  .det-empty {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    color: var(--color-text-muted); gap: 8px; padding: 24px 0;
    p { font-size: 12px; margin: 0; }
  }

  .det-list {
    flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;
    padding: 4px 0;
    max-height: 340px;

    // 滚动条美化
    &::-webkit-scrollbar { width: 4px; }
    &::-webkit-scrollbar-track { background: transparent; }
    &::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 2px; }
  }

  .det-item {
    background: rgba(30, 58, 95, 0.25);
    border: 1px solid rgba(30, 58, 95, 0.5);
    border-radius: 6px; padding: 7px 10px;
    display: flex; flex-direction: column; gap: 5px;
    transition: border-color 0.2s;
    &:hover { border-color: var(--color-primary); }
  }

  .det-row {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
  }

  .det-cls {
    font-size: 13px; font-weight: 600; font-family: var(--font-mono);
    text-transform: capitalize;
  }
  .det-dist {
    font-size: 12px; font-family: var(--font-mono);
    color: var(--color-warning); white-space: nowrap;
  }
  .dist-unknown { color: var(--color-text-muted); }

  .conf-bar-wrap {
    flex: 1; height: 4px; background: rgba(255,255,255,0.08);
    border-radius: 2px; overflow: hidden;
    .conf-bar {
      height: 100%; border-radius: 2px;
      transition: width 0.3s ease;
    }
  }
  .conf-val {
    font-size: 10px; font-family: var(--font-mono);
    color: var(--color-text-muted); white-space: nowrap;
  }

  .det-count {
    font-size: 11px; font-family: var(--font-mono); color: var(--color-primary);
  }

  .det-footer {
    display: flex; gap: 12px; padding-top: 8px;
    border-top: 1px solid rgba(30,58,95,0.4);
    font-size: 10px; font-family: var(--font-mono); color: var(--color-text-muted);
  }
}

// ── 深度图例 ──────────────────────────────────────────────────────────────────
.depth-legend {
  display: flex; align-items: center; gap: 8px; margin-top: 8px;
  .legend-label { font-size: 10px; color: var(--color-text-muted); }
  .legend-bar {
    flex: 1; height: 6px; border-radius: 3px;
    background: linear-gradient(90deg, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff);
  }
}

// ── VLM 场景理解 ──────────────────────────────────────────────────────────────
.vlm-card {
  .vlm-provider {
    font-size: 10px; font-family: var(--font-mono);
    color: var(--color-text-muted); margin-left: 8px; font-weight: normal;
  }
  .actions { display: flex; align-items: center; gap: 6px; }

  // ── 本地/云端 模式徽标 ──────────────────────────────────────────────────
  .mode-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    margin-left: 8px;
    padding: 1px 8px;
    border-radius: 10px;
    border: 1px solid;
    font-size: 11px;
    font-family: var(--font-mono);
    font-weight: 600;
    line-height: 18px;
    letter-spacing: 0.3px;

    .mode-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      box-shadow: 0 0 6px currentColor;
      animation: mode-dot-pulse 1.4s ease-in-out infinite;
    }
  }
}

@keyframes mode-dot-pulse {
  0%, 100% { opacity: 1;   transform: scale(1); }
  50%      { opacity: 0.5; transform: scale(0.85); }
}

.vlm-latest {
  min-height: 64px;
  background: rgba(167, 139, 250, 0.06);
  border: 1px solid rgba(167, 139, 250, 0.25);
  border-radius: 6px; padding: 10px 12px;
  display: flex; flex-direction: column; gap: 6px;

  .vlm-text {
    font-size: 14px; line-height: 1.6; color: var(--color-text);
    white-space: pre-wrap; word-break: break-word;
  }
  .vlm-empty {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 6px; padding: 12px 0; color: var(--color-text-muted);
    p { font-size: 12px; margin: 0; }
    .hint { font-size: 10px; font-family: var(--font-mono); color: #a78bfa; opacity: 0.7; }
  }
  .vlm-meta {
    display: flex; gap: 10px;
    font-size: 10px; font-family: var(--font-mono); color: var(--color-text-muted);
  }
}

.vlm-prompt-bar {
  margin-top: 8px;
  display: flex; gap: 8px;
}

.vlm-history {
  margin-top: 4px;
  :deep(.el-collapse-item__header) {
    font-size: 12px; color: var(--color-text-muted);
    background: transparent; border-bottom: 1px dashed rgba(30,58,95,0.4);
  }
  :deep(.el-collapse-item__wrap) { background: transparent; border: 0; }
  :deep(.el-collapse-item__content) { padding-bottom: 6px; }

  .vlm-history-empty {
    font-size: 11px; color: var(--color-text-muted); padding: 6px 0;
  }
  .vlm-history-item {
    display: flex; gap: 10px; padding: 5px 0;
    border-bottom: 1px dashed rgba(30,58,95,0.25);
    font-size: 12px; line-height: 1.5;
    &:last-child { border-bottom: 0; }
    .hist-ts {
      font-family: var(--font-mono); color: var(--color-text-muted);
      flex-shrink: 0; min-width: 56px;
    }
    .hist-text { color: var(--color-text); word-break: break-word; }
  }
}

// ── 相机参数 ──────────────────────────────────────────────────────────────────
.param-item {
  display: flex; flex-direction: column; padding: 8px 0;
  border-bottom: 1px solid rgba(30,58,95,0.4);
  .param-label { font-size: 11px; color: var(--color-text-muted); }
  .param-value {
    font-size: 13px; font-family: var(--font-mono);
    color: var(--color-primary); margin-top: 2px;
  }
}
</style>
