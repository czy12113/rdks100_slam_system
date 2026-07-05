// =============================================================================
// useFireAlert —— 全局火警告警状态（模块级单例）
//
// 数据流：vlm_node 发布 /alert/fire（JSON）→ backend 透传到 WS topic "fire_alert"
//        → 本 composable 订阅一次，所有组件共享同一份 state
//
// 暴露：
//   - latest:        最新一条 fire_alert（v-if 触发横幅/弹窗）
//   - history:       最近 N 条历史（侧栏 / 调试用）
//   - hasUnread:     有未确认的高危警告（level=high）
//   - dismiss():     用户点"我知道了"，把当前 latest 置为已读
//   - clearAll():    清空历史
//   - audioEnabled:  Web Audio 是否已被用户首次交互解锁（浏览器自动播放限制）
//   - unlockAudio(): 在首次用户点击/键盘按下时调用，激活 AudioContext
// =============================================================================

import { ref, computed, onScopeDispose, getCurrentScope } from 'vue'
import { wsClient } from '@/api/websocket'

// ---- 类型 ----
export interface FireAlertBox {
  class_id?: number
  class_name?: string
  confidence?: number
  x1?: number
  y1?: number
  x2?: number
  y2?: number
  distance_m?: number
}

export interface FireAlertPrealert {
  timestamp?: number
  frame_id?: number
  hits?: number
  boxes?: FireAlertBox[]
  [k: string]: unknown
}

export interface FireAlertPayload {
  timestamp: number
  frame_id: number
  level: 'none' | 'low' | 'high'
  fire_detected: boolean
  smoke_detected: boolean
  confidence: number
  reason: string
  recommendation: string
  raw?: string
  provider?: string
  model?: string
  elapsed_ms?: number
  prealert?: FireAlertPrealert
  image_b64?: string
}

// ---- 模块级单例 state（所有组件共享同一份） ----
const HISTORY_MAX = 50

const latest = ref<FireAlertPayload | null>(null)
const history = ref<FireAlertPayload[]>([])
const dismissedFrameIds = ref<Set<number>>(new Set())
const audioEnabled = ref(false)

// AudioContext 单例（延迟创建，浏览器要求用户交互后才能 resume）
let _audioCtx: AudioContext | null = null
let _wsBound = false
let _wsOff: (() => void) | null = null

function _ensureAudioCtx(): AudioContext | null {
  if (_audioCtx) return _audioCtx
  try {
    const Ctor =
      (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext })
        .AudioContext ||
      (window as unknown as { AudioContext?: typeof AudioContext; webkitAudioContext?: typeof AudioContext })
        .webkitAudioContext
    if (!Ctor) return null
    _audioCtx = new Ctor()
    return _audioCtx
  } catch {
    return null
  }
}

/**
 * 浏览器自动播放限制：必须由用户主动手势（点击/按键）激活 AudioContext。
 * 在 App.vue 挂载时绑定一次 pointerdown，可保证后续报警音能正常播放。
 */
function unlockAudio() {
  const ctx = _ensureAudioCtx()
  if (!ctx) return
  if (ctx.state === 'suspended') {
    ctx.resume().catch(() => { /* ignore */ })
  }
  audioEnabled.value = true
}

/**
 * 用 Web Audio 合成一段 "嘀-嘀-嘀" 三连声警报（无需外部音频文件）。
 *   - high 级：4 声、800Hz、0.18s 一拍
 *   - low  级：2 声、500Hz、0.20s 一拍
 *   - none 级：不发声
 * 用户未解锁音频时静默返回。
 */
function playAlarm(level: 'none' | 'low' | 'high') {
  if (level === 'none') return
  const ctx = _ensureAudioCtx()
  if (!ctx || ctx.state !== 'running') return

  const beats = level === 'high' ? 4 : 2
  const freq = level === 'high' ? 880 : 520
  const beatMs = level === 'high' ? 180 : 220
  const gapMs = 80

  let t = ctx.currentTime
  for (let i = 0; i < beats; i++) {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'square'
    osc.frequency.value = freq
    // ADSR 简化：瞬升、保持、瞬降，避免爆音
    gain.gain.setValueAtTime(0, t)
    gain.gain.linearRampToValueAtTime(0.35, t + 0.01)
    gain.gain.setValueAtTime(0.35, t + beatMs / 1000 - 0.02)
    gain.gain.linearRampToValueAtTime(0, t + beatMs / 1000)
    osc.connect(gain).connect(ctx.destination)
    osc.start(t)
    osc.stop(t + beatMs / 1000 + 0.01)
    t += (beatMs + gapMs) / 1000
  }
}

// ---- WS 订阅（模块加载即注册，单例） ----
function _bindWebSocket() {
  if (_wsBound) return
  _wsBound = true
  _wsOff = wsClient.on('fire_alert', (data) => {
    if (!data || typeof data !== 'object') return
    const payload = data as FireAlertPayload
    // 规范化 level
    const lv = String(payload.level || 'none').toLowerCase()
    if (lv !== 'none' && lv !== 'low' && lv !== 'high') {
      payload.level = 'low'
    } else {
      payload.level = lv as 'none' | 'low' | 'high'
    }

    latest.value = payload
    history.value.unshift(payload)
    if (history.value.length > HISTORY_MAX) {
      history.value.length = HISTORY_MAX
    }

    // 触发报警音（level=none 不响）
    playAlarm(payload.level)

    // 控制台留痕，方便调试
    if (payload.level !== 'none') {
      // eslint-disable-next-line no-console
      console.warn(
        `[FIRE_ALERT] level=${payload.level} fire=${payload.fire_detected} ` +
        `smoke=${payload.smoke_detected} conf=${payload.confidence?.toFixed?.(2)} ` +
        `reason=${payload.reason}`,
      )
    }
  })
}

// 立即绑定（避免组件懒挂载时漏掉首条警告）
_bindWebSocket()

/**
 * Composable 入口：所有组件都通过它读取 / 操作火警状态。
 * 同一份 state 跨组件共享，不会重复订阅 WS。
 */
export function useFireAlert() {
  const isLatestDismissed = computed(() => {
    if (!latest.value) return true
    return dismissedFrameIds.value.has(latest.value.frame_id)
  })

  const visibleLatest = computed(() => {
    // 只有当存在 latest 且 level != none 且未被用户 dismiss 时才返回，
    // 否则返回 null（横幅/弹窗都不显示）
    if (!latest.value) return null
    if (latest.value.level === 'none') return null
    if (isLatestDismissed.value) return null
    return latest.value
  })

  const hasUnreadHigh = computed(() => {
    return !!visibleLatest.value && visibleLatest.value.level === 'high'
  })

  function dismiss() {
    if (latest.value) {
      dismissedFrameIds.value.add(latest.value.frame_id)
      // 触发响应式更新（Set 直接 add 不会被 Vue 自动追踪）
      dismissedFrameIds.value = new Set(dismissedFrameIds.value)
    }
  }

  function clearAll() {
    history.value = []
    latest.value = null
    dismissedFrameIds.value = new Set()
  }

  // 不在组件卸载时取消 WS 订阅：composable 是全局单例，
  // 多个组件同时使用时不能因任一组件卸载而取消。
  // 仅在 HMR 或测试时显式调用 _disposeForTest() 才解绑。
  if (getCurrentScope()) {
    onScopeDispose(() => { /* no-op，保留单例 */ })
  }

  return {
    latest,
    history,
    visibleLatest,
    hasUnreadHigh,
    audioEnabled,
    unlockAudio,
    dismiss,
    clearAll,
  }
}

/** 仅供测试 / HMR 使用，正常代码不要调用 */
export function _disposeFireAlertForTest() {
  if (_wsOff) {
    _wsOff()
    _wsOff = null
  }
  _wsBound = false
  latest.value = null
  history.value = []
  dismissedFrameIds.value = new Set()
}
