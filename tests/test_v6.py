import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import requests

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtCore import QEventLoop, QTimer
from PyQt6.QtWidgets import QApplication

import weather_widget_v6.config as config
from weather_widget_v6.city_search import CitySearchDialog
from weather_widget_v6.models import DailyForecast, HourlyForecast, WeatherData
from weather_widget_v6.service import LocationUnavailableError, WeatherService
from weather_widget_v6.widget import PremiumWeatherWidget
from weather_widget_v6.worker import WeatherWorker


def sample_weather():
    now = datetime.now().astimezone()
    hourly = [HourlyForecast(now + timedelta(hours=i), 20 + i, 19 + i, 10 + i, code, True) for i, code in enumerate((0, 2, 3, 61, 71, 95))]
    daily = [DailyForecast(now + timedelta(days=i), 25 + i, 14 + i, 20, code) for i, code in enumerate((0, 2, 3, 61, 71))]
    return WeatherData("Valencia", 39.47, -.38, 22, 21, 56, 12, 1014, 20, 0, 10, 2, True, "Europe/Madrid", now, hourly, daily)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def api_payload():
    hours = [f"2026-09-13T{hour:02d}:00" for hour in range(10, 22)]
    days = [f"2026-09-{day:02d}" for day in range(13, 18)]
    return {
        "timezone": "Europe/Madrid",
        "current_units": {
            "temperature_2m": "°C", "wind_speed_10m": "km/h", "precipitation": "mm",
        },
        "current": {
            "time": hours[0], "temperature_2m": 22.5, "apparent_temperature": 22.0,
            "relative_humidity_2m": 56, "precipitation": 0.0, "weather_code": 2,
            "cloud_cover": 20, "surface_pressure": 1014.0, "wind_speed_10m": 12.0,
            "is_day": 1,
        },
        "hourly": {
            "time": hours, "temperature_2m": [22 + i for i in range(12)],
            "apparent_temperature": [21 + i for i in range(12)],
            "precipitation_probability": [10 + i for i in range(12)],
            "weather_code": [2] * 12, "is_day": [1] * 12,
        },
        "daily": {
            "time": days, "weather_code": [2] * 5, "temperature_2m_max": [27] * 5,
            "temperature_2m_min": [17] * 5, "precipitation_probability_max": [20] * 5,
            "sunrise": [f"{day}T07:30" for day in days],
            "sunset": [f"{day}T20:15" for day in days],
        },
    }


class ModelAndServiceTests(unittest.TestCase):
    def test_invalid_settings_are_sanitized(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            config.APP_DIR = app_dir
            config.SETTINGS_FILE = app_dir / "settings.json"
            config.CACHE_FILE = app_dir / "cache.json"
            config.SETTINGS_FILE.write_text('{"config_version":"bad","update_minutes":"never","theme":"Unknown","position":["x",2]}')
            settings = config.load_settings()
            self.assertEqual(settings["update_minutes"], 15)
            self.assertEqual(settings["theme"], "Atmospheric")
            self.assertIsNone(settings["position"])

    def test_cache_round_trip_marks_data_stale(self):
        restored = WeatherData.from_dict(sample_weather().to_dict())
        self.assertTrue(restored.stale)
        self.assertEqual(restored.city, "Valencia")
        self.assertEqual(len(restored.hourly), 6)
        self.assertEqual(len(restored.daily), 5)

    def test_incomplete_open_meteo_payload_has_clear_error(self):
        service = WeatherService()
        service.session.get = lambda *args, **kwargs: FakeResponse({"current": {}, "hourly": {}, "daily": {}})
        with self.assertRaisesRegex(ValueError, "Open-Meteo incompleta"):
            service.fetch(1, 2, "Test")

    def test_location_failure_never_silently_falls_back_to_madrid(self):
        service = WeatherService()
        service.session.get = lambda *args, **kwargs: (_ for _ in ()).throw(requests.ConnectionError("offline"))
        with self.assertRaisesRegex(LocationUnavailableError, "Elige una ciudad"):
            service.locate()

    def test_forecast_request_is_bounded_and_uses_selected_units(self):
        captured = {}
        payload = api_payload()
        payload["current_units"] = {
            "temperature_2m": "°F", "wind_speed_10m": "mp/h", "precipitation": "inch",
        }
        service = WeatherService(units="imperial")

        def fake_get(_url, **kwargs):
            captured.update(kwargs["params"])
            return FakeResponse(payload)

        service.session.get = fake_get
        weather = service.fetch(39.47, -0.38, "Valencia")
        self.assertEqual(captured["forecast_hours"], 12)
        self.assertEqual(captured["forecast_days"], 5)
        self.assertEqual(captured["temperature_unit"], "fahrenheit")
        self.assertEqual(captured["wind_speed_unit"], "mph")
        self.assertEqual(weather.temperature_unit, "°F")
        self.assertEqual(weather.wind_speed_unit, "mph")
        self.assertEqual(weather.precipitation_probability, 10)
        self.assertEqual(len(weather.hourly), 12)
        self.assertEqual(len(weather.daily), 5)

    def test_invalid_current_value_is_rejected(self):
        payload = api_payload()
        payload["current"]["relative_humidity_2m"] = None
        service = WeatherService()
        service.session.get = lambda *args, **kwargs: FakeResponse(payload)
        with self.assertRaisesRegex(ValueError, "relative_humidity_2m"):
            service.fetch(39.47, -0.38, "Valencia")

    def test_cache_is_scoped_by_location_and_units(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            config.APP_DIR = app_dir
            config.CACHE_FILE = app_dir / "cache.json"
            valencia = sample_weather()
            config.save_cache(valencia.to_dict())
            madrid = sample_weather()
            madrid.city, madrid.latitude, madrid.longitude = "Madrid", 40.4168, -3.7038
            config.save_cache(madrid.to_dict())
            restored = config.load_cache({"latitude": 39.47, "longitude": -.38}, "metric")
            self.assertEqual(restored["city"], "Valencia")
            self.assertIsNone(config.load_cache({"latitude": 39.47, "longitude": -.38}, "imperial"))

    def test_expired_cache_is_not_restored(self):
        with tempfile.TemporaryDirectory() as directory:
            app_dir = Path(directory)
            config.APP_DIR = app_dir
            config.CACHE_FILE = app_dir / "cache.json"
            payload = sample_weather().to_dict()
            payload["updated_at"] = (datetime.now().astimezone() - timedelta(hours=25)).isoformat()
            config.save_cache(payload)
            self.assertIsNone(config.load_cache({"latitude": 39.47, "longitude": -.38}, "metric"))


class WidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        app_dir = Path(self.temp.name)
        config.APP_DIR = app_dir
        config.SETTINGS_FILE = app_dir / "settings.json"
        config.CACHE_FILE = app_dir / "cache.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_all_themes_render_with_transparent_corners(self):
        widget = PremiumWeatherWidget()
        widget.weather = sample_weather()
        widget.loading = False
        widget.current_height = widget.target_height = float(widget.EXPANDED)
        widget.resize(widget.WIDTH, widget.EXPANDED)
        for theme in widget.THEMES:
            widget.settings["theme"] = theme
            image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(0)
            painter = QPainter(image)
            widget.render(painter)
            painter.end()
            self.assertEqual(image.pixelColor(0, 0).alpha(), 0, theme)
            self.assertGreater(image.pixelColor(widget.width() // 2, 20).alpha(), 0, theme)
        widget.close()

    def test_expand_collapses_immediately_without_animations(self):
        widget = PremiumWeatherWidget()
        widget.settings["animations"] = False
        widget.resize(widget.WIDTH, widget.EXPANDED)
        widget.current_height = float(widget.EXPANDED)
        widget.target_height = float(widget.COLLAPSED)
        widget.animate()
        self.assertEqual(widget.height(), widget.COLLAPSED)
        widget.close()

    def test_zero_opacity_removes_only_decorative_backgrounds(self):
        widget = PremiumWeatherWidget()
        widget.weather = sample_weather()
        widget.loading = False
        widget.settings["opacity"] = 0.0
        widget.current_height = widget.target_height = float(widget.EXPANDED)
        widget.resize(widget.WIDTH, widget.EXPANDED)
        image = QImage(widget.size(), QImage.Format.Format_ARGB32_Premultiplied)
        image.fill(0)
        painter = QPainter(image)
        widget.render(painter)
        painter.end()
        self.assertEqual(image.pixelColor(380, 300).alpha(), 0)
        self.assertGreater(image.pixelColor(63, 120).alpha(), 0)
        widget.close()

    def test_temperature_palette_moves_from_cold_to_hot(self):
        widget = PremiumWeatherWidget()
        cold = widget.temperature_color(-4)
        mild = widget.temperature_color(22)
        hot = widget.temperature_color(38)
        self.assertGreater(cold.blue(), cold.red())
        self.assertLess(abs(mild.red() - mild.blue()), 20)
        self.assertGreater(hot.red(), hot.blue())
        widget.settings["theme"] = "Pearl"
        self.assertLess(widget.temperature_color(22).red(), 80)
        widget.close()

    def test_weather_refresh_does_not_block_ui_thread(self):
        class SlowService:
            def locate(self, _city, _allow_ip=True):
                time.sleep(.15)
                return 1, 2, "Test"

            def fetch(self, _lat, _lon, _city):
                return sample_weather()

        widget = PremiumWeatherWidget()
        widget.service = SlowService()
        ui_tick = []
        loop = QEventLoop()
        QTimer.singleShot(20, lambda: ui_tick.append(True))
        QTimer.singleShot(60, loop.quit)
        widget.refresh_weather()
        loop.exec()
        self.assertTrue(ui_tick)
        self.assertTrue(widget.loading)
        deadline = time.monotonic() + 1
        while widget.loading and time.monotonic() < deadline:
            self.app.processEvents()
            time.sleep(.01)
        self.assertFalse(widget.loading)
        widget.close()

    def test_city_search_shows_specific_location_metadata(self):
        dialog = CitySearchDialog(favorites=[])
        dialog.request_id = 4
        worker = object()
        dialog.workers.add(worker)
        dialog._show_results(worker, 4, [{
            "name": "Valencia",
            "admin1": "Comunitat Valenciana",
            "country": "España",
            "latitude": 39.4698,
            "longitude": -0.3774,
        }])
        self.assertEqual(dialog.results.count(), 1)
        self.assertIn("Comunitat Valenciana", dialog.results.item(0).text())
        self.assertEqual(dialog.selected_location["latitude"], 39.4698)
        self.assertTrue(dialog.use_button.isEnabled())
        dialog.close()

    def test_selected_coordinates_skip_repeated_geocoding(self):
        class ExactService:
            def locate(self, _city):
                raise AssertionError("geocoding should not run")

            def fetch(self, lat, lon, city):
                self.received = (lat, lon, city)
                return sample_weather()

        service = ExactService()
        worker = WeatherWorker(service, "Valencia", {
            "latitude": 39.4698,
            "longitude": -0.3774,
            "label": "Valencia, Comunitat Valenciana",
        })
        worker.run()
        self.assertEqual(service.received, (39.4698, -0.3774, "Valencia, Comunitat Valenciana"))


if __name__ == "__main__":
    unittest.main()
