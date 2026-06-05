# Backend

FastAPI service for Enterprise Procurement Agent.

## Setup

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m app.scripts.generate_products
python -m app.scripts.seed_db
python -m app.scripts.ingest_products
python -m app.scripts.run_mock_evaluation
uvicorn main:app --reload --port 8000
```

## Tests

```powershell
cd backend
pytest
```

## Main Endpoints

- `GET /health`
- `GET /api/products`
- `POST /api/chat`
- `GET /api/llm/status`
- `POST /api/llm/test`
- `POST /api/procurement/plan`
- `POST /api/orders`
- `POST /api/payments/create-checkout-session`
- `GET /api/payments/status`
- `GET /api/observability/summary`
- `GET /api/evaluation/summary`
- `POST /api/evaluation/run-agent`

The default path uses CSV and JSON fallback files so the demo works without
Alibaba Cloud, OpenAI, Stripe, Langfuse, Ragas, or MLflow credentials.

## Connect Alibaba Cloud qwen3.7-max With LangChain Tongyi

Install dependencies:

```powershell
cd backend
pip install -r requirements.txt
```

Configure `backend/.env` or the project root `.env`:

```text
LLM_PROVIDER=tongyi
USE_MOCK_LLM=false
DASHSCOPE_API_KEY=your_alibaba_cloud_bailian_api_key
QWEN_MODEL=qwen3.7-max
QWEN_TOP_P=0.8
QWEN_MAX_TOKENS=2000
```

Test qwen3.7-max:

```powershell
python -m app.scripts.test_qwen_call
```

Start the backend:

```powershell
uvicorn main:app --reload --port 8000
```

Check the LLM endpoints:

```text
GET http://localhost:8000/api/llm/status
POST http://localhost:8000/api/llm/test
```

Use this AI Chat prompt:

```text
We need to buy equipment for 20 interns. Budget is under $3000. Each person needs a keyboard, mouse and headset. Prefer high rating and delivery within 5 days.
```

Confirm `/api/chat` returns:

```json
{
  "model_provider": "tongyi",
  "model_name": "qwen3.7-max",
  "used_mock_llm": false
}
```

`USE_MOCK_LLM=true` does not call qwen3.7-max. Missing `DASHSCOPE_API_KEY` also uses mock fallback. Never commit `.env` to GitHub. `qwen3.7-max` is the default model. If `used_mock_llm=true`, the response did not come from a real qwen3.7-max call.
