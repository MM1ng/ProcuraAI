from __future__ import annotations

from app.rag.ingest import ingest_products


def main() -> None:
    count = ingest_products()
    print(f"Ingested {count} products into the local retrieval index")


if __name__ == "__main__":
    main()
