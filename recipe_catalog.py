"""Bounded private recipe catalog. Call mutations while holding the server lock."""
import json
import re
import uuid
from recipes import safe_url
from integrations import SourceUnavailable

MAX_RECIPE = 24576
MAX_CATALOG = 20 * 1024 * 1024
MAX_LEGACY_RECIPE = 3 * 1024 * 1024
MAX_SAVED = 200
MAX_RECENT = 5


class CatalogError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def content(value, legacy=False):
    if not isinstance(value, dict):
        raise CatalogError('Recipe must be an object')
    result = {}
    for key, limit in [('title', 200), ('description', 2000), ('yield', 100 if legacy else 80),
                       ('totalTime', 80), ('notes', 4000), ('url', 4096)]:
        text = value.get(key, '')
        if not isinstance(text, str) or len(text) > limit or re.search(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', text):
            raise CatalogError('Invalid recipe ' + key)
        result[key] = text.strip()
    if not result['title']:
        raise CatalogError('Give the recipe a title')
    if result['url']:
        result['url'] = safe_url(result['url'])
    for key, count, limit in [('ingredients', 100, 500), ('steps', 100, 2000), ('tags', 12, 50)]:
        lines = value.get(key, [])
        if not isinstance(lines, list) or len(lines) > count:
            raise CatalogError('Invalid recipe ' + key)
        if any(not isinstance(line, str) or len(line) > limit or re.search(r'[\x00-\x1f\x7f]', line) for line in lines):
            raise CatalogError('Invalid recipe ' + key)
        result[key] = [line.strip() for line in lines if line.strip()]
        if key != 'tags' and not result[key]:
            raise CatalogError('Add at least one ' + ('ingredient' if key == 'ingredients' else 'step'))
    if len(json.dumps(result, ensure_ascii=True).encode()) > (MAX_LEGACY_RECIPE if legacy else MAX_RECIPE):
        raise CatalogError('Recipe is too large (24 KB maximum)')
    return result


class RecipeCatalog:
    def __init__(self, store):
        self.store = store

    def read(self):
        # Fail closed: Store.read's forgiving default would overwrite damaged data.
        try:
            with (self.store.dir / 'recipes.json').open('rb') as handle:
                raw = handle.read(MAX_CATALOG + 1)
            if len(raw) > MAX_CATALOG:
                raise ValueError()
            rows = json.loads(raw)
            if not isinstance(rows, list) or len(rows) > MAX_SAVED + MAX_RECENT:
                raise ValueError()
            result, ids = [], set()
            for row in rows:
                if not isinstance(row, dict) or not re.fullmatch('[a-f0-9]{12}', str(row.get('id', ''))) or row['id'] in ids:
                    raise ValueError()
                ids.add(row['id'])
                legacy = row.get('legacy') is True or ('revision' not in row and 'saved' not in row)
                data = content(row, legacy=legacy)
                if legacy:
                    data['legacy'] = True
                saved, revision = row.get('saved', True), row.get('revision', 1)
                if type(saved) is not bool or type(revision) is not int or revision < 1:
                    raise ValueError()
                result.append(dict(data, id=row['id'], saved=saved, revision=revision))
            if sum(r['saved'] for r in result) > MAX_SAVED or sum(not r['saved'] for r in result) > MAX_RECENT:
                raise ValueError()
            return result
        except FileNotFoundError:
            return []
        except (OSError, ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            raise SourceUnavailable('Recipe catalog could not be read; existing data has been preserved') from None

    def write(self, rows):
        if sum(r['saved'] for r in rows) > MAX_SAVED:
            raise CatalogError('Catalog is full (200 saved recipes); delete one before saving another', 409)
        if len(json.dumps(rows, indent=1, sort_keys=True).encode()) > MAX_CATALOG:
            raise CatalogError('Recipe catalog storage limit reached', 409)
        try:
            self.store.write('recipes', rows)
        except OSError:
            raise SourceUnavailable('Recipe could not be saved; check server storage and retry') from None

    def listing(self):
        return {'recipes': [{k: r[k] for k in ('id', 'title', 'url', 'yield', 'totalTime', 'tags', 'saved', 'revision')}
                            for r in self.read()], 'maxSaved': MAX_SAVED}

    def get(self, recipe_id):
        return self.find(self.read(), recipe_id)

    @staticmethod
    def find(rows, recipe_id):
        row = next((r for r in rows if r['id'] == recipe_id), None)
        if row is None:
            raise CatalogError('Recipe no longer exists', 404)
        return row

    def create(self, value, saved=True):
        data, rows = content(value), self.read()
        # Reimport never overwrites an existing recipe or its personal edits.
        if data['url']:
            previous = next((r for r in rows if r['url'] == data['url']), None)
            if previous:
                if saved:
                    raise CatalogError('This source is already in your catalog. Open that recipe to edit or save it.', 409)
                return previous
        row = dict(data, id=uuid.uuid4().hex[:12], saved=saved, revision=1)
        rows.insert(0, row)
        recent = [r for r in rows if not r['saved']][:MAX_RECENT]
        self.write([r for r in rows if r['saved'] or r in recent])
        return row

    def change(self, recipe_id, body, delete=False):
        rows = self.read()
        old = self.find(rows, recipe_id)
        if type(body.get('revision')) is not int or body['revision'] != old['revision']:
            raise CatalogError('Recipe changed in another window. Reopen it before editing or deleting.', 409)
        if delete:
            self.write([r for r in rows if r['id'] != recipe_id])
            return {'deleted': recipe_id}
        if not set(body) <= {'revision', 'recipe', 'saved'} or (body.get('saved', True) is not True):
            raise CatalogError('Invalid recipe update')
        data = content(body['recipe'], legacy=old.get('legacy', False)) if 'recipe' in body else {k: v for k, v in old.items() if k not in ('id', 'revision', 'saved')}
        if old.get('legacy'):
            data['legacy'] = True
        row = dict(data, id=recipe_id, saved=True, revision=old['revision'] + 1)
        self.write([row if r['id'] == recipe_id else r for r in rows])
        return row
