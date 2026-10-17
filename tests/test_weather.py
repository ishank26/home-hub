"""Forecast contracts with generated dates; never calls the provider."""
import copy
import time
import unittest
from unittest.mock import patch

from integrations import SourceUnavailable
from weather import Weather


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.weather = Weather({'latitude': 0, 'longitude': 0, 'name': 'Test town'})
        now = int(time.time())
        self.data = {
            'current': {'time': now, 'temperature_2m': 60, 'weather_code': 0},
            'hourly': {'time': [now + i * 3600 for i in range(24)],
                       'temperature_2m': [60] * 24, 'weather_code': [0] * 24,
                       'precipitation_probability': [20] * 24},
            'daily': {'time': [now + i * 86400 for i in range(7)], 'weather_code': [0] * 7,
                      'temperature_2m_max': [70] * 7, 'temperature_2m_min': [50] * 7,
                      'precipitation_probability_max': [20] * 7}}

    def test_live_shape_and_model_label(self):
        with patch.object(self.weather, 'request', return_value=self.data) as request:
            first = self.weather.get()
            self.assertEqual(first, self.weather.get())
        self.assertEqual(request.call_count, 1)
        self.assertEqual(len(first['daily']), 7)
        self.assertEqual(len(first['hourly']), 12)
        self.assertIsNone(first['observedAt'])
        self.assertIn('model estimate', first['currentLabel'])
        self.assertNotIn('humidity', first['current'])

    def test_failure_preserves_success_time_and_backs_off(self):
        with patch.object(self.weather, 'request', return_value=self.data):
            value = self.weather.get()
        self.weather.loaded = 0
        with patch.object(self.weather, 'request', side_effect=OSError('private URL')) as request:
            for _ in range(2):
                with self.assertRaisesRegex(SourceUnavailable, '^Weather unavailable'):
                    self.weather.get()
        self.assertEqual(request.call_count, 1)
        self.assertEqual(self.weather.health, {'state': 'stale', 'updatedAt': value['forecastAt']})

    def test_incomplete_or_nonfinite_forecast_fails_closed(self):
        for broken in [{}, {'current': {}}, copy.deepcopy(self.data)]:
            if 'hourly' in broken:
                broken['hourly']['temperature_2m'][0] = float('nan')
            with patch.object(self.weather, 'request', return_value=broken):
                self.weather.retry_at = 0
                with self.assertRaises(SourceUnavailable):
                    self.weather.get()

    def test_location_validation_and_unconfigured(self):
        self.assertEqual(Weather(None).get()['source'], 'unconfigured')
        for invalid in [None, True, 1000, float('nan')]:
            with self.assertRaises(ValueError):
                Weather({'latitude': invalid, 'longitude': 0})
