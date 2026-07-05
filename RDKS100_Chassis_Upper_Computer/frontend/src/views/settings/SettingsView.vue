<template>
  <div class="settings-view">
    <div class="page-header">
      <h2>设备管理与参数配置</h2>
      <span class="subtitle">Device Management & Configuration</span>
    </div>
    <el-tabs v-model="activeTab" class="settings-tabs">

      <!-- ===== 设备信息 ===== -->
      <el-tab-pane label="设备信息" name="device">
        <div class="tab-content">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-card class="info-card">
                <template #header><span>基本信息</span></template>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="设备名称">{{ deviceInfo.name }}</el-descriptions-item>
                  <el-descriptions-item label="平台">{{ deviceInfo.platform }}</el-descriptions-item>
                  <el-descriptions-item label="CPU">{{ deviceInfo.cpu }}</el-descriptions-item>
                  <el-descriptions-item label="操作系统">{{ deviceInfo.os }}</el-descriptions-item>
                  <el-descriptions-item label="系统版本">{{ deviceInfo.version }}</el-descriptions-item>
                  <el-descriptions-item label="模拟模式">
                    <el-tag :type="deviceInfo.mock_mode ? 'warning' : 'success'" size="small">
                      {{ deviceInfo.mock_mode ? '模拟模式' : '真实模式' }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="ROS2 接入">
                    <el-tag :type="deviceInfo.ros2_enabled ? 'success' : 'info'" size="small">
                      {{ deviceInfo.ros2_enabled ? '已启用' : '未启用' }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="运行时间">{{ uptimeStr }}</el-descriptions-item>
                </el-descriptions>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card class="info-card">
                <template #header>
                  <div class="card-header-row">
                    <span>网络信息</span>
                  </div>
                </template>
                <el-descriptions :column="1" border>
                  <el-descriptions-item label="IP 地址">{{ networkInfo.ip }}</el-descriptions-item>
                  <el-descriptions-item label="网络接口">{{ networkInfo.interface }}</el-descriptions-item>
                  <el-descriptions-item label="连接状态">
                    <el-tag :type="networkInfo.connected ? 'success' : 'danger'" size="small">
                      {{ networkInfo.connected ? '已连接' : '未连接' }}
                    </el-tag>
                  </el-descriptions-item>
                  <el-descriptions-item label="下行速率">{{ networkInfo.rx_rate.toFixed(0) }} KB/s</el-descriptions-item>
                  <el-descriptions-item label="上行速率">{{ networkInfo.tx_rate.toFixed(0) }} KB/s</el-descriptions-item>
                </el-descriptions>
              </el-card>

              <el-card class="info-card" style="margin-top:16px">
                <template #header>
                  <div class="card-header-row">
                    <span>传感器状态</span>
                    <el-button size="small" @click="loadSensorStatus" :loading="sensorLoading">刷新</el-button>
                  </div>
                </template>
                <div class="sensor-list" v-loading="sensorLoading">
                  <div v-for="sensor in sensors" :key="sensor.key" class="sensor-item">
                    <div class="sensor-info">
                      <span class="sensor-name">{{ sensor.name }}</span>
                      <span class="sensor-topic">{{ sensor.topic }}</span>
                    </div>
                    <el-tag
                      :type="sensor.status === 'online' ? 'success' : sensor.status === 'error' ? 'danger' : 'info'"
                      size="small"
                    >
                      {{ sensor.status === 'online' ? '在线' : sensor.status === 'error' ? '错误' : '离线' }}
                    </el-tag>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- ===== 运动参数 ===== -->
      <el-tab-pane label="运动参数" name="motion">
        <div class="tab-content">
          <el-card>
            <template #header>
              <div class="card-header-row">
                <span>速度限制配置</span>
                <el-button type="primary" size="small" @click="saveMotionConfig" :loading="motionSaving">保存</el-button>
              </div>
            </template>
            <el-form :model="motionConfig" label-width="180px">
              <el-form-item label="最大线速度 (m/s)">
                <el-slider v-model="motionConfig.max_linear" :min="0.1" :max="2.0" :step="0.05" show-input />
              </el-form-item>
              <el-form-item label="最大角速度 (rad/s)">
                <el-slider v-model="motionConfig.max_angular" :min="0.1" :max="3.14" :step="0.05" show-input />
              </el-form-item>
              <el-form-item label="加速度限制 (m/s²)">
                <el-slider v-model="motionConfig.max_accel" :min="0.1" :max="2.0" :step="0.1" show-input />
              </el-form-item>
              <el-form-item label="减速度限制 (m/s²)">
                <el-slider v-model="motionConfig.max_decel" :min="0.1" :max="3.0" :step="0.1" show-input />
              </el-form-item>
            </el-form>
          </el-card>
        </div>
      </el-tab-pane>

      <!-- ===== 传感器配置 ===== -->
      <el-tab-pane label="传感器配置" name="sensor">
        <div class="tab-content">
          <el-row :gutter="20">
            <el-col :span="12">
              <el-card>
                <template #header>
                  <div class="card-header-row">
                    <span>激光雷达配置</span>
                    <el-button type="primary" size="small" @click="saveLidarConfig">保存</el-button>
                  </div>
                </template>
                <el-form :model="lidarConfig" label-width="160px">
                  <el-form-item label="Topic 名称">
                    <el-input v-model="lidarConfig.topic" />
                  </el-form-item>
                  <el-form-item label="最大距离 (m)">
                    <el-input-number v-model="lidarConfig.max_range" :min="1" :max="40" />
                  </el-form-item>
                  <el-form-item label="最小距离 (m)">
                    <el-input-number v-model="lidarConfig.min_range" :min="0.01" :max="1" :step="0.01" />
                  </el-form-item>
                  <el-form-item label="启用滤波">
                    <el-switch v-model="lidarConfig.filter_enabled" />
                  </el-form-item>
                  <el-form-item label="安装俯仰角 (°)">
                    <el-input-number
                      v-model="lidarConfig.mount_pitch"
                      :min="-90" :max="90" :step="1"
                      :precision="1"
                    />
                    <span class="form-tip">水平安装为 0°，前倾为负值，后仰为正值。保存后点云立即补偿</span>
                  </el-form-item>
                </el-form>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card>
                <template #header>
                  <div class="card-header-row">
                    <span>串口 / STM32 配置</span>
                    <el-button type="primary" size="small" @click="saveSerialConfig">保存</el-button>
                  </div>
                </template>
                <el-form :model="serialConfig" label-width="140px">
                  <el-form-item label="串口设备">
                    <el-input v-model="serialConfig.port" placeholder="/dev/ttyUSB0" />
                  </el-form-item>
                  <el-form-item label="波特率">
                    <el-select v-model="serialConfig.baudrate">
                      <el-option :value="9600" label="9600" />
                      <el-option :value="57600" label="57600" />
                      <el-option :value="115200" label="115200" />
                      <el-option :value="230400" label="230400" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="发布 TF">
                    <el-switch v-model="serialConfig.publish_tf" />
                  </el-form-item>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

      <!-- ===== 系统配置 ===== -->
      <el-tab-pane label="系统配置" name="system">
        <div class="tab-content">
          <el-card>
            <template #header>
              <div class="card-header-row">
                <span>后端连接配置</span>
                <el-button type="primary" size="small" @click="saveSystemConfig">保存</el-button>
              </div>
            </template>
            <el-form :model="systemConfig" label-width="180px">
              <el-form-item label="后端地址">
                <el-input v-model="systemConfig.host" placeholder="例: 10.21.1.145" />
              </el-form-item>
              <el-form-item label="后端端口">
                <el-input-number v-model="systemConfig.port" :min="1024" :max="65535" />
              </el-form-item>
              <el-form-item label="模拟数据模式">
                <el-switch v-model="systemConfig.mock_mode" />
                <span class="form-tip">开启后使用模拟数据，无需真实硬件</span>
              </el-form-item>
              <el-form-item label="WebSocket 心跳间隔 (s)">
                <el-input-number v-model="systemConfig.heartbeat_interval" :min="5" :max="60" />
              </el-form-item>
              <el-form-item label="日志级别">
                <el-select v-model="systemConfig.log_level">
                  <el-option label="DEBUG" value="debug" />
                  <el-option label="INFO" value="info" />
                  <el-option label="WARNING" value="warning" />
                  <el-option label="ERROR" value="error" />
                </el-select>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card style="margin-top:16px">
            <template #header><span>危险操作</span></template>
            <div class="danger-zone">
              <div class="danger-item">
                <div>
                  <div class="danger-title">重启后端服务</div>
                  <div class="danger-desc">重启 FastAPI 后端，WebSocket 连接将断开并自动重连</div>
                </div>
                <el-button type="warning" @click="restartBackend">重启服务</el-button>
              </div>
              <div class="danger-item">
                <div>
                  <div class="danger-title">恢复默认配置</div>
                  <div class="danger-desc">将所有参数恢复为出厂默认值</div>
                </div>
                <el-button type="danger" @click="resetConfig">恢复默认</el-button>
              </div>
            </div>
          </el-card>
        </div>
      </el-tab-pane>

    </el-tabs>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { deviceApi } from '@/api/http'
import { useRobotStore } from '@/stores/robot'
import { ElMessage, ElMessageBox } from 'element-plus'

const robotStore = useRobotStore()
const activeTab = ref('device')
const sensorLoading = ref(false)
const motionSaving = ref(false)

// ---- 设备信息（从 API 加载） ----
const deviceInfo = ref({
  name: 'RDK S100 智能机器人',
  platform: 'RDK S100',
  cpu: 'Cortex-A78AE + R52 + BPU',
  os: 'Ubuntu 22.04 (RDK Linux)',
  version: '1.0.0',
  mock_mode: true,
  ros2_enabled: false,
})

// 网络信息从 store 实时读取
const networkInfo = computed(() => ({
  ip: robotStore.systemInfo?.network.ip ?? '--',
  interface: 'eth0',
  connected: robotStore.systemInfo?.network.connected ?? false,
  rx_rate: robotStore.systemInfo?.network.rx_rate ?? 0,
  tx_rate: robotStore.systemInfo?.network.tx_rate ?? 0,
}))

// 运行时间从 store 实时读取
const uptimeStr = computed(() => {
  const s = robotStore.systemInfo?.uptime ?? 0
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return d > 0 ? `${d}d ${h}h ${m}m` : `${h}h ${m}m`
})

// ---- 传感器状态 ----
const sensors = ref([
  { key: 'lidar', name: '激光雷达 (LiDAR)', status: 'offline', topic: '/livox/lidar' },
  { key: 'imu', name: 'IMU 惯性测量单元', status: 'offline', topic: '/livox/imu' },
  { key: 'camera', name: 'RGB 摄像头', status: 'offline', topic: '/camera/color/image_raw' },
  { key: 'motor', name: '驱动电机 / 里程计', status: 'offline', topic: '/odom' },
  { key: 'battery', name: '电池管理系统', status: 'offline', topic: '/battery_state' },
])

// ---- 运动参数 ----
const motionConfig = ref({
  max_linear: 1.0,
  max_angular: 1.57,
  max_accel: 0.5,
  max_decel: 1.0,
})

// ---- 激光雷达配置 ----
const lidarConfig = ref({
  topic: '/livox/lidar',
  max_range: 40.0,
  min_range: 0.02,
  filter_enabled: true,
  mount_pitch: 0.0,  // 安装俯仰角（度）：水平安装为 0
})

// ---- 串口配置 ----
const serialConfig = ref({
  port: '/dev/ttyUSB0',
  baudrate: 115200,
  publish_tf: true,
})

// ---- 系统配置 ----
const systemConfig = ref({
  host: window.location.hostname,
  port: 8000,
  mock_mode: true,
  heartbeat_interval: 30,
  log_level: 'info',
})

// ---- 加载函数 ----
async function loadDeviceInfo() {
  try {
    const res: any = await deviceApi.getInfo()
    // 后端直接返回对象（axios 拦截器已解包 .data）
    const data = res?.data ?? res
    if (data) {
      Object.assign(deviceInfo.value, {
        name: data.name ?? deviceInfo.value.name,
        platform: data.platform ?? deviceInfo.value.platform,
        cpu: data.cpu ?? deviceInfo.value.cpu,
        os: data.os ?? deviceInfo.value.os,
        version: data.version ?? deviceInfo.value.version,
        mock_mode: data.mock_mode ?? deviceInfo.value.mock_mode,
        ros2_enabled: data.ros2_enabled ?? deviceInfo.value.ros2_enabled,
      })
    }
  } catch {
    // 使用默认值
  }
}

async function loadSensorStatus() {
  sensorLoading.value = true
  try {
    const res: any = await deviceApi.getSensors()
    const data = res?.data ?? res
    // 后端返回 { sensors: [...], devices: {...} }
    const list = data?.sensors ?? []
    if (list.length > 0) {
      sensors.value = list.map((s: any) => ({
        key: s.key ?? s.name,
        name: s.name,
        status: s.status,
        topic: s.topic ?? '',
      }))
    }
  } catch {
    // 保持默认离线状态
  } finally {
    sensorLoading.value = false
  }
}

async function loadConfig() {
  try {
    const res: any = await deviceApi.getConfig()
    const cfg = res?.data ?? res
    if (cfg?.lidar) Object.assign(lidarConfig.value, cfg.lidar)
    if (cfg?.motion) Object.assign(motionConfig.value, cfg.motion)
    if (cfg?.serial) Object.assign(serialConfig.value, cfg.serial)
  } catch { /* 使用默认值 */ }
}

// ---- 保存函数 ----
async function saveMotionConfig() {
  motionSaving.value = true
  try {
    await deviceApi.updateConfig({ motion: motionConfig.value })
    ElMessage.success('运动参数已保存')
  } catch {
    ElMessage.error('保存失败')
  } finally {
    motionSaving.value = false
  }
}

async function saveLidarConfig() {
  try {
    await deviceApi.updateConfig({ lidar: lidarConfig.value })
    ElMessage.success('激光雷达配置已保存')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function saveSerialConfig() {
  try {
    await deviceApi.updateConfig({ serial: serialConfig.value })
    ElMessage.success('串口配置已保存')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function saveSystemConfig() {
  try {
    await deviceApi.updateConfig({ system: systemConfig.value })
    ElMessage.success('系统配置已保存')
  } catch {
    ElMessage.error('保存失败')
  }
}

async function restartBackend() {
  try {
    await ElMessageBox.confirm(
      '确定要重启后端服务吗？WebSocket 连接将短暂断开。',
      '确认重启',
      { confirmButtonText: '确定重启', cancelButtonText: '取消', type: 'warning' }
    )
    await deviceApi.reboot()
    ElMessage.info('重启指令已发送，请稍候...')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('操作失败')
  }
}

async function resetConfig() {
  try {
    await ElMessageBox.confirm(
      '确定要恢复所有配置为默认值吗？此操作不可撤销。',
      '确认恢复',
      { confirmButtonText: '确定恢复', cancelButtonText: '取消', type: 'error' }
    )
    await deviceApi.resetConfig()
    motionConfig.value = { max_linear: 1.0, max_angular: 1.57, max_accel: 0.5, max_decel: 1.0 }
    lidarConfig.value = { topic: '/livox/lidar', max_range: 40.0, min_range: 0.02, filter_enabled: true, mount_pitch: 0.0 }
    serialConfig.value = { port: '/dev/ttyUSB0', baudrate: 115200, publish_tf: true }
    ElMessage.success('已恢复默认配置')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.error('操作失败')
  }
}

onMounted(() => {
  loadDeviceInfo()
  loadSensorStatus()
  loadConfig()
})
</script>

<style scoped lang="scss">
.settings-view {
  padding: 20px;
  height: 100%;
  overflow-y: auto;
}

.page-header {
  margin-bottom: 20px;
  h2 { margin: 0 0 4px; font-size: 20px; color: var(--el-text-color-primary); }
  .subtitle { font-size: 13px; color: var(--el-text-color-secondary); }
}

.settings-tabs {
  :deep(.el-tabs__header) { margin-bottom: 16px; }
}

.tab-content { padding: 4px 0; }

.info-card {
  :deep(.el-card__header) { padding: 12px 16px; font-weight: 600; }
}

.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}

.sensor-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-height: 40px;
}

.sensor-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  &:last-child { border-bottom: none; }

  .sensor-info {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .sensor-name { font-size: 14px; color: var(--el-text-color-regular); }
  .sensor-topic { font-size: 11px; color: var(--el-text-color-secondary); font-family: monospace; }
}

.form-tip {
  margin-left: 10px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.danger-zone {
  display: flex;
  flex-direction: column;
  gap: 16px;

  .danger-item {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 12px;
    border: 1px solid var(--el-color-danger-light-5);
    border-radius: 6px;
    background: var(--el-color-danger-light-9);

    .danger-title { font-weight: 600; color: var(--el-color-danger); margin-bottom: 4px; }
    .danger-desc { font-size: 12px; color: var(--el-text-color-secondary); }
  }
}
</style>
