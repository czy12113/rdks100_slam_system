// =============================================================================
// Vue Router 路由配置
// =============================================================================

import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/layouts/MainLayout.vue'),
    children: [
      {
        path: '',
        redirect: '/dashboard',
      },
      {
        path: 'dashboard',
        name: 'Dashboard',
        component: () => import('@/views/dashboard/DashboardView.vue'),
        meta: { title: '综合监控', icon: 'Monitor' },
      },
      {
        path: 'video',
        name: 'Video',
        component: () => import('@/views/video/VideoView.vue'),
        meta: { title: '视频监控', icon: 'VideoCamera' },
      },
      {
        path: 'lidar',
        name: 'Lidar',
        component: () => import('@/views/lidar/LidarView.vue'),
        meta: { title: '激光雷达', icon: 'Aim' },
      },
      {
        path: 'imu',
        name: 'IMU',
        component: () => import('@/views/imu/ImuView.vue'),
        meta: { title: 'IMU 姿态', icon: 'Compass' },
      },
      {
        path: 'control',
        name: 'Control',
        component: () => import('@/views/control/ControlView.vue'),
        meta: { title: '机器人控制', icon: 'GamePad' },
      },
      {
        path: 'slam',
        name: 'SLAM',
        component: () => import('@/views/slam/SlamView.vue'),
        meta: { title: 'SLAM 建图', icon: 'MapLocation' },
      },
      {
        path: 'navigation',
        name: 'Navigation',
        component: () => import('@/views/navigation/NavigationView.vue'),
        meta: { title: '导航规划', icon: 'Position' },
      },
      {
        path: 'settings',
        name: 'Settings',
        component: () => import('@/views/settings/SettingsView.vue'),
        meta: { title: '设备管理', icon: 'Setting' },
      },
    ],
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'RDK S100'} - 智能机器人上位机`
})

export default router
