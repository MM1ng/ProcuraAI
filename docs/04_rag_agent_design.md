# RAG 与 Agent 设计
# RAG And Agent Design

## 商品上下文构建
## Product Context Construction

每个商品会被转换成一段检索文本，包含商品名、品牌、品类、供应商、描述、标签、价格、评分、库存、配送天数和合规等级。本地入库脚本会把这些上下文写入忽略版本控制的 JSON fallback 索引 `data/retrieval_index.json`，并写入本地 Chroma `products` collection。

Each product is converted into a retrieval text that combines product name, brand, category, supplier, description, tags, price, rating, stock, delivery days, and compliance level. The local ingest script writes this context to the ignored JSON fallback index at `data/retrieval_index.json` and to the local Chroma `products` collection.

采购政策和供应商画像来自：

Procurement policies and supplier profiles are loaded from:

- `data/procurement_policies.json`
- `data/suppliers.json`

它们会被分别写入名为 `procurement_policies` 和 `suppliers` 的 Chroma collections。

They are ingested into separate Chroma collections named `procurement_policies` and `suppliers`.

## Embedding 与向量库
## Embeddings And Vector Store

默认向量路径使用阿里云百炼 `text-embedding-v4`，维度为 1024。商品、政策和供应商文档使用 `text_type=document` 入库，用户查询使用 `text_type=query` 生成查询向量。Chroma/vector-store 和 retriever 层共用 `embed_text()` 接口，因此大部分检索代码不需要关心具体 provider。

The default vector path uses Alibaba Cloud Bailian `text-embedding-v4` embeddings with 1024 dimensions. Product, policy, and supplier documents are embedded with `text_type=document`; user queries are embedded with `text_type=query`. The same `embed_text()` interface is used by the Chroma/vector-store and retriever layers, so most retrieval code does not need provider-specific logic.

如果缺少 `DASHSCOPE_API_KEY`，或者 embedding API 调用失败，后端会回退到本地确定性 hash embedding，并使用同样的配置维度。这保证了测试稳定性和无 key demo 能力；如果要获得生产级语义召回，需要用百炼模型重新构建 Chroma collection。

If `DASHSCOPE_API_KEY` is missing or the embedding API fails, the backend falls back to deterministic local hash embeddings using the configured dimension. This keeps tests stable and preserves a no-key demo path, but production-quality semantic recall requires rebuilding the Chroma collections with the Bailian model.

Chroma 是本地向量数据库。如果 Chroma 不可用、为空或查询异常，检索会回退到本地 JSON/CSV 搜索路径。修改 embedding 模型或维度后，需要运行 `python -m app.scripts.ingest_products`，确保文档向量和查询向量维度一致。

Chroma is used as the local vector database. If Chroma is unavailable, empty, or throws during query, retrieval falls back to the local JSON/CSV search path. After changing the embedding model or dimension, run `python -m app.scripts.ingest_products` so stored document vectors and query vectors have matching dimensions.

## 混合检索
## Hybrid Retrieval

检索流程结合以下信号：

Retrieval combines:

- 商品上下文的向量召回。
- Vector recall over product context.
- 解析并归一化后的品类过滤。
- Category filtering from parsed and normalized intent.
- 价格、评分、库存和配送天数等结构化约束。
- Structured constraints for price, rating, stock, and delivery days.
- 向量分数、RRF 分数、评分、配送速度和价格排序。
- Ranking by vector score, RRF score, rating, delivery speed, and price.

对于多品类采购请求，retriever 不再直接混合原始向量分数和 BM25 分数，而是使用 RRF 和 diversity 策略。向量召回和 BM25 召回会通过 Reciprocal Rank Fusion 融合；每个请求品类会先获得最低配额，剩余名额再按综合排序补齐。这可以避免“摄像头、耳机、扩展坞”这类请求只返回某一个强势品类。

For multi-category procurement requests, the retriever uses a hybrid RRF and diversity strategy instead of raw score merging. Vector recall and BM25 recall are fused with Reciprocal Rank Fusion, and requested categories receive a minimum quota before remaining slots are filled by the combined ranking. This avoids the common failure mode where a request for webcams, headsets, and docking stations returns only one dominant category.

如果严格结构化过滤后没有候选，retriever 会返回最佳候选，并在 retrieval evidence 中标记 `constraints_relaxed=true`，让 UI 能解释这次约束放松。

If all candidates are removed by structured filters, the retriever returns the best candidates with `constraints_relaxed=true` in retrieval evidence so the UI can explain the relaxation.

`POST /api/chat` 会返回可选的 `retrieval_evidence`：

`POST /api/chat` includes optional `retrieval_evidence`:

- `products`：商品 Top-K 摘要，包含 score、RRF score、检索通道、原因、排名和匹配字段。
- `products`: product Top-K summary with score, RRF score, retrieval channels, reason, ranks, and matched fields.
- `policies`：匹配的采购政策片段。
- `policies`: matching procurement policy snippets.
- `suppliers`：匹配的供应商画像片段。
- `suppliers`: matching supplier profile snippets.
- `constraints`：检索中应用的结构化过滤条件。
- `constraints`: structured filters applied during retrieval.
- `constraints_relaxed`：是否因为严格过滤无结果而放松约束。
- `constraints_relaxed`: whether no candidate survived strict filtering.

## 面试亮点：检索优化难点
## Interview Talking Point: Retrieval Optimization Challenge

面试中可以重点讲这个多品类 RAG 检索 bug 和优化过程。最开始我们以为问题来自 embedding，于是比较了本地 hash embedding 和 `text-embedding-v4`。但评测显示，仅替换 embedding 并没有改善最终 hybrid 指标，因为品类解析、BM25 和业务过滤主导了排序。真正的问题是结果多样性：多品类请求会被某一个品类霸榜。

A strong project difficulty to mention in interviews is the multi-category RAG retrieval bug and optimization. Replacing the local hash embedding with `text-embedding-v4` alone did not improve the final hybrid retrieval metrics, because category parsing, BM25, and business filters dominated the ranking. The real issue was result diversity: multi-category requests could be dominated by one category.

修复过程包括：用可复现脚本对比 hash 和 `text-embedding-v4`，把评测拆成 pure-vector 和 hybrid 两种模式，然后加入 RRF 融合与按品类配额选择。手动测试 `采购摄像头、耳机和扩展坞，给10名远程员工使用。` 时，又发现 BM25 的二级 bug：它先做全局 BM25 再按品类过滤，导致高分扩展坞挤掉摄像头和耳机。最终修复为在每个品类子集内单独运行 BM25，再交错合并结果。

The fix was to compare hash and `text-embedding-v4` with a repeatable evaluation script, split the benchmark into pure-vector and hybrid modes, then add RRF fusion plus per-category quota selection. During manual backend testing with `采购摄像头、耳机和扩展坞，给10名远程员工使用。`, a second bug surfaced in BM25: category search used global BM25 results and filtered afterward, so high-scoring docking stations could crowd out webcams and headsets. The fix was to run BM25 inside each category subset before interleaving results.

这个案例适合面试，因为它展示了“换模型”和“优化检索系统”的区别。可量化结果是：当前评测集上 hybrid category coverage 从 `0.5278` 提升到 `1.0000`，同时 `hit@5` 和 MRR 保持 `1.0000`。

This is a good interview example because it shows the difference between changing a model and improving a retrieval system. The measurable outcome was hybrid category coverage improving from `0.5278` to `1.0000` on the current evaluation set, while `hit@5` and MRR stayed at `1.0000`.

## 动态品类归一化
## Dynamic Category Normalization

在品类过滤前，agent 会从 `data/products.csv` 加载允许的品类列表。这样品类归一化会跟随真实商品目录，而不是写死在代码里。

Before category filtering, the agent loads allowed categories from `data/products.csv`. This keeps category normalization tied to the actual catalog instead of a fixed code-only list.

归一化顺序如下：

The normalization order is:

1. 与允许品类精确匹配。
1. Exact match against an allowed category.
2. 与允许品类做大小写不敏感匹配。
2. Case-insensitive match against an allowed category.
3. 使用稳定的中英文采购术语别名表。
3. Stable multilingual aliases for common procurement terms.
4. 对接近的英文变体做保守字符串相似度匹配。
4. Conservative string similarity for close English variants.
5. 可选使用 LLM 做品类选择，但必须限制在允许品类内。
5. Optional LLM category selection, constrained to the allowed categories.

如果置信度低，系统会保留原始品类并在 parsed intent 中加入 warning，避免静默映射到错误目录品类。

When confidence is low, the original category is preserved and the parsed intent includes a warning. This avoids silently mapping an unknown request to the wrong catalog category.

每个 parsed intent 可以包含以下 trace 字段：

Each parsed intent can include trace data:

- `original_category`
- `normalized_category`
- `normalization_method`
- `allowed_categories`
- `warning`

例如中文请求中的 `显示器` 会在检索前归一化为 `Monitor`，因此结构化品类过滤可以匹配商品目录中的 Monitor 行。

For example, the Chinese request category `显示器` normalizes to `Monitor` before retrieval, so the structured category filter can match the Monitor rows in the catalog.

## Agent 工具
## Agent Tools

工作流包含以下工具式函数：

The workflow includes tool-style functions:

- `parse_purchase_request`
- `search_products`
- `filter_products_by_constraints`
- `check_inventory`
- `calculate_budget`
- `generate_procurement_plan`
- `generate_plan_options`
- `create_order`
- `create_stripe_checkout`
- `log_observability_event`
- `evaluate_response_mock`

## qwen-turbo LLM 策略
## qwen-turbo LLM Strategy

后端通过 `app.services.llm_service.safe_llm_invoke` 使用 `langchain_community.llms.tongyi.Tongyi` 和 `settings.QWEN_MODEL`。创建 Tongyi 模型前，会从环境读取 `DASHSCOPE_API_KEY` 并写入 `os.environ["DASHSCOPE_API_KEY"]`。

The backend uses `langchain_community.llms.tongyi.Tongyi` with `settings.QWEN_MODEL` through `app.services.llm_service.safe_llm_invoke`. `DASHSCOPE_API_KEY` is read from the environment and copied into `os.environ["DASHSCOPE_API_KEY"]` before creating the Tongyi model.

qwen-turbo 负责：

qwen-turbo is used for:

- 从自然语言采购请求中抽取结构化 JSON 意图。
- Purchase intent extraction from natural language into structured JSON.
- 只基于已检索商品和已计算采购方案生成自然语言推荐解释。
- Natural language recommendation explanation based only on retrieved products and the calculated procurement plan.
- 通过 agent response path 生成多轮采购回复，并把 provider metadata 返回给 chat API。
- Multi-turn procurement response generation through the agent response path, with provider metadata returned to the chat API.

检索、库存校验、预算计算和商品选择都保持在确定性代码中。qwen-turbo 不允许编造商品、价格、库存、供应商、配送天数、评分或折扣，只负责解释后端已经检索和计算出的数据。

Retrieval, inventory validation, budget calculation, and product selection stay deterministic in code. qwen-turbo is not allowed to invent products, prices, stock, suppliers, delivery days, ratings, or discounts; it only explains data already retrieved and calculated by the backend.

当 `USE_MOCK_LLM=true`，或者缺少 `DASHSCOPE_API_KEY`，或者 Tongyi 调用失败时，服务会回退到 mock-safe 输出。此时意图解析使用规则解析器，方案解释使用本地模板，因此 demo 仍然可复现。

When `USE_MOCK_LLM=true`, or when `DASHSCOPE_API_KEY` is missing or Tongyi raises an error, the service falls back to mock-safe output. Intent parsing then uses the rule-based parser, and plan explanation uses the local template, so the demo remains reproducible.

## 方案对比
## Compare Plans

v2 的方案对比层是增量能力。原有 `recommended_plan` 字段继续保留以兼容 v1，同时 agent 还会返回 `plan_options`。

The v2 plan comparison layer is additive. The original calculated `recommended_plan` remains available for backward compatibility, while the agent also returns `plan_options`.

- `plan_a`：成本优先。
- `plan_a`: cost optimized.
- `plan_b`：均衡方案。
- `plan_b`: balanced.
- `plan_c`：高端方案。
- `plan_c`: premium.

每个方案使用同一批检索结果和同一个 parsed intent。策略层会在每个品类中选择不同的合格商品，然后复用确定性的采购方案计算逻辑，确保总价、预算状态、库存状态和约束满足情况一致。

Each option uses the same retrieved product set and the same parsed intent. The strategy layer selects different eligible products per category, then reuses the deterministic procurement plan calculation so totals, budget status, inventory status, and constraint satisfaction are computed consistently.

默认优先选择预算内的 `plan_b`。如果 `plan_b` 超出预算且其他方案在预算内，后端会选择最低成本的预算安全方案作为默认 `recommended_plan`。前端切换方案只改变当前展示和后续操作目标，不会修改商品目录、检索结果或 session parsing。

`plan_b` is preferred by default when it is within budget. If it exceeds the user's budget and another option is budget-safe, the backend selects the lowest-cost within-budget option as the default `recommended_plan`. The frontend selection only changes the currently displayed plan and downstream actions; it does not mutate the catalog, retrieval results, or session parsing.
