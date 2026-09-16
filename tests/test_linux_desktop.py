import os
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QWidget

from weather_widget_v6.linux_desktop import (
    configure_desktop_window,
    restack_desktop_window,
    session_backend,
)


class DesktopWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_x11_sets_dock_and_below_together_before_mapping(self):
        widget = QWidget()
        with patch("weather_widget_v6.linux_desktop.session_backend", return_value="x11"):
            configure_desktop_window(widget)
        self.assertFalse(widget.isVisible())
        self.assertFalse(widget.testAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDesktop))
        self.assertTrue(widget.testAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDock))
        self.assertFalse(widget.windowFlags() & Qt.WindowType.WindowStaysOnTopHint)
        self.assertTrue(widget.windowFlags() & Qt.WindowType.WindowStaysOnBottomHint)
        widget.close()

    def test_wayland_retains_bottom_hint_without_x11_desktop_attributes(self):
        widget = QWidget()
        with patch("weather_widget_v6.linux_desktop.session_backend", return_value="wayland"):
            configure_desktop_window(widget)
        self.assertTrue(widget.windowFlags() & Qt.WindowType.WindowStaysOnBottomHint)
        self.assertFalse(widget.testAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDesktop))
        self.assertFalse(widget.testAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDock))
        widget.close()

    def test_x11_lowers_without_raising_or_activating(self):
        widget = Mock()
        widget.isActiveWindow.return_value = False
        with patch("weather_widget_v6.linux_desktop.session_backend", return_value="x11"):
            restack_desktop_window(widget)
        widget.raise_.assert_not_called()
        widget.lower.assert_called_once_with()
        widget.activateWindow.assert_not_called()

    def test_wayland_never_raises_widget(self):
        widget = Mock()
        with patch("weather_widget_v6.linux_desktop.session_backend", return_value="wayland"):
            for active in (True, False):
                widget.isActiveWindow.return_value = active
                restack_desktop_window(widget)
        widget.lower.assert_called_once_with()
        widget.raise_.assert_not_called()

    def test_backend_follows_qt_platform_including_xwayland(self):
        for platform, expected in (("xcb", "x11"), ("dxcb", "x11"), ("wayland", "wayland"), ("wayland-egl", "wayland"), ("offscreen", "offscreen")):
            with self.subTest(platform=platform), patch("weather_widget_v6.linux_desktop.QGuiApplication.platformName", return_value=platform):
                self.assertEqual(session_backend(), expected)
