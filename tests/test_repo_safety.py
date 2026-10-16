"""Publication policy tests with synthetic secret strings and reviewed font bytes."""
import importlib.machinery
import importlib.util
import json
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
        for name in ['data/shopping.json', 'backups/frame.img', 'diagnostics/status.txt', '.env', 'secrets.json', 'key.jks', 'private.pem', 'private.key', 'export.p12', 'export.pfx',
                     'aura-session.json', 'device-token', 'config.local.json']:
            self.assertEqual(SAFETY.scan_blob(name, b'{}'), 'runtime/secret-like path')

    def test_synthetic_secret_detected_and_plain_docs_allowed(self):
        synthetic = ('github_' + 'pat_' + 'a' * 50).encode()
        self.assertEqual(SAFETY.scan_blob('notes.md', synthetic), 'secret-looking content')
        self.assertIsNone(SAFETY.scan_blob('notes.md', b'Keep passwords outside Git.'))

    def test_additional_credential_formats(self):
        candidates = [
            '-----BEGIN PGP ' + 'PRIVATE KEY BLOCK-----',
            'eyJ' + 'a' * 20 + '.' + 'b' * 20 + '.' + 'c' * 20,
            '-'.join(['abcd', 'efgh', 'ijkl', 'mnop']),
            'https://' + 'owner:credential@example.invalid',
        ]
        for value in candidates:
            self.assertEqual(SAFETY.scan_blob('notes.md', value.encode()), 'secret-looking content')

    def test_json_credential_assignments(self):
        for key in ['password', 'api_key', 'access_token', 'auth_token',
                    'homeassistant_token', 'device-token', 'token']:
            value = json.dumps({key: 'synthetic-' + 'Q' * 40}).encode()
            self.assertEqual(SAFETY.scan_blob('notes.json', value), 'secret-looking content', key)

    def test_password_punctuation_and_env_comments(self):
        values = [json.dumps({'password': 'synthetic!' + 'Q' * 40}),
                  'PASSWORD=' + 'Q' * 40 + ' # local account']
        for value in values:
            self.assertEqual(SAFETY.scan_blob('notes.txt', value.encode()), 'secret-looking content')

    def test_git_modes_refuse_symlinks_and_submodules(self):
        for mode in ['120000', '160000']:
            with self.assertRaises(ValueError):
                SAFETY.check_entry('safe.txt', mode, b'harmless')


if __name__ == '__main__':
    unittest.main()
