#!/bin/bash
# RDK S100 上位机启动脚本
# 用法: ./start.sh [dev|prod|backend|frontend]

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
STATIC_DIR="$BACKEND_DIR/static/dist"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()  { echo -e "${BLUE}[STEP]${NC} $1"; }

MODE="${1:-prod}"

check_python() {
    if ! command -v python3 &>/dev/null; then
        log_error "未找到 python3，请先安装 Python 3.8+"
        exit 1
    fi
    log_info "Python: $(python3 --version)"
}

check_node() {
    if ! command -v node &>/dev/null; then
        log_warn "未找到 node，跳过前端构建"
        return 1
    fi
    log_info "Node: $(node --version)"
    return 0
}

install_backend_deps() {
    log_step "安装后端依赖..."
    cd "$BACKEND_DIR"
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        log_info "已创建虚拟环境"
    fi
    source venv/bin/activate
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    log_info "后端依赖安装完成"
}

build_frontend() {
    log_step "构建前端..."
    cd "$FRONTEND_DIR"
    if [ ! -d "node_modules" ]; then
        log_step "安装前端依赖..."
        npm install
    fi
    # vite outDir 已配置为 ../backend/static/dist，构建产物直接输出到后端目录，无需 cp
    npm run build
    log_info "前端构建完成，输出到 $STATIC_DIR"
}

start_backend() {
    log_step "启动后端服务..."
    cd "$BACKEND_DIR"
    source venv/bin/activate 2>/dev/null || true

    # 清理 __pycache__，防止旧字节码缓存导致环境变量读取异常
    find "$BACKEND_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    log_info "已清理 __pycache__"

    # 默认关闭 ROS2（后续按条件覆盖）
    export ROS2_ENABLED=false

    # 加载 ROS2 环境
    ROS2_BASE=""
    for ros_setup in /opt/ros/humble/setup.bash /opt/ros/foxy/setup.bash /opt/ros/galactic/setup.bash; do
        if [ -f "$ros_setup" ]; then
            source "$ros_setup"
            ROS2_BASE="$ros_setup"
            log_info "已加载 ROS2 环境: $ros_setup"
            break
        fi
    done
    if [ -z "$ROS2_BASE" ]; then
        log_warn "未找到 ROS2 安装，将以模拟数据模式运行"
    fi

    # 加载雷达工作空间（如果存在且已编译）
    ROS2_WS="$PROJECT_DIR/ros2_ws"
    if [ -f "$ROS2_WS/install/setup.bash" ]; then
        source "$ROS2_WS/install/setup.bash"
        export ROS2_ENABLED=true
        log_info "已加载雷达 ROS2 工作空间，ROS2_ENABLED=true"
    elif [ -n "$ROS2_BASE" ]; then
        # ROS2 基础环境存在但工作空间未编译，仍可接收标准 /scan topic
        export ROS2_ENABLED=true
        log_warn "雷达工作空间未编译（$ROS2_WS/install/setup.bash 不存在）"
        log_warn "ROS2_ENABLED=true，将尝试订阅 /scan topic（需外部节点发布）"
    else
        export ROS2_ENABLED=false
        log_warn "雷达工作空间未编译且无 ROS2 环境，激光雷达数据将使用模拟"
    fi

    log_info "ROS2_ENABLED=${ROS2_ENABLED}"
    log_info "后端启动于 http://0.0.0.0:8000"
    log_info "前端访问地址: http://$(hostname -I | awk '{print $1}'):8000"
    python3 main.py
}

start_frontend_dev() {
    log_step "启动前端开发服务器..."
    cd "$FRONTEND_DIR"
    if [ ! -d "node_modules" ]; then
        npm install
    fi
    npm run dev
}

case "$MODE" in
    "dev")
        log_info "=== 开发模式 ==="
        check_python
        check_node
        install_backend_deps
        # 后台启动后端
        (cd "$BACKEND_DIR" && source venv/bin/activate 2>/dev/null || true && python3 main.py) &
        BACKEND_PID=$!
        log_info "后端 PID: $BACKEND_PID"
        sleep 2
        # 前台启动前端开发服务器
        start_frontend_dev
        ;;
    "prod")
        log_info "=== 生产模式 ==="
        check_python
        install_backend_deps
        if check_node; then
            build_frontend
        else
            if [ ! -d "$STATIC_DIR" ]; then
                log_error "未找到前端构建产物且无法构建，请先在有 Node.js 的机器上构建"
                exit 1
            fi
            log_warn "使用已有的前端构建产物"
        fi
        start_backend
        ;;
    "backend")
        log_info "=== 仅启动后端 ==="
        check_python
        install_backend_deps
        start_backend
        ;;
    "frontend")
        log_info "=== 仅启动前端开发服务器 ==="
        check_node || exit 1
        start_frontend_dev
        ;;
    "build")
        log_info "=== 仅构建前端 ==="
        check_node || exit 1
        build_frontend
        ;;
    *)
        echo "用法: $0 [dev|prod|backend|frontend|build]"
        echo "  dev      - 开发模式（后端+前端热重载）"
        echo "  prod     - 生产模式（构建前端+启动后端，默认）"
        echo "  backend  - 仅启动后端"
        echo "  frontend - 仅启动前端开发服务器"
        echo "  build    - 仅构建前端"
        exit 1
        ;;
esac
