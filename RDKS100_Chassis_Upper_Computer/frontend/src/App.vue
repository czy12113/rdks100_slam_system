<template>
  <router-view />
  <!-- 全局火警告警层：横幅 + 弹窗 + 报警音，所有页面共享 -->
  <FireAlertOverlay />
  <!-- 全局动态行人避障事件层：横幅（stop）+ toast（reroute）+ 详情弹窗 -->
  <SafetyEventOverlay />
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useRobotStore } from '@/stores/robot'
import { wsClient } from '@/api/websocket'
import { controlApi } from '@/api/http'
import FireAlertOverlay from '@/components/FireAlertOverlay.vue'
import SafetyEventOverlay from '@/components/SafetyEventOverlay.vue'

const robotStore = useRobotStore()

/**
 * 全局兜底急停：
 *   即使用户从未进入"机器人控制"页，浏览器关闭/刷新/导航离开/标签隐藏时
 *   也要保证 STM32 收到停车指令。
 *   - pagehide / beforeunload：通过 sendBeacon 走 HTTP，浏览器允许在卸载阶段发出
 *   - visibilitychange (hidden)：通过 WebSocket 发零速 + estop（仍在线时低成本）
 */
function globalSafetyStop() {
  try {
    wsClient.sendCmdVel(0, 0, 0)
    wsClient.sendEstop()
  } catch (_) { /* ignore */ }
  // sendBeacon：浏览器卸载阶段也能保证发出
  wsClient.beaconEstop('/api/control/stop')
  controlApi.stop().catch(() => {})
}

function onPageHide() { globalSafetyStop() }
function onBeforeUnload() { globalSafetyStop() }
function onVisibility() {
  if (document.visibilityState === 'hidden') {
    // 隐藏时只发零速，不锁急停（避免回来时被锁住）
    try {
      wsClient.sendCmdVel(0, 0, 0)
    } catch (_) { /* ignore */ }
  }
}

onMounted(() => {
  robotStore.initWebSocket()
  window.addEventListener('pagehide', onPageHide)
  window.addEventListener('beforeunload', onBeforeUnload)
  document.addEventListener('visibilitychange', onVisibility)
})

onUnmounted(() => {
  window.removeEventListener('pagehide', onPageHide)
  window.removeEventListener('beforeunload', onBeforeUnload)
  document.removeEventListener('visibilitychange', onVisibility)
})
</script>
