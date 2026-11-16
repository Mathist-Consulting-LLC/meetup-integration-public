"""Checkout-only CI tests, run explicitly; not installed provider discovery."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check-whitespace.py"


class WhitespaceTests(unittest.TestCase):
    def test_event_comparisons(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            origin = Path(tmp) / "origin.git"
            subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
            subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)

            def git(*args):
                return subprocess.check_output(["git", "-C", str(repo), *args], text=True).strip()

            git("config", "user.name", "Synthetic")
            git("config", "user.email", "synthetic@example.invalid")
            (repo / "base").write_text("base\n")
            git("add", ".")
            git("commit", "-m", "base")
            base = git("rev-parse", "HEAD")
            git("remote", "add", "origin", str(origin))
            git("push", "origin", "main")
            git("checkout", "-b", "candidate")
            (repo / "new").write_text("dirty trailing space \n")
            git("add", ".")
            git("commit", "-m", "dirty")
            dirty = git("rev-parse", "HEAD")

            def check(event, before, head, branch="main"):
                return subprocess.run([sys.executable, str(SCRIPT)], cwd=repo,
                    env={**os.environ, "EVENT_NAME": event, "BASE": before,
                         "HEAD": head, "DEFAULT_BRANCH": branch},
                    text=True, capture_output=True)

            for event, before in [("push", "0" * 40), ("push", base), ("pull_request", base)]:
                result = check(event, before, dirty)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn("trailing whitespace", result.stderr + result.stdout)
                self.assertEqual(check(event, before, base).returncode, 0)
            (repo / "later").write_text("clean addition\n")
            git("add", ".")
            git("commit", "-m", "later clean change")
            later = git("rev-parse", "HEAD")
            # Unchanged historical whitespace is not a new normal-push/PR error.
            for event in ("push", "pull_request"):
                self.assertEqual(check(event, dirty, later).returncode, 0)
            self.assertNotEqual(check("push", "0" * 40, later).returncode, 0)
            for event, before, head, branch in [
                ("pull_request", "0" * 40, dirty, "main"),
                ("push", "", dirty, "main"), ("push", "f" * 40, dirty, "main"),
                ("push", base, "f" * 40, "main"), ("push", base, "HEAD", "main"),
                ("push", "0" * 40, dirty, "missing"),
                ("push", "0" * 40, dirty, "../bad"),
                ("schedule", base, dirty, "main"),
            ]:
                result = check(event, before, head, branch)
                self.assertNotEqual(result.returncode, 0)
                self.assertNotIn("trailing whitespace", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
