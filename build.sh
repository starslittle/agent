#!/usr/bin/env bash
# PaaS 平台部署构建脚本
# 用于自动构建前端和安装后端依赖

set -o errexit  # 遇到错误立即退出

echo "🚀 开始构建应用..."

# 1. 构建前端
echo "📦 正在构建前端..."
cd frontend

# 检查 package.json 是否存在
if [ ! -f "package.json" ]; then
    echo "❌ 错误: 找不到 package.json 文件"
    exit 1
fi

# 安装前端依赖并构建
echo "📥 安装前端依赖..."
npm install

echo "🔨 构建前端应用..."
npm run build

# 回到项目根目录
cd ..

# 2. 安装后端依赖
echo "🐍 安装 Python 依赖..."
pip install -r backend/requirements.txt

echo "✅ 构建完成！"
echo "💡 提示: 确保在生产环境中设置了以下环境变量："
echo "   - DATABASE_URL (PostgreSQL 连接字符串)"
echo "   - ENVIRONMENT=production"
echo "   - DASHSCOPE_API_KEY (你的 API 密钥)"
