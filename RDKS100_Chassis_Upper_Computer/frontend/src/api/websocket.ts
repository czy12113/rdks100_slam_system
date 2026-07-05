// =============================================================================
// WebSocket 客户端管理器
// 自动重连、心跳保活、topic 订阅分发
// =============================================================================

import {
  WS_URL,
  WS_RECONNECT_DELAY_MS,
  WS_RECONNECT_MAX_DELAY_MS,
  WS_RECONNECT_BACKOFF,
  WS_HEARTBEAT_MS,
} from '@/config'

export type WsTopicHandler = (data: unknown) => void

export type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

/**
 * 后端默认就会推送的轻量 topic（与 backend WebSocketManager.DEFAULT_TOPICS 对齐）。
 * 这些 topic 不需要前端额外 subscribe，连上 /ws 就会收到。
 * 其余 topic（lidar / video_* / slam_map / detection_results 等）属于重型 topic，
 * 必须由页面在 wsClient.on() 时显式 subscribe、卸载时 unsubscribe。
 */
const AUTO_SUBSCRIBED_TOPICS = new Set<string>([
  'system',
  'robot_status',
  'heartbeat',
  'log',
  'odom',
  'vlm_status',    // VLM 节点心跳，前端任何页面都可观测
  'fire_alert',    // 安全关键：任何页面都必须能收到火警，与后端 DEFAULT_TOPICS 对齐
  'safety_event',  // 创新点：动态行人 + Nav2 联合决策安全事件，所有页面都能弹窗
])

class WebSocketClient {
  private ws: WebSocket | null = null
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null
  private reconnectDelay: number = WS_RECONNECT_DELAY_MS
  private _status: WsStatus = 'disconnected'
  private _statusListeners: Array<(s: WsStatus) => void> = []

  // topic -> handlers[]
  private handlers: Map<string, WsTopicHandler[]> = new Map()
  // 已经向后端 subscribe 的重型 topic（用于断线重连时重发 subscribe）
  private subscribedTopics: Set<string> = new Set()

  connect() {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) return
    this._setStatus('connecting')
    try {
      this.ws = new WebSocket(WS_URL)
      this.ws.onopen = this._onOpen.bind(this)
      this.ws.onmessage = this._onMessage.bind(this)
      this.ws.onclose = this._onClose.bind(this)
      this.ws.onerror = this._onError.bind(this)
    } catch (e) {
      console.error('[WS] 连接失败:', e)
      this._scheduleReconnect()
    }
  }

  disconnect() {
    this._clearTimers()
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
    this._setStatus('disconnected')
  }

  /**
   * 订阅指定 topic 的消息。
   * 对于重型 topic（不在 AUTO_SUBSCRIBED_TOPICS 中），第一次注册 handler 时
   * 自动向后端发送 subscribe；最后一个 handler 卸载时自动 unsubscribe。
   * 这样 VideoView 卸载后后端就不会再生成视频帧 JSON，反之亦然。
   */
  on(topic: string, handler: WsTopicHandler): () => void {
    if (!this.handlers.has(topic)) {
      this.handlers.set(topic, [])
    }
    const list = this.handlers.get(topic)!
    const wasEmpty = list.length === 0
    list.push(handler)

    if (wasEmpty && !AUTO_SUBSCRIBED_TOPICS.has(topic)) {
      this.subscribedTopics.add(topic)
      this.subscribe(topic)
    }
    return () => this.off(topic, handler)
  }

  /** 取消订阅 */
  off(topic: string, handler: WsTopicHandler) {
    const list = this.handlers.get(topic)
    if (!list) return
    const idx = list.indexOf(handler)
    if (idx !== -1) list.splice(idx, 1)

    // 重型 topic 在没有 handler 时主动通知后端停止推送
    if (list.length === 0 && !AUTO_SUBSCRIBED_TOPICS.has(topic)) {
      this.subscribedTopics.delete(topic)
      this.unsubscribe(topic)
    }
  }

  /** 监听连接状态变化 */
  onStatusChange(cb: (s: WsStatus) => void): () => void {
    this._statusListeners.push(cb)
    return () => {
      const i = this._statusListeners.indexOf(cb)
      if (i !== -1) this._statusListeners.splice(i, 1)
    }
  }

  /** 发送消息到后端 */
  send(msg: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  /**
   * 发送速度控制指令（WebSocket 低延迟通道）
   * 相比 HTTP 消除了请求排队/重发延迟，是主控制通道。
   * 返回 true 表示 WebSocket 已连接并发送成功。
   */
  sendCmdVel(vx: number, vy: number, wz: number): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify({ action: 'cmd_vel', vx, vy, wz }))
    return true
  }

  /**
   * 通过 WebSocket 发送急停指令（双保险：同时也会触发 HTTP stop）
   * WebSocket 通道延迟更低，HTTP 通道更可靠（有重试），两者并行。
   */
  sendEstop(): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify({ action: 'estop' }))
    return true
  }

  /**
   * sendBeacon 兜底：浏览器关闭/刷新/导航离开时仍能把停车送达后端。
   * 通过独立的 HTTP 通道（/api/control/stop）保证 WebSocket 没机会发的最后一帧也能到达。
   * 失败不会阻塞 unload 流程。
   */
  beaconEstop(httpEndpoint: string): boolean {
    try {
      const blob = new Blob(['{}'], { type: 'application/json' })
      return navigator.sendBeacon(httpEndpoint, blob)
    } catch {
      return false
    }
  }

  /** 订阅指定 topic（通知后端） */
  subscribe(topic: string) {
    this.send({ action: 'subscribe', topic })
  }

  /** 取消订阅指定 topic（通知后端） */
  unsubscribe(topic: string) {
    this.send({ action: 'unsubscribe', topic })
  }

  get status(): WsStatus {
    return this._status
  }

  get isConnected(): boolean {
    return this._status === 'connected'
  }

  // ---------------------------------------------------------------------------
  private _onOpen() {
    console.info('[WS] 连接成功')
    this._setStatus('connected')
    this.reconnectDelay = WS_RECONNECT_DELAY_MS
    this._startHeartbeat()
    // 断线重连后：把当前页面已经监听的重型 topic 重新 subscribe 给后端
    for (const topic of this.subscribedTopics) {
      this.subscribe(topic)
    }
  }

  private _onMessage(event: MessageEvent) {
    try {
      const msg = JSON.parse(event.data as string) as { topic: string; data: unknown }
      const { topic, data } = msg
      const list = this.handlers.get(topic)
      if (list && list.length > 0) {
        list.forEach(h => h(data))
      }
    } catch (e) {
      console.warn('[WS] 消息解析失败:', e)
    }
  }

  private _onClose(event: CloseEvent) {
    console.warn(`[WS] 连接断开 code=${event.code}`)
    this._setStatus('disconnected')
    this._clearTimers()
    if (event.code !== 1000) {
      this._scheduleReconnect()
    }
  }

  private _onError(event: Event) {
    console.error('[WS] 连接错误:', event)
    this._setStatus('error')
  }

  private _startHeartbeat() {
    this._clearHeartbeat()
    this.heartbeatTimer = setInterval(() => {
      this.send({ action: 'ping', ts: Date.now() })
    }, WS_HEARTBEAT_MS)
  }

  private _clearHeartbeat() {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer)
      this.heartbeatTimer = null
    }
  }

  private _scheduleReconnect() {
    if (this.reconnectTimer) return
    console.info(`[WS] ${this.reconnectDelay}ms 后重连...`)
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, this.reconnectDelay)
    // 指数退避
    this.reconnectDelay = Math.min(
      this.reconnectDelay * WS_RECONNECT_BACKOFF,
      WS_RECONNECT_MAX_DELAY_MS,
    )
  }

  private _clearTimers() {
    this._clearHeartbeat()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
  }

  private _setStatus(s: WsStatus) {
    this._status = s
    this._statusListeners.forEach(cb => cb(s))
  }
}

// 全局单例
export const wsClient = new WebSocketClient()
