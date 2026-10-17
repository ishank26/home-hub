"""Bridge one existing HA shopping list, keeping tablet details in private storage."""
import copy
import hashlib
import json
import re
import threading
import time
from datetime import datetime

from integrations import SourceUnavailable


class ShoppingBridge:
    def __init__(self, ha, store, categories, quick_add):
        self.ha, self.store = ha, store
        self.categories, self.quick_add = list(categories), quick_add
        self.lock = threading.RLock()
        self.loaded, self.value = 0, None
        self.health = {'state': 'failed', 'updatedAt': None}

    @staticmethod
    def alias(uid):
        return hashlib.sha256(uid.encode()).hexdigest()[:12]

    @staticmethod
    def signature(item):
        value = {k: item.get(k, '') for k in ('name', 'qty', 'notes', 'category')}
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    def raw(self):
        rows = self.ha.request('/api/shopping_list')
        if not isinstance(rows, list) or len(rows) > 1000:
            raise SourceUnavailable('Shopping list unavailable')
        seen = set()
        for row in rows:
            if (not isinstance(row, dict) or not re.fullmatch(r'[a-f0-9]{32}', str(row.get('id', '')))
                    or type(row.get('complete')) is not bool or not isinstance(row.get('name'), str)
                    or len(row['name']) > 1000 or row['id'] in seen):
                raise SourceUnavailable('Shopping list unavailable')
            seen.add(row['id'])
        return rows

    def state(self):
        value = self.store.read('shopping-ha-details', {'details': {}, 'completed': {}, 'pending': None})
        if not isinstance(value, dict) or not all(isinstance(value.get(k), dict) for k in ('details', 'completed')):
            raise SourceUnavailable('Shopping details unavailable')
        return value

    def resolve(self, rows, state):
        pending = state.get('pending')
        if pending:
            if pending.get('id'):
                matches = [r for r in rows if r['id'] == pending['id']]
            else:
                matches = [r for r in rows if r['id'] not in pending['before'] and r['name'] == pending['name']]
            if len(matches) == 1:
                state['details'][self.alias(matches[0]['id'])] = pending['details']
                state['completed'][pending['key']] = {'id': matches[0]['id'], 'signature': pending['signature']}
                state['pending'] = None
                self.save(state)

    def save(self, state):
        # Bound local receipts as well as upstream data. Never store credentials.
        state['completed'] = dict(list(state['completed'].items())[-256:])
        state['details'] = dict(list(state['details'].items())[-1000:])
        self.store.write('shopping-ha-details', state)

    def render(self, rows, state):
        items = []
        for row in rows:
            key = self.alias(row['id'])
            meta = state['details'].get(key, {})
            category = meta.get('category', 'Other')
            if category not in self.categories:
                category = 'Other'
            items.append({'id': key, 'name': row['name'], 'done': row['complete'],
                          'qty': meta.get('qty', ''), 'notes': meta.get('notes', ''),
                          'category': category, 'created': meta.get('created', '')})
        return {'source': 'homeassistant', 'updatedAt': datetime.now().astimezone().isoformat(),
                'items': items, 'categories': self.categories, 'quickAdd': self.quick_add}

    def get(self, force=False):
        with self.lock:
            if not force and self.value is not None and time.monotonic() - self.loaded < 15:
                return self.value
            try:
                rows, state = self.raw(), self.state()
                self.resolve(rows, state)
                value = self.render(rows, state)
            except SourceUnavailable:
                self.health = {'state': 'stale' if self.value else 'failed',
                               'updatedAt': self.value['updatedAt'] if self.value else None}
                raise
            self.value, self.loaded = value, time.monotonic()
            self.health = {'state': 'current', 'updatedAt': value['updatedAt']}
            return value

    def mutate(self, change, request_key=None):
        with self.lock:
            rows, state = self.raw(), self.state()
            self.resolve(rows, state)
            old = self.render(rows, state)
            items = copy.deepcopy(old['items'])
            change(items)
            before = {i['id']: i for i in old['items']}
            after = {i['id']: i for i in items}
            added = [i for i in items if i['id'] not in before]
            deleted = [i for i in old['items'] if i['id'] not in after]
            changed = [i for i in items if i['id'] in before and i != before[i['id']]]
            remote = {self.alias(r['id']): r['id'] for r in rows}
            added_id = None
            try:
                if added:
                    if len(added) != 1 or deleted or changed or not re.fullmatch(r'[a-f0-9]{32}', request_key or ''):
                        raise ValueError('Invalid shopping request')
                    if request_key in state['completed']:
                        if state['completed'][request_key]['signature'] != self.signature(added[0]):
                            raise ValueError('Shopping request key was reused')
                        result = self.get(force=True)
                        added_id = self.alias(state['completed'][request_key]['id'])
                        if not any(i['id'] == added_id for i in result['items']):
                            raise SourceUnavailable('Previously added item is no longer on the shared list')
                        return dict(result, addedId=added_id)
                    if state.get('pending'):
                        raise SourceUnavailable('Previous shopping add is unconfirmed; check the HA list before retrying')
                    item = added[0]
                    state['pending'] = {'key': request_key, 'name': item['name'], 'signature': self.signature(item),
                                        'before': [r['id'] for r in rows],
                                        'details': {k: item.get(k, '') for k in ('qty', 'notes', 'category', 'created')}}
                    self.save(state)
                    # A timeout is ambiguous: keep the receipt and never repeat
                    # this POST until a read proves which item was added.
                    result = self.ha.request('/api/shopping_list/item', {'name': item['name']})
                    if (not isinstance(result, dict) or not re.fullmatch(r'[a-f0-9]{32}', str(result.get('id', '')))
                            or result.get('id') in state['pending']['before']
                            or result.get('name') != item['name'] or result.get('complete') is not False):
                        raise SourceUnavailable('Shopping add is not yet confirmed')
                    state['details'][self.alias(result['id'])] = state['pending']['details']
                    state['pending']['id'] = result['id']
                    added_id = self.alias(result['id'])
                    self.save(state)
                elif deleted:
                    if changed:
                        raise ValueError('Invalid shopping request')
                    if len(deleted) == 1:
                        self.ha.request('/api/services/todo/remove_item',
                                        {'entity_id': 'todo.shopping_list', 'item': remote[deleted[0]['id']]})
                    elif all(i['done'] for i in deleted) and {i['id'] for i in deleted} == {i['id'] for i in old['items'] if i['done']}:
                        self.ha.request('/api/shopping_list/clear_completed', {})
                    else:
                        raise ValueError('Invalid shopping request')
                elif changed:
                    if len(changed) != 1 or type(changed[0].get('done')) is not bool:
                        raise ValueError('Invalid shopping request')
                    item = changed[0]
                    self.ha.request('/api/shopping_list/item/' + remote[item['id']], {'complete': item['done']})
                result = self.get(force=True)
                current = {i['id']: i for i in result['items']}
                if added_id and added_id not in current:
                    raise SourceUnavailable('Shopping add is not yet confirmed')
                if any(i['id'] in current for i in deleted) or any(current.get(i['id'], {}).get('done') != i['done'] for i in changed):
                    raise SourceUnavailable('Shopping change is not yet confirmed')
                return dict(result, addedId=added_id) if added_id else result
            finally:
                self.loaded = 0
