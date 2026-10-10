"""OS exclusive lease, held for the entire single-writer process lifespan."""
from contextlib import contextmanager
from functools import wraps
import os
from pathlib import Path
from threading import RLock
from app.services.caller_identity import CallerDenied

TRANSACTION_LOCK = RLock()
_LEASES = {}

def canonical_order_path(path):
    return os.path.normcase(str(Path(path).resolve()))

@contextmanager
def order_writer_lease(path):
    key = canonical_order_path(path)
    with TRANSACTION_LOCK:
        if key in _LEASES and _LEASES[key]["pid"] == os.getpid():
            _LEASES[key]["refs"] += 1
        else:
            fd = None
            try:
                fd = os.open(key + ".writer.lock", os.O_CREAT | os.O_RDWR, 0o600)
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                os.lseek(fd, 0, os.SEEK_SET)
                if os.name == "nt":
                    import msvcrt
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                _LEASES[key] = {"fd": fd, "refs": 1, "pid": os.getpid()}
            except OSError:
                if fd is not None:
                    os.close(fd)
                raise CallerDenied("ORDER_WRITER_LEASE_UNAVAILABLE", 503) from None
    try:
        yield
    finally:
        with TRANSACTION_LOCK:
            record = _LEASES[key]
            record["refs"] -= 1
            if not record["refs"]:
                os.close(record["fd"])
                del _LEASES[key]

def require_writer_lease():
    from app.services import order_service
    record = _LEASES.get(canonical_order_path(order_service.ORDERS_FILE))
    if not record or record["pid"] != os.getpid():
        raise CallerDenied("ORDER_WRITER_LEASE_REQUIRED", 503)
    try:
        os.fstat(record["fd"])
    except OSError:
        raise CallerDenied("ORDER_WRITER_LEASE_UNKNOWN", 503) from None

def transaction_locked(fn):
    @wraps(fn)
    def locked(*args, **kwargs):
        with TRANSACTION_LOCK:
            require_writer_lease()
            return fn(*args, **kwargs)
    return locked
