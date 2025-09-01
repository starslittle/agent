# 奇点AI Agent

一体化对话与任务代理：默认走简单聊天；在命理模式与深度思考模式下，按需启用受限域智能路由与 ReAct 工具链，支持流式输出与可扩展的 RAG 能力。

## 目录
- 项目概述
- 核心能力
- 快速开始
- 运行与模式说明
- API 速览
- 部署与持久化

## 项目概述
- 名称：奇点AI Agent
- 一句话：简单问题直答，复杂任务智能分流（命理/研究/RAG），前后端一体化、流式反馈。
- 主要价值：
  - 默认直连 LLM，响应快、成本低；
  - 按按钮选择“命理/深度思考”时，自动切换到合适的 Agent 与工具；
  - 支持本地与云端向量库，便于生产部署与数据持久化。

## 核心能力
- 简单聊天直答：`default_llm_agent`，无 ReAct、稳定输出。
- 命理智能分析：命理模式下受限域智能路由，命理问题走 `fortune_agent`，非命理回退聊天。
- 深度思考检索：深度模式下在 `research_agent` 与 `general_rag_agent` 之间路由，支持网络检索与本地/Notion/Pandas 知识库。
- 流式输出：`/query_stream` 持续返回增量文本，前端顺滑展示。

## 快速开始
1) 安装依赖（建议 Python 3.10+）
```bash
pip install -r requirements.txt
```
2) 本地运行后端
```bash
# PowerShell 请分两步
cd C:\Users\10245\Desktop\agent
uvicorn src.api.main:app --reload
```
3) 本地运行前端（可选，若需要二开）
```bash
cd frontend
npm install
npm run dev
```

> 环境变量：复制 `env.example` 为 `.env`，至少设置 `DASHSCOPE_API_KEY`；如需云数据库，配置 `DATABASE_URL` 与 `ENVIRONMENT=production`。

## 运行与模式说明
前端通过按钮控制模式，后端遵循以下约定（`QueryRequest.agent_name`）：
- 默认/未选/`default`：固定 `default_llm_agent`（简单聊天；不触发路由与 ReAct）
- `fortune` 或 `fortune_agent`：命理智能路由
  - 真命理 → `fortune_agent`
  - 闲聊/非命理 → 回退 `default_llm_agent`
- `research` 或 `research_agent`：深度思考智能路由
  - 研究/检索 → `research_agent`
  - 一般分析 → `general_rag_agent`
  - 闲聊 → 回退 `default_llm_agent`
- `auto`：全局智能路由（可选）

## API 速览
- POST `/query`
  - 入参：`{ query: string, agent_name?: string, chat_history?: {role,content}[] }`
  - 出参：`{ agent_name: string, answer: string, output?: string }`
- POST `/query_stream`
  - NDJSON 流式返回：`{"type":"delta","data":"..."}`，结束为 `{"type":"done"}`
- GET `/healthz`：服务健康与已加载 Agent 列表

## 部署与持久化
- 一体化部署：使用 `build.sh`（先构建前端，再安装后端依赖），`Start Command` 示例：
```bash
uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```
- 数据持久化（RAG）：
  - 开发：默认使用本地 Chroma（`storage/chroma`）
  - 生产：配置 `DATABASE_URL` 与 `ENVIRONMENT=production`，自动切换到 PostgreSQL（pgvector）。
  - 提供 `scripts/migrate_chroma_to_pg.py` 用于数据迁移。

---
更多细节请参考 `DEPLOYMENT.md` 与源码注释。
