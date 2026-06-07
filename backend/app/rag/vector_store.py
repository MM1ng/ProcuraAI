from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import DATA_DIR
from app.rag.embeddings import embed_text


INDEX_FILE = DATA_DIR / "retrieval_index.json"
CHROMA_DIR = DATA_DIR / "chroma"
PRODUCT_COLLECTION = "products"
POLICY_COLLECTION = "procurement_policies"
SUPPLIER_COLLECTION = "suppliers"


def build_local_index(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = []
    for product in products:
        text = build_product_document(product)
        index.append({"product_id": product.get("product_id"), "text": text, "metadata": product})
    return index


def build_product_document(product: dict[str, Any]) -> str:
    return (
        f"{product.get('name')} {product.get('brand')} {product.get('category')} "
        f"{product.get('supplier')} {product.get('description')} {product.get('tags')} "
        f"price {product.get('price')} rating {product.get('rating')} stock {product.get('stock')} "
        f"delivery {product.get('delivery_days')} compliance {product.get('compliance_level')}"
    )


def save_local_index(index: list[dict[str, Any]], path: Path = INDEX_FILE) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2), encoding="utf-8")


def load_local_index(path: Path = INDEX_FILE) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _chromadb():
    try:
        import chromadb

        return chromadb
    except Exception:
        return None


def _client(persist_dir: Path | str = CHROMA_DIR):
    chromadb = _chromadb()
    if chromadb is None:
        return None
    return chromadb.PersistentClient(path=str(persist_dir))


def _metadata(value: dict[str, Any], kind: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {"kind": kind}
    for key, item in value.items():
        if isinstance(item, (str, int, float, bool)) or item is None:
            metadata[key] = "" if item is None else item
    return metadata


def _reset_collection(client: Any, name: str) -> Any:
    try:
        client.delete_collection(name)
    except Exception:
        pass
    return client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})


def _add_documents(collection: Any, rows: list[dict[str, Any]], kind: str) -> None:
    if not rows:
        return
    ids = [str(row["id"]) for row in rows]
    documents = [str(row["document"]) for row in rows]
    metadatas = [_metadata(dict(row["metadata"]), kind) for row in rows]
    embeddings = [embed_text(document) for document in documents]
    collection.add(ids=ids, documents=documents, metadatas=metadatas, embeddings=embeddings)


def _product_rows(products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(product.get("product_id")),
            "document": build_product_document(product),
            "metadata": product,
        }
        for product in products
        if product.get("product_id")
    ]


def _policy_rows(policies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(policy.get("id")),
            "document": f"{policy.get('title', '')} {policy.get('text', '')}",
            "metadata": policy,
        }
        for policy in policies
        if policy.get("id")
    ]


def _supplier_rows(suppliers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": str(supplier.get("id")),
            "document": f"{supplier.get('supplier', '')} {supplier.get('text', '')}",
            "metadata": supplier,
        }
        for supplier in suppliers
        if supplier.get("id")
    ]


def rebuild_vector_collections(
    products: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    suppliers: list[dict[str, Any]],
    persist_dir: Path | str = CHROMA_DIR,
) -> dict[str, int]:
    client = _client(persist_dir)
    if client is None:
        return {PRODUCT_COLLECTION: 0, POLICY_COLLECTION: 0, SUPPLIER_COLLECTION: 0}

    product_rows = _product_rows(products)
    policy_rows = _policy_rows(policies)
    supplier_rows = _supplier_rows(suppliers)

    _add_documents(_reset_collection(client, PRODUCT_COLLECTION), product_rows, "product")
    _add_documents(_reset_collection(client, POLICY_COLLECTION), policy_rows, "policy")
    _add_documents(_reset_collection(client, SUPPLIER_COLLECTION), supplier_rows, "supplier")
    return {
        PRODUCT_COLLECTION: len(product_rows),
        POLICY_COLLECTION: len(policy_rows),
        SUPPLIER_COLLECTION: len(supplier_rows),
    }


def query_vector_collection(
    collection_name: str,
    query: str,
    top_k: int = 12,
    persist_dir: Path | str = CHROMA_DIR,
) -> list[dict[str, Any]]:
    client = _client(persist_dir)
    if client is None:
        return []
    try:
        collection = client.get_collection(collection_name)
        if collection.count() == 0:
            return []
        result = collection.query(
            query_embeddings=[embed_text(query)],
            n_results=top_k,
            include=["documents", "metadatas", "distances"],
        )
    except Exception:
        return []

    ids = result.get("ids", [[]])[0]
    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]
    rows: list[dict[str, Any]] = []
    for index, row_id in enumerate(ids):
        distance = float(distances[index] or 0)
        rows.append(
            {
                "id": row_id,
                "document": documents[index],
                "metadata": dict(metadatas[index] or {}),
                "distance": distance,
                "score": round(max(0.0, 1.0 - distance), 6),
            }
        )
    return rows
