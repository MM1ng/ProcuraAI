from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator

from app.observability import local_tracer
from app.services import order_service


@dataclass(frozen=True)
class ShadowObservationStorage:
    """Temporary local persistence paths for one controlled DEV replay."""

    root: Path
    orders_file: Path
    observability_file: Path


@contextmanager
def isolated_shadow_observation_storage() -> Iterator[ShadowObservationStorage]:
    """Route controlled DEV replay writes to a disposable local directory.

    The production defaults remain unchanged outside this explicit harness. It
    intentionally reuses the existing file-backed order and observability
    stores rather than changing transaction, payment, or router semantics.
    """
    original_orders_file = order_service.ORDERS_FILE
    original_observability_file = local_tracer.TRACE_FILE
    with TemporaryDirectory(prefix="procuraai-jev-shadow-observation-") as directory:
        root = Path(directory)
        storage = ShadowObservationStorage(
            root=root,
            orders_file=root / "orders.json",
            observability_file=root / "observability_logs.json",
        )
        order_service.ORDERS_FILE = storage.orders_file
        local_tracer.TRACE_FILE = storage.observability_file
        try:
            yield storage
        finally:
            order_service.ORDERS_FILE = original_orders_file
            local_tracer.TRACE_FILE = original_observability_file
