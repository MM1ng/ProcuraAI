from __future__ import annotations

import csv
import json
import math
import time
from datetime import datetime, timezone
from typing import Any

from app.agent.procurement_agent import run_procurement_agent
from app.core.config import DATA_DIR
from app.evaluation.agent_eval_runner import _context_from_product
from app.evaluation.business_metrics import calculate_business_metrics
from app.evaluation.mock_eval_runner import QUESTIONS_FILE
from app.rag.embeddings import embed_text, embed_texts
from app.services.llm_service import safe_llm_invoke, settings

try:
    from langchain_core.embeddings import Embeddings
except Exception:
    Embeddings = object


RAGAS_EVAL_FILE = DATA_DIR / "ragas_evaluation_logs.json"
RAGAS_METRIC_FIELDS = [
    "faithfulness",
    "answer_relevancy",
    "answer_correctness",
    "context_precision",
    "context_recall",
    "budget_compliance_aspect",
    "category_coverage",
    "constraint_adherence",
]

PROCUREMENT_ASPECTS = [
    {
        "name": "budget_compliance_aspect",
        "definition": (
            "Does the procurement plan stay within the stated budget? Score 1 if total cost is "
            "under budget or budget is not specified, 0 if over budget."
        ),
    },
    {
        "name": "category_coverage",
        "definition": (
            "Does the answer cover all product categories mentioned in the user's request? "
            "Score 1 if all requested categories are addressed, proportional if partial."
        ),
    },
    {
        "name": "constraint_adherence",
        "definition": (
            "Does the plan respect explicit constraints on rating minimum and delivery time maximum? "
            "Score 1 if all constraints met, proportional if partial."
        ),
    },
]


class RagasMockLLMSkipped(RuntimeError):
    """Raised when DashScope falls back to the local mock LLM during judging."""


class DashScopeRagasLLM:
    """Small RAGAS LLM adapter backed by the project's safe DashScope caller."""

    def generate(self, prompts: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            from langchain_core.outputs import Generation, LLMResult
        except Exception:
            Generation = None
            LLMResult = None

        prompt_list = prompts if isinstance(prompts, list) else [prompts]
        generations = []
        for prompt in prompt_list:
            content = self._invoke(_prompt_to_text(prompt))
            if Generation is None:
                generations.append([{"text": content}])
            else:
                generations.append([Generation(text=content)])

        if LLMResult is None:
            return {"generations": generations}
        return LLMResult(generations=generations)

    def _invoke(self, prompt: str) -> str:
        result = safe_llm_invoke(prompt, purpose="ragas_judge", language="en")
        if result.get("used_mock_llm"):
            raise RagasMockLLMSkipped("RAGAS judge used mock LLM; skipping evaluation.")
        return str(result.get("content") or "")


class TongyiRagasEmbeddings(Embeddings):
    """RAGAS embeddings adapter backed by DashScope text-embedding-v4."""

    def __init__(self) -> None:
        self.run_config = None

    def set_run_config(self, run_config: Any) -> None:
        self.run_config = run_config

    def embed_query(self, text: str) -> list[float]:
        return embed_text(text, text_type="query")

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return embed_texts(texts, text_type="document")

    async def aembed_query(self, text: str) -> list[float]:
        return self.embed_query(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.embed_documents(texts)

    async def embed_text(self, text: str, is_async: bool = True) -> list[float]:
        return self.embed_query(text)

    async def embed_texts(self, texts: list[str], is_async: bool = True) -> list[list[float]]:
        return self.embed_documents(texts)


def _prompt_to_text(prompt: Any) -> str:
    if hasattr(prompt, "to_string"):
        return str(prompt.to_string())
    if hasattr(prompt, "to_messages"):
        return "\n".join(str(getattr(message, "content", message)) for message in prompt.to_messages())
    if isinstance(prompt, list):
        return "\n".join(str(getattr(message, "content", message)) for message in prompt)
    return str(prompt)


def _build_chat_model() -> Any:
    try:
        from langchain_core.callbacks import CallbackManagerForLLMRun
        from langchain_core.language_models.chat_models import BaseChatModel
        from langchain_core.messages import AIMessage, BaseMessage
        from langchain_core.outputs import ChatGeneration, ChatResult
    except Exception:
        return DashScopeRagasLLM()

    class DashScopeSafeChatModel(BaseChatModel):
        @property
        def _llm_type(self) -> str:
            return "dashscope-safe-llm-invoke"

        def _generate(
            self,
            messages: list[BaseMessage],
            stop: list[str] | None = None,
            run_manager: CallbackManagerForLLMRun | None = None,
            **kwargs: Any,
        ) -> ChatResult:
            prompt = "\n".join(str(message.content) for message in messages)
            result = safe_llm_invoke(prompt, purpose="ragas_judge", language="en")
            if result.get("used_mock_llm"):
                raise RagasMockLLMSkipped("RAGAS judge used mock LLM; skipping evaluation.")
            message = AIMessage(content=str(result.get("content") or ""))
            return ChatResult(generations=[ChatGeneration(message=message)])

    return DashScopeSafeChatModel()


def _read_question_rows() -> list[dict[str, str]]:
    if not QUESTIONS_FILE.exists():
        return []
    with QUESTIONS_FILE.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [
            {
                "question": row.get("question", "").strip(),
                "ground_truth": row.get("ground_truth", "").strip(),
                "depends_on": row.get("depends_on", "").strip(),
            }
            for row in reader
            if row.get("question")
        ]


def _single_turn_sample(question: str, answer: str, contexts: list[str], ground_truth: str) -> Any:
    try:
        from ragas import SingleTurnSample
    except Exception:
        return {
            "user_input": question,
            "response": answer,
            "retrieved_contexts": contexts,
            "reference": ground_truth,
        }

    try:
        return SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=contexts,
            reference=ground_truth,
        )
    except TypeError:
        return SingleTurnSample(
            question=question,
            answer=answer,
            contexts=contexts,
            ground_truth=ground_truth,
        )


def _plan_item_context(item: dict[str, Any]) -> str:
    product_like = dict(item)
    if product_like.get("price") is None and item.get("unit_price") is not None:
        product_like["price"] = item.get("unit_price")
    context = _context_from_product(product_like)
    extras = []
    if item.get("quantity") is not None:
        extras.append(f"quantity {item.get('quantity')}")
    if item.get("subtotal") is not None:
        extras.append(f"subtotal ${_format_context_money(item.get('subtotal'))}")
    if item.get("supplier"):
        extras.append(f"supplier {item.get('supplier')}")
    if extras:
        context = f"{context} | {' | '.join(extras)}"
    return context


def _format_context_money(value: Any) -> str:
    try:
        return f"{float(value):g}"
    except (TypeError, ValueError):
        return str(value)


def _plan_metadata_context(plan: dict[str, Any], label: str = "Plan metadata") -> str:
    return (
        f"{label}: "
        f"total_amount=${plan.get('total_amount')}, "
        f"budget_status={plan.get('budget_status')}, "
        f"inventory_status={plan.get('inventory_status')}, "
        f"constraint_satisfaction={plan.get('constraint_satisfaction')}, "
        f"avg_rating={plan.get('avg_rating')}"
    )


def _previous_plan_contexts(previous_plan: dict[str, Any] | None) -> list[str]:
    if not previous_plan:
        return []
    contexts = [_plan_metadata_context(previous_plan, label="Previous plan metadata")]
    contexts.extend(
        f"Previous plan item: {_plan_item_context(item)}"
        for item in previous_plan.get("items") or []
    )
    return contexts


def _intent_summary_context(intent: dict[str, Any] | None) -> str | None:
    if not intent:
        return None
    parts: list[str] = []
    if intent.get("people_count") is not None:
        parts.append(f"people_count={intent.get('people_count')}")
    categories = intent.get("categories") or []
    if categories:
        parts.append("categories=" + ", ".join(str(category) for category in categories))
    if intent.get("budget") is not None:
        parts.append(f"budget=${_format_context_money(intent.get('budget'))}")
    quantities = intent.get("quantity_per_category") or {}
    if quantities:
        quantity_text = ", ".join(
            f"{category}:{quantity}" for category, quantity in quantities.items()
        )
        parts.append(f"quantity_per_category={quantity_text}")
    if intent.get("min_rating") is not None:
        parts.append(f"min_rating={intent.get('min_rating')}")
    if intent.get("max_delivery_days") is not None:
        parts.append(f"max_delivery_days={intent.get('max_delivery_days')}")
    if intent.get("revision_intent"):
        parts.append(f"revision_intent={intent.get('revision_intent')}")
    if not parts:
        return None
    return "Intent summary: " + ", ".join(parts)


def _plan_options_context(result: dict[str, Any], plan: dict[str, Any]) -> str | None:
    plan_options = result.get("plan_options") or []
    count = int(plan.get("plan_options_count") or len(plan_options) or 0)
    if count <= 0:
        return None

    blocked_count = 0
    for option in plan_options:
        option_plan = option.get("plan") or {}
        if option_plan.get("budget_status") == "over_budget" or option_plan.get("selectable") is False:
            blocked_count += 1
    executable_count = max(0, count - blocked_count)
    return (
        f"Plan options: {count} candidate plans generated. "
        f"{executable_count} plans within budget, {blocked_count} plans over budget."
    )


def _evaluate_ragas_samples(samples: list[Any], llm: Any | None = None) -> list[dict[str, float]]:
    from ragas import EvaluationDataset, evaluate
    from ragas.metrics import (
        AspectCritic,
        answer_correctness,
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    dataset = EvaluationDataset(samples=samples)
    chat_model = llm or _build_chat_model()
    llm_type = getattr(chat_model, "_llm_type", "unknown")
    print(f"RAGAS judge LLM: {llm_type} (type={type(chat_model).__name__})")
    embeddings = TongyiRagasEmbeddings()
    aspect_metrics = [
        AspectCritic(name=aspect["name"], definition=aspect["definition"])
        for aspect in PROCUREMENT_ASPECTS
    ]

    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            answer_correctness,
            context_precision,
            context_recall,
            *aspect_metrics,
        ],
        llm=chat_model,
        embeddings=embeddings,
    )

    if hasattr(result, "to_pandas"):
        frame = result.to_pandas()
        return [
            {field: _float_or_none(record.get(field)) for field in RAGAS_METRIC_FIELDS}
            for record in frame.to_dict(orient="records")
        ]
    if isinstance(result, dict):
        length = max((len(value) for value in result.values() if isinstance(value, list)), default=1)
        return [
            {
                field: _float_or_none(
                    result.get(field, [None] * length)[index]
                    if isinstance(result.get(field), list)
                    else result.get(field)
                )
                for field in RAGAS_METRIC_FIELDS
            }
            for index in range(length)
        ]
    return [{field: None for field in RAGAS_METRIC_FIELDS} for _ in samples]


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None:
            return None
        numeric = float(value)
        if math.isnan(numeric):
            return None
        return round(numeric, 3)
    except (TypeError, ValueError):
        return None


def _row_from_agent_result(
    index: int,
    question: str,
    ground_truth: str,
    result: dict[str, Any],
    latency_ms: float,
    depends_on: str = "",
    previous_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    plan = result.get("recommended_plan") or {}
    retrieved_products = result.get("retrieved_products") or []
    selected_contexts: list[str] = []
    seen_product_ids: set[str] = set()

    for item in plan.get("items") or []:
        product_id = item.get("product_id")
        product_id_key = str(product_id) if product_id is not None else None
        selected_contexts.append(_plan_item_context(item))
        if product_id_key:
            seen_product_ids.add(product_id_key)

    remaining_retrieved_contexts = [
        _context_from_product(product)
        for product in retrieved_products
        if str(product.get("product_id")) not in seen_product_ids
    ]
    metadata_contexts = [_plan_metadata_context(plan)]
    plan_options_context = _plan_options_context(result, plan)
    if plan_options_context:
        metadata_contexts.append(plan_options_context)
    metadata_contexts.extend(_previous_plan_contexts(previous_plan))
    intent_context = _intent_summary_context(result.get("parsed_intent") or {})
    intent_contexts = [intent_context] if intent_context else []

    if result.get("type") == "product_results":
        contexts = (
            intent_contexts
            + remaining_retrieved_contexts
            + selected_contexts
            + metadata_contexts
        )
    elif selected_contexts:
        contexts = intent_contexts + selected_contexts + metadata_contexts
    else:
        contexts = intent_contexts + remaining_retrieved_contexts + metadata_contexts
    return {
        "log_id": index,
        "evaluation_mode": "ragas",
        "depends_on": depends_on,
        "question": question,
        "answer": str(result.get("answer") or ""),
        "contexts": contexts,
        "ground_truth": ground_truth,
        "faithfulness": None,
        "answer_relevancy": None,
        "answer_relevance": None,
        "answer_correctness": None,
        "context_precision": None,
        "context_recall": None,
        "budget_compliance_aspect": None,
        "category_coverage": None,
        "constraint_adherence": None,
        "ragas_skipped": bool(result.get("used_mock_llm")),
        "skip_reason": (
            "Agent used mock LLM; RAGAS judging skipped." if result.get("used_mock_llm") else None
        ),
        "budget_compliance": plan.get("budget_status") != "over_budget",
        "inventory_validity": plan.get("inventory_status") == "valid",
        "constraint_satisfaction": plan.get("constraint_satisfaction") == "satisfied",
        "latency_ms": round(latency_ms, 2),
        "trace_id": result.get("trace_id"),
        "model_provider": result.get("model_provider"),
        "model_name": result.get("model_name") or settings.QWEN_MODEL,
        "used_mock_llm": result.get("used_mock_llm"),
        "llm_error": result.get("llm_error") or result.get("error"),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


def _apply_scores(row: dict[str, Any], scores: dict[str, Any]) -> None:
    for field in RAGAS_METRIC_FIELDS:
        row[field] = _float_or_none(scores.get(field))
    row["answer_relevance"] = row["answer_relevancy"]
    row["ragas_skipped"] = False
    row["skip_reason"] = None


def run_ragas_evaluation() -> list[dict[str, Any]]:
    question_rows = _read_question_rows()
    rows: list[dict[str, Any]] = []
    samples: list[Any] = []
    sample_row_indexes: list[int] = []
    case_context: dict[str, dict[str, Any]] = {}
    session_context: dict[str, dict[str, Any]] = {}

    for index, item in enumerate(question_rows, start=1):
        depends_on = item.get("depends_on") or ""
        dependency = case_context.get(depends_on)
        if dependency:
            session_id = dependency["session_id"]
            previous_intent = dependency.get("parsed_intent")
            previous_plan = dependency.get("recommended_plan")
        else:
            session_id = f"eval-ragas-{index}"
            previous_intent = None
            previous_plan = None

        start = time.perf_counter()
        result = run_procurement_agent(
            item["question"],
            session_id=session_id,
            previous_intent=previous_intent,
            previous_plan=previous_plan,
            language="en",
        )
        session_context[session_id] = {
            "parsed_intent": result.get("parsed_intent"),
            "recommended_plan": result.get("recommended_plan"),
            "previous_intent": previous_intent,
            "previous_plan": previous_plan,
        }
        case_context[str(index)] = {
            "session_id": session_id,
            **session_context[session_id],
        }
        latency_ms = (time.perf_counter() - start) * 1000
        row = _row_from_agent_result(
            index=index,
            question=item["question"],
            ground_truth=item["ground_truth"],
            result=result,
            latency_ms=latency_ms,
            depends_on=depends_on,
            previous_plan=previous_plan,
        )
        rows.append(row)

        if row["ragas_skipped"]:
            continue
        samples.append(
            _single_turn_sample(
                question=row["question"],
                answer=row["answer"],
                contexts=row["contexts"],
                ground_truth=row["ground_truth"],
            )
        )
        sample_row_indexes.append(len(rows) - 1)

    if samples:
        try:
            score_rows = _evaluate_ragas_samples(samples)
            for row_index, scores in zip(sample_row_indexes, score_rows):
                _apply_scores(rows[row_index], scores)
        except RagasMockLLMSkipped as exc:
            for row_index in sample_row_indexes:
                rows[row_index]["ragas_skipped"] = True
                rows[row_index]["skip_reason"] = str(exc)
        except Exception as exc:
            print(f"RAGAS evaluation failed: {type(exc).__name__}: {exc}")
            for row_index in sample_row_indexes:
                rows[row_index]["ragas_skipped"] = True
                rows[row_index]["skip_reason"] = (
                    f"RAGAS evaluation failed: {type(exc).__name__}: {exc}"
                )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAGAS_EVAL_FILE.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")

    summary = summarize_ragas_evaluations()
    print(
        "RAGAS averages: "
        f"faithfulness={summary['faithfulness']}, "
        f"answer_relevancy={summary['answer_relevancy']}, "
        f"answer_correctness={summary['answer_correctness']}, "
        f"context_precision={summary['context_precision']}, "
        f"context_recall={summary['context_recall']}, "
        f"budget_aspect={summary['budget_compliance_aspect']}, "
        f"category_aspect={summary['category_coverage']}, "
        f"constraint_aspect={summary['constraint_adherence']}"
    )
    return rows


def _average_evaluated(rows: list[dict[str, Any]], field: str) -> float:
    values = [
        float(row[field])
        for row in rows
        if not row.get("ragas_skipped") and isinstance(row.get(field), (int, float))
    ]
    if not values:
        return 0
    return round(sum(values) / len(values), 3)


def summarize_ragas_evaluations() -> dict[str, Any]:
    if not RAGAS_EVAL_FILE.exists():
        rows = run_ragas_evaluation()
    else:
        rows = json.loads(RAGAS_EVAL_FILE.read_text(encoding="utf-8"))

    business = calculate_business_metrics(rows)
    evaluated_cases = sum(1 for row in rows if not row.get("ragas_skipped"))
    skipped_cases = sum(1 for row in rows if row.get("ragas_skipped"))
    return {
        "context_precision": _average_evaluated(rows, "context_precision"),
        "context_recall": _average_evaluated(rows, "context_recall"),
        "faithfulness": _average_evaluated(rows, "faithfulness"),
        "answer_relevancy": _average_evaluated(rows, "answer_relevancy"),
        "answer_relevance": _average_evaluated(rows, "answer_relevance"),
        "answer_correctness": _average_evaluated(rows, "answer_correctness"),
        "average_latency": _average_evaluated(rows, "latency_ms"),
        "budget_compliance_aspect": _average_evaluated(rows, "budget_compliance_aspect"),
        "category_coverage": _average_evaluated(rows, "category_coverage"),
        "constraint_adherence": _average_evaluated(rows, "constraint_adherence"),
        "evaluated_cases": evaluated_cases,
        "skipped_cases": skipped_cases,
        "results": rows,
        **business,
    }
