"""Private catalog persistence and failure-path regressions, no live data."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from server import Store
from integrations import SourceUnavailable
from recipe_catalog import RecipeCatalog, CatalogError


def recipe(i=0):
    return dict(title='Soup '+str(i), ingredients=['1 cup water'], steps=['Simmer.'],
                url='https://example.com/soup'+str(i), notes='Personal note', tags=['Dinner'])


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name)
        self.catalog=RecipeCatalog(self.store)

    def test_migration_and_saved_never_evicted(self):
        legacy=dict(recipe(),id='012345abcdef')
        self.store.write('recipes',[legacy])
        self.assertTrue(self.catalog.get(legacy['id'])['saved'])
        for i in range(1,10):
            self.catalog.create(recipe(i),saved=False)
        rows=self.catalog.read()
        self.assertEqual(len(rows),6)
        self.assertTrue(self.catalog.get(legacy['id'])['saved'])
        self.assertEqual(sum(not r['saved'] for r in rows),5)
        listing=self.catalog.listing()['recipes']
        self.assertTrue(all('steps' not in r and 'ingredients' not in r and 'notes' not in r for r in listing))

    def test_larger_legacy_recipes_survive_migration_and_edits(self):
        legacy=dict(recipe(),id='012345abcdef',yield_='unused')
        legacy['yield']='x'*100
        legacy['steps']=['x'*2000]*13
        self.store.write('recipes',[legacy])
        loaded=self.catalog.get(legacy['id'])
        self.assertEqual(loaded['steps'],legacy['steps'])
        self.catalog.create(recipe(1))
        self.assertEqual(self.catalog.get(legacy['id'])['yield'],legacy['yield'])
        changed=self.catalog.change(legacy['id'],{'revision':1,'recipe':dict(loaded,title='Legacy edited')})
        self.assertEqual(changed['steps'],legacy['steps'])
        self.assertEqual(RecipeCatalog(Store(self.temp.name)).get(legacy['id'])['title'],'Legacy edited')
        with self.assertRaises(CatalogError):self.catalog.create(dict(recipe(2),steps=legacy['steps']))

    def test_crud_persistence_revisions_and_reimport(self):
        original=self.catalog.create(recipe(),saved=False)
        saved=self.catalog.change(original['id'],{'revision':1,'saved':True})
        edited=self.catalog.change(saved['id'],{'revision':2,'recipe':dict(recipe(),title='My soup',notes='<script>personal</script>')})
        self.assertEqual(RecipeCatalog(Store(self.temp.name)).get(edited['id'])['title'],'My soup')
        self.assertEqual(self.catalog.create(recipe(),saved=False),edited)
        for delete in (True,False):
            with self.assertRaises(CatalogError) as ctx:
                self.catalog.change(edited['id'],{'revision':2},delete)
            self.assertEqual(ctx.exception.status,409)
        self.catalog.change(edited['id'],{'revision':3},True)
        with self.assertRaises(CatalogError) as ctx:self.catalog.get(edited['id'])
        self.assertEqual(ctx.exception.status,404)

    def test_corruption_is_preserved(self):
        path=Path(self.temp.name)/'recipes.json'
        for bad in [b'bad json',b'{}',b'[{}]',json.dumps([dict(recipe(),id='012345abcdef',saved='yes')]).encode()]:
            path.write_bytes(bad)
            with self.assertRaises(SourceUnavailable):self.catalog.create(recipe())
            self.assertEqual(path.read_bytes(),bad)

    def test_limits_fail_without_evicting_saved(self):
        for i in range(8):self.catalog.create(recipe(i))
        with patch('recipe_catalog.MAX_SAVED',8):
            with self.assertRaises(CatalogError):self.catalog.create(recipe(9))
            self.assertEqual(len(self.catalog.read()),8)
        for changes in [dict(title=''),dict(steps=[]),dict(tags='Dinner'),dict(url='http://localhost'),dict(notes='x'*4001),dict(steps=['x'*2000]*20)]:
            with self.assertRaises(ValueError):self.catalog.create(dict(recipe(9),**changes))
        self.assertEqual(len(self.catalog.read()),8)

    def test_failed_atomic_write_preserves_data(self):
        self.catalog.create(recipe())
        before=(Path(self.temp.name)/'recipes.json').read_bytes()
        with patch.object(self.store,'write',side_effect=OSError('disk full')):
            with self.assertRaises(SourceUnavailable):self.catalog.create(recipe(1))
        self.assertEqual((Path(self.temp.name)/'recipes.json').read_bytes(),before)
