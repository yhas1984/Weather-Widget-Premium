"""Exercise desktop identity lookup with isolated XDG installation paths."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from weather_widget_v6.main import _desktop_file_id


class DesktopIdentityTests(unittest.TestCase):
    def test_uninstalled_source_does_not_advertise_missing_desktop_entry(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {
                "XDG_DATA_HOME": str(Path(directory) / "user"),
                "XDG_DATA_DIRS": str(Path(directory) / "system"),
            }):
                self.assertEqual(_desktop_file_id(), "")

    def test_user_and_system_installations_keep_premium_identity(self):
        for location in ("user", "system"):
            with self.subTest(location=location), tempfile.TemporaryDirectory() as directory:
                entry = Path(directory) / location / "applications" / "weather-widget-premium.desktop"
                entry.parent.mkdir(parents=True)
                entry.write_text(
                    "[Desktop Entry]\nType=Application\nName=Weather Widget Premium\n"
                    "Exec=weather-widget-premium\n", encoding="utf-8"
                )
                with patch.dict(os.environ, {
                    "XDG_DATA_HOME": str(Path(directory) / "user"),
                    "XDG_DATA_DIRS": str(Path(directory) / "system"),
                }):
                    self.assertEqual(_desktop_file_id(), "weather-widget-premium")
