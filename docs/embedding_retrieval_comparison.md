# 向量检索对比报告
# Embedding Retrieval Comparison

本文档对比原始本地哈希向量检索路径和阿里云百炼 `text-embedding-v4` 模型。

This report compares the original local hash embedding retrieval path with the Alibaba Cloud Bailian `text-embedding-v4` model.

## 方法
## Method

对比脚本如下：

The comparison script is:

```powershell
cd backend
python -m app.scripts.compare_embeddings
```

脚本会在 `data/embedding_eval/<run_id>/` 下构建临时 Chroma 索引，并用同一组六条采购检索用例分别评估不同 embedding provider。

It builds temporary Chroma indexes under `data/embedding_eval/<run_id>/` and evaluates the same six procurement retrieval cases against each embedding provider.

指标说明：

Metrics:

- `hit@5`：Top 5 中是否至少出现一个期望品类。
- `hit@5`: whether at least one expected category appears in the top five.
- `MRR`：第一个期望品类命中的倒数排名。
- `MRR`: reciprocal rank of the first expected-category hit.
- `category_coverage`：Top 5 中覆盖的期望品类占比。
- `category_coverage`: share of expected categories represented in the top five.
- `unique_categories_returned`：Top 5 中实际返回的唯一品类。
- `unique_categories_returned`: distinct categories in the top five.
- `missing_categories`：Top 5 中缺失的期望品类。
- `missing_categories`: expected categories absent from the top five.
- `avg_latency_ms`：临时索引构建完成后的平均检索延迟。
- `avg_latency_ms`: average retrieval latency after the temporary index has been built.

Tongyi 评测会启用 `EMBEDDING_STRICT=true`，避免百炼调用失败时静默回退到本地哈希，并被误判为 Tongyi 结果。

The script uses `EMBEDDING_STRICT=true` for the Tongyi run. This prevents a failed Bailian call from silently falling back to local hash embeddings and being misreported as a Tongyi result.

## 当前结果
## Current Result

最新结果文件：

Latest result file:

```text
data/embedding_retrieval_comparison.json
```

哈希纯向量检索：

Hash pure vector:

```text
hit@5 = 1.0000
MRR = 1.0000
category_coverage = 0.6944
avg_latency_ms = 671.21
```

RRF + 品类配额优化后的哈希混合检索：

Hash hybrid after RRF + category quota:

```text
hit@5 = 1.0000
MRR = 1.0000
category_coverage = 1.0000
avg_latency_ms = 1542.57
```

Tongyi `text-embedding-v4` 纯向量检索：

Tongyi `text-embedding-v4` pure vector:

```text
hit@5 = 1.0000
MRR = 1.0000
category_coverage = 0.6944
avg_latency_ms = 654.26
```

RRF + 品类配额优化后的 Tongyi `text-embedding-v4` 混合检索：

Tongyi `text-embedding-v4` hybrid after RRF + category quota:

```text
hit@5 = 1.0000
MRR = 1.0000
category_coverage = 1.0000
avg_latency_ms = 1509.86
```

## 解读
## Interpretation

优化后的混合检索在当前六条评测用例上，将品类覆盖率从之前的 `0.5278` 提升到 `1.0000`。提升主要来自 RRF 融合和按品类配额选择，而不是单纯更换 embedding 后端。

The optimized hybrid retriever improves category coverage from the previous baseline of `0.5278` to `1.0000` on the six-case evaluation set. The gain comes from RRF fusion plus per-category quota selection, not from changing the embedding backend alone.

纯向量检索中，哈希和 `text-embedding-v4` 的品类覆盖率都只有 `0.6944`，说明仅靠向量召回仍不足以保证多品类请求的覆盖，需要额外的 diversity 层。

Pure vector retrieval still reaches only `0.6944` category coverage for both hash and `text-embedding-v4`, which shows why the diversity layer is needed.

优化后的混合检索已经能覆盖全部请求品类，包括中文请求中的摄像头、耳机和扩展坞。

The hybrid path now covers all requested categories, including the Chinese request for webcams, headsets, and docking stations.

在当前小规模评测集上，哈希和 `text-embedding-v4` 的顶层质量指标仍然一致。现有证据说明真正有效的提升来自检索策略，而不是 embedding 模型替换本身；后续需要用更大、更偏语义改写的评测集继续验证 embedding 模型差异。

The top-level quality metrics remain identical between hash and `text-embedding-v4` on this small dataset. The current evidence says the retrieval strategy change is the meaningful improvement; the embedding model choice should be evaluated further with a larger paraphrase-heavy dataset.

## 完成标准
## Expected Completion Criteria

当前评测设置下，本次对比已经完成，原因如下：

This comparison is complete for the current evaluation setup because:

1. `data/embedding_retrieval_comparison.json` 中，`hash` 和 `tongyi` 都在 `pure_vector` 与 `hybrid` 模式下包含非空 `rows`。
1. `data/embedding_retrieval_comparison.json` contains non-empty `rows` for both `hash` and `tongyi` in both `pure_vector` and `hybrid` modes.
2. `tongyi` provider 没有 `error` 字段。
2. The `tongyi` provider has no `error` field.
3. 汇总表同时对比了两个 provider、两种模式下的 `hit@5`、`MRR`、`category_coverage` 和 latency。
3. The summary table compares `hit@5`, `MRR`, `category_coverage`, and latency for both providers and modes.

后续可继续实验：

Good next experiments:

- 将评测集从六条扩展到更多样本，并加入更多语义改写类查询，让 embedding 差异更容易体现。
- Increase the evaluation set beyond six examples and include paraphrase cases where semantic embedding should matter more than category parsing.
- 当候选集规模变大后，在 RRF 后增加 reranker。
- Add a reranker after RRF when the candidate set grows larger.
