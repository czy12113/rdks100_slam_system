# 地图文件目录
# 使用 save_map.sh 保存的地图将存放于此目录
# 格式：
#   my_map.pgm   - 最新地图（灰度图像）
#   my_map.yaml  - 最新地图元数据
#   map_YYYYMMDD_HHMMSS.pgm/.yaml - 按时间戳备份

# 地图YAML格式说明：
# image: my_map.pgm
# resolution: 0.05          # 每像素对应0.05米
# origin: [x, y, theta]    # 地图左下角坐标（米）和朝向（弧度）
# negate: 0                 # 是否反转颜色（0=白色=空闲）
# occupied_thresh: 0.65     # 占据概率阈值
# free_thresh: 0.196        # 空闲概率阈值
