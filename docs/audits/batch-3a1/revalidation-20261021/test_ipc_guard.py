"""Standalone harness tests. No ProcuraAI product/test changes or providers."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import socket
import sys
import unittest

from ipc_guard import IPCGuard

GUARD = IPCGuard()
sys.addaudithook(GUARD.audit)


def pair_roundtrip():
    a, b = socket.socketpair()
    try:
        a.settimeout(2)
        b.settimeout(2)
        a.sendall(b"ipc-probe")
        return b.recv(9)
    finally:
        a.close()
        b.close()


class GuardTests(unittest.TestCase):
    def test_pair_roundtrip(self):
        self.assertEqual(pair_roundtrip(), b"ipc-probe")

    def test_asyncio_internal_ipc(self):
        async def probe():
            await asyncio.sleep(0)
            return "ok"
        self.assertEqual(asyncio.run(probe()), "ok")

    def test_ipv6_pair(self):
        if not socket.has_ipv6:
            self.fail("IPv6 capability unavailable: do not silently skip")
        a, b = socket.socketpair(socket.AF_INET6)
        a.close()
        b.close()

    def test_localhost_service_connect_denied(self):
        with socket.socket() as peer:
            with self.assertRaises(PermissionError):
                peer.connect(("127.0.0.1", 8000))

    def test_arbitrary_loopback_connect_denied(self):
        with socket.socket() as peer:
            with self.assertRaises(PermissionError):
                peer.connect(("127.0.0.1", 49152))

    def test_ipv6_connect_denied(self):
        with socket.socket(socket.AF_INET6) as peer:
            with self.assertRaises(PermissionError):
                peer.connect(("::1", 8000))

    def test_external_ip_connect_denied(self):
        with socket.socket() as peer:
            with self.assertRaises(PermissionError):
                peer.connect(("203.0.113.1", 443))

    def test_dns_denied(self):
        with self.assertRaises(PermissionError):
            socket.getaddrinfo("provider.invalid", 443)

    def test_udp_send_denied(self):
        with socket.socket(type=socket.SOCK_DGRAM) as peer:
            with self.assertRaises(PermissionError):
                peer.sendto(b"must-not-send", ("127.0.0.1", 9))

    def test_arbitrary_bind_denied(self):
        with socket.socket() as peer:
            with self.assertRaises(PermissionError):
                peer.bind(("127.0.0.1", 0))

    def test_concurrency_does_not_leak_allowance(self):
        def operation(index):
            if index % 2 == 0:
                return pair_roundtrip() == b"ipc-probe"
            with socket.socket() as peer:
                try:
                    peer.connect(("127.0.0.1", 8000))
                except PermissionError:
                    return True
            return False
        with ThreadPoolExecutor(max_workers=8) as pool:
            self.assertTrue(all(pool.map(operation, range(32))))

    def test_connect_ex_cannot_bypass(self):
        with socket.socket() as peer:
            with self.assertRaises(PermissionError):
                peer.connect_ex(("127.0.0.1", 8000))


if __name__ == "__main__":
    import json
    from pathlib import Path
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(GuardTests))
    Path(sys.argv[1]).write_text(json.dumps({"tests_run": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": len(result.skipped), "guard": GUARD.summary()}, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
