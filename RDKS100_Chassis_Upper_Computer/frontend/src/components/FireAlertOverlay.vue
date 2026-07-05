<!--
  FireAlertOverlay —— 全局火警告警 UI
  包含三部分：
    1. 顶部红色横幅（level=high 显示在最顶层，永不被路由切换隐藏）
    2. 中央弹窗 ElDialog（带画面截图 + 处置建议 + "我知道了"按钮）
    3. 音频解锁兜底（用户首次点击页面任意位置时激活 AudioContext）

  通过 useFireAlert composable 与全局 state 同步，因此放在 App.vue 根部即可全局生效。
-->
<template>
  <!-- 顶部红色横幅：仅在 level=high 且未 dismiss 时显示 -->
  <transition name="fire-banner">
    <div
      v-if="visibleLatest && visibleLatest.level === 'high'"
      class="fire-banner"
      role="alert"
    >
      <span class="fire-icon">🔥</span>
      <div class="banner-text">
        <strong>火警告警 · 高危</strong>
        <span class="banner-detail">
          {{ shortReason }}
          <span v-if="visibleLatest.confidence != null" class="conf">
            置信度 {{ (visibleLatest.confidence * 100).toFixed(0) }}%
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

  <!-- 低级告警（low）：右下角 toast 风格小条，不阻塞操作 -->
  <transition name="fire-toast">
    <div
      v-if="visibleLatest && visibleLatest.level === 'low'"
      class="fire-toast"
      role="status"
    >
      <span class="toast-icon">⚠️</span>
      <div class="toast-text">
        <strong>疑似火情</strong>
        <span class="toast-detail">{{ shortReason }}</span>
      </div>
      <el-button size="small" link @click="onOpenDialog">详情</el-button>
      <el-button size="small" link @click="onDismiss">忽略</el-button>
    </div>
  </transition>

  <!-- 中央详情弹窗 -->
  <el-dialog
    v-model="dialogVisible"
    :title="dialogTitle"
    width="640px"
    :close-on-click-modal="false"
    :show-close="true"
    class="fire-dialog"
    @close="onDialogClose"
  >
    <div v-if="dialogPayload" class="dialog-body">
      <!-- 画面截图（若 backend 带了 image_b64） -->
      <div v-if="dialogPayload.image_b64" class="snapshot">
        <img
          :src="`data:image/jpeg;base64,${dialogPayload.image_b64}`"
          alt="火警画面截图"
        />
      </div>
      <div v-else class="snapshot snapshot-empty">
        <span>本次未附带画面（可在 vlm_params.yaml 打开 fire_alert_include_image）</span>
      </div>

      <!-- 结构化信息 -->
      <el-descriptions :column="2" border size="small" class="info">
        <el-descriptions-item label="级别">
          <el-tag
            :type="dialogPayload.level === 'high' ? 'danger' : 'warning'"
            effect="dark"
          >
            {{ levelText(dialogPayload.level) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="置信度">
          {{ (dialogPayload.confidence * 100).toFixed(0) }}%
        </el-descriptions-item>
        <el-descriptions-item label="火焰">
          {{ dialogPayload.fire_detected ? '检出' : '未检出' }}
        </el-descriptions-item>
        <el-descriptions-item label="烟雾">
          {{ dialogPayload.smoke_detected ? '检出' : '未检出' }}
        </el-descriptions-item>
        <el-descriptions-item label="时间">
          {{ formatTime(dialogPayload.timestamp) }}
        </el-descriptions-item>
        <el-descriptions-item label="模型">
          {{ dialogPayload.provider || '-' }} / {{ dialogPayload.model || '-' }}
        </el-descriptions-item>
        <el-descriptions-item label="判定依据" :span="2">
          {{ dialogPayload.reason || '（VLM 未给出说明）' }}
        </el-descriptions-item>
        <el-descriptions-item label="处置建议" :span="2">
          <strong class="reco">{{ dialogPayload.recommendation || '请人工核实现场情况。' }}</strong>
        </el-descriptions-item>
      </el-descriptions>
    </div>

    <template #footer>
      <el-button @click="onDialogClose">关闭</el-button>
      <el-button type="danger" @click="onAcknowledge">我已知晓</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useFireAlert, type FireAlertPayload } from '@/composables/useFireAlert'

const { visibleLatest, unlockAudio, dismiss } = useFireAlert()

const dialogVisible = ref(false)
const dialogPayload = ref<FireAlertPayload | null>(null)

// 高危警告自动弹窗（首次出现新 frame_id 时）
const lastAutoOpenedFrameId = ref<number | null>(null)
watch(visibleLatest, (curr) => {
  if (!curr) return
  if (curr.level !== 'high') return
  if (curr.frame_id === lastAutoOpenedFrameId.value) return
  lastAutoOpenedFrameId.value = curr.frame_id
  dialogPayload.value = curr
  dialogVisible.value = true
})

const shortReason = computed(() => {
  const r = visibleLatest.value?.reason || ''
  return r.length > 60 ? r.slice(0, 60) + '…' : r
})

const dialogTitle = computed(() => {
  if (!dialogPayload.value) return '火警详情'
  return dialogPayload.value.level === 'high'
    ? '🔥 火警告警 · 高危'
    : '⚠️ 疑似火情 · 待核实'
})

function levelText(lv?: string): string {
  switch (lv) {
    case 'high': return '高危'
    case 'low': return '疑似'
    case 'none': return '无'
    default: return lv || '-'
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

// ---- 音频解锁兜底 ----
// 浏览器要求 AudioContext 必须由用户手势激活。
// 全局监听一次 pointerdown / keydown，触发后立刻取消监听。
function _handleFirstInteract() {
  unlockAudio()
  window.removeEventListener('pointerdown', _handleFirstInteract)
  window.removeEventListener('keydown', _handleFirstInteract)
}

onMounted(() => {
  window.addEventListener('pointerdown', _handleFirstInteract, { once: false })
  window.addEventListener('keydown', _handleFirstInteract, { once: false })
})

onBeforeUnmount(() => {
  window.removeEventListener('pointerdown', _handleFirstInteract)
  window.removeEventListener('keydown', _handleFirstInteract)
})
</script>

<style lang="scss" scoped>
// ---- 顶部红色横幅（高危）----
.fire-banner {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 18px;
  background: linear-gradient(90deg, #d32029 0%, #ff4d4f 50%, #d32029 100%);
  background-size: 200% 100%;
  color: #fff;
  box-shadow: 0 4px 14px rgba(255, 0, 0, 0.5);
  animation: fire-banner-pulse 1.2s ease-in-out infinite;
  font-size: 14px;

  .fire-icon {
    font-size: 22px;
    line-height: 1;
    animation: fire-icon-shake 0.6s ease-in-out infinite alternate;
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
      opacity: 0.9;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      .conf { margin-left: 8px; font-family: var(--font-mono); }
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

// ---- 右下角小条（low）----
.fire-toast {
  position: fixed;
  bottom: 18px;
  right: 18px;
  z-index: 9998;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: rgba(40, 30, 0, 0.95);
  color: #ffd666;
  border: 1px solid rgba(255, 197, 61, 0.5);
  border-radius: 8px;
  box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4);
  font-size: 13px;
  max-width: 420px;

  .toast-icon { font-size: 18px; line-height: 1; }
  .toast-text {
    display: flex;
    flex-direction: column;
    gap: 2px;
    overflow: hidden;
    strong { color: #ffd666; }
    .toast-detail {
      font-size: 11px;
      color: #d8c89a;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
  }
}

// ---- 动画 ----
@keyframes fire-banner-pulse {
  0%, 100% { background-position: 0% 50%; }
  50%      { background-position: 100% 50%; }
}

@keyframes fire-icon-shake {
  0%   { transform: translateY(0) scale(1); }
  100% { transform: translateY(-2px) scale(1.1); }
}

.fire-banner-enter-active,
.fire-banner-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.fire-banner-enter-from,
.fire-banner-leave-to {
  transform: translateY(-100%);
  opacity: 0;
}

.fire-toast-enter-active,
.fire-toast-leave-active {
  transition: transform 0.25s ease, opacity 0.25s ease;
}
.fire-toast-enter-from,
.fire-toast-leave-to {
  transform: translateY(20px);
  opacity: 0;
}

// ---- 弹窗内部布局 ----
.fire-dialog {
  .dialog-body {
    display: flex;
    flex-direction: column;
    gap: 14px;
  }
  .snapshot {
    width: 100%;
    border-radius: 6px;
    overflow: hidden;
    background: #000;
    img {
      width: 100%;
      display: block;
      object-fit: contain;
      max-height: 320px;
    }
    &.snapshot-empty {
      padding: 24px;
      color: var(--color-text-muted);
      text-align: center;
      font-size: 12px;
      background: var(--color-bg-card);
    }
  }
  .info {
    .reco {
      color: var(--color-danger, #ff4d4f);
      font-weight: 700;
    }
  }
}
</style>
