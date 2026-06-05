# Observability Design

Each agent run records:

- Session and trace IDs.
- User query.
- Parsed intent.
- Retrieved products.
- Selected products.
- Final answer.
- LLM provider metadata: `model_provider`, `model_name`, `used_mock_llm`, and
  `llm_error`.
- Tool calls and statuses.
- Latency in milliseconds.
- Errors and payment status when available.

Local traces are stored in `data/observability_logs.json`, and the dashboard
reads summary and trace endpoints from FastAPI. If Langfuse credentials are
configured, the `LangfuseClient` adapter can forward trace metadata to
Langfuse.

Dashboard metrics include total conversations, average latency, tool call
success rate, retrieval success rate, payment success rate, error rate, recent
traces, latency trend, and tool call distribution.

For qwen3.7-max runs, `used_mock_llm=false` indicates a real Tongyi call returned
successfully. If `used_mock_llm=true`, the trace explains the fallback reason in
`llm_error`, such as missing `DASHSCOPE_API_KEY`, `USE_MOCK_LLM=true`, or a
Tongyi runtime error. The existing `latency_ms` field captures total agent
latency for the parsing, retrieval, planning, LLM explanation, and logging path.
