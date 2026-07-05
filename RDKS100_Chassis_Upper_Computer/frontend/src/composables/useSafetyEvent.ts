// =============================================================================
// useSafetyEvent —— 全局安全事件状态（模块级单例）
//
// 数据流：dynamic_person_obstacle_node 发布 /vlm/safety_event（JSON）
//        → backend push_safety_event 转发到 WS topic "safety_event"
//        → 本 composable 订阅一次，所有组件共享同一份 state
//
// 与 useFireAlert 结构一致：
//   - latest:          最新一次动作事件（clear/reroute/stop）
//   - visibleLatest:   仅在 action 不为 clear 且未 dismiss 时返回
//   - dismiss():       "我知道了"，抑制当前横幅
//   - counters:        累计 reroute / stop / estop 次数（前端可用于统计展示）
// =============================================================================

import { ref, computed, onScopeDispose, getCurrentScope } from 'vue'
import { wsClient } from '@/api/websocket'

export type SafetyAction = 'clear' | 'reroute' | 'stop'

export interface SafetyEventVlmSummary {
  provider?: string
  backend?: string       // "hf" | "rule_based" | "cloud" | ...
  model?: string
  description?: string
  elapsed_ms?: number
}

export interface SafetyEventPayload {
  timestamp: number
  action: SafetyAction
  prev_action?: SafetyAction
  person_count?: number
  min_distance_m?: number
  reason?: string
  vlm_summary?: SafetyEventVlmSummary
  replan_count?: number
  estop_triggered?: boolean
}

const HISTORY_MAX = 50

const latest = ref<SafetyEventPayload | null>(null)
const history = ref<SafetyEventPayload[]>([])
const dismissedTimestamps = ref<Set<number>>(new Set())
const counters = ref({
  clear: 0,
  reroute: 0,
  stop: 0,
  estop: 0,
})

let _wsBound = false
let _wsOff: (() => void) | null = null

function _bindWebSocket() {
  if (_wsBound) return
  _wsBound = true
  _wsOff = wsClient.on('safety_event', (data) => {
    if (!data || typeof data !== 'object') return
    const p = data as SafetyEventPayload
    const act = String(p.action || 'clear').toLowerCase()
    if (act !== 'clear' && act !== 'reroute' && act !== 'stop') {
      p.action = 'clear'
    } else {
      p.action = act as SafetyAction
    }

    latest.value = p
    history.value.unshift(p)
    if (history.value.length > HISTORY_MAX) {
      history.value.length = HISTORY_MAX
    }

    counters.value[p.action] = (counters.value[p.action] || 0) + 1
    if (p.estop_triggered) {
      counters.value.estop = (counters.value.estop || 0) + 1
    }

    if (p.action !== 'clear') {
      // eslint-disable-next-line no-console
      console.warn(
        `[SAFETY] action=${p.action} dist=${p.min_distance_m?.toFixed?.(2)}m ` +
        `person=${p.person_count} reason=${p.reason ?? ''}`,
      )
    }
  })
}

_bindWebSocket()

export function useSafetyEvent() {
  const isLatestDismissed = computed(() => {
    if (!latest.value) return true
    return dismissedTimestamps.value.has(latest.value.timestamp)
  })

  const visibleLatest = computed(() => {
    if (!latest.value) return null
    if (latest.value.action === 'clear') return null
    if (isLatestDismissed.value) return null
    return latest.value
  })

  const currentAction = computed<SafetyAction>(() => latest.value?.action ?? 'clear')

  const currentBackendLabel = computed<string>(() => {
    const be = latest.value?.vlm_summary?.backend
    if (be === 'hf') return '本地HF'
    if (be === 'rule_based') return '本地规则'
    if (be === 'cloud') return '云端'
    return be || '未知'
  })

  function dismiss() {
    if (latest.value) {
      dismissedTimestamps.value.add(latest.value.timestamp)
      dismissedTimestamps.value = new Set(dismissedTimestamps.value)
    }
  }

  function clearAll() {
    history.value = []
    latest.value = null
    dismissedTimestamps.value = new Set()
    counters.value = { clear: 0, reroute: 0, stop: 0, estop: 0 }
  }

  if (getCurrentScope()) {
    onScopeDispose(() => { /* no-op：单例 */ })
  }

  return {
    latest,
    history,
    counters,
    visibleLatest,
    currentAction,
    currentBackendLabel,
    dismiss,
    clearAll,
  }
}

/** 仅供测试 / HMR 使用 */
export function _disposeSafetyEventForTest() {
  if (_wsOff) {
    _wsOff()
    _wsOff = null
  }
  _wsBound = false
  latest.value = null
  history.value = []
  dismissedTimestamps.value = new Set()
  counters.value = { clear: 0, reroute: 0, stop: 0, estop: 0 }
}
