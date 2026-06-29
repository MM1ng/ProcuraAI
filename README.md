# Enterprise Procurement Agent / 企业采购智能体

**基于 Agentic RAG 的电商/采购推荐智能体系统**

An intelligent procurement recommendation system powered by Agentic RAG and
LLMs. It understands natural language purchase requests, retrieves relevant
products, generates optimized procurement plans, creates orders, and supports
mock or Stripe payments through a conversational interface.

这是一个由 Agentic RAG 和大模型驱动的智能采购推荐系统。它可以理解自然语言采购
需求，检索相关商品，生成优化后的采购方案，创建订单，并通过对话界面完成模拟支付
或 Stripe 支付。

---

## Tech Stack / 技术栈

| Layer / 层级 | Technology / 技术 |
|---|---|
| Frontend / 前端 | Next.js 16, TypeScript 5.5, Ant Design 5.20, Recharts 2.12 |
| Backend / 后端 | FastAPI, Python 3.12+, SQLAlchemy 2.0, Pydantic 2.7 |
| Agent / 智能体 | LangChain, Custom Intent Parser, Plan Generator, Plan Variants |
| RAG / 检索增强生成 | Chroma (local), Alibaba Cloud Bailian embeddings, hybrid vector + structured filters |
| Database / 数据库 | SQLite (dev), PostgreSQL-ready SQLAlchemy models |
| Payment / 支付 | Stripe SDK (test mode) + Mock Payment mode |
| Observability / 可观测性 | Local JSON traces + Langfuse adapter (optional) |
| Evaluation / 评估 | Mock metrics + Ragas extension (optional) + MLflow adapter (optional) |
| LLM / 大模型 | Qwen (Alibaba Cloud Bailian) + Mock LLM fallback |

---

## Features / 功能

- **Intelligent Procurement Recommendation / 智能采购推荐** - Natural language requests become optimized product recommendations / 将自然语言采购需求转成优化商品推荐
- **Agentic RAG / 智能体式 RAG** - Hybrid search with vector retrieval and structured filters / 结合向量检索与类别、价格、评分、库存、配送等结构化过滤
- **Vector Knowledge Retrieval / 向量知识检索** - Local Chroma collections for products, policies, and suppliers / 使用本地 Chroma 集合检索商品、政策和供应商画像
- **Multi-turn Memory / 多轮记忆** - Keeps session context across conversation turns / 在多轮对话中保留会话上下文
- **Mock LLM Fallback / 模拟大模型兜底** - Runs without API keys using deterministic rules / 无需 API key 也能用规则兜底运行
- **Compare Plans / 多方案对比** - Cost Optimized, Balanced, and Premium options / 提供成本优先、均衡、高端三种方案
- **Quick Optimization / 快速优化** - Make cheaper, improve quality, faster delivery, prefer Dell / 支持降本、提质、加快配送、优先 Dell 等快捷操作
- **Order Management / 订单管理** - Full lifecycle from creation to payment / 覆盖从创建到支付的订单流程
- **Stripe Payment / Stripe 支付** - Test mode and mock checkout / 支持 Stripe 测试模式和模拟支付
- **Observability Dashboard / 可观测性看板** - Trace logs, latency, tool call stats / 展示链路日志、延迟和工具调用统计
- **Evaluation Dashboard / 评估看板** - Business metrics and RAG metrics / 展示业务指标与 RAG 指标
- **Procurement History / 采购历史** - Save, restore, and delete plans / 保存、恢复和删除采购方案
- **Excel Export / Excel 导出** - Download procurement plans as `.xlsx` / 将采购方案下载为 `.xlsx`
- **Category Normalization / 类别标准化** - Multilingual catalog category resolution / 支持多语言请求中的商品类别归一化
- **Multi-language UI / 多语言界面** - Chinese and English / 中文和英文

---

## Project Structure / 项目结构

```text
enterprise-procurement-agent/
├── backend/              # FastAPI application / FastAPI 后端应用
│   ├── app/
│   │   ├── agent/        # Intent parsing and plan generation / 意图解析与方案生成
│   │   ├── api/          # REST endpoints / REST 接口
│   │   ├── core/         # Config, database, logging / 配置、数据库、日志
│   │   ├── evaluation/   # Evaluation metrics and runners / 评估指标与运行器
│   │   ├── models/       # SQLAlchemy ORM models / SQLAlchemy ORM 模型
│   │   ├── observability/# Tracing and Langfuse integration / 链路追踪与 Langfuse 集成
│   │   ├── rag/          # Hybrid search and vector store / 混合检索与向量库
│   │   ├── schemas/      # Pydantic schemas / Pydantic 请求响应结构
│   │   ├── scripts/      # Data generation and ingestion / 数据生成与导入脚本
│   │   ├── services/     # Business logic services / 业务逻辑服务
│   │   └── tools/        # Stripe AI tools / Stripe AI 工具
│   ├── tests/            # Pytest suite / Pytest 测试
│   └── main.py           # FastAPI entry point / FastAPI 入口
├── frontend/             # Next.js application / Next.js 前端应用
│   ├── app/              # App Router pages / App Router 页面
│   ├── components/       # Reusable React components / 可复用 React 组件
│   ├── lib/              # i18n, auth, API client, types / 国际化、认证、API 客户端、类型
│   └── styles/           # CSS styles / 样式
├── data/                 # Product data, retrieval index, logs / 商品数据、检索索引、日志
├── docs/                 # Design documents / 设计文档
└── docker-compose.yml    # Docker orchestration / Docker 编排
```

---

## Quick Start / 快速开始

### Prerequisites / 前置要求

- Python 3.12+
- Node.js 20+
- npm

### Backend Setup / 后端启动

```bash
cd backend
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt

# Set up environment / 设置环境变量
cp .env.example .env
# Edit .env; mock mode works without API keys
# 编辑 .env；mock 模式不需要任何 API key

# Initialize data / 初始化数据
python -m app.scripts.generate_products
python -m app.scripts.seed_db
python -m app.scripts.ingest_products

# Start backend / 启动后端
uvicorn main:app --reload --port 8000
```

### Frontend Setup / 前端启动

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:3000**.

打开 **http://localhost:3000**。

### Verify / 验证

```bash
curl http://localhost:8000/health
# -> {"status":"ok","service":"enterprise-procurement-agent"}
```

---

## Environment Variables / 环境变量

| Variable / 变量 | Description / 说明 | Default / 默认值 |
|---|---|---|
| `USE_MOCK_LLM` | Use deterministic mock LLM; no API key needed / 使用确定性的模拟大模型，无需 API key | `true` |
| `USE_MOCK_PAYMENT` | Use mock payment URLs / 使用模拟支付链接 | `true` |
| `LLM_PROVIDER` | LLM provider; `tongyi` means Qwen / 大模型提供商，`tongyi` 表示通义千问 | `tongyi` |
| `DASHSCOPE_API_KEY` | Alibaba Cloud Bailian API key / 阿里云百炼 API key | optional / 可选 |
| `QWEN_MODEL` | Qwen model name / 通义千问模型名 | `qwen-turbo` |
| `EMBEDDING_PROVIDER` | Embedding provider, `tongyi` or `hash` / 嵌入模型提供方，可选 `tongyi` 或 `hash` | `tongyi` |
| `EMBEDDING_MODEL` | Bailian embedding model name / 百炼嵌入模型名 | `text-embedding-v4` |
| `EMBEDDING_DIMENSION` | Embedding vector dimension / 嵌入向量维度 | `1024` |
| `DATABASE_URL` | Database URL / 数据库连接地址 | `sqlite:///./procurement.db` |
| `STRIPE_SECRET_KEY` | Stripe secret key for test mode / Stripe 测试模式 secret key | optional / 可选 |
| `STRIPE_PUBLISHABLE_KEY` | Stripe publishable key / Stripe publishable key | optional / 可选 |
| `LANGFUSE_PUBLIC_KEY` | Langfuse public key / Langfuse public key | optional / 可选 |
| `LANGFUSE_SECRET_KEY` | Langfuse secret key / Langfuse secret key | optional / 可选 |
| `MLFLOW_TRACKING_URI` | MLflow tracking URI / MLflow 跟踪地址 | optional / 可选 |

---

## Default Login Accounts / 默认登录账号

| Role / 角色 | Username / 用户名 | Password / 密码 |
|---|---|---|
| Administrator / 管理员 | `admin` | `admin123` |
| Consumer / 普通用户 | `user` | `user123` |

Admin users can access Dashboard, Observability, Evaluation, Traces, and RAG
Evidence.

管理员可以访问仪表盘、可观测性、评估、链路追踪和 RAG 证据页面。

Consumer users can access Chat, Products, Procurement Plan, and Orders.

普通用户可以访问聊天、商品、采购方案和订单页面。

---

## API Endpoints / API 接口

| Method / 方法 | Path / 路径 | Description / 说明 |
|---|---|---|
| `GET` | `/health` | Health check / 健康检查 |
| `POST` | `/api/chat` | Chat with procurement agent / 与采购智能体对话 |
| `POST` | `/api/chat/optimize` | Quick optimization / 快速优化 |
| `POST` | `/api/export/excel` | Export plan to Excel / 导出采购方案到 Excel |
| `GET` | `/api/products` | List or search products / 查询商品列表 |
| `GET` | `/api/products/{id}` | Product detail / 商品详情 |
| `POST` | `/api/orders` | Create order / 创建订单 |
| `GET` | `/api/orders` | List orders / 查询订单 |
| `POST` | `/api/payments/stripe/checkout` | Create Stripe checkout session / 创建 Stripe 支付会话 |
| `GET` | `/api/payments/status` | Payment status / 支付状态 |
| `GET` | `/api/history` | List procurement history / 查询采购历史 |
| `GET` | `/api/history/{id}` | Get history record / 获取历史记录 |
| `POST` | `/api/history` | Save history record / 保存历史记录 |
| `DELETE` | `/api/history/{id}` | Delete history record / 删除历史记录 |
| `GET` | `/api/observability/summary` | Observability summary / 可观测性汇总 |
| `GET` | `/api/observability/traces` | List traces / 查询链路追踪 |
| `GET` | `/api/evaluation/summary` | Evaluation summary / 评估汇总 |
| `POST` | `/api/evaluation/run-mock` | Run mock evaluation / 运行模拟评估 |
| `POST` | `/api/evaluation/run-agent` | Run agent evaluation / 运行智能体评估 |
| `GET` | `/api/llm/status` | LLM model status / 大模型状态 |
| `POST` | `/api/llm/test` | Test LLM connection / 测试大模型连接 |

---

## Mock Mode / 模拟模式

The system runs without external API keys in mock mode.

系统在 mock 模式下无需任何外部 API key 即可运行。

| Feature / 功能 | Mock Behavior / 模拟行为 |
|---|---|
| LLM / 大模型 | Deterministic rule-based intent parsing / 使用确定性规则解析意图 |
| Payment / 支付 | Returns local success URL / 返回本地成功页面链接 |
| Retrieval / 检索 | Local CSV/JSON fallback; Chroma uses Bailian embeddings if configured, otherwise hash fallback / 使用本地 CSV/JSON 兜底；配置百炼时用真实 embedding，否则用 hash embedding |
| Observability / 可观测性 | Local JSON trace files / 本地 JSON 链路日志 |
| Evaluation / 评估 | Pre-computed mock metrics / 预计算模拟指标 |

Set `USE_MOCK_LLM=true` and `USE_MOCK_PAYMENT=true` in `.env`.

在 `.env` 中设置 `USE_MOCK_LLM=true` 和 `USE_MOCK_PAYMENT=true`。

---

## Architecture / 架构

```text
Frontend (Next.js 16 + TypeScript)
前端：Next.js 16 + TypeScript
  -> HTTP REST
Backend (FastAPI)
后端：FastAPI
  -> Agent: intent parser, router, plan generator
     智能体：意图解析、路由、方案生成
  -> RAG: retriever, hybrid search, vector store, Chroma
     RAG：检索器、混合检索、向量库、Chroma
  -> Services: LLM, product, order, payment, history
     服务层：大模型、商品、订单、支付、历史记录
  -> Data: SQLite/PostgreSQL-ready models, CSV/JSON, Chroma
     数据层：SQLite/PostgreSQL-ready 模型、CSV/JSON、Chroma
```

Key external services are optional and mock-safe:

以下外部服务都是可选的，并且有 mock 兜底：

- **Alibaba Cloud Bailian (Qwen) / 阿里云百炼（通义千问）** - LLM provider with mock fallback / 大模型提供方，可回退到 mock
- **Stripe / Stripe 支付** - Test payment with mock fallback / 测试支付，可回退到模拟支付
- **Langfuse / Langfuse 可观测性** - Optional tracing / 可选链路追踪
- **MLflow / MLflow 实验跟踪** - Optional experiment tracking / 可选实验跟踪
- **Ragas / RAG 评估** - Optional RAG evaluation metrics / 可选 RAG 评估指标

---

## Demo Flow / 演示流程

1. Open `http://localhost:3000` and go to `/login` / 打开 `http://localhost:3000`，进入 `/login`
2. Login as `user` / `user123` / 使用 `user` / `user123` 登录
3. Navigate to Chat page / 进入聊天页面
4. Submit: `我们需要为20名实习生购买设备。预算在3000美元以内。每人需要键盘、鼠标和耳机。偏好高评分和快速配送。`
5. View parsed intent, retrieval evidence, and recommended plan / 查看解析意图、检索证据和推荐方案
6. Compare Plan A/B/C and select one / 对比 A/B/C 三个方案并选择一个
7. Use quick optimization buttons / 使用快捷优化按钮
8. Create Order and pay with mock Stripe / 创建订单并使用模拟 Stripe 支付
9. Save to history / 保存到历史记录
10. Login as `admin` / `admin123` to view admin dashboards / 使用 `admin` / `admin123` 登录查看管理看板

---

## Observability & Evaluation / 可观测性与评估

### Observability / 可观测性

- **Local Tracer / 本地追踪器** - Stores chat and agent traces as JSON under `data/` / 将聊天和智能体链路保存为 `data/` 下的 JSON
- **Langfuse / Langfuse** - Optional adapter enabled by `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` / 通过 `LANGFUSE_PUBLIC_KEY` 和 `LANGFUSE_SECRET_KEY` 启用的可选适配器
- **API / 接口** - `/api/observability/summary`, `/api/observability/traces`

### Evaluation / 评估

- **Mock Evaluation / 模拟评估** - Pre-computed demo metrics via `/api/evaluation/run-mock` / 通过 `/api/evaluation/run-mock` 运行预计算演示指标
- **Agent Evaluation / 智能体评估** - Runs agent against test cases via `/api/evaluation/run-agent` / 通过 `/api/evaluation/run-agent` 用测试用例评估智能体
- **Ragas / Ragas** - Optional RAG metrics; requires OpenAI API key / 可选 RAG 指标，需要 OpenAI API key
- **MLflow / MLflow** - Optional experiment tracking; requires MLflow server / 可选实验跟踪，需要 MLflow 服务
- **Business Metrics / 业务指标** - Budget compliance, inventory validity, constraint satisfaction, purchase completion / 预算合规、库存有效性、约束满足、采购完成情况

---

## Current Limitations & Future Work / 当前限制与后续工作

- Mock LLM is deterministic and does not handle complex multi-intent scenarios / 模拟大模型是确定性的，不适合复杂多意图场景
- No real user authentication; demo accounts are hardcoded / 没有真实用户认证，演示账号是硬编码的
- No persistent order storage in mock payment mode / 模拟支付模式下订单持久化能力有限
- Chroma collections are local only / Chroma 集合仅为本地模式
- Ragas and MLflow require separate server or credential setup / Ragas 和 MLflow 需要额外服务或凭证配置
- Chat responses use simulated streaming instead of real WebSocket streaming / 聊天响应使用模拟流式输出，不是真正的 WebSocket 实时流
- No production deployment configuration / 暂无生产环境部署配置

---

## License / 许可证

MIT
