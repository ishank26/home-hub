"""Pinned optional static app: no downloads or live browser data in unit tests."""
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import recipe_tracker as tracker


class TrackerTests(unittest.TestCase):
    def test_fixed_routes_and_hash_verification(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'assets/test.js';path.parent.mkdir();path.write_bytes(b'console.log("fixture")')
            assets={'assets/test.js':(hashlib.sha256(path.read_bytes()).hexdigest(),'application/javascript')}
            with patch.object(tracker,'ASSETS',assets):
                self.assertEqual(tracker.response('/recipe_tracker/',directory)[1],'text/html; charset=utf-8')
                self.assertEqual(tracker.response('/recipe_tracker/assets/test.js',directory)[0],path.read_bytes())
                self.assertIn(b'getRandomValues',tracker.response('/recipe_tracker/compat.js',directory)[0])
                self.assertIn("connect-src 'none'",tracker.CSP)
                for attack in ['../config.json','assets/../../config.json','%2e%2e/config.json','assets/missing.js']:
                    with self.assertRaises(FileNotFoundError):tracker.response('/recipe_tracker/'+attack,directory)
                path.write_bytes(b'altered build')
                with self.assertRaises(ValueError):tracker.response('/recipe_tracker/',directory)
                with self.assertRaises(ValueError):tracker.response('/recipe_tracker/assets/test.js',directory)
