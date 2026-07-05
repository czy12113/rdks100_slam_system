// =============================================================================
// useVlmProvider —— 全局 VLM Provider 状态（模块级单例）
//
// 数据流：vlm_node 发布 /vlm/status（JSON） → backend push_vlm_status
//        → WS topic "vlm_status" → 本 composable 单例订阅
//        另外还监听 vlm_description 内的 provider 字段做兜底。
//
// 主要用于视频页顶部显示"本地离线 / 云端增强"标签，帮助演示：
//   - internvl_local + backend=rule_based → "本地离线（规则兜底）"
//   - internvl_local + backend=hf         → "本地轻量VLM"
//   - qwen_vl / openai_vision / ...       → "云端增强"
// =============================================================================

import { ref, computed, onScopeDispose, getCurrentScope } from 'vue'
import { wsClient } from '@/api/websocket'

export interface VlmStatusPayload {
  timestamp?: number
  state?: 'idle' | 'inferring' | 'error' | string
  provider?: string
  model?: string
  last_error?: string | null
  stats?: {
    requests?: number
    errors?: number
    avg_ms?: number
  }
  // 少数消息（如 startup / heartbeat）会包含 sub/pub topic 列表
  sub?: Record<string, string>
  pub?: Record<string, string>
  ready?: boolean
  providers_available?: string[]
}

export interface VlmDescriptionPayload {
  timestamp?: number
  provider?: string
  model?: string
  elapsed_ms?: number
  description?: string
  backend?: string     // internvl_local 自己带 "hf" | "rule_based"
  [k: string]: unknown
}

// ---- 单例 state ----
const status = ref<VlmStatusPayload | null>(null)
const lastDescription = ref<VlmDescriptionPayload | null>(null)

let _wsBound = false
let _offStatus: (() => void) | null = null
let _offDesc: (() => void) | null = null

function _bindOnce() {
  if (_wsBound) return
  _wsBound = true
  _offStatus = wsClient.on('vlm_status', (data) => {
    if (!data || typeof data !== 'object') return
    status.value = data as VlmStatusPayload
  })
  _offDesc = wsClient.on('vlm_description', (data) => {
    if (!data || typeof data !== 'object') return
    lastDescription.value = data as VlmDescriptionPayload
  })
}
_bindOnce()

const LOCAL_PROVIDERS = new Set(['internvl_local', 'local', 'mock'])

export function useVlmProvider() {
  const provider = computed<string>(() => {
    return (
      status.value?.provider ||
      lastDescription.value?.provider ||
      'unknown'
    )
  })

  const backend = computed<string>(() => {
    // internvl_local 会在 /vlm/scene_description JSON 里塞一个 backend 字段
    // ("hf" | "rule_based")，让前端区分"真正本地推理"与"规则兜底"
    return String(lastDescription.value?.backend || '')
  })

  const isLocal = computed<boolean>(() => LOCAL_PROVIDERS.has(provider.value))

  const modeLabel = computed<string>(() => {
    if (provider.value === 'mock') return '离线Mock'
    if (provider.value === 'internvl_local') {
      if (backend.value === 'hf') return '本地轻量VLM'
      if (backend.value === 'rule_based') return '本地规则兜底'
      return '本地轻量VLM'
    }
    if (provider.value === 'qwen_vl') return '云端·通义千问VL'
    if (provider.value === 'openai_vision') return '云端·OpenAI兼容'
    if (provider.value === 'deepseek_text') return '云端·DeepSeek'
    if (provider.value === 'unknown') return '未知'
    return `云端·${provider.value}`
  })

  const modeColor = computed<string>(() => {
    return isLocal.value ? '#22c55e' : '#3b82f6'   // 本地绿、云端蓝
  })

  const avgLatencyMs = computed<number | null>(() => {
    const v = status.value?.stats?.avg_ms
    return typeof v === 'number' && isFinite(v) ? v : null
  })

  if (getCurrentScope()) {
    onScopeDispose(() => { /* 单例 */ })
  }

  return {
    status,
    lastDescription,
    provider,
    backend,
    isLocal,
    modeLabel,
    modeColor,
    avgLatencyMs,
  }
}

/** 仅供测试 / HMR 使用 */
export function _disposeVlmProviderForTest() {
  if (_offStatus) { _offStatus(); _offStatus = null }
  if (_offDesc)   { _offDesc();   _offDesc = null }
  _wsBound = false
  status.value = null
  lastDescription.value = null
}