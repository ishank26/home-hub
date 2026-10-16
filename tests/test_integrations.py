"""Source-contract tests with synthetic HA responses; no credentials or real devices."""
import tempfile
import os
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from integrations import HomeAssistant, SourceUnavailable, private_json


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.adapter = HomeAssistant({'calendars': [{'entity': 'calendar.family', 'name': 'Family'}],
                                      'lights': [{'entity': 'light.kitchen', 'name': 'Kitchen'}],
                                      'contacts': [{'entity': 'binary_sensor.door'}]}, 'synthetic-test-token')

    def test_calendar_overlaps_all_day_and_timezones(self):
        events = [
            {'summary': 'All day', 'start': {'date': '2026-10-15'}, 'end': {'date': '2026-10-16'}},
            {'summary': 'Late event', 'start': {'dateTime': '2026-10-16T01:00:00Z'},
             'end': {'dateTime': '2026-10-16T02:00:00Z'}},
            {'summary': 'Outside', 'start': {'date': '2026-10-12'}, 'end': {'date': '2026-10-13'}}]
        start = datetime.fromisoformat('2026-10-15T00:00:00-04:00')
        end = datetime.fromisoformat('2026-10-16T00:00:00-04:00')
        with patch.object(self.adapter, 'request', return_value=events) as request:
            result = self.adapter.calendar(start, end)
            again = self.adapter.calendar(start, end)
        self.assertEqual(request.call_count, 1)
        self.assertEqual(result, again)
        self.assertEqual([e['title'] for e in result['events']], ['All day', 'Late event'])
        self.assertTrue(result['events'][0]['allDay'])
        self.assertNotIn('calendar.family', str(result))
        self.assertNotIn('synthetic-test-token', str(result))

    def test_unconfigured_does_not_show_sample_calendar_or_devices(self):
        adapter = HomeAssistant({})
        now = datetime.now().astimezone()
        self.assertEqual(adapter.calendar(now, now)['events'], [])
        self.assertEqual(adapter.home()['lights'], [])
        self.assertEqual(adapter.home()['source'], 'unconfigured')

    def test_unknown_state_is_not_closed_or_controllable(self):
        with patch.object(self.adapter, 'request', return_value={'state': 'unavailable'}):
            home = self.adapter.home()
            self.assertIsNone(home['contacts'][0]['open'])
            self.assertFalse(home['lights'][0]['available'])
            with self.assertRaises(SourceUnavailable):
                self.adapter.action({'kind': 'light', 'id': home['lights'][0]['id'], 'on': True})

    def test_malformed_state_is_a_source_failure(self):
        for response in [[], None, {'state': 'on', 'attributes': None}]:
            with self.subTest(response=response), patch.object(self.adapter, 'request', return_value=response):
                with self.assertRaises(SourceUnavailable):
                    self.adapter.home()
                with self.assertRaises(SourceUnavailable):
                    self.adapter.action({'kind': 'light', 'id': self.adapter.alias('light.kitchen'), 'on': True})

    def test_light_is_confirmed_only_after_state_readback(self):
        alias = self.adapter.alias('light.kitchen')
        body = {'kind': 'light', 'id': alias, 'on': True}
        with patch.object(self.adapter, 'request', side_effect=[{'state': 'off'}, [], {'state': 'on'}]) as request:
            self.assertEqual(self.adapter.action(body)['result'], 'confirmed')
            self.assertEqual(request.call_args_list[1].args,
                             ('/api/services/light/turn_on', {'entity_id': 'light.kitchen'}))
        with patch.object(self.adapter, 'request', side_effect=[{'state': 'off'}, [], {'state': 'off'}]):
            with self.assertRaises(SourceUnavailable):
                self.adapter.action(body)
        with patch.object(self.adapter, 'request') as request:
            for invalid in [{'kind': 'scene', 'id': alias}, {'kind': 'light', 'id': 'arbitrary', 'on': True}]:
                with self.assertRaises(ValueError):
                    self.adapter.action(invalid)
            request.assert_not_called()

    def test_outage_marks_old_data_stale_without_fresh_timestamp(self):
        with patch.object(self.adapter, 'request', return_value={'state': 'off'}):
            original = self.adapter.home()
        self.adapter.cache['home'] = (0, original)
        with patch.object(self.adapter, 'request', side_effect=SourceUnavailable('offline')):
            with self.assertRaises(SourceUnavailable):
                self.adapter.home()
        self.assertEqual(self.adapter.health['home']['state'], 'stale')
        self.assertEqual(self.adapter.health['home']['updatedAt'], original['updatedAt'])

    def test_configuration_boundary(self):
        with patch.dict(os.environ, {'http_proxy': 'http://example.com:8080', 'no_proxy': ''}):
            adapter = HomeAssistant({})
            self.assertFalse(any(getattr(handler, 'proxies', {}) for handler in adapter.transport.handlers))
        with self.assertRaises(ValueError):
            HomeAssistant({'url': 'https://example.com'})
        with self.assertRaises(ValueError):
            HomeAssistant({'lights': [{'entity': 'lock.front_door'}]})
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text('{}')
            path.chmod(0o644)
            with self.assertRaises(ValueError):
                private_json(path)
            path.chmod(0o600)
            self.assertEqual(private_json(path), {})
            link = Path(directory) / 'link.json'
            link.symlink_to(path)
            with self.assertRaises(ValueError):
                private_json(link)
