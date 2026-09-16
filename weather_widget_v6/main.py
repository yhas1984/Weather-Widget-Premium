import os
import signal
import sys

from PyQt6.QtCore import QStandardPaths, QTimer
from PyQt6.QtWidgets import QApplication

from .widget import PremiumWeatherWidget


def _normalize_qt_platform() -> None:
    """Repair distro fallback values such as ``dxcb;xcb`` for stock Qt."""
    configured = os.environ.get("QT_QPA_PLATFORM", "").strip().lower()
    if configured == "dxcb" or ";" in configured:
        if os.environ.get("WAYLAND_DISPLAY") and "wayland" in configured:
            os.environ["QT_QPA_PLATFORM"] = "wayland"
        elif os.environ.get("DISPLAY"):
            os.environ["QT_QPA_PLATFORM"] = "xcb"
        else:
            os.environ.pop("QT_QPA_PLATFORM", None)


def _desktop_file_id() -> str:
    """Only advertise an app ID that the desktop portal can resolve.

    Source checkouts and extracted binaries need not have a desktop entry.
    The Debian package installs one in the standard applications directory.
    """
    app_id = "weather-widget-premium"
    entry = QStandardPaths.locate(
        QStandardPaths.StandardLocation.ApplicationsLocation, f"{app_id}.desktop"
    )
    return app_id if entry else ""


def main() -> int:
    _normalize_qt_platform()
    app = QApplication(sys.argv)
    app.setApplicationName("Weather Widget Premium")
    app.setOrganizationName("WeatherWidgetPremium")
    app.setDesktopFileName(_desktop_file_id())
    widget = PremiumWeatherWidget()
    widget.show()

    def request_shutdown(_signum=None, _frame=None):
        widget.close()
        app.quit()

    signal.signal(signal.SIGINT, request_shutdown)
    signal.signal(signal.SIGTERM, request_shutdown)
    signal_timer = QTimer()
    signal_timer.start(250)
    signal_timer.timeout.connect(lambda: None)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
