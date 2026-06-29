"""Tests for BM25 Chinese retrieval with synonym expansion.

Verifies that Chinese queries correctly retrieve English product categories.
"""
from __future__ import annotations

import sys
import os
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.rag.bm25_retriever import BM25Retriever, get_bm25_retriever
import app.rag.bm25_retriever as bm25_module
from app.rag.retriever import retrieve_products_with_evidence


def _top_categories(products: list[dict]) -> list[str]:
    """Extract unique categories from products in order of appearance."""
    seen: set[str] = set()
    result: list[str] = []
    for p in products:
        cat = str(p.get("category", ""))
        if cat and cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


class TestChineseBM25Retrieval:
    """BM25 retriever correctly maps Chinese keywords to English product categories."""

    def test_cn_webcam(self):
        result = retrieve_products_with_evidence("摄像头", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Webcam" in cats, f"Expected Webcam in {cats}"

    def test_cn_headset(self):
        result = retrieve_products_with_evidence("耳机", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Headset" in cats, f"Expected Headset in {cats}"

    def test_cn_docking_station(self):
        result = retrieve_products_with_evidence("扩展坞", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Docking Station" in cats, f"Expected Docking Station in {cats}"

    def test_cn_office_chair(self):
        result = retrieve_products_with_evidence("办公椅", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Office Chair" in cats, f"Expected Office Chair in {cats}"

    def test_cn_monitor(self):
        result = retrieve_products_with_evidence("显示器", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Monitor" in cats, f"Expected Monitor in {cats}"

    def test_cn_keyboard(self):
        result = retrieve_products_with_evidence("键盘", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Keyboard" in cats, f"Expected Keyboard in {cats}"

    def test_cn_mouse(self):
        result = retrieve_products_with_evidence("鼠标", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Mouse" in cats, f"Expected Mouse in {cats}"

    def test_cn_laptop(self):
        result = retrieve_products_with_evidence("笔记本", {"categories": []}, top_k=5)
        cats = _top_categories(result.products)
        assert "Laptop" in cats, f"Expected Laptop in {cats}"

    def test_cn_mixed_categories(self):
        """Mixed Chinese query with multiple categories (simulating intent parser)."""
        # In the real flow, the intent parser extracts ["Webcam", "Headset", "Docking Station"]
        result = retrieve_products_with_evidence(
            "需要购买摄像头、耳机和扩展坞",
            {"categories": ["Webcam", "Headset", "Docking Station"]},
            top_k=15,
        )
        cats = _top_categories(result.products)
        for expected in ("Webcam", "Headset", "Docking Station"):
            assert expected in cats, f"Expected {expected} in {cats}"

    def test_cn_bm25_score_nonzero(self):
        """BM25 scores should be > 0 for matched Chinese queries."""
        result = retrieve_products_with_evidence("耳机", {"categories": []}, top_k=3)
        scores = [float(p.get("retrieval_score", 0) or 0) for p in result.products]
        assert any(s > 0 for s in scores), f"Expected positive BM25 scores, got {scores}"

    def test_search_by_categories_filters_each_category(self):
        retriever = BM25Retriever(
            products=[
                {
                    "product_id": "webcam-1",
                    "name": "Logitech Webcam",
                    "category": "Webcam",
                    "brand": "Logitech",
                    "supplier": "Northwind",
                    "description": "camera for meetings",
                    "tags": "webcam camera",
                },
                {
                    "product_id": "headset-1",
                    "name": "Poly Headset",
                    "category": "Headset",
                    "brand": "Poly",
                    "supplier": "Northwind",
                    "description": "audio for meetings",
                    "tags": "headset audio",
                },
                {
                    "product_id": "dock-1",
                    "name": "HP Docking Station",
                    "category": "Docking Station",
                    "brand": "HP",
                    "supplier": "Contoso",
                    "description": "usb c dock",
                    "tags": "dock docking station",
                },
            ]
        )

        results = retriever.search_by_categories(
            "采购摄像头、耳机和扩展坞，给10名远程员工使用。",
            ["Webcam", "Headset", "Docking Station"],
            top_k=6,
        )

        assert [item["category"] for item in results] == ["Webcam", "Headset", "Docking Station"]


def test_get_bm25_retriever_loads_cache_when_products_csv_mtime_matches(tmp_path, monkeypatch):
    products_csv = tmp_path / "products.csv"
    products_csv.write_text("product_id,name\n", encoding="utf-8")
    products_csv_mtime = products_csv.stat().st_mtime
    cache_file = tmp_path / "bm25_index.pkl"
    monkeypatch.setattr(bm25_module, "DATA_DIR", tmp_path)
    products = [
        {
            "product_id": "cached-1",
            "name": "Cached Webcam",
            "category": "Webcam",
            "brand": "Logitech",
            "supplier": "Northwind",
            "description": "camera",
            "tags": "webcam camera",
        }
    ]
    cached = BM25Retriever(products)
    cached.save(cache_file)

    load_calls: list[bool] = []
    monkeypatch.setattr(bm25_module, "_BUILT_INDEX", None)
    monkeypatch.setattr(
        bm25_module,
        "load_products_from_csv",
        lambda: load_calls.append(True) or [
            {
                "product_id": "rebuilt-1",
                "name": "Rebuilt Headset",
                "category": "Headset",
                "brand": "Poly",
                "supplier": "Northwind",
                "description": "audio",
                "tags": "headset audio",
            }
        ],
    )

    retriever = get_bm25_retriever()

    assert retriever.products[0]["product_id"] == "cached-1"
    assert retriever.products_csv_mtime == products_csv_mtime
    assert load_calls == []


def test_get_bm25_retriever_rebuilds_cache_when_products_csv_mtime_changes(tmp_path, monkeypatch):
    products_csv = tmp_path / "products.csv"
    products_csv.write_text("product_id,name\n", encoding="utf-8")
    cache_file = tmp_path / "bm25_index.pkl"
    monkeypatch.setattr(bm25_module, "DATA_DIR", tmp_path)
    cached = BM25Retriever(
        [
            {
                "product_id": "cached-1",
                "name": "Cached Webcam",
                "category": "Webcam",
                "brand": "Logitech",
                "supplier": "Northwind",
                "description": "camera",
                "tags": "webcam camera",
            }
        ]
    )
    cached.save(cache_file)
    products_csv.write_text("product_id,name\nrebuilt-1,Rebuilt Headset\n", encoding="utf-8")
    os.utime(products_csv, (products_csv.stat().st_mtime + 10, products_csv.stat().st_mtime + 10))

    monkeypatch.setattr(bm25_module, "_BUILT_INDEX", None)
    monkeypatch.setattr(
        bm25_module,
        "load_products_from_csv",
        lambda: [
            {
                "product_id": "rebuilt-1",
                "name": "Rebuilt Headset",
                "category": "Headset",
                "brand": "Poly",
                "supplier": "Northwind",
                "description": "audio",
                "tags": "headset audio",
            }
        ],
    )

    retriever = get_bm25_retriever()
    reloaded = BM25Retriever()
    reloaded.load(cache_file)

    assert retriever.products[0]["product_id"] == "rebuilt-1"
    assert retriever.products_csv_mtime == products_csv.stat().st_mtime
    assert reloaded.products[0]["product_id"] == "rebuilt-1"
