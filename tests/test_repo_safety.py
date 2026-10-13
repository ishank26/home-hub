"""Publication policy tests with synthetic secret strings and reviewed font bytes."""
import importlib.machinery
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOADER = importlib.machinery.SourceFileLoader('repo_safety', str(ROOT / 'scripts/check-repo-safety'))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
assert SPEC is not None
SAFETY = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(SAFETY)


class RepoSafetyTests(unittest.TestCase):
    def test_reviewed_fonts_require_exact_hash(self):
        for name in SAFETY.FONT_HASHES:
            data = (ROOT / name).read_bytes()
            self.assertIsNone(SAFETY.scan_blob(name, data))
            self.assertEqual(SAFETY.scan_blob(name, data + b'tamper'), 'reviewed font hash mismatch')

    def test_unreviewed_binary_refused(self):
        self.assertEqual(SAFETY.scan_blob('static/unknown.woff2', b'\xff\x00'), 'unreviewed binary')

    def test_runtime_and_credentials_paths_refused(self):
        for name in ['data/shopping.json', 'backups/frame.img', 'diagnostics/status.txt', '.env', 'secrets.json', 'key.jks']:
            self.assertEqual(SAFETY.scan_blob(name, b'{}'), 'runtime/secret-like path')

    def test_synthetic_secret_detected_and_plain_docs_allowed(self):
        synthetic = ('github_' + 'pat_' + 'a' * 50).encode()
        self.assertEqual(SAFETY.scan_blob('notes.md', synthetic), 'secret-looking content')
        self.assertIsNone(SAFETY.scan_blob('notes.md', b'Keep passwords outside Git.'))


if __name__ == '__main__':
    unittest.main()
