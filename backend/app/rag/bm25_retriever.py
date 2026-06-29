"""BM25 hybrid retriever with THULAC Chinese tokenization.

Keeps the existing vector retrieval unchanged; this module provides an
additional BM25 channel for Chinese/mixed queries with synonym expansion.
"""

from __future__ import annotations

import math
import pickle
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.services.product_service import load_products_from_csv


# ── Chinese-English category synonyms ──────────────────────────────
CATEGORY_SYNONYMS: dict[str, str] = {
    # Chinese → English category name (the canonical name in products.csv)
    "摄像头": "Webcam",
    "相机": "Webcam",
    "摄像头设备": "Webcam",
    "耳机": "Headset",
    "耳麦": "Headset",
    "头戴耳机": "Headset",
    "耳罩": "Headset",
    "扩展坞": "Docking Station",
    "扩展底座": "Docking Station",
    "底座": "Docking Station",
    "usb集线器": "Docking Station",
    "显示器": "Monitor",
    "显示屏": "Monitor",
    "屏幕": "Monitor",
    "电脑显示器": "Monitor",
    "办公椅": "Office Chair",
    "椅子": "Office Chair",
    "电脑椅": "Office Chair",
    "笔记本": "Laptop",
    "笔记本电脑": "Laptop",
    "开发电脑": "Laptop",
    "键盘": "Keyboard",
    "鼠标": "Mouse",
    "打印机": "Printer",
    "投影仪": "Projector",
    "投影": "Projector",
    "交换机": "Network Switch",
    "路由器": "Router",
    "会议音响": "Conference Speaker",
    "扬声器": "Conference Speaker",
    "音箱": "Conference Speaker",
    "平板": "Tablet",
    "平板电脑": "Tablet",
    "ssd": "External SSD",
    "移动硬盘": "External SSD",
    "外置硬盘": "External SSD",
    "固态硬盘": "External SSD",
    "dock": "Docking Station",
    "坞": "Docking Station",
    "扩展": "Docking Station",
    "mic": "Webcam",
    "camera": "Webcam",
    "phone": "Headset",
    "chair": "Office Chair",
    "screen": "Monitor",
    "disk": "External SSD",
    "drive": "External SSD",
    "storage": "External SSD",
    "printer": "Printer",
    "tablet": "Tablet",
    "laptop": "Laptop",
}

# Built from CATEGORY_SYNONYMS values: English plural/variant → canonical
ENGLISH_CATEGORY_VARIANTS: dict[str, str] = {
    "webcams": "Webcam",
    "cameras": "Webcam",
    "headsets": "Headset",
    "headphones": "Headset",
    "docks": "Docking Station",
    "docking": "Docking Station",
    "monitors": "Monitor",
    "laptops": "Laptop",
    "keyboards": "Keyboard",
    "mice": "Mouse",
    "mouses": "Mouse",
    "printers": "Printer",
    "chairs": "Office Chair",
    "office chairs": "Office Chair",
    "routers": "Router",
    "tablets": "Tablet",
    "ssds": "External SSD",
    "projectors": "Projector",
    "speakers": "Conference Speaker",
}

_WHITESPACE = re.compile(r"\s+")
_ENGLISH_TOKEN = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9#+\-.]+")
_KNOWN_BRANDS = {
    "logitech", "dell", "hp", "lenovo", "samsung", "sony", "apple",
    "anker", "razer", "keychron", "jabra", "wd", "seagate", "brother",
    "viewsonic", "benq", "lg", "asus", "acer", "microsoft", "poly",
    "plantronics", "kingston", "corsair", "steelseries", "hyperx",
    "sennheiser", "bose", "jbl", "yamaha", "epson", "canon",
    "humancentric", "herman miller", "steelcase", "autonomous",
    "northwind", "umbrella",
}

# Stopwords for Chinese
_CHINESE_STOP = frozenset({
    "的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都",
    "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你",
    "会", "着", "没有", "看", "好", "自己", "这", "他", "她", "它",
    "们", "那", "些", "来", "出", "为", "与", "及", "或", "但",
    "被", "把", "对", "从", "以", "而", "所", "如", "将", "能",
    "可以", "应该", "需要", "可能", "已经", "还", "又", "再",
    "个", "只", "每", "什么", "怎么", "如何",
})


def _tokenize(text: str) -> list[str]:
    """Tokenize mixed Chinese/English text.

    - English words (letter/digit sequences) are lowercased.
    - Chinese text is segmented via THULAC.
    - Return filtered tokens (stopwords removed, short tokens kept).
    """
    text = text.lower().strip()
    if not text:
        return []

    tokens: list[str] = []

    # Extract English tokens first
    eng_tokens = _ENGLISH_TOKEN.findall(text)
    tokens.extend(t.lower() for t in eng_tokens)

    # Remove English tokens from text for Chinese segmentation
    remaining = text
    for t in eng_tokens:
        remaining = remaining.replace(t, " ", 1)
    remaining = _WHITESPACE.sub(" ", remaining).strip()

    # Chinese segmentation with THULAC
    if remaining and any(ord(c) > 127 for c in remaining):
        try:
            import thulac
            thu = thulac.thulac(seg_only=True, model_path=None)
            seg_result = thu.cut(remaining, text=True)
            seg_tokens = seg_result.split()
            for token in seg_tokens:
                token = token.strip()
                if len(token) >= 2 and token not in _CHINESE_STOP:
                    tokens.append(token)
                elif len(token) == 1 and token in "电缆线卡板":
                    # Keep short meaningful tokens like "线" (cable)
                    tokens.append(token)
        except Exception:
            # Fallback: character bigrams
            for i in range(len(remaining) - 1):
                bigram = remaining[i:i+2]
                if bigram not in _CHINESE_STOP and not _WHITESPACE.match(bigram):
                    tokens.append(bigram)

    # Also split remaining on whitespace for any leftover mixed tokens
    for token in remaining.split():
        token = token.strip().lower()
        if token and token not in _CHINESE_STOP and len(token) >= 2:
            # Only add if not already captured by THULAC or English tokenizer
            if token not in tokens:
                tokens.append(token)

    return tokens


def _expand_synonyms(tokens: list[str]) -> list[str]:
    """Expand tokens through category synonyms and brand aliases."""
    expanded = list(tokens)
    for token in tokens:
        # Chinese → English category
        if token in CATEGORY_SYNONYMS:
            target = CATEGORY_SYNONYMS[token].lower()
            expanded.append(target)
            # Also add individual words for multi-word targets (e.g. "office chair" -> ["office", "chair"])
            for part in target.split():
                if part not in expanded:
                    expanded.append(part)
        # English variant → canonical category
        if token in ENGLISH_CATEGORY_VARIANTS:
            target = ENGLISH_CATEGORY_VARIANTS[token].lower()
            expanded.append(target)
            for part in target.split():
                if part not in expanded:
                    expanded.append(part)
    return expanded


def _idf(num_docs: int, doc_freq: int) -> float:
    """BM25-style IDF."""
    if doc_freq == 0:
        return 0.0
    return math.log(1.0 + (num_docs - doc_freq + 0.5) / (doc_freq + 0.5))


class BM25Retriever:
    """BM25 retriever with THULAC Chinese segmentation and synonym expansion.

    Builds an in-memory inverted index over product fields.
    Designed as an additive channel alongside existing vector retrieval.
    """

    def __init__(self, products: list[dict[str, Any]] | None = None, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.products: list[dict[str, Any]] = []
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0.0
        self.inverted_index: dict[str, list[tuple[int, int]]] = defaultdict(list)  # term → [(doc_id, count)]
        self.doc_freq: dict[str, int] = Counter()
        self.num_docs: int = 0
        self.products_csv_mtime: float | None = None

        if products is not None:
            self.build_index(products)

    def _doc_tokens(self, product: dict[str, Any]) -> list[str]:
        """Extract and tokenize all searchable fields from a product."""
        fields = [
            str(product.get("name", "")),
            str(product.get("category", "")),
            str(product.get("brand", "")),
            str(product.get("supplier", "")),
            str(product.get("description", "")),
            str(product.get("tags", "")),
        ]
        text = " ".join(fields)
        tokens = _tokenize(text)
        return _expand_synonyms(tokens)

    def build_index(self, products: list[dict[str, Any]]) -> None:
        """Build the inverted index from a product list."""
        self.products = list(products)
        self.num_docs = len(self.products)
        self.inverted_index.clear()
        self.doc_freq.clear()
        self.doc_lengths = []

        for doc_id, product in enumerate(self.products):
            tokens = self._doc_tokens(product)
            term_counts: Counter[str] = Counter()
            for token in tokens:
                term_counts[token] += 1
            self.doc_lengths.append(sum(term_counts.values()))
            for term, count in term_counts.items():
                self.inverted_index[term].append((doc_id, count))
                self.doc_freq[term] += 1

        if self.doc_lengths:
            self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths)
        else:
            self.avg_doc_length = 1.0
        products_csv = DATA_DIR / "products.csv"
        self.products_csv_mtime = products_csv.stat().st_mtime if products_csv.exists() else None

    def save(self, path: Path) -> None:
        """Persist the BM25 index and source CSV mtime to a pickle file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        products_csv = DATA_DIR / "products.csv"
        payload = {
            "inverted_index": dict(self.inverted_index),
            "doc_lengths": self.doc_lengths,
            "avg_doc_length": self.avg_doc_length,
            "doc_freq": dict(self.doc_freq),
            "num_docs": self.num_docs,
            "products": self.products,
            "products_csv_mtime": products_csv.stat().st_mtime if products_csv.exists() else self.products_csv_mtime,
        }
        with path.open("wb") as handle:
            pickle.dump(payload, handle)
        self.products_csv_mtime = payload["products_csv_mtime"]

    def load(self, path: Path) -> None:
        """Restore the BM25 index fields from a pickle file."""
        with path.open("rb") as handle:
            payload = pickle.load(handle)
        self.inverted_index = defaultdict(list, payload["inverted_index"])
        self.doc_lengths = payload["doc_lengths"]
        self.avg_doc_length = payload["avg_doc_length"]
        self.doc_freq = Counter(payload["doc_freq"])
        self.num_docs = payload["num_docs"]
        self.products = payload["products"]
        self.products_csv_mtime = payload.get("products_csv_mtime")

    def search(self, query: str, top_k: int = 12) -> list[dict[str, Any]]:
        """Search products by BM25 score.

        Returns products with added 'bm25_score' and 'bm25_matched_terms'.
        """
        query_tokens = _expand_synonyms(_tokenize(query))
        if not query_tokens:
            return []

        # Score each document
        scores: dict[int, float] = defaultdict(float)
        matched_terms: dict[int, set[str]] = defaultdict(set)
        doc_len = self.doc_lengths or [1] * self.num_docs

        for term in set(query_tokens):
            idf = _idf(self.num_docs, self.doc_freq.get(term, 0))
            if idf == 0.0:
                continue
            for doc_id, term_count in self.inverted_index.get(term, []):
                dl = doc_len[doc_id] if doc_id < len(doc_len) else 1
                tf = term_count / (1.0 - self.b + self.b * (dl / self.avg_doc_length))
                scores[doc_id] += idf * (tf * (self.k1 + 1.0)) / (tf + self.k1)
                matched_terms[doc_id].add(term)

        # Rank
        ranked = sorted(scores.items(), key=lambda x: -x[1])[:top_k]

        results: list[dict[str, Any]] = []
        for doc_id, score in ranked:
            product = dict(self.products[doc_id])
            product["bm25_score"] = round(score, 4)
            product["bm25_matched_terms"] = sorted(matched_terms.get(doc_id, []))
            results.append(product)

        return results

    def search_with_synonym_boost(
        self,
        query: str,
        intent: dict[str, Any] | None = None,
        top_k: int = 12,
    ) -> list[dict[str, Any]]:
        """Search with additional boost for categories mentioned in intent."""
        results = self.search(query, top_k=top_k * 2)

        # Apply category boost from intent
        intent_categories = [
            str(c).lower() for c in (intent or {}).get("categories") or []
        ]
        if intent_categories:
            for product in results:
                product_cat = str(product.get("category", "")).lower()
                if product_cat in intent_categories:
                    product["bm25_score"] = (product.get("bm25_score", 0) or 0) * 1.3

        return sorted(results, key=lambda p: -(p.get("bm25_score", 0) or 0))[:top_k]

    def search_by_categories(
        self,
        query: str,
        categories: list[str] | None = None,
        top_k: int = 12,
    ) -> list[dict[str, Any]]:
        """Search BM25 per-category and merge results for diversity.

        When intent categories are available, query each category independently
        and interleave results so that all requested categories are represented.
        """
        if not categories:
            return self.search(query, top_k=top_k)

        per_cat: dict[str, list[dict[str, Any]]] = {}
        for cat in categories:
            cat_query = f"{query} {cat}"
            category_products = [
                product
                for product in self.products
                if str(product.get("category", "")).lower() == str(cat).lower()
            ]
            if category_products:
                category_retriever = BM25Retriever(category_products, k1=self.k1, b=self.b)
                cat_results = category_retriever.search(cat_query, top_k=max(1, top_k))
            else:
                cat_results = self.search(cat_query, top_k=1)
            if cat_results:
                per_cat[cat] = cat_results

        # Interleave results round-robin across categories
        merged: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        max_len = max(len(v) for v in per_cat.values()) if per_cat else 0
        for i in range(max_len):
            for cat in categories:
                cat_list = per_cat.get(cat, [])
                if i < len(cat_list):
                    p = cat_list[i]
                    pid = p.get("product_id")
                    if pid and pid not in seen_ids:
                        merged.append(p)
                        seen_ids.add(pid)
                        if len(merged) >= top_k:
                            return merged
        return merged[:top_k]


# ── Module-level singleton ─────────────────────────────────────────
_BUILT_INDEX: BM25Retriever | None = None


def get_bm25_retriever(refresh: bool = False) -> BM25Retriever:
    """Get or create the BM25 retriever singleton."""
    global _BUILT_INDEX
    if _BUILT_INDEX is None or refresh:
        cache_file = DATA_DIR / "bm25_index.pkl"
        products_csv = DATA_DIR / "products.csv"
        products_csv_mtime = products_csv.stat().st_mtime if products_csv.exists() else None
        if not refresh and cache_file.exists():
            cached = BM25Retriever()
            cached.load(cache_file)
            if cached.products_csv_mtime == products_csv_mtime:
                _BUILT_INDEX = cached
                return _BUILT_INDEX
        products = load_products_from_csv()
        _BUILT_INDEX = BM25Retriever(products=products)
        _BUILT_INDEX.products_csv_mtime = products_csv_mtime
        _BUILT_INDEX.save(cache_file)
    return _BUILT_INDEX
