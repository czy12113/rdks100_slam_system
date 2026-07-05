<template>
  <el-container class="main-layout">
    <!-- 侧边栏 -->
    <el-aside :width="isCollapsed ? '64px' : '200px'" class="sidebar">
      <div class="logo" @click="isCollapsed = !isCollapsed">
        <span class="logo-icon">🤖</span>
        <span v-show="!isCollapsed" class="logo-text">RDK S100</span>
      </div>
      <el-menu
        :default-active="currentRoute"
        :collapse="isCollapsed"
        router
        class="sidebar-menu"
        background-color="transparent"
        text-color="#6b7a99"
        active-text-color="#00d4ff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><Monitor /></el-icon>
          <template #title>综合监控</template>
        </el-menu-item>
        <el-menu-item index="/video">
          <el-icon><VideoCamera /></el-icon>
          <template #title>视频监控</template>
        </el-menu-item>
        <el-menu-item index="/lidar">
          <el-icon><Aim /></el-icon>
          <template #title>激光雷达</template>
        </el-menu-item>
        <el-menu-item index="/imu">
          <el-icon><Compass /></el-icon>
          <template #title>IMU 姿态</template>
        </el-menu-item>
        <el-menu-item index="/control">
          <el-icon><Promotion /></el-icon>
          <template #title>机器人控制</template>
        </el-menu-item>
        <el-menu-item index="/slam">
          <el-icon><MapLocation /></el-icon>
          <template #title>SLAM 建图</template>
        </el-menu-item>
        <el-menu-item index="/navigation">
          <el-icon><Position /></el-icon>
          <template #title>导航规划</template>
        </el-menu-item>
        <el-menu-item index="/settings">
          <el-icon><Setting /></el-icon>
          <template #title>设备管理</template>
        </el-menu-item>
      </el-menu>

      <!-- 底部状态 -->
      <div v-show="!isCollapsed" class="sidebar-footer">
        <div class="ws-status">
          <span class="status-dot" :class="wsStatusClass"></span>
          <span class="status-text">{{ wsStatusText }}</span>
        </div>
      </div>
    </el-aside>

    <!-- 主内容区 -->
    <el-container class="main-container">
      <!-- 顶部栏 -->
      <el-header class="top-bar" height="48px">
        <div class="top-left">
          <span class="page-title">{{ currentTitle }}</span>
        </div>
        <div class="top-right">
          <div class="status-item" v-if="robotStore.systemInfo">
            <span class="label">CPU</span>
            <span class="value" :class="robotStore.cpuLevel">{{ robotStore.cpuUsage.toFixed(0) }}%</span>
          </div>
          <div class="status-item" v-if="robotStore.systemInfo">
            <span class="label">温度</span>
            <span class="value" :class="robotStore.tempLevel">{{ robotStore.temperature.toFixed(0) }}°C</span>
          </div>
          <div class="status-item" v-if="robotStore.robotStatus">
            <span class="label">电量</span>
            <span class="value" :class="robotStore.batteryLevel">{{ robotStore.batteryPercent.toFixed(0) }}%</span>
          </div>
          <div class="status-item">
            <span class="status-dot" :class="robotStore.isOnline ? 'online pulse' : 'offline'"></span>
            <span class="value">{{ robotStore.isOnline ? '在线' : '离线' }}</span>
          </div>
        </div>
      </el-header>

      <!-- 页面内容 -->
      <el-main class="page-content">
        <router-view v-slot="{ Component }">
          <transition name="fade" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </el-main>
    </el-container>
  </el-container>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useRobotStore } from '@/stores/robot'

const route = useRoute()
const robotStore = useRobotStore()
const isCollapsed = ref(false)

const currentRoute = computed(() => route.path)
const currentTitle = computed(() => (route.meta?.title as string) || 'RDK S100')

const wsStatusClass = computed(() => {
  switch (robotStore.wsStatus) {
    case 'connected': return 'online'
    case 'connecting': return 'warn pulse'
    case 'error': return 'offline'
    default: return 'offline'
  }
})

const wsStatusText = computed(() => {
  switch (robotStore.wsStatus) {
    case 'connected': return '已连接'
    case 'connecting': return '连接中...'
    case 'error': return '连接错误'
    default: return '未连接'
  }
})
</script>

<style lang="scss" scoped>
.main-layout {
  height: 100vh;
  overflow: hidden;
}

.sidebar {
  background: var(--color-bg-card);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  transition: width 0.3s ease;
  overflow: hidden;
}

.logo {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
  border-bottom: 1px solid var(--color-border);
  .logo-icon { font-size: 22px; }
  .logo-text {
    font-size: 14px;
    font-weight: 700;
    color: var(--color-primary);
    white-space: nowrap;
  }
}

.sidebar-menu {
  flex: 1;
  border-right: none !important;
  :deep(.el-menu-item) {
    height: 44px;
    line-height: 44px;
    border-radius: 6px;
    margin: 2px 6px;
    &.is-active {
      background: rgba(0, 212, 255, 0.1) !important;
      border-left: 3px solid var(--color-primary);
    }
    &:hover {
      background: rgba(0, 212, 255, 0.05) !important;
    }
  }
}

.sidebar-footer {
  padding: 12px;
  border-top: 1px solid var(--color-border);
  .ws-status {
    display: flex;
    align-items: center;
    gap: 6px;
    .status-text {
      font-size: 11px;
      color: var(--color-text-muted);
    }
  }
}

.main-container {
  flex: 1;
  overflow: hidden;
}

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--color-bg-card);
  border-bottom: 1px solid var(--color-border);
  padding: 0 20px;
  .page-title {
    font-size: 15px;
    font-weight: 600;
    color: var(--color-text);
  }
  .top-right {
    display: flex;
    align-items: center;
    gap: 16px;
  }
  .status-item {
    display: flex;
    align-items: center;
    gap: 4px;
    .label {
      font-size: 11px;
      color: var(--color-text-muted);
    }
    .value {
      font-size: 12px;
      font-family: var(--font-mono);
      color: var(--color-text);
      &.warn { color: var(--color-warning); }
      &.critical { color: var(--color-danger); }
    }
  }
}

.page-content {
  padding: 16px;
  overflow-y: auto;
  background: var(--color-bg);
}

.fade-enter-active, .fade-leave-active {
  transition: opacity 0.15s ease;
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
}
</style>
