# 部署指南

这个指南将帮助你将项目从本地开发环境部署到 PaaS 云平台，实现数据持久化存储。

## 📋 部署概览

项目现在支持**环境自适应**的数据库配置：
- **开发环境**：使用本地 ChromaDB（快速、无需网络）
- **生产环境**：使用云端 PostgreSQL（持久化、高可用）

## 🛠️ 部署步骤

### 第一阶段：准备云数据库

#### 1. 在 Render 上创建 PostgreSQL 数据库

1. 登录 [Render Dashboard](https://dashboard.render.com/)
2. 点击 "New +" → 选择 "PostgreSQL"
3. 配置数据库：
   - **Name**: `agent-db`（或你喜欢的名字）
   - **Database**: `agent`
   - **User**: 保持默认
   - **Region**: 选择离你最近的区域
   - **Plan**: 选择 "Free"（开始阶段足够）
4. 点击 "Create Database"
5. 等待数据库创建完成（约 2-3 分钟）

#### 2. 获取数据库连接信息

数据库创建完成后，进入数据库管理页面：
1. 在 "Connections" 部分，你会看到两个 URL：
   - **Internal Database URL**: 用于生产环境（Web Service 连接）
   - **External Database URL**: 用于本地迁移脚本
2. **复制并保存这两个 URL**，稍后会用到

### 第二阶段：数据迁移（可选）

如果你已经有本地的 ChromaDB 数据需要迁移：

#### 1. 配置本地环境

在你的本地 `.env` 文件中添加：
```bash
DATABASE_URL=你复制的_External_Database_URL
```

#### 2. 执行迁移脚本

在项目根目录运行：
```bash
# 安装新的依赖
pip install -r requirements.txt

# 执行数据迁移
python scripts/migrate_chroma_to_pg.py
```

脚本会自动：
- 连接到本地 ChromaDB
- 读取所有向量数据
- 将数据迁移到云端 PostgreSQL
- 验证迁移结果

### 第三阶段：部署 Web 应用

#### 1. 推送代码到 Git 仓库

确保所有修改都已提交并推送：
```bash
git add .
git commit -m "feat: Add PostgreSQL support for production deployment"
git push
```

#### 2. 在 Render 上创建 Web Service

1. 在 Render Dashboard 点击 "New +" → 选择 "Web Service"
2. 连接你的 Git 仓库
3. 配置服务：
   - **Name**: `my-agent-app`（或你喜欢的名字）
   - **Root Directory**: 留空
   - **Environment**: Python 3
   - **Build Command**: `./build.sh`
   - **Start Command**: `uvicorn src.api.main:app --host=0.0.0.0 --port=$PORT`

#### 3. 配置环境变量

在 "Environment Variables" 部分添加：

| Key | Value | 说明 |
|-----|-------|------|
| `ENVIRONMENT` | `production` | 启用生产环境模式 |
| `DATABASE_URL` | 你的_Internal_Database_URL | 数据库连接（使用内部 URL） |
| `DASHSCOPE_API_KEY` | 你的_API_密钥 | 必填：通义千问 API |
| `TAVILY_API_KEY` | 你的_API_密钥 | 可选：网络搜索 |
| `SENIVERSE_API_KEY` | 你的_API_密钥 | 可选：天气查询 |

#### 4. 部署应用

点击 "Create Web Service"，Render 将：
1. 拉取你的代码
2. 执行 `build.sh` 构建前端和安装依赖
3. 启动后端服务
4. 提供一个 `*.onrender.com` 的公开访问地址

## 🔄 本地开发工作流

修改完成后，你的本地开发体验保持不变：

### 本地运行（开发模式）
```bash
# 后端（使用本地 ChromaDB）
uvicorn src.api.main:app --reload

# 前端
cd frontend
npm run dev
```

你的本地 `.env` 文件只需要：
```bash
DASHSCOPE_API_KEY=你的API密钥
# DATABASE_URL 和 ENVIRONMENT 不需要设置，会使用默认值
```

### 测试生产模式（本地）
如果你想在本地测试生产环境的配置：
```bash
# 在 .env 中临时设置
ENVIRONMENT=production
DATABASE_URL=你的_External_Database_URL

# 然后正常启动
uvicorn src.api.main:app --reload
```

## 🔍 故障排除

### 常见问题

**1. 本地启动报错 "DATABASE_URL 未设置"**
- 检查 `.env` 文件中是否设置了 `ENVIRONMENT=production`
- 如果是本地开发，删除或注释掉这一行

**2. 迁移脚本报错 "找不到 ChromaDB 路径"**
- 确认 `storage/chroma/local` 目录存在
- 检查 `scripts/migrate_chroma_to_pg.py` 中的路径配置

**3. 生产环境部署失败**
- 检查 Render 的构建日志
- 确认所有环境变量都已正确设置
- 确认 `build.sh` 文件有执行权限

**4. 向量搜索不工作**
- 确认数据库中有数据（运行迁移脚本）
- 检查 PostgreSQL 是否启用了 pgvector 扩展

### 查看日志

**本地开发：**
```bash
uvicorn src.api.main:app --reload --log-level debug
```

**生产环境：**
在 Render 的服务页面查看 "Logs" 标签页

## 📊 监控和维护

### 数据库管理

你可以通过以下方式管理云数据库：
1. **Render Dashboard**: 查看连接数、存储使用量
2. **psql 命令行**: 使用 External URL 直接连接
3. **GUI 工具**: 如 pgAdmin、DBeaver 等

### 备份策略

Render 的 PostgreSQL 会自动进行日常备份，但建议：
1. 定期导出重要数据
2. 在重大更新前手动创建备份点

## 🎯 下一步

部署完成后，你可以考虑：
1. **自定义域名**: 在 Render 中配置自定义域名
2. **HTTPS 证书**: Render 自动提供 SSL 证书
3. **监控告警**: 设置服务健康监控
4. **性能优化**: 根据使用情况升级数据库套餐

---

🎉 恭喜！你的 AI Agent 应用现在已经具备了生产级别的数据持久化能力！
