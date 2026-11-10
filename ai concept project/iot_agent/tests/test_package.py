import tempfile
import unittest
from pathlib import Path

from package_submission import find_secrets, included_files


class PackageTests(unittest.TestCase):
    def test_secrets_and_caches_are_left_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("app.py", ".env", ".env.example", ".cache/chroma/x.bin", "agent/__pycache__/a.pyc",
                        "results/comparison.md"):
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text("x", encoding="utf-8")
            names = {str(rel) for _, rel in included_files(root)}
        self.assertEqual(names, {"app.py", ".env.example", "results/comparison.md"})

    def test_hardcoded_key_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            leaked = Path(tmp) / "config.py"
            leaked.write_text('API_KEY = "sk-' + "a1" * 16 + '"', encoding="utf-8")
            clean = Path(tmp) / ".env.example"
            clean.write_text("DEEPSEEK_API_KEY=your-api-key", encoding="utf-8")
            self.assertEqual(find_secrets([(leaked, "config.py"), (clean, ".env.example")]), ["config.py"])


if __name__ == "__main__":
    unittest.main()
