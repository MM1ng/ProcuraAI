"""Python network audit policy for trusted pytest, NOT an OS security sandbox.

Only the current stdlib Windows socketpair fallback's exact client socket and
its own live loopback listener may connect. No general localhost exception.
"""
import ipaddress
import socket
import sys
import threading


class IPCGuard:
    def __init__(self):
        fallback = socket.socketpair
        self.pair_code = fallback.__code__ if getattr(fallback, "__name__", "") == "_fallback_socketpair" else None
        self.allowed = []
        self.denied = []
        self._lock = threading.Lock()

    def _record(self, rows, item):
        with self._lock:
            rows.append(item)

    def _pair_frame(self):
        frame = sys._getframe(1)
        while frame is not None:
            if self.pair_code is not None and frame.f_code is self.pair_code:
                return frame
            frame = frame.f_back
        return None

    def _is_internal(self, event, sock, address):
        frame = self._pair_frame()
        if frame is None or not isinstance(address, tuple) or len(address) < 2:
            return False
        try:
            if not ipaddress.ip_address(address[0]).is_loopback:
                return False
            local = frame.f_locals
            if event == "socket.bind":
                return local.get("lsock") is sock and address[1] == 0
            listener = local.get("lsock")
            return (event == "socket.connect" and local.get("csock") is sock
                    and listener is not None
                    and tuple(listener.getsockname()[:2]) == tuple(address[:2])
                    and (local.get("addr"), local.get("port")) == tuple(address[:2]))
        except (ValueError, OSError, TypeError):
            return False

    def audit(self, event, args):
        if event not in {"socket.connect", "socket.bind", "socket.getaddrinfo", "socket.sendto", "socket.sendmsg"}:
            return
        address = args[1] if len(args) > 1 else None
        if event in {"socket.bind", "socket.connect"} and self._is_internal(event, args[0], address):
            self._record(self.allowed, {"event": event, "reason": "exact_stdlib_socketpair_object_and_listener",
                                       "address": list(address)})
            return
        self._record(self.denied, {"event": event, "address": repr(address), "reason": "not_exact_stdlib_socketpair"})
        raise PermissionError("REVALIDATION NETWORK BLOCKED: " + event)

    def summary(self):
        return {"policy": "deny network except exact stdlib socketpair IPC",
                "allowed_ipc_events": list(self.allowed), "denied_events": list(self.denied),
                "limitations": "Trusted Python code audit; not an OS firewall/native-code sandbox"}
