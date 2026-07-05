<!--
  SafetyEventOverlay —— 全局"动态行人避障"安全事件 UI

  数据来源：
    dynamic_person_obstacle_node 发布 /vlm/safety_event
      → backend push_safety_event → WS topic "safety_event"
      → useSafetyEvent() composable

  展示分层：
    1. 顶部红色横幅：action === 'stop'（紧急停车 · 高风险）
    2. 右下角小条 toast：action === 'reroute'（绕行中 · 低风险）
    3. ElDialog：显示完整详情（人数、最近距离、原因、VLM 摘要、重规划次数）

  与 FireAlertOverlay 并列挂载在 App.vue，二者互不干扰。
-->
<template>
  <!-- ============== 顶部红色横幅（stop） ============== -->
  <transition name="safety-banner">
    <div
      v-if="visibleLatest && visibleLatest.action === 'stop'"
      class="safety-banner"
      role="alert"
    >
      <span class="safety-icon">🛑</span>
      <div class="banner-text">
        <strong>紧急停车 · 前方有人</strong>
        <span class="banner-detail">
          {{ shortReason }}
          <span v-if="visibleLatest.min_distance_m != null" class="dist">
            最近 {{ visibleLatest.min_distance_m.toFixed(2) }} m
          </span>
          <span v-if="visibleLatest.person_count != null" class="cnt">
            · 行人 {{ visibleLatest.person_count }}
          </span>
          <span class="be">
            · {{ currentBackendLabel }}
          </span>
        </span>
      </div>
      <el-button
        type="warning"
        size="small"
        class="banner-btn"
        @click="onOpenDialog"
      >
        查看详情
      </el-button>
      <el-button
        size="small"
        text
        class="banner-close"
        @click="onDismiss"
        title="关闭横幅（不会清除历史）"
      >
        ✕
      </el-button>
    </div>
  </transition>

  <!-- ============== 右下角小条（reroute） ============== -->
  <transition name="safety-toast">
    <div
      v-if="visibleLatest && visibleLatest.action === 'reroute'"
      class="safety-toast"
      role="status"
    >
      <span class="toast-icon">🚧</span>
      <div class="toast-text">
        <strong>正在绕行</strong>
        <span class="toast-detail">
          {{ shortReason }}
          <span v-if="visibleLatest.min_distance_m != null" class="dist">
            {{ visibleLatest.min_distance_m.toFixed(2) }} m
          </span>
          <span class="be">
            · {{ currentBackendLabel }}
          </span>
        </span>
      </div>
      <el-button size="small" link @click="onOpenDialog">详情</el-button>
      <el-button size="small" link @click="onDismiss">忽略</el-button>
    </div>
  </transition>

  <!-- ============== 中央详情弹窗 ============== -->
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="560px"
    :close-on-click-modal="false"
    :show-close="true"
    class="safety-dialog"
    @close="onDialogClose"
  >
    <div v-if="dialogPayload" class="dialog-body">
      <el-descriptions :column="2" border size="small" class="info">
        <el-descriptions-item label="动作">
          <el-tag
            :type="actionTagType(dialogPayload.action)"
            effect="dark"
          >
            {{ actionText(dialogPayload.action) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="上次动作">
          {{ actionText(dialogPayload.prev_action) }}
        </el-descriptions-item>
        <el-descriptions-item label="行人数量">
          {{ dialogPayload.person_count ?? '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="最近距离">
          <span class="mono">
            {{ dialogPayload.min_distance_m != null
                ? dialogPayload.min_distance_m.toFixed(2) + ' m'
                : '-' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="重规划次数">
          <span class="mono">{{ dialogPayload.replan_count ?? 0 }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="急停触发">
          <el-tag
            :type="dialogPayload.estop_triggered ? 'danger' : 'info'"
            size="small"
          >
            {{ dialogPayload.estop_triggered ? '是' : '否' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="时间" :span="2">
          {{ formatTime(dialogPayload.timestamp) }}
        </el-descriptions-item>
        <el-descriptions-item label="判定依据" :span="2">
          {{ dialogPayload.reason || '（未提供）' }}
        </el-descriptions-item>
      </el-descriptions>

      <div class="vlm-summary">
        <div class="summary-header">
          <strong>VLM 判定摘要</strong>
          <el-tag
            :type="backendTagType(dialogPayload.vlm_summary?.backend)"
            size="small"
          >
            {{ backendLabel(dialogPayload.vlm_summary?.backend) }}
          </el-tag>
          <el-tag
            v-if="dialogPayload.vlm_summary?.provider"
            type="info"
            size="small"
          >
            {{ dialogPayload.vlm_summary.provider }}
          </el-tag>
          <span
            v-if="dialogPayload.vlm_summary?.elapsed_ms != null"
            class="latency mono"
          >
            {{ dialogPayload.vlm_summary.elapsed_ms.toFixed(0) }} ms
          </span>
        </div>
        <div class="summary-body">
          {{ dialogPayload.vlm_summary?.description || '（VLM 未给出描述）' }}
        </div>
      </div>

      <!-- 计数器统计 -->
      <div class="counter-row">
        <div class="counter-item">
          <span class="counter-label">累计绕行</span>
          <span class="counter-value mono">{{ counters.reroute }}</span>
        </div>
        <div class="counter-item">
          <span class="counter-label">累计停车</span>
          <span class="counter-value mono danger">{{ counters.stop }}</span>
        </div>
        <div class="counter-item">
          <span class="counter-label">急停触发</span>
          <span class="counter-value mono danger">{{ counters.estop }}</span>
        </div>
      </div>
    </div>

    <template #footer>
      <el-button @click="onDialogClose">关闭</el-button>
      <el-button type="danger" @click="onAcknowledge">我已知晓</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import {
  useSafetyEvent,
  type SafetyEventPayload,
  type SafetyAction,
} from '@/composables/useSafetyEvent'

const {
  visibleLatest,
  counters,
  currentBackendLabel,
  dismiss,
} = useSafetyEvent()

const dialogVisible = ref(false)
const dialogPayload = ref<SafetyEventPayload | null>(null)

// stop 动作自动弹窗（同一时间戳只弹一次）
const lastAutoOpenedTs = ref<number | null>(null)
watch(visibleLatest, (curr) => {
  if (!curr) return
  if (curr.action !== 'stop') return
  if (curr.timestamp === lastAutoOpenedTs.value) return
  lastAutoOpenedTs.value = curr.timestamp
  dialogPayload.value = curr
  dialogVisible.value = true
})

const shortReason = computed(() => {
  const r = visibleLatest.value?.reason || ''
  return r.length > 48 ? r.slice(0, 48) + '…' : r
})

const dialogTitle = computed(() => {
  if (!dialogPayload.value) return '安全事件详情'
  switch (dialogPayload.value.action) {
    case 'stop':    return '🛑 紧急停车 · 前方有人'
    case 'reroute': return '🚧 动态障碍绕行中'
    default:        return '安全事件详情'
  }
})

function actionText(act?: SafetyAction | string): string {
  switch (act) {
    case 'stop':    return '停车'
    case 'reroute': return '绕行'
    case 'clear':   return '通畅'
    default:        return act || '-'
  }
}

function actionTagType(act?: SafetyAction | string) {
  switch (act) {
    case 'stop':    return 'danger'
    case 'reroute': return 'warning'
    case 'clear':   return 'success'
    default:        return 'info'
  }
}

function backendLabel(be?: string): string {
  switch (be) {
    case 'hf':         return '本地 · HuggingFace'
    case 'rule_based': return '本地 · 规则兜底'
    case 'cloud':      return '云端'
    default:           return be || '未知'
  }
}

function backendTagType(be?: string) {
  switch (be) {
    case 'hf':         return 'success'
    case 'rule_based': return 'warning'
    case 'cloud':      return 'primary'
    default:           return 'info'
  }
}

function formatTime(ts?: number): string {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  const pad = (n: number) => n.toString().padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ` +
         `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

function onOpenDialog() {
  dialogPayload.value = visibleLatest.value
  dialogVisible.value = true
}

function onDialogClose() {
  dialogVisible.value = false
}

function onAcknowledge() {
  dismiss()
  dialogVisible.value = false
}

function onDismiss() {
  dismiss()
}
</script>

<style lang="scss" scoped>
// ---- 顶部红色横幅（stop） ----
.safety-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9997;   // 略低于 FireAlertOverlay(9999)，让火警优先
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 18px;
  background: linear-gradient(90deg, #a8071a 0%, #f5222d 50%, #a8071a 100%);
  background-size: 200% 100%;
  color: #fff;
  box-shadow: 0 4px 14px rgba(255, 0, 0, 0.4);
  animation: safety-banner-pulse 1.4s ease-in-out infinite;
  font-size: 14px;

  .safety-icon {
    font-size: 22px;
    line-height: 1;
    animation: safety-icon-shake 0.5s ease-in-out infinite alternate;
  }

  .banner-text {
    flex: 1;
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow: hidden;
    strong { font-size: 14px; font-weight: 700; }
    .banner-detail {
      font-size: 12px;
      opacity: 0.92;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      .dist, .cnt, .be {
        margin-left: 6px;
        font-family: var(--font-mono);
      }
      .be { opacity: 0.85; }
    }
  }

  .banner-btn { flex-shrink: 0; }
  .banner-close {
    color: #fff;
    flex-shrink: 0;
    font-size: 16px;
    line-height: 1;
    &:hover { background: rgba(255, 255, 255, 0.15); }
  }
}

// ---- 右下角小条（reroute） ----
.safety-toast {
  position: fixed;
  bottom: 18px;
  right: 18px;
  z-index: 9996;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(28, 30, 40, 0.95);
  color: #91caff;
  border: 1px solid rgba(64, 150, 255, 0.55);
  border-radius: 8px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
  font-size: 13px;
  max-width: 460px;

  .toast-icon { font-size: 18px; line-height: 1; }
  .toast-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow: hidden;
    strong { color: #91caff; }
    .toast-detail {
      font-size: 11px;
      color: #a3c3e0;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      .dist, .be {
        margin-left: 6px;
        font-family: var(--font-mono);
      }
    }
  }
}

// ---- 动画 ----
@keyframes safety-banner-pulse {
  0%, 100% { background-position: 0% 50%; }
  50%      { background-position: 100% 50%; }
}

@keyframes safety-icon-shake {
  0%   { transform: translateY(0) scale(1); }
  100% { transform: translateY(-2px) scale(1.15); }
}

.safety-banner-enter-active,
.safety-banner-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.safety-banner-enter-from,
.safety-banner-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}

.safety-toast-enter-active,
.safety-toast-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.safety-toast-enter-from,
.safety-toast-leave-to {
  transform: translateY(20px);
  opacity: 0;
}

// ---- 弹窗内部布局 ----
.safety-dialog {
  .dialog-body {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .mono {
    font-family: var(--font-mono, monospace);
  }
  .danger {
    color: var(--color-danger, #ff4d4f);
    font-weight: 700;
  }

  .vlm-summary {
    background: var(--color-bg-card, #1a1c24);
    border: 1px solid var(--color-border, #2b2f3a);
    border-radius: 6px;
    padding: 10px 12px;

    .summary-header {
      display: flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 6px;
      strong { font-size: 13px; }
      .latency {
        margin-left: auto;
        color: var(--color-text-muted, #909399);
        font-size: 12px;
      }
    }
    .summary-body {
      font-size: 13px;
      line-height: 1.55;
      color: var(--color-text-primary, #e5e7eb);
      white-space: pre-wrap;
      word-break: break-word;
    }
  }

  .counter-row {
    display: flex;
    gap: 16px;
    padding: 8px 4px 2px;
    .counter-item {
      display: flex;
      flex-direction: column;
      gap: 2px;
      .counter-label {
        font-size: 11px;
        color: var(--color-text-muted, #909399);
      }
      .counter-value {
        font-size: 18px;
        font-weight: 700;
      }
    }
  }
}
</style>
