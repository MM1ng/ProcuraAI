import json
from pathlib import Path
import subprocess
import sys
import unittest
from process_guard import allowed_process

ROOT = Path(__file__).resolve().parent / "attempt-04" / "runtime"


class ProcessTests(unittest.TestCase):
    def test_windows_none_executable_whoami(self):
        self.assertIsNotNone(allowed_process(None, "whoami /user /fo csv /nh", ROOT))

    def test_windows_icacls_path_with_spaces(self):
        args = ["icacls", str(ROOT / "path with spaces"), "/inheritance:r", "/grant:r",
                "*S-1-5-21-123-456-789-1001:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"]
        self.assertIsNotNone(allowed_process(None, subprocess.list2cmdline(args), ROOT))

    def test_python_denied(self):
        self.assertIsNone(allowed_process(None, [sys.executable, "-c", "pass"], ROOT))

    def test_shell_denied(self):
        self.assertIsNone(allowed_process(None, "cmd.exe /c whoami", ROOT))

    def test_extra_whoami_args_denied(self):
        self.assertIsNone(allowed_process(None, "whoami /user /fo csv /nh /all", ROOT))

    def test_outside_acl_denied(self):
        self.assertIsNone(allowed_process(None, ["icacls", str(ROOT.parent), "/inheritance:r", "/grant:r",
                          "*S-1-5-21-1:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], ROOT))

    def test_broad_acl_denied(self):
        self.assertIsNone(allowed_process(None, ["icacls", str(ROOT / "nested"), "/inheritance:r", "/grant:r",
                          "Everyone:F", "*S-1-5-18:(OI)(CI)F"], ROOT))

    def test_executable_mismatch_denied(self):
        self.assertIsNone(allowed_process("cmd.exe", "whoami /user /fo csv /nh", ROOT))


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ProcessTests))
    Path(sys.argv[1]).write_text(json.dumps({"tests_run": result.testsRun, "failures": len(result.failures),
        "errors": len(result.errors), "skipped": len(result.skipped)}, indent=2) + "\n", encoding="utf-8")
    raise SystemExit(0 if result.wasSuccessful() else 1)
