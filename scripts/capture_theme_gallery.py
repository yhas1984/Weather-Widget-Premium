#!/usr/bin/env python3
"""Capture the real Premium widget renderer for the README theme gallery."""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from pathlib import Path
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/weather-widget-premium-gallery")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QPoint, QPointF
from PyQt6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient
from PyQt6.QtWidgets import QApplication

from weather_widget_v6.models import DailyForecast, HourlyForecast, WeatherData
from weather_widget_v6.widget import PremiumWeatherWidget


def gallery_weather() -> WeatherData:
    now = datetime.now().astimezone().replace(minute=0, second=0, microsecond=0)
    hourly_codes = (0, 1, 2, 2, 3, 61, 61, 2, 1, 0, 0, 1)
    hourly_temperatures = (30, 29, 29, 28, 28, 27, 26, 26, 25, 24, 24, 23)
    hourly = [
        HourlyForecast(
            time=now + timedelta(hours=index),
            temperature=temperature,
            apparent_temperature=temperature + 1,
            precipitation_probability=(0, 0, 5, 8, 18, 42, 55, 25, 10, 5, 0, 0)[index],
            weather_code=hourly_codes[index],
            is_day=index < 10,
        )
        for index, temperature in enumerate(hourly_temperatures)
    ]
    daily = [
        DailyForecast(
            date=now + timedelta(days=index),
            temperature_max=max_temp,
            temperature_min=min_temp,
            precipitation_probability_max=rain,
            weather_code=code,
        )
        for index, (max_temp, min_temp, rain, code) in enumerate(
            ((30, 20, 5, 0), (31, 19, 18, 2), (31, 18, 8, 1), (29, 19, 35, 61), (27, 23, 45, 3))
        )
    ]
    return WeatherData(
        city="Valencia, Comunitat Valenciana",
        latitude=39.4698,
        longitude=-0.3764,
        temperature=30,
        apparent_temperature=31,
        humidity=40,
        wind_speed=9,
        pressure=1014,
        cloud_cover=8,
        precipitation=0,
        precipitation_probability=0,
        weather_code=0,
        is_day=True,
        timezone="Europe/Madrid",
        updated_at=datetime.now().astimezone(),
        hourly=hourly,
        daily=daily,
    )


def paint_desktop(canvas: QImage, theme_index: int) -> None:
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    background = QLinearGradient(0, 0, canvas.width(), canvas.height())
    background.setColorAt(0, QColor(31, 38, 52))
    background.setColorAt(1, QColor(7, 10, 17))
    painter.fillRect(canvas.rect(), background)
    glow = QRadialGradient(QPointF(70 + theme_index * 35, 70), 260)
    glow.setColorAt(0, QColor(54, 121, 164, 105))
    glow.setColorAt(1, QColor(18, 29, 48, 0))
    painter.fillRect(canvas.rect(), glow)
    painter.end()


def capture_theme(theme: str, output: Path, theme_index: int) -> None:
    widget = PremiumWeatherWidget()
    widget.startup_timer.stop()
    widget.animation_timer.stop()
    widget.position_timer.stop()
    widget.weather_timer.stop()
    widget.weather = gallery_weather()
    widget.loading = False
    widget.offline_message = ""
    widget.expanded = True
    widget.current_height = widget.target_height = float(widget.EXPANDED)
    widget.settings.update({"theme": theme, "opacity": 0.68, "animations": True, "units": "metric"})
    widget.resize(widget.WIDTH, widget.EXPANDED)

    canvas = QImage(440, 600, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor(8, 11, 18))
    paint_desktop(canvas, theme_index)
    painter = QPainter(canvas)
    widget.render(painter, QPoint(24, 22))
    painter.end()
    if not canvas.save(str(output), "PNG"):
        raise RuntimeError(f"No se pudo guardar {output}")
    widget.close()


def main() -> int:
    app = QApplication.instance() or QApplication([])
    output_dir = ROOT / "docs" / "screenshots"
    output_dir.mkdir(parents=True, exist_ok=True)
    for index, theme in enumerate(("Atmospheric", "Glass", "Minimal", "Pearl")):
        capture_theme(theme, output_dir / f"theme-{theme.lower()}.png", index)
    app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
