from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = PROJECT_ROOT / "backend"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

for env_path in (PROJECT_ROOT / ".env", BACKEND_ROOT / ".env"):
    if env_path.exists():
        load_dotenv(env_path, override=False)

from app.services.llm_service import safe_llm_invoke, settings  # noqa: E402


def main() -> None:
    if not settings.DASHSCOPE_API_KEY:
        print(f"DASHSCOPE_API_KEY is not configured. Add it to .env to call {settings.QWEN_MODEL}.")
    elif settings.USE_MOCK_LLM:
        print(f"USE_MOCK_LLM=true, so this script will not call {settings.QWEN_MODEL}.")

    result = safe_llm_invoke("你是谁呀能做什么？", purpose="llm_test")

    print(f"model_provider: {result.get('model_provider')}")
    print(f"model_name: {result.get('model_name')}")
    print(f"used_mock_llm: {result.get('used_mock_llm')}")
    print(f"content: {result.get('content')}")
    print(f"error: {result.get('error')}")


if __name__ == "__main__":
    main()
