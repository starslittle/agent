# 迁移后清理清单

## 🗑️ 可以删除的目录和文件

### 1. 旧代码目录（已迁移）

#### ✅ 可以删除
```
backend/src/              # 旧的源代码目录
├── agent_app/           # → 已迁移到 agent/
├── api/                 # → 已迁移到 app/api/
├── core/                # → 已迁移到 app/core/
├── eval/                # → 评估代码（保留或迁移到 tests/eval）
├── rag/                 # → 已迁移到 rag/
└── workers/             # → 已迁移到 workers/
```

### 2. 旧配置文件目录

#### ✅ 可以删除
```
backend/prompts/          # → 已迁移到 agent/prompts/
```

### 3. 缓存目录

#### ✅ 可以删除
```
所有 __pycache__/ 目录
所有 *.pyc 文件
所有 *.pyo 文件
```

### 4. 重复的节点文件

#### ✅ 可以删除
```
backend/graph/nodes/generation.py    # 被 generate.py 替代
backend/graph/nodes/tools.py         # 已改为兼容层，保留
```

## 📝 保留的重要文件

### 必须保留
- ✅ `backend/app/` - 新的应用层
- ✅ `backend/agent/` - 智能体层
- ✅ `backend/graph/` - LangGraph层
- ✅ `backend/rag/` - RAG层
- ✅ `backend/infra/` - 基础设施层
- ✅ `backend/workers/` - Workers
- ✅ `backend/configs/` - 配置文件
- ✅ `backend/scripts/` - 脚本
- ✅ `backend/tests/` - 测试
- ✅ `backend/requirements/` - 依赖
- ✅ `.env` - 仓库根目录的唯一环境变量来源
- ✅ `backend/data/` - 数据目录
- ✅ `backend/storage/` - 存储目录

## 🧹 清理步骤

### 方法1：使用清理脚本（推荐）

```bash
cd backend
python cleanup_migration.py
```

### 方法2：手动清理

```bash
cd backend

# 删除旧的src目录
rm -rf src/

# 删除旧的prompts目录
rm -rf prompts/

# 清理所有__pycache__
find . -type d -name "__pycache__" -exec rm -rf {} +

# 清理.pyc文件
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete
```

## 📊 清理前后对比

### 清理前
```
backend/
├── src/                  ❌ 旧代码
├── prompts/              ❌ 旧prompts
├── app/                  ✅ 新代码
├── agent/                ✅ 新代码
├── graph/                ✅ 新代码
├── rag/                  ✅ 新代码
├── __pycache__/           ❌ 缓存
└── ...
```

### 清理后
```
backend/
├── app/                  ✅ 应用层
├── agent/                ✅ 智能体层
├── graph/                ✅ LangGraph层
├── rag/                  ✅ RAG层
├── infra/                ✅ 基础设施层
├── workers/              ✅ Workers
├── configs/              ✅ 配置
├── scripts/              ✅ 脚本
├── tests/                ✅ 测试
├── requirements/         ✅ 依赖
├── data/                 ✅ 数据
└── storage/              ✅ 存储
```

## ⚠️ 注意事项

1. **备份建议**：清理前建议先备份整个项目
2. **测试验证**：清理后运行测试确保功能正常
3. **Git提交**：建议先提交当前更改，再进行清理

## 🚀 执行清理

清理命令：
```bash
cd backend
python cleanup_migration.py
```

或者手动执行：
```bash
# Windows PowerShell
cd backend
Remove-Item -Recurse -Force src
Remove-Item -Recurse -Force prompts
Get-ChildItem -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
```

清理后验证：
```bash
# 启动服务测试
python run.py

# 或运行测试
python test_graph.py
```
