<template>
  <div class="slam-view">
    <el-row :gutter="12">
      <!-- 栅格地图可视化 -->
      <el-col :xs="24" :sm="17">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title">
              <el-icon><MapLocation /></el-icon> 栅格地图
              <el-tag size="small" class="ml8" v-if="currentGrid">
                {{ currentGrid.width }} × {{ currentGrid.height }} · {{ currentGrid.resolution.toFixed(3) }} m/px
              </el-tag>
            </span>
            <div class="actions">
              <el-tag size="small" :type="loading ? 'warning' : 'success'">
                {{ loading ? '加载中' : (currentGrid ? '已加载' : '未选择') }}
              </el-tag>

              <!-- 三模式切换 -->
              <el-radio-group v-model="mode" size="small">
                <el-radio-button label="browse">
                  <el-icon><View /></el-icon> 浏览
                </el-radio-button>
                <el-radio-button label="single">
                  <el-icon><EditPen /></el-icon> 单点
                </el-radio-button>
                <el-radio-button label="batch">
                  <el-icon><Grid /></el-icon> 批量
                </el-radio-button>
              </el-radio-group>

              <el-button size="small" text @click="resetMapView">
                <el-icon><Refresh /></el-icon> 复位
              </el-button>
            </div>
          </div>

          <!-- 批量模式工具条 -->
          <div class="batch-toolbar" v-if="mode === 'batch'">
            <div class="batch-info">
              <el-icon><Select /></el-icon>
              已选 <span class="num">{{ selectedCells.size }}</span> 个障碍格
              <span class="hint">· 点击障碍格切换选中，Shift+拖动框选</span>
            </div>
            <div class="batch-actions">
              <el-button size="small" @click="clearSelection" :disabled="!selectedCells.size">
                清空选择
              </el-button>
              <el-button
                size="small"
                type="primary"
                :disabled="!selectedCells.size"
                @click="openBatchDialog"
              >
                <el-icon><Check /></el-icon> 一键标注 ({{ selectedCells.size }})
              </el-button>
            </div>
          </div>

          <div class="map-wrap" ref="mapWrapRef">
            <canvas
              ref="mapCanvasRef"
              class="map-canvas"
              :class="[
                mode === 'single' ? 'cursor-cross' : '',
                mode === 'batch' ? 'cursor-pointer' : '',
              ]"
              @wheel="onWheel"
              @mousedown="onMouseDown"
              @mousemove="onMouseMove"
              @mouseup="onMouseUp"
              @mouseleave="onMouseUp"
              @click="onCanvasClick"
              @contextmenu.prevent="onCanvasRightClick"
            />
            <div class="map-legend">
              <span class="legend-item free">空闲</span>
              <span class="legend-item occupied">障碍</span>
              <span class="legend-item unknown">未知</span>
              <span class="legend-item annotated">已标注</span>
              <span class="legend-item selected" v-if="mode === 'batch'">已选</span>
            </div>
            <div class="map-hover" v-if="hoverInfo">
              row: {{ hoverInfo.row }} · col: {{ hoverInfo.col }} · 值: {{ hoverInfo.val }}
              <span v-if="hoverInfo.annotation">· 标注: {{ hoverInfo.annotation.text }}</span>
            </div>
            <div class="map-empty" v-if="!currentGrid && !loading">
              请从右侧下拉框选择一张已保存的栅格地图
            </div>
          </div>
        </div>
      </el-col>

      <!-- 右侧控制面板 -->
      <el-col :xs="24" :sm="7">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title">已保存地图</span>
            <el-button size="small" text @click="refreshMapList">
              <el-icon><Refresh /></el-icon>
            </el-button>
          </div>

          <div class="ctrl-section">
            <div class="ctrl-label">地图目录</div>
            <div class="dir-hint mono">{{ mapDir || '—' }}</div>
          </div>

          <div class="ctrl-section">
            <div class="ctrl-label">切换地图</div>
            <el-select
              v-model="selectedMap"
              size="small"
              class="full-width"
              placeholder="选择一张地图"
              :loading="loading"
              @change="onMapChange"
            >
              <el-option
                v-for="m in mapList"
                :key="m.name"
                :label="m.name + (m.has_annotations ? '  ✎' : '')"
                :value="m.name"
              />
            </el-select>
            <div class="map-meta" v-if="currentMapInfo">
              <span>大小 {{ (currentMapInfo.size / 1024).toFixed(1) }} KB</span>
              <span>修改 {{ formatTime(currentMapInfo.modified) }}</span>
            </div>
          </div>

          <div class="ctrl-section" v-if="currentGrid">
            <div class="ctrl-label">地图信息</div>
            <div class="status-item">
              <span class="label">分辨率</span>
              <span class="val mono">{{ currentGrid.resolution.toFixed(3) }} m/px</span>
            </div>
            <div class="status-item">
              <span class="label">尺寸</span>
              <span class="val mono">{{ currentGrid.width }} × {{ currentGrid.height }}</span>
            </div>
            <div class="status-item">
              <span class="label">原点</span>
              <span class="val mono">
                ({{ currentGrid.origin.x.toFixed(2) }}, {{ currentGrid.origin.y.toFixed(2) }})
              </span>
            </div>
            <div class="status-item">
              <span class="label">障碍栅格</span>
              <span class="val mono">{{ occupiedCount }}</span>
            </div>
            <div class="status-item">
              <span class="label">已标注</span>
              <span class="val mono">{{ annotations.length }} 格 / {{ groupList.length }} 组</span>
            </div>
          </div>
        </div>

        <!-- 标注列表：按组聚合 -->
        <div class="tech-card mt8" v-if="currentGrid">
          <div class="card-header">
            <span class="card-title">障碍物标注</span>
            <el-button size="small" text type="danger" v-if="annotations.length" @click="clearAllAnnotations">
              清空
            </el-button>
          </div>
          <div class="anno-list">
            <div
              v-for="g in groupList"
              :key="g.key"
              class="anno-item"
              @click="focusGroup(g)"
            >
              <span class="dot" :style="{ background: g.color || '#ff8c00' }" />
              <div class="anno-text">
                <div class="text">
                  {{ g.text }}
                  <span class="badge" v-if="g.cells.length > 1">×{{ g.cells.length }}</span>
                </div>
                <div class="pos mono">
                  <template v-if="g.cells.length === 1">
                    ({{ g.cells[0].row }}, {{ g.cells[0].col }})
                  </template>
                  <template v-else>
                    共 {{ g.cells.length }} 格 · 覆盖 ({{ g.minRow }}-{{ g.maxRow }}, {{ g.minCol }}-{{ g.maxCol }})
                  </template>
                </div>
              </div>
              <el-button size="small" text @click.stop="removeGroup(g)">
                <el-icon><Delete /></el-icon>
              </el-button>
            </div>
            <div class="empty-tip" v-if="!annotations.length">
              切换到「单点」或「批量」模式后开始标注
            </div>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 单格标注对话框 -->
    <el-dialog v-model="annoDialog.visible" :title="annoDialog.editing ? '编辑障碍标注' : '新增障碍标注'" width="420px">
      <div class="anno-dialog-body">
        <div class="row">
          <span class="k">栅格坐标</span>
          <span class="v mono">row {{ annoDialog.row }} · col {{ annoDialog.col }}</span>
        </div>
        <div class="row">
          <span class="k">世界坐标</span>
          <span class="v mono">
            ({{ annoDialog.worldX.toFixed(2) }}, {{ annoDialog.worldY.toFixed(2) }}) m
          </span>
        </div>
        <div class="row">
          <span class="k">标注文本</span>
          <el-input
            v-model="annoDialog.text"
            placeholder="例如：柱子 / 桌腿 / 墙角"
            maxlength="30"
            show-word-limit
            @keyup.enter="submitAnnotation"
          />
        </div>
        <div class="row">
          <span class="k">颜色</span>
          <div class="color-picker">
            <span
              v-for="c in COLOR_PALETTE"
              :key="c"
              class="color-swatch"
              :class="{ active: annoDialog.color === c }"
              :style="{ background: c }"
              @click="annoDialog.color = c"
            />
          </div>
        </div>
      </div>
      <template #footer>
        <el-button size="small" @click="annoDialog.visible = false">取消</el-button>
        <el-button
          size="small"
          type="danger"
          v-if="annoDialog.editing"
          @click="deleteCurrentAnnotation"
        >
          删除
        </el-button>
        <el-button size="small" type="primary" @click="submitAnnotation">保存</el-button>
      </template>
    </el-dialog>

    <!-- 批量标注对话框 -->
    <el-dialog v-model="batchDialog.visible" title="一键标注（多格 → 同一障碍物）" width="460px">
      <div class="anno-dialog-body">
        <div class="row">
          <span class="k">已选栅格</span>
          <span class="v mono">
            {{ batchDialog.count }} 格 · row [{{ batchDialog.minRow }}-{{ batchDialog.maxRow }}]
            · col [{{ batchDialog.minCol }}-{{ batchDialog.maxCol }}]
          </span>
        </div>
        <div class="row">
          <span class="k">世界范围</span>
          <span class="v mono">
            ({{ batchDialog.worldX0.toFixed(2) }}, {{ batchDialog.worldY0.toFixed(2) }})
            ~ ({{ batchDialog.worldX1.toFixed(2) }}, {{ batchDialog.worldY1.toFixed(2) }}) m
          </span>
        </div>
        <div class="row">
          <span class="k">标注文本</span>
          <el-input
            v-model="batchDialog.text"
            placeholder="例如：柱子 / 桌子 / 墙体（整块障碍物名称）"
            maxlength="30"
            show-word-limit
            @keyup.enter="submitBatchAnnotate"
          />
        </div>
        <div class="row">
          <span class="k">颜色</span>
          <div class="color-picker">
            <span
              v-for="c in COLOR_PALETTE"
              :key="c"
              class="color-swatch"
              :class="{ active: batchDialog.color === c }"
              :style="{ background: c }"
              @click="batchDialog.color = c"
            />
          </div>
        </div>
      </div>
      <template #footer>
        <el-button size="small" @click="batchDialog.visible = false">取消</el-button>
        <el-button size="small" type="primary" @click="submitBatchAnnotate">
          确认标注 ({{ batchDialog.count }} 格)
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, reactive, nextTick } from 'vue'
import { slamApi, type SavedMap, type MapGrid, type MapAnnotation } from '@/api/http'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  MapLocation, Refresh, Delete, View, EditPen, Grid, Select, Check,
} from '@element-plus/icons-vue'

// -----------------------------------------------------------------------------
// 常量
// -----------------------------------------------------------------------------
const CELL_FREE = 0
const CELL_OCCUPIED = 100
const CELL_UNKNOWN = 255
const COLOR_PALETTE = ['#ff8c00', '#ff4d4f', '#faad14', '#52c41a', '#1890ff', '#722ed1']

type Mode = 'browse' | 'single' | 'batch'

// -----------------------------------------------------------------------------
// 响应式状态
// -----------------------------------------------------------------------------
const mapCanvasRef = ref<HTMLCanvasElement>()
const mapWrapRef = ref<HTMLDivElement>()

const mapList = ref<SavedMap[]>([])
const mapDir = ref<string>('')
const selectedMap = ref<string>('')
const loading = ref(false)

const currentGrid = ref<MapGrid | null>(null)
/** 解码后的三态栅格 bytes（0/100/255），长度 = width*height */
let cells: Uint8Array | null = null

const annotations = ref<MapAnnotation[]>([])

/** 三态模式：浏览 / 单点标注 / 批量标注 */
const mode = ref<Mode>('browse')

/** 批量模式下已选栅格集合，key = row * width + col */
const selectedCells = ref<Set<number>>(new Set())

const hoverInfo = ref<{ row: number; col: number; val: number; annotation?: MapAnnotation } | null>(null)

// 视图变换
let zoom = 2.0
let offsetX = 0
let offsetY = 0
let isPanning = false
let panMoved = false
let panSX = 0
let panSY = 0

// 框选（Shift+拖动）
let isBoxSelect = false
let boxStart: { x: number; y: number } | null = null
let boxCurrent: { x: number; y: number } | null = null

const currentMapInfo = computed<SavedMap | undefined>(() =>
  mapList.value.find((m) => m.name === selectedMap.value),
)

const occupiedCount = computed(() => {
  if (!cells) return 0
  let n = 0
  for (let i = 0; i < cells.length; i++) if (cells[i] === CELL_OCCUPIED) n++
  return n
})

// 按 group_id 聚合标注（单格标注 group_id 为 null，各自独立成组）
interface AnnoGroup {
  key: string
  group_id: string | null
  text: string
  color: string | null
  cells: MapAnnotation[]
  minRow: number
  maxRow: number
  minCol: number
  maxCol: number
}
const groupList = computed<AnnoGroup[]>(() => {
  const map = new Map<string, AnnoGroup>()
  for (const a of annotations.value) {
    const gid = a.group_id || `single_${a.row}_${a.col}`
    let g = map.get(gid)
    if (!g) {
      g = {
        key: gid,
        group_id: a.group_id || null,
        text: a.text,
        color: a.color || null,
        cells: [],
        minRow: a.row,
        maxRow: a.row,
        minCol: a.col,
        maxCol: a.col,
      }
      map.set(gid, g)
    }
    g.cells.push(a)
    if (a.row < g.minRow) g.minRow = a.row
    if (a.row > g.maxRow) g.maxRow = a.row
    if (a.col < g.minCol) g.minCol = a.col
    if (a.col > g.maxCol) g.maxCol = a.col
  }
  return Array.from(map.values())
})

// -----------------------------------------------------------------------------
// 对话框
// -----------------------------------------------------------------------------
const annoDialog = reactive({
  visible: false,
  editing: false,
  row: 0,
  col: 0,
  text: '',
  color: COLOR_PALETTE[0],
  worldX: 0,
  worldY: 0,
})

const batchDialog = reactive({
  visible: false,
  count: 0,
  minRow: 0,
  maxRow: 0,
  minCol: 0,
  maxCol: 0,
  worldX0: 0,
  worldY0: 0,
  worldX1: 0,
  worldY1: 0,
  text: '',
  color: COLOR_PALETTE[0],
})

function openAnnoDialog(row: number, col: number) {
  const exist = annotations.value.find((a) => a.row === row && a.col === col)
  const grid = currentGrid.value
  const worldX = grid ? grid.origin.x + col * grid.resolution : 0
  const worldY = grid ? grid.origin.y + (grid.height - 1 - row) * grid.resolution : 0
  annoDialog.editing = !!exist
  annoDialog.row = row
  annoDialog.col = col
  annoDialog.text = exist?.text ?? ''
  annoDialog.color = exist?.color || COLOR_PALETTE[0]
  annoDialog.worldX = worldX
  annoDialog.worldY = worldY
  annoDialog.visible = true
}

async function submitAnnotation() {
  const text = annoDialog.text.trim()
  if (!text) {
    ElMessage.warning('标注文本不能为空')
    return
  }
  try {
    const res: any = await slamApi.upsertAnnotation(
      selectedMap.value,
      annoDialog.row,
      annoDialog.col,
      text,
      annoDialog.color,
    )
    annotations.value = res.annotations ?? annotations.value
    annoDialog.visible = false
    ElMessage.success(annoDialog.editing ? '标注已更新' : '标注已添加')
    drawMap()
  } catch (e) {
    ElMessage.error('保存标注失败')
  }
}

async function deleteCurrentAnnotation() {
  try {
    await slamApi.deleteAnnotation(selectedMap.value, annoDialog.row, annoDialog.col)
    annotations.value = annotations.value.filter(
      (a) => !(a.row === annoDialog.row && a.col === annoDialog.col),
    )
    annoDialog.visible = false
    ElMessage.success('标注已删除')
    drawMap()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function removeGroup(g: AnnoGroup) {
  try {
    if (g.group_id) {
      const res: any = await slamApi.deleteAnnotationGroup(selectedMap.value, g.group_id)
      annotations.value = res.annotations ?? annotations.value.filter((a) => a.group_id !== g.group_id)
    } else {
      // 单格：group_id 为 null，直接按坐标删
      const a = g.cells[0]
      await slamApi.deleteAnnotation(selectedMap.value, a.row, a.col)
      annotations.value = annotations.value.filter((x) => !(x.row === a.row && x.col === a.col))
    }
    ElMessage.success(`已删除 ${g.cells.length} 格标注`)
    drawMap()
  } catch {
    ElMessage.error('删除失败')
  }
}

async function clearAllAnnotations() {
  try {
    await ElMessageBox.confirm('确定清空该地图的全部障碍物标注？', '提示', {
      type: 'warning',
      confirmButtonText: '清空',
      cancelButtonText: '取消',
    })
  } catch {
    return
  }
  try {
    await slamApi.putAnnotations(selectedMap.value, [])
    annotations.value = []
    drawMap()
    ElMessage.success('已清空标注')
  } catch {
    ElMessage.error('清空失败')
  }
}

function focusGroup(g: AnnoGroup) {
  const canvas = mapCanvasRef.value
  if (!canvas) return
  const centerRow = (g.minRow + g.maxRow) / 2
  const centerCol = (g.minCol + g.maxCol) / 2
  const cellSize = zoom
  offsetX = canvas.width / 2 - (centerCol + 0.5) * cellSize
  offsetY = canvas.height / 2 - (centerRow + 0.5) * cellSize
  drawMap()
}

// -----------------------------------------------------------------------------
// 批量选择
// -----------------------------------------------------------------------------
function cellKey(row: number, col: number) {
  const w = currentGrid.value?.width ?? 0
  return row * w + col
}

function keyToRowCol(key: number): [number, number] {
  const w = currentGrid.value?.width ?? 1
  return [Math.floor(key / w), key % w]
}

function toggleCellSelection(row: number, col: number) {
  if (!currentGrid.value || !cells) return
  const idx = row * currentGrid.value.width + col
  // 只能选障碍格；如果已经被标注过也允许选（可与新组合并覆盖）
  if (cells[idx] !== CELL_OCCUPIED) {
    ElMessage.info('只能选择障碍栅格')
    return
  }
  const key = cellKey(row, col)
  const next = new Set(selectedCells.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  selectedCells.value = next
  drawMap()
}

function clearSelection() {
  selectedCells.value = new Set()
  drawMap()
}

function selectCellsInBox(r0: number, c0: number, r1: number, c1: number) {
  if (!currentGrid.value || !cells) return
  const { width, height } = currentGrid.value
  const rMin = Math.max(0, Math.min(r0, r1))
  const rMax = Math.min(height - 1, Math.max(r0, r1))
  const cMin = Math.max(0, Math.min(c0, c1))
  const cMax = Math.min(width - 1, Math.max(c0, c1))
  const next = new Set(selectedCells.value)
  for (let r = rMin; r <= rMax; r++) {
    for (let c = cMin; c <= cMax; c++) {
      if (cells[r * width + c] === CELL_OCCUPIED) {
        next.add(r * width + c)
      }
    }
  }
  selectedCells.value = next
  drawMap()
}

function openBatchDialog() {
  const grid = currentGrid.value
  if (!grid || !selectedCells.value.size) return

  let minRow = Infinity, maxRow = -Infinity, minCol = Infinity, maxCol = -Infinity
  for (const k of selectedCells.value) {
    const [r, c] = keyToRowCol(k)
    if (r < minRow) minRow = r
    if (r > maxRow) maxRow = r
    if (c < minCol) minCol = c
    if (c > maxCol) maxCol = c
  }
  batchDialog.count = selectedCells.value.size
  batchDialog.minRow = minRow
  batchDialog.maxRow = maxRow
  batchDialog.minCol = minCol
  batchDialog.maxCol = maxCol
  batchDialog.worldX0 = grid.origin.x + minCol * grid.resolution
  batchDialog.worldY0 = grid.origin.y + (grid.height - 1 - maxRow) * grid.resolution
  batchDialog.worldX1 = grid.origin.x + maxCol * grid.resolution
  batchDialog.worldY1 = grid.origin.y + (grid.height - 1 - minRow) * grid.resolution
  batchDialog.text = ''
  batchDialog.color = COLOR_PALETTE[0]
  batchDialog.visible = true
}

async function submitBatchAnnotate() {
  const text = batchDialog.text.trim()
  if (!text) {
    ElMessage.warning('请输入障碍物名称')
    return
  }
  const list = Array.from(selectedCells.value).map((k) => {
    const [row, col] = keyToRowCol(k)
    return { row, col }
  })
  try {
    const res: any = await slamApi.batchAnnotate(
      selectedMap.value, list, text, batchDialog.color,
    )
    annotations.value = res.annotations ?? annotations.value
    ElMessage.success(`已把 ${list.length} 个栅格标注为「${text}」`)
    batchDialog.visible = false
    clearSelection()
    drawMap()
  } catch {
    ElMessage.error('批量标注失败')
  }
}

// -----------------------------------------------------------------------------
// 视图交互
// -----------------------------------------------------------------------------
function resetMapView() {
  const canvas = mapCanvasRef.value
  const grid = currentGrid.value
  if (!canvas || !grid) {
    zoom = 2.0
    offsetX = 0
    offsetY = 0
    drawMap()
    return
  }
  const fitZoom = Math.min(canvas.width / grid.width, canvas.height / grid.height) * 0.95
  zoom = Math.max(0.5, fitZoom)
  offsetX = (canvas.width - grid.width * zoom) / 2
  offsetY = (canvas.height - grid.height * zoom) / 2
  drawMap()
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  const canvas = mapCanvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  const oldZoom = zoom
  const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
  zoom = Math.max(0.3, Math.min(30, zoom * factor))
  offsetX = mx - ((mx - offsetX) * zoom) / oldZoom
  offsetY = my - ((my - offsetY) * zoom) / oldZoom
  drawMap()
}

function canvasPointToCell(mx: number, my: number): { row: number; col: number } | null {
  const grid = currentGrid.value
  if (!grid) return null
  const col = Math.floor((mx - offsetX) / zoom)
  const row = Math.floor((my - offsetY) / zoom)
  if (row < 0 || col < 0 || row >= grid.height || col >= grid.width) return null
  return { row, col }
}

function onMouseDown(e: MouseEvent) {
  const canvas = mapCanvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  // 批量模式 + Shift 键：框选障碍格
  if (mode.value === 'batch' && e.shiftKey) {
    isBoxSelect = true
    boxStart = { x: mx, y: my }
    boxCurrent = { x: mx, y: my }
    return
  }

  // 其它情况：平移
  isPanning = true
  panMoved = false
  panSX = e.clientX - offsetX
  panSY = e.clientY - offsetY
}

function onMouseMove(e: MouseEvent) {
  const canvas = mapCanvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const mx = e.clientX - rect.left
  const my = e.clientY - rect.top

  if (isBoxSelect && boxStart) {
    boxCurrent = { x: mx, y: my }
    drawMap()
    return
  }

  if (isPanning) {
    const nx = e.clientX - panSX
    const ny = e.clientY - panSY
    if (Math.abs(nx - offsetX) > 2 || Math.abs(ny - offsetY) > 2) panMoved = true
    offsetX = nx
    offsetY = ny
    drawMap()
    return
  }

  // 悬停信息
  if (!currentGrid.value || !cells) {
    hoverInfo.value = null
    return
  }
  const rc = canvasPointToCell(mx, my)
  if (!rc) {
    hoverInfo.value = null
    return
  }
  const val = cells[rc.row * currentGrid.value.width + rc.col]
  const ann = annotations.value.find((a) => a.row === rc.row && a.col === rc.col)
  hoverInfo.value = { row: rc.row, col: rc.col, val, annotation: ann }
}

function onMouseUp(e?: MouseEvent) {
  const canvas = mapCanvasRef.value

  // 结束框选：把矩形内的障碍格加入选中
  if (isBoxSelect && boxStart && boxCurrent && canvas) {
    const a = canvasPointToCell(boxStart.x, boxStart.y)
    const b = canvasPointToCell(boxCurrent.x, boxCurrent.y)
    // 允许起/止有一端在边界外；用像素反算最近栅格
    const clampCell = (p: { x: number; y: number }) => {
      const grid = currentGrid.value!
      const col = Math.max(0, Math.min(grid.width - 1, Math.floor((p.x - offsetX) / zoom)))
      const row = Math.max(0, Math.min(grid.height - 1, Math.floor((p.y - offsetY) / zoom)))
      return { row, col }
    }
    if (currentGrid.value) {
      const aa = a ?? clampCell(boxStart)
      const bb = b ?? clampCell(boxCurrent)
      selectCellsInBox(aa.row, aa.col, bb.row, bb.col)
    }
    isBoxSelect = false
    boxStart = null
    boxCurrent = null
    drawMap()
    return
  }

  isPanning = false
}

function onCanvasClick(e: MouseEvent) {
  if (panMoved || isBoxSelect) return
  if (!currentGrid.value || !cells) return
  const canvas = mapCanvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const rc = canvasPointToCell(e.clientX - rect.left, e.clientY - rect.top)
  if (!rc) return
  const { row, col } = rc
  const val = cells[row * currentGrid.value.width + col]

  if (mode.value === 'single') {
    const hasAnn = annotations.value.some((a) => a.row === row && a.col === col)
    if (val !== CELL_OCCUPIED && !hasAnn) {
      ElMessage.info('只能对障碍栅格进行标注')
      return
    }
    openAnnoDialog(row, col)
    return
  }

  if (mode.value === 'batch') {
    toggleCellSelection(row, col)
    return
  }
}

function onCanvasRightClick(e: MouseEvent) {
  // 批量模式：右键快速取消选择当前栅格
  if (mode.value !== 'batch' || !currentGrid.value) return
  const canvas = mapCanvasRef.value
  if (!canvas) return
  const rect = canvas.getBoundingClientRect()
  const rc = canvasPointToCell(e.clientX - rect.left, e.clientY - rect.top)
  if (!rc) return
  const key = cellKey(rc.row, rc.col)
  if (selectedCells.value.has(key)) {
    const next = new Set(selectedCells.value)
    next.delete(key)
    selectedCells.value = next
    drawMap()
  }
}

// -----------------------------------------------------------------------------
// 数据加载
// -----------------------------------------------------------------------------
async function refreshMapList() {
  loading.value = true
  try {
    const res: any = await slamApi.listMaps()
    mapList.value = res.maps ?? []
    mapDir.value = res.dir ?? ''
    if (mapList.value.length && !mapList.value.find((m) => m.name === selectedMap.value)) {
      selectedMap.value = mapList.value[0].name
      await loadMap(selectedMap.value)
    }
  } catch (e) {
    ElMessage.error('获取地图列表失败')
  } finally {
    loading.value = false
  }
}

async function onMapChange(name: string) {
  if (!name) return
  await loadMap(name)
}

function base64ToBytes(b64: string): Uint8Array {
  const bin = atob(b64)
  const buf = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) buf[i] = bin.charCodeAt(i)
  return buf
}

async function loadMap(name: string) {
  loading.value = true
  try {
    const [grid, ann]: any = await Promise.all([
      slamApi.getMapGrid(name),
      slamApi.getAnnotations(name),
    ])
    currentGrid.value = grid as MapGrid
    cells = base64ToBytes((grid as MapGrid).cells_base64)
    annotations.value = (ann?.annotations ?? []) as MapAnnotation[]
    // 切换地图时清空批量选择
    selectedCells.value = new Set()
    await nextTick()
    resetMapView()
  } catch (e) {
    ElMessage.error(`加载地图 ${name} 失败`)
    currentGrid.value = null
    cells = null
    annotations.value = []
    drawMap()
  } finally {
    loading.value = false
  }
}

// -----------------------------------------------------------------------------
// 绘制
// -----------------------------------------------------------------------------
function drawMap() {
  const canvas = mapCanvasRef.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  const W = canvas.width
  const H = canvas.height
  ctx.clearRect(0, 0, W, H)
  ctx.fillStyle = '#050a14'
  ctx.fillRect(0, 0, W, H)

  const grid = currentGrid.value
  if (!grid || !cells) return

  const cellSize = zoom
  const width = grid.width
  const height = grid.height

  const startCol = Math.max(0, Math.floor(-offsetX / cellSize))
  const endCol = Math.min(width, Math.ceil((W - offsetX) / cellSize))
  const startRow = Math.max(0, Math.floor(-offsetY / cellSize))
  const endRow = Math.min(height, Math.ceil((H - offsetY) / cellSize))

  ctx.fillStyle = 'rgba(107,122,153,0.25)'
  ctx.fillRect(
    offsetX + startCol * cellSize,
    offsetY + startRow * cellSize,
    (endCol - startCol) * cellSize,
    (endRow - startRow) * cellSize,
  )

  for (let row = startRow; row < endRow; row++) {
    for (let col = startCol; col < endCol; col++) {
      const val = cells[row * width + col]
      if (val === CELL_FREE) {
        ctx.fillStyle = '#e6ecf5'
      } else if (val === CELL_OCCUPIED) {
        ctx.fillStyle = '#111a2e'
      } else {
        continue
      }
      ctx.fillRect(offsetX + col * cellSize, offsetY + row * cellSize, cellSize + 0.5, cellSize + 0.5)
    }
  }

  if (cellSize >= 6) {
    ctx.strokeStyle = 'rgba(255,255,255,0.05)'
    ctx.lineWidth = 1
    for (let row = startRow; row < endRow; row++) {
      for (let col = startCol; col < endCol; col++) {
        if (cells[row * width + col] === CELL_OCCUPIED) {
          ctx.strokeRect(offsetX + col * cellSize, offsetY + row * cellSize, cellSize, cellSize)
        }
      }
    }
  }

  // 绘制批量选择高亮
  if (mode.value === 'batch' && selectedCells.value.size) {
    ctx.fillStyle = 'rgba(0,212,255,0.45)'
    ctx.strokeStyle = '#00d4ff'
    ctx.lineWidth = 1
    for (const k of selectedCells.value) {
      const [row, col] = keyToRowCol(k)
      if (row < startRow || row >= endRow || col < startCol || col >= endCol) continue
      const x = offsetX + col * cellSize
      const y = offsetY + row * cellSize
      ctx.fillRect(x, y, cellSize, cellSize)
      if (cellSize >= 4) ctx.strokeRect(x, y, cellSize, cellSize)
    }
  }

  // 绘制已有标注（组内格子共享同色）
  for (const a of annotations.value) {
    if (a.row < startRow || a.row >= endRow || a.col < startCol || a.col >= endCol) continue
    const x = offsetX + a.col * cellSize
    const y = offsetY + a.row * cellSize
    const color = a.color || '#ff8c00'

    ctx.fillStyle = color
    ctx.globalAlpha = 0.55
    ctx.fillRect(x, y, cellSize, cellSize)
    ctx.globalAlpha = 1

    ctx.strokeStyle = color
    ctx.lineWidth = Math.max(1, cellSize * 0.12)
    ctx.strokeRect(x, y, cellSize, cellSize)
  }

  // 每组标注只画一个文字标签（画在组的边界框附近）
  if (cellSize >= 4) {
    for (const g of groupList.value) {
      if (!g.text) continue
      if (g.maxRow < startRow || g.minRow >= endRow || g.maxCol < startCol || g.minCol >= endCol) continue
      const x = offsetX + g.maxCol * cellSize + cellSize + 4
      const y = offsetY + ((g.minRow + g.maxRow) / 2) * cellSize + cellSize / 2
      const label = g.cells.length > 1 ? `${g.text} ×${g.cells.length}` : g.text
      const fontSize = Math.min(14, Math.max(11, cellSize * 0.6))
      ctx.font = `${fontSize}px sans-serif`
      const tw = ctx.measureText(label).width
      ctx.fillStyle = 'rgba(0,0,0,0.7)'
      ctx.fillRect(x - 3, y - fontSize + 2, tw + 6, fontSize + 4)
      ctx.fillStyle = g.color || '#ff8c00'
      ctx.fillText(label, x, y)
    }
  }

  // 悬停指示
  if (hoverInfo.value && mode.value !== 'browse') {
    const { row, col, val } = hoverInfo.value
    ctx.strokeStyle = val === CELL_OCCUPIED ? '#00d4ff' : '#666'
    ctx.lineWidth = 2
    ctx.strokeRect(offsetX + col * cellSize, offsetY + row * cellSize, cellSize, cellSize)
  }

  // 框选矩形
  if (isBoxSelect && boxStart && boxCurrent) {
    const x = Math.min(boxStart.x, boxCurrent.x)
    const y = Math.min(boxStart.y, boxCurrent.y)
    const w = Math.abs(boxCurrent.x - boxStart.x)
    const h = Math.abs(boxCurrent.y - boxStart.y)
    ctx.fillStyle = 'rgba(0,212,255,0.15)'
    ctx.fillRect(x, y, w, h)
    ctx.strokeStyle = '#00d4ff'
    ctx.lineWidth = 1
    ctx.setLineDash([4, 4])
    ctx.strokeRect(x, y, w, h)
    ctx.setLineDash([])
  }
}

function resizeCanvas() {
  const canvas = mapCanvasRef.value
  const wrap = mapWrapRef.value
  if (!canvas || !wrap) return
  canvas.width = wrap.clientWidth
  canvas.height = wrap.clientHeight
  drawMap()
}

// -----------------------------------------------------------------------------
// 工具
// -----------------------------------------------------------------------------
function formatTime(ts: number) {
  if (!ts) return '--'
  const d = new Date(ts * 1000)
  return `${d.getMonth() + 1}/${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// -----------------------------------------------------------------------------
// 生命周期
// -----------------------------------------------------------------------------
onMounted(async () => {
  await nextTick()
  resizeCanvas()
  window.addEventListener('resize', resizeCanvas)
  await refreshMapList()
})

onUnmounted(() => {
  window.removeEventListener('resize', resizeCanvas)
})
</script>

<style lang="scss" scoped>
.slam-view {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.ml8 {
  margin-left: 8px;
}

.mt8 {
  margin-top: 12px;
}

.actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.full-width {
  width: 100%;
}

.batch-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 6px 10px;
  margin-bottom: 8px;
  background: rgba(0, 212, 255, 0.08);
  border: 1px solid rgba(0, 212, 255, 0.35);
  border-radius: 4px;

  .batch-info {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 12px;
    color: var(--color-text, #cfd8dc);

    .num {
      color: #00d4ff;
      font-weight: 600;
      margin: 0 2px;
    }
    .hint {
      color: var(--color-text-muted);
      margin-left: 4px;
    }
  }

  .batch-actions {
    display: flex;
    gap: 6px;
  }
}

.map-wrap {
  position: relative;
  background: #050a14;
  border-radius: 6px;
  overflow: hidden;
  height: 560px;

  .map-canvas {
    width: 100%;
    height: 100%;
    cursor: grab;

    &:active {
      cursor: grabbing;
    }

    &.cursor-cross {
      cursor: crosshair;

      &:active {
        cursor: grabbing;
      }
    }

    &.cursor-pointer {
      cursor: cell;

      &:active {
        cursor: grabbing;
      }
    }
  }

  .map-legend {
    position: absolute;
    bottom: 8px;
    left: 8px;
    display: flex;
    gap: 8px;

    .legend-item {
      font-size: 10px;
      padding: 2px 6px;
      border-radius: 3px;

      &.free {
        background: rgba(230, 236, 245, 0.85);
        color: #333;
      }
      &.occupied {
        background: #111a2e;
        color: #ccc;
        border: 1px solid rgba(255, 255, 255, 0.15);
      }
      &.unknown {
        background: rgba(107, 122, 153, 0.5);
        color: #ddd;
      }
      &.annotated {
        background: rgba(255, 140, 0, 0.6);
        color: #fff;
      }
      &.selected {
        background: rgba(0, 212, 255, 0.5);
        color: #fff;
      }
    }
  }

  .map-hover {
    position: absolute;
    top: 8px;
    left: 8px;
    background: rgba(0, 0, 0, 0.6);
    color: #cfd8dc;
    padding: 4px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-family: var(--font-mono, monospace);
    pointer-events: none;
  }

  .map-empty {
    position: absolute;
    inset: 0;
    display: flex;
    align-items: center;
    justify-content: center;
    color: rgba(255, 255, 255, 0.5);
    font-size: 13px;
  }
}

.ctrl-section {
  margin-bottom: 12px;

  .ctrl-label {
    font-size: 11px;
    color: var(--color-text-muted);
    margin-bottom: 6px;
  }

  .dir-hint {
    font-size: 11px;
    color: var(--color-text-muted);
    word-break: break-all;
    background: rgba(255, 255, 255, 0.03);
    padding: 4px 6px;
    border-radius: 4px;
  }

  .map-meta {
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
    font-size: 11px;
    color: var(--color-text-muted);
  }
}

.status-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 0;
  border-bottom: 1px solid rgba(30, 58, 95, 0.4);

  .label {
    font-size: 11px;
    color: var(--color-text-muted);
  }
  .val {
    font-size: 12px;
    color: var(--color-text);
  }
  .mono {
    font-family: var(--font-mono, monospace);
  }
}

.anno-list {
  max-height: 280px;
  overflow-y: auto;

  .anno-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 4px;
    border-bottom: 1px solid rgba(30, 58, 95, 0.3);
    cursor: pointer;
    transition: background 0.15s;

    &:hover {
      background: rgba(255, 255, 255, 0.03);
    }

    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      flex-shrink: 0;
    }

    .anno-text {
      flex: 1;
      overflow: hidden;

      .text {
        font-size: 12px;
        color: var(--color-text);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;

        .badge {
          background: rgba(0, 212, 255, 0.2);
          color: #00d4ff;
          font-size: 10px;
          padding: 1px 5px;
          border-radius: 8px;
          margin-left: 4px;
        }
      }
      .pos {
        font-size: 10px;
        color: var(--color-text-muted);
      }
    }
  }

  .empty-tip {
    font-size: 11px;
    color: var(--color-text-muted);
    text-align: center;
    padding: 14px;
  }
}

.anno-dialog-body {
  display: flex;
  flex-direction: column;
  gap: 12px;

  .row {
    display: flex;
    align-items: center;
    gap: 12px;

    .k {
      width: 72px;
      color: var(--color-text-muted);
      font-size: 12px;
      flex-shrink: 0;
    }
    .v {
      color: var(--color-text);
      font-size: 12px;
    }
    .mono {
      font-family: var(--font-mono, monospace);
    }
  }

  .color-picker {
    display: flex;
    gap: 6px;

    .color-swatch {
      width: 22px;
      height: 22px;
      border-radius: 4px;
      cursor: pointer;
      border: 2px solid transparent;
      transition: border-color 0.15s;

      &.active {
        border-color: #fff;
      }
    }
  }
}
</style>
