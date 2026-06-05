# ProcuraAI

**Enterprise Procurement Agent** — powered by Agentic RAG and LLMs.

An intelligent procurement assistant that understands natural language purchase requests, retrieves relevant products, generates optimized procurement plans, creates orders, and handles mock or real Stripe payments — all through a conversational interface.

**Current Stable Version:** v1.0.0

---

## Features

- **Intelligent Procurement Recommendation** — Parses natural language purchase requests and recommends optimal products
- **Agentic RAG** — Hybrid search combining vector retrieval with structured filtering (category, price, rating, stock, delivery)
- **Multi-turn Memory** — Maintains session context across conversation turns for coherent multi-step procurement
- **Qwen3.7-Max & Qwen-Max Support** — Seamless integration with Alibaba Cloud Tongyi LLMs via LangChain
- **Mock LLM Fallback** — Works out-of-the-box without any API keys using deterministic rule-based fallback
- **Supplier Comparison** — Ranks products by rating, price, and delivery speed
- **Budget Optimization** — Intelligently allocates budget across requested items within constraints
- **Order Management** — Full order lifecycle from creation to payment
- **Stripe Payment Integration** — Test mode and mock mode checkout
- **Observability Dashboard** — Local trace logging with optional Langfuse adapter
- **Evaluation Dashboard** — Business metrics, RAG metrics, and system health monitoring
- **Multi-language UI** — Built with Next.js + Ant Design + Recharts

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Frontend (Next.js)                  │
│  Chat │ Products │ Orders │ Payment │ Observability │
└──────────────────────┬──────────────────────────────┘
                       │ HTTP/REST
┌──────────────────────▼──────────────────────────────┐
│                 Backend (FastAPI)                     │
│  ┌─────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │  Agent  │ │   RAG    │ │     Services         │ │
│  │ Intent  │ │Hybrid    │ │  LLM │ Order │ Payment│ │
│  │ Parser  │ │Search    │ │  Product │ Dashboard │ │
│  │ Planner │ │Retriever │ │  Stripe              │ │
│  └─────────┘ └──────────┘ └──────────────────────┘ │
│  ┌─────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │Observab.│ │Evaluation│ │     Database         │ │
│  │ Tracing │ │Metrics   │ │  SQLite / PostgreSQL │ │
│  │ Langfuse│ │Ragas/MLfl│ │  CSV / JSON Data     │ │
│  └─────────┘ └──────────┘ └──────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, TypeScript, Ant Design, Recharts |
| Backend | FastAPI, Python 3.12+, SQLAlchemy, Pydantic |
| Agent | LangChain, Custom Intent Parser, Plan Generator |
| RAG | Hybrid Search (BM25 + Structured Filters) |
| Database | SQLite (dev), PostgreSQL-ready models |
| Payment | Stripe SDK + Mock Mode |
| Observability | Local JSON traces, Langfuse adapter |
| Evaluation | Mock metrics, Ragas extension, MLflow adapter |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- npm or yarn

### Environment Setup

```bash
# 1. Clone the repository
git clone https://github.com/MM1ng/ProcuraAI.git
cd ProcuraAI

# 2. Backend setup
cd backend
python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

```bash
# 3. Set up environment variables
cp .env.example .env
# Edit .env and add your API keys (optional — mock mode works without any)

# 4. Initialize data
python -m app.scripts.generate_products
python -m app.scripts.seed_db
python -m app.scripts.ingest_products
```

```bash
# 5. Frontend setup
cd ../frontend
npm install
```

### Run Project

Start the backend (from `backend/`):

```bash
uvicorn main:app --reload --port 8000
```

In a new terminal, start the frontend (from `frontend/`):

```bash
npm run dev
```

Open **http://localhost:3000** and navigate to the Chat page.

### Verify

```bash
curl http://localhost:8000/health
```

### Test the Chat

Submit a natural language procurement request:

> "We need to buy equipment for 20 interns. Budget is under $3000. Each person needs a keyboard, mouse and headset. Prefer high rating and delivery within 5 days."

## Mock Mode

ProcuraAI runs **without any external API keys** in mock mode:

| Feature | Mock Behavior |
|---------|--------------|
| LLM | Deterministic rule-based intent parsing |
| Payment | Returns local success URL |
| Retrieval | Local product CSV and JSON index |
| Observability | Local JSON trace files |
| Evaluation | Pre-computed mock metrics |

Set `USE_MOCK_LLM=true` and `USE_MOCK_PAYMENT=true` in `.env`.

## Connect Qwen LLM

To use qwen3.7-max via Alibaba Cloud Bailian:

```bash
# Configure .env
LLM_PROVIDER=tongyi
USE_MOCK_LLM=false
DASHSCOPE_API_KEY=your_api_key_here
QWEN_MODEL=qwen3.7-max

# Test the connection
python -m app.scripts.test_qwen_call
```

## Data

- **375 products** across 15 procurement categories in `data/products.csv`
- **Retrieval index** built by `ingest_products.py` into `data/retrieval_index.json`
- **Mock evaluation logs** and **observability traces** in `data/`

## Tests

```bash
cd backend
pytest
```

Covers intent parsing, hybrid search, budget rules, and order creation.

## Project Structure

```
ProcuraAI/
├── backend/            # FastAPI application
│   ├── app/
│   │   ├── agent/      # Intent parsing, plan generation, procurement agent
│   │   ├── api/        # REST endpoints (chat, products, orders, payments)
│   │   ├── core/       # Config, database, logging
│   │   ├── evaluation/ # Evaluation metrics & runners
│   │   ├── models/     # SQLAlchemy ORM models
│   │   ├── observability/ # Tracing & Langfuse integration
│   │   ├── rag/        # Hybrid search, vector store, retriever
│   │   ├── schemas/    # Pydantic request/response schemas
│   │   ├── scripts/    # Data generation & ingestion scripts
│   │   └── services/   # Business logic (LLM, order, payment, product)
│   ├── tests/          # Pytest suite
│   └── main.py         # FastAPI entry point
├── frontend/           # Next.js application
│   ├── app/            # App router pages
│   │   ├── chat/       # AI Chat procurement interface
│   │   ├── products/   # Product catalog
│   │   ├── orders/     # Order management
│   │   ├── payment/    # Payment flow
│   │   ├── procurement/ # Procurement plans
│   │   ├── evaluation/ # Evaluation dashboard
│   │   └── observability/ # Observability dashboard
│   ├── components/     # Reusable React components
│   ├── lib/            # Utility functions
│   └── styles/         # CSS and theme
├── data/               # Product data, retrieval index, logs
├── docs/               # Design documents & course reports
├── docker-compose.yml  # Docker orchestration
└── .env.example        # Environment template
```

## Roadmap

- [x] **v1.0.0** — Core procurement agent with RAG, chat, orders, and payments
- [ ] **v1.1.0** — PostgreSQL production readiness, Docker optimization
- [ ] **v1.2.0** — Real LLM RAG evaluation, advanced agent workflows
- [ ] **v1.3.0** — Multi-tenant support, user authentication
- [ ] **v2.0.0** — Production deployment with monitoring, CI/CD pipeline

## License

MIT — see [LICENSE](LICENSE) for details.
