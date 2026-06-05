# Demo Script

1. Start the backend:

   ```powershell
   cd backend
   .venv\Scripts\activate
   uvicorn main:app --reload --port 8000
   ```

2. Start the frontend:

   ```powershell
   cd frontend
   npm run dev
   ```

3. Open `GET http://localhost:8000/api/llm/status` and show:

   ```json
   {
     "llm_provider": "tongyi",
     "model_name": "qwen3.7-max",
     "has_api_key": true,
     "use_mock_llm": false
   }
   ```

4. Open `POST http://localhost:8000/api/llm/test` with:

   ```json
   {
     "message": "你是谁呀能做什么？"
   }
   ```

   Show that qwen3.7-max returns content with `used_mock_llm=false`.

5. Open `http://localhost:3000/chat`.

6. Submit:

   ```text
   We need to buy equipment for 20 interns. Budget is under $3000. Each person needs a keyboard, mouse and headset. Prefer high rating and fast delivery.
   ```

7. Show `/api/chat` returns `model_provider="tongyi"`, `model_name="qwen3.7-max"`,
   and `used_mock_llm=false`.

8. Explain that `parsed_intent.used_llm_parser=true` means qwen3.7-max parsed the
   purchase intent JSON.

9. Show RAG retrieved products and the calculated procurement plan, including
   budget status, inventory status, selected items, and recommendation
   rationale.

10. Open the observability trace and show `model_provider`, `model_name`,
    `used_mock_llm`, `llm_error`, and `latency_ms` recorded for the qwen3.7-max
    call path.

11. Click `Create Order`, then `Pay with Stripe`.

12. Open Products, Orders, Observability, and Evaluation pages.

13. Run Agent Evaluation from the Evaluation page to show metrics generated
    from real agent answers and retrieved product contexts. Use Mock Evaluation
    only when a deterministic fallback demo is needed.
