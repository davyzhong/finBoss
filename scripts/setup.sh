#!/bin/bash
# ===========================================
# FinBoss 环境初始化脚本
# ===========================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==========================================="
echo "FinBoss 环境初始化"
echo "==========================================="

# 1. 检查 Docker
echo "[1/5] 检查 Docker 环境..."
if ! command -v docker &> /dev/null; then
    echo "错误: Docker 未安装"
    exit 1
fi

if ! docker info &> /dev/null; then
    echo "错误: Docker 未运行"
    exit 1
fi
echo "✓ Docker 已就绪"

# 2. 复制环境变量文件
echo "[2/5] 配置环境变量..."
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        cp "$PROJECT_ROOT/.env.example" "$PROJECT_ROOT/.env"
        echo "✓ 已创建 .env 文件，请编辑填入实际值"
    else
        echo "警告: .env.example 不存在"
    fi
else
    echo "✓ .env 文件已存在"
fi

# 3. 启动 Docker Compose
echo "[3/5] 启动基础设施组件..."
cd "$PROJECT_ROOT/config"
docker-compose up -d

echo "等待组件启动..."
sleep 10

# 4. 检查组件状态
echo "[4/5] 检查组件状态..."
COMPONENTS=("zookeeper" "kafka" "minio" "doris-fe" "doris-be" "clickhouse" "flink-jobmanager")

for component in "${COMPONENTS[@]}"; do
    if docker ps | grep -q "$component"; then
        echo "  ✓ $component"
    else
        echo "  ✗ $component (未运行)"
    fi
done

# 5. 创建 MinIO Bucket
echo "[5/5] 创建 MinIO Bucket..."
docker exec finboss-minio mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
docker exec finboss-minio mc mb local/finboss --ignore-existing 2>/dev/null || true

echo ""
echo "==========================================="
echo "环境初始化完成！"
echo "==========================================="
echo ""
echo "访问地址:"
echo "  - MinIO Console: http://localhost:9001 (minioadmin/minioadmin)"
echo "  - Flink Dashboard: http://localhost:8081"
echo "  - Doris FE: mysql://localhost:9030"
echo ""
echo "下一步:"
echo "  1. 编辑 .env 填入金蝶数据库连接信息"
echo "  2. 运行 'uv sync' 安装 Python 依赖"
echo "  3. 运行 'uv run uvicorn api.main:app --reload' 启动 API"
