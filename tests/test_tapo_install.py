"""Credential-free archive validation for the privileged Tapo installer."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('tapo_install', Path(__file__).resolve().parents[1] / 'scripts/install-tapo-control.py')
install = importlib.util.module_from_spec(spec)
spec.loader.exec_module(install)


class TapoArchiveTests(unittest.TestCase):
    def archive(self, extra=(), version='7.2.8'):
        output = io.BytesIO()
        manifest = json.dumps({'domain': 'tapo_control', 'version': version,
                              'requirements': ['pytapo==3.4.26', 'python-kasa[speedups]>=0.10.2']}).encode()
        with tarfile.open(fileobj=output, mode='w:gz') as target:
            for name, content, kind in [('manifest.json', manifest, tarfile.REGTYPE), *extra]:
                member = tarfile.TarInfo(install.PREFIX + name)
                member.type = kind
                if kind == tarfile.SYMTYPE:
                    member.linkname = '/etc/passwd'
                else:
                    member.size = len(content)
                target.addfile(member, io.BytesIO(content))
        return output.getvalue()

    def validate(self, data):
        with patch.object(install, 'ARCHIVE_SHA256', hashlib.sha256(data).hexdigest()):
            return install.component_files(data)

    def test_valid_component_preserves_content(self):
        files = self.validate(self.archive([('__init__.py', b'# synthetic component', tarfile.REGTYPE)]))
        self.assertEqual(files['__init__.py'], b'# synthetic component')
        self.assertEqual(set(files), {'manifest.json', '__init__.py'})

    def test_wrong_digest_fails_before_opening_archive(self):
        with self.assertRaisesRegex(ValueError, 'hash mismatch'):
            install.component_files(b'not the pinned archive')

    def test_traversal_and_symlink_members_rejected(self):
        for name, kind in [('../escape', tarfile.REGTYPE), ('/escape', tarfile.REGTYPE), ('escape', tarfile.SYMTYPE)]:
            with self.subTest(name=name, kind=kind), self.assertRaises(ValueError):
                self.validate(self.archive([(name, b'x', kind)]))

    def test_duplicate_and_wrong_version_rejected(self):
        with self.assertRaises(ValueError):
            self.validate(self.archive([('manifest.json', b'{}', tarfile.REGTYPE)]))
        with self.assertRaisesRegex(ValueError, 'manifest'):
            self.validate(self.archive(version='999.0'))

    def test_large_component_rejected(self):
        with self.assertRaisesRegex(ValueError, 'member'):
            self.validate(self.archive([('big.py', b'x' * 4_000_001, tarfile.REGTYPE)]))

    def test_privacy_filter_suppresses_formatted_tokens_and_tracebacks(self):
        import logging
        import sys
        logger = logging.getLogger('synthetic-tapo-install-test')
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        logger.addHandler(handler)
        namespace = {'logging': logging, 'LOGGER': logger}
        try:
            exec(install.PRIVATE_LOG_FILTER, namespace)
            try:
                raise RuntimeError('synthetic-private-exception')
            except RuntimeError:
                logger.error('request /stok=%s/ds', 'synthetic-session', exc_info=sys.exc_info())
            logger.debug('synthetic-debug-payload')
            value = output.getvalue()
            self.assertIn('suppressed for privacy', value)
            for forbidden in ('synthetic-session', '/stok=', 'synthetic-private-exception', 'Traceback', 'synthetic-debug-payload'):
                self.assertNotIn(forbidden, value)
        finally:
            logger.removeHandler(handler)
            logger.filters.clear()

    def test_privacy_patch_requires_exact_logger_anchor(self):
        with self.assertRaisesRegex(ValueError, 'anchor'):
            install.privacy_patch({'const.py': b'# changed upstream'})

    def test_pinned_source_patch_blocks_framework_exception_disclosure(self):
        import ast
        if not install.ARCHIVE.exists():
            self.skipTest('Private source archive not downloaded on this machine')
        files=install.privacy_patch(install.component_files(install.ARCHIVE.read_bytes()))
        for name in ('const.py','__init__.py'):
            compile(files[name],name,'exec')
        raises=[]
        for node in ast.walk(ast.parse(files['__init__.py'])):
            if isinstance(node,ast.Raise) and isinstance(node.exc,ast.Call) and isinstance(node.exc.func,ast.Name) and node.exc.func.id in ('ConfigEntryAuthFailed','ConfigEntryNotReady'):
                raises.append(node)
                self.assertTrue(all(isinstance(arg,ast.Constant) for arg in node.exc.args))
                self.assertIsInstance(node.cause,ast.Constant)
                self.assertIsNone(node.cause.value)
        self.assertEqual(len(raises),12)
