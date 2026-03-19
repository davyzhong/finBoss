#!/bin/bash
# ===========================================
# dbt 初始化脚本
# ===========================================
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

echo "==========================================="
echo "dbt 初始化"
echo "==========================================="

cd "$PROJECT_ROOT/config/dbt/finboss"

# 检查 dbt 是否安装
if ! command -v dbt &> /dev/null; then
    echo "错误: dbt 未安装"
    echo "安装: pip install dbt-core dbt-doris"
    exit 1
fi

# 初始化 profiles.yml
echo "[1/3] 配置 profiles.yml..."
mkdir -p ~/.dbt
cat > ~/.dbt/profiles.yml << 'EOF'
finboss:
  target: dev
  outputs:
    dev:
      type: doris
      host: localhost
      port: 9030
      user: root
      password: ""
      database: finboss
      schema: dm
      threads: 4
EOF
echo "✓ profiles.yml 已创建"

# 调试连接
echo "[2/3] 测试连接..."
dbt debug --profiles-dir ~/.dbt || echo "警告: 连接测试失败，继续..."

# 安装依赖
echo "[3/3] 安装 dbt 依赖..."
dbt deps --profiles-dir ~/.dbt || echo "警告: 无额外依赖"

echo ""
echo "==========================================="
echo "dbt 初始化完成！"
echo "==========================================="
echo ""
echo "常用命令:"
echo "  dbt run --profiles-dir ~/.dbt        # 运行所有模型"
echo "  dbt test --profiles-dir ~/.dbt       # 运行测试"
echo "  dbt docs generate --profiles-dir ~/.dbt  # 生成文档"
