# 智能 AI Agent 售前服务系统

一款企业级售前客服 AI Agent 系统，打通「数据脱敏管道 → 混合检索 → 售前咨询 Agent → 内容生成 Agent → 可视化前端」的完整链路。

> 对应设计文档《智能AI-Agent售前服务系统-设计文档》，实现 PRD 的全部功能需求（FR-01 ~ FR-07）与目标（G-1 ~ G-6）。

## 特性

- **LangGraph 编排**：两个 Agent 均以 `LangGraph StateGraph` 实现（售前 ReAct 决策循环 / 内容生成多阶段工作流），工具以 LangChain `Tool` 封装，满足技术栈锁定（LangChain 1.x + LangGraph）。
- **无需 API Key 亦可跑通**：LLM 无 Key 时走离线 Mock、向量后端 chromadb 未装时自动回退内置 `simple`（特征哈希），端到端演示与跑测试不受影响。
- **六模块分层**：`app-core` 框架 / `data-pipeline` 数据管道 / `retrieval` 混合检索 / 售前咨询 Agent（ReAct）/ 内容生成 Agent（SubGraph）/ Vue 3 前端（FastAPI 网关）。
- **可靠性内置**：统一 `safe_call` 重试/退避/降级，整体故障率为 0（G-5）；`max_steps` 兜底防死循环；Checkpointer 支持断点恢复。
- **PII 脱敏 100%**（G-3）、**会话隔离 100%**（G-4）、**混合检索 FTS5 + 向量融合**（G-2，命中率 ≥85%，见 `docs/检索评测报告.md`）。

## 快速开始

```bash
cd agent-system

# 0) 安装依赖（LangGraph / LangChain 1.x 为必装）
pip install -r requirements.txt

# 1) 端到端演示（无需 API Key）
python demo.py

# 2) 运行全部单元测试（含 G-2 检索评测、G-4 会话隔离）
python run_tests.py
```

启动 Web 前端（Vue 3 + FastAPI，总览 / 智能问答 / 知识入库 / 内容生成 / 数据管道五个页面）：

```bash
pip install -r requirements.txt          # fastapi/uvicorn 等
# 双击 启动前端.bat（自动构建 frontend/dist 并启动）,或手动:
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
# 浏览器访问 http://127.0.0.1:8000

# 前端开发模式(热更新,需另一个终端):
cd frontend && npm install && npm run dev   # http://localhost:5173,/api 自动代理到 8000
```

接入真实大模型：复制 `.env.example` 为 `.env`，填入 `LLM_MODEL` / `LLM_API_KEY` / `LLM_BASE_URL`（兼容 OpenAI 接口）。

## 目录结构

```
agent-system/
├── app_core/            # 模块 A：配置/日志/异常/模型/safe_call/LLM 客户端
├── data_pipeline/       # 模块 B：清洗/去重/会话切分/PII 脱敏
├── retrieval/           # 模块 C：FTS5 全文 + 向量 + 混合融合
├── agents/
│   ├── pre_sale/        # 模块 D：售前咨询 Agent（ReAct）
│   └── content/         # 模块 E：内容生成 Agent（SubGraph + Checkpointer）
├── frontend/            # 模块 F：Vue 3 前端（Vite + Element Plus + ECharts）
├── api/                 # 模块 F：FastAPI 网关（REST API + 托管前端静态资源）
├── tests/               # 单元测试（unittest,含 API 测试）
├── docs/                # 测试报告 / 检索评测报告 / 验收清单（G-6）
├── data/                # 运行期数据 + eval_qa.json 评测集
├── service.py           # 系统门面：统一装配各模块
├── demo.py              # 端到端演示脚本
├── run_tests.py         # 测试入口
├── config.yaml          # 非敏感配置
├── .env.example         # 敏感配置模板
└── requirements.txt     # 依赖（版本锁定）
```

## 核心设计

### 售前咨询 Agent（ReAct 状态机）

```
idle → thinking → acting → observing → responding → done
        失败 → retry(≤2) → 降级回答 → done
        超 max_steps=10 → 终止 → done
```

`ToolRouter` 按关键词路由到 `search_knowledge` / `get_product_info` / `get_stock`，调用统一走 `safe_call`。

### 内容生成 Agent（SubGraph 工作流）

```
idle → topic_generation → copy_generation → script_generation → done
        任一阶段失败 → retry(≤3) → skip_node → partial_done
        Checkpointer 记录状态，支持 resume 断点恢复
```

### 混合检索

```
query → FTS5 全文检索(归一化) ─┐
      → 向量检索(归一化)       ─┴→ final = fts_weight·f + vector_weight·v → top_k
```

## 验收标准映射

| 目标 | 指标 | 对应实现/测试 |
| --- | --- | --- |
| G-1 | 三大核心模块组装可运行 | `demo.py` 端到端全链路 |
| G-2 | 混合检索准确率 ≥85% | `retrieval/eval.py`，`data/eval_qa.json`，`tests/test_retrieval_quality.py` |
| G-3 | PII 脱敏准确率 100% | `data_pipeline/masker.py`，`tests/test_masker.py` |
| G-4 | 会话隔离率 100% | `app_core/session.py`，`service.py`，`tests/test_session.py` |
| G-5 | 工具调用故障率 0 | `app_core/safe_call.py`，`tests/test_agent.py`，`tests/test_safe_call.py` |

## 关于 LangChain/LangGraph

本项目的两个 Agent **均以官方 `LangGraph StateGraph` 编排**：

- `agents/pre_sale/graph.py`：售前咨询 ReAct 状态机（`think → act → observe → respond/degrade`）。
- `agents/content/graph.py`：内容生成多阶段工作流（`topic → copy → script`），编译时挂载 `InMemorySaver`（LangGraph Checkpointer）。

工具以 `langchain_core.tools.Tool` 封装（见 `agents/pre_sale/tools.py:build_langchain_tools`）。LLM 调用仍走 `app_core.llm` 的 OpenAI 兼容封装（标准库 urllib，无额外依赖）。

> 说明：LangGraph 的持久化 Checkpointer（SQLite 后端）需额外安装 `langgraph-checkpoint-sqlite`，故内容生成任务的跨进程断点恢复复用 `agents/content/persist.py` 的 JSON Checkpointer。