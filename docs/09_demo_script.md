# 演示脚本
# Demo Script

1. 启动后端：
1. Start the backend:

   ```powershell
   cd backend
   .venv\Scripts\activate
   uvicorn main:app --reload --port 8000
   ```

2. 启动前端：
2. Start the frontend:

   ```powershell
   cd frontend
   npm run dev
   ```

3. 打开 `GET http://localhost:8000/api/llm/status`，展示以下状态：
3. Open `GET http://localhost:8000/api/llm/status` and show:

   ```json
   {
     "llm_provider": "tongyi",
     "model_name": "qwen-turbo",
     "has_api_key": true,
     "use_mock_llm": false
   }
   ```

4. 使用下面的请求测试 `POST http://localhost:8000/api/llm/test`：
4. Open `POST http://localhost:8000/api/llm/test` with:

   ```json
   {
     "message": "你是谁呀能做什么？"
   }
   ```

   展示 qwen-turbo 返回内容，并且 `used_mock_llm=false`。

   Show that qwen-turbo returns content with `used_mock_llm=false`.

5. 打开 `http://localhost:3000/chat`。
5. Open `http://localhost:3000/chat`.

6. 提交下面的采购请求：
6. Submit:

   ```text
   We need to buy equipment for 20 interns. Budget is under $3000. Each person needs a keyboard, mouse and headset. Prefer high rating and fast delivery.
   ```

7. 展示 `/api/chat` 返回 `model_provider="tongyi"`、`model_name="qwen-turbo"`，以及 `used_mock_llm=false`。
7. Show `/api/chat` returns `model_provider="tongyi"`, `model_name="qwen-turbo"`, and `used_mock_llm=false`.

8. 解释 `parsed_intent.used_llm_parser=true` 表示 qwen-turbo 参与了解析采购意图 JSON。
8. Explain that `parsed_intent.used_llm_parser=true` means qwen-turbo parsed the purchase intent JSON.

9. 展示 RAG 检索到的商品和计算出的采购方案，包括预算状态、库存状态、选中商品和推荐理由。
9. Show RAG retrieved products and the calculated procurement plan, including budget status, inventory status, selected items, and recommendation rationale.

10. 打开 observability trace，展示 qwen-turbo 调用链路中记录的 `model_provider`、`model_name`、`used_mock_llm`、`llm_error` 和 `latency_ms`。
10. Open the observability trace and show `model_provider`, `model_name`, `used_mock_llm`, `llm_error`, and `latency_ms` recorded for the qwen-turbo call path.

11. 点击 `Create Order`，然后点击 `Pay with Stripe`。
11. Click `Create Order`, then `Pay with Stripe`.

12. 打开 Products、Orders、Observability 和 Evaluation 页面。
12. Open Products, Orders, Observability, and Evaluation pages.

13. 在 Evaluation 页面运行 Agent Evaluation，展示真实 agent 回答和检索上下文生成的指标；只有在需要确定性兜底演示时才使用 Mock Evaluation。
13. Run Agent Evaluation from the Evaluation page to show metrics generated from real agent answers and retrieved product contexts. Use Mock Evaluation only when a deterministic fallback demo is needed.

14. 如果被问到系统中最难的优化点，展示多品类 RAG 检索案例：
14. If asked about the hardest system optimization, show the multi-category RAG retrieval case:

    ```text
    采购摄像头、耳机和扩展坞，给10名远程员工使用。
    ```

    说明单纯把 hash embeddings 换成 `text-embedding-v4` 并没有改善最终 hybrid 指标。真正的修复是 RRF 融合、按品类配额选择，以及修复 BM25 bug：BM25 需要在每个请求品类的商品子集内检索。这个优化把当前评测集上的 hybrid category coverage 从 `0.5278` 提升到 `1.0000`。

    Explain that simply replacing hash embeddings with `text-embedding-v4` did not improve final hybrid metrics. The real fix was RRF fusion plus per-category quota selection, and a BM25 bug fix that runs search inside each requested category subset. This raised hybrid category coverage from `0.5278` to `1.0000` in the current evaluation set.
