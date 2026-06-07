from __future__ import annotations

from app.rag.ingest import ingest_products


def main() -> None:
    count = ingest_products()
    print(f"Ingested {count} products into the JSON fallback index and local Chroma collections")


if __name__ == "__main__":
    main()
