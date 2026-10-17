"""HA shopping readback, phone edits and ambiguous create/retry contracts."""
import copy
import tempfile
import unittest

from integrations import SourceUnavailable
from server import Store, CATEGORIES, QUICK_ADD
from shopping import ShoppingBridge


class FakeHA:
    def __init__(self):
        self.rows, self.adds = [], 0
        self.fail_after_add = self.fail_before_add = False
        self.concurrent_same_name = False

    def request(self, path, body=None):
        if path == '/api/shopping_list':
            return copy.deepcopy(self.rows)
        if path == '/api/shopping_list/item':
            self.adds += 1
            if self.fail_before_add:
                raise SourceUnavailable('offline')
            row = {'id': f'{self.adds:032x}', 'name': body['name'], 'complete': False}
            self.rows.append(row)
            if self.concurrent_same_name:
                self.rows.append({'id': 'c' * 32, 'name': body['name'], 'complete': False})
            if self.fail_after_add:
                raise SourceUnavailable('lost response')
            return copy.deepcopy(row)
        if path.startswith('/api/shopping_list/item/'):
            next(r for r in self.rows if r['id'] == path.rsplit('/', 1)[-1])['complete'] = body['complete']
            return {}
        if path == '/api/services/todo/remove_item':
            assert body['entity_id'] == 'todo.shopping_list'
            self.rows[:] = [r for r in self.rows if r['id'] != body['item']]
            return []
        if path == '/api/shopping_list/clear_completed':
            self.rows[:] = [r for r in self.rows if not r['complete']]
            return {}
        raise AssertionError('Unexpected operation')


class ShoppingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store, self.ha = Store(self.temp.name), FakeHA()
        self.bridge = ShoppingBridge(self.ha, self.store, CATEGORIES, QUICK_ADD)

    def add(self, key='a' * 32, name='Apples'):
        return self.bridge.mutate(lambda rows: rows.append({'id': 'f' * 12, 'name': name,
                                  'qty': '2', 'category': 'Produce', 'notes': 'ripe', 'done': False}), key)

    def test_add_readback_metadata_and_idempotent_retry(self):
        result = self.add()
        self.assertEqual(result['source'], 'homeassistant')
        self.assertEqual(result['items'][0]['qty'], '2')
        self.assertEqual(result['items'][0]['notes'], 'ripe')
        self.assertNotIn(self.ha.rows[0]['id'], str(result))
        self.add()
        self.assertEqual(self.ha.adds, 1)
        with self.assertRaises(ValueError):
            self.add(name='Different request')

    def test_ambiguous_add_survives_restart_without_duplicate(self):
        self.ha.fail_after_add = True
        with self.assertRaises(SourceUnavailable):
            self.add()
        self.bridge = ShoppingBridge(self.ha, self.store, CATEGORIES, QUICK_ADD)
        self.ha.fail_after_add = False
        result = self.add()
        self.assertEqual(len(result['items']), 1)
        self.assertEqual(self.ha.adds, 1)

    def test_unknown_add_is_not_blindly_repeated(self):
        self.ha.fail_before_add = True
        for _ in range(2):
            with self.assertRaises(SourceUnavailable):
                self.add()
        self.assertEqual(self.ha.adds, 1)

    def test_concurrent_same_name_phone_add_uses_exact_response_id(self):
        self.ha.concurrent_same_name = True
        result = self.add()
        self.assertEqual(result['addedId'], self.bridge.alias(self.ha.rows[0]['id']))
        self.assertNotEqual(result['addedId'], result['items'][-1]['id'])
        self.assertIsNone(self.bridge.state()['pending'])
        self.ha.concurrent_same_name = False
        self.add(key='b' * 32, name='Milk')
        self.assertEqual(self.ha.adds, 2)

    def test_ack_without_readback_never_reports_success(self):
        original = self.ha.request

        def inconsistent(path, body=None):
            if path == '/api/shopping_list/item':
                result = original(path, body)
                self.ha.rows.clear()
                return result
            return original(path, body)

        self.ha.request = inconsistent
        for _ in range(2):
            with self.assertRaises(SourceUnavailable):
                self.add()
        self.assertEqual(self.ha.adds, 1)

    def test_phone_rename_after_ack_uses_identity_not_name(self):
        original = self.ha.request

        def rename_after_ack(path, body=None):
            result = original(path, body)
            if path == '/api/shopping_list/item':
                self.ha.rows[-1]['name'] = 'Renamed on phone'
            return result

        self.ha.request = rename_after_ack
        result = self.add()
        self.assertEqual(result['items'][0]['name'], 'Renamed on phone')
        self.assertIsNone(self.bridge.state()['pending'])
        self.add(key='b' * 32, name='Milk')
        self.assertEqual(self.ha.adds, 2)

    def test_phone_edits_completion_and_removal(self):
        row = self.add()['items'][0]
        self.bridge.mutate(lambda rows: rows[0].update(done=True))
        self.assertTrue(self.ha.rows[0]['complete'])
        self.ha.rows.append({'id': 'b' * 32, 'name': 'Phone addition', 'complete': False})
        result = self.bridge.get(force=True)
        self.assertEqual(result['items'][1]['category'], 'Other')
        self.bridge.mutate(lambda rows: rows.__setitem__(slice(None), [i for i in rows if i['id'] != row['id']]))
        self.assertEqual([r['name'] for r in self.ha.rows], ['Phone addition'])

    def test_malformed_upstream_fails_closed(self):
        self.ha.rows = [{'id': '../not-an-id', 'name': 'bad', 'complete': False}]
        with self.assertRaises(SourceUnavailable):
            self.bridge.get()
