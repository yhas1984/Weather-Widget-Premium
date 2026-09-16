from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, pyqtSignal


class WorkerSignals(QObject):
    result = pyqtSignal(object)
    error = pyqtSignal(str)
    finished = pyqtSignal()


class WeatherWorker:
    def __init__(
        self,
        service,
        manual_city: str = "",
        location: dict | None = None,
        allow_ip_location: bool = True,
    ):
        self.service = service
        self.manual_city = manual_city
        self.location = location
        self.allow_ip_location = allow_ip_location
        self.signals = WorkerSignals()
        self.thread = threading.Thread(target=self.run, name="weather-fetch", daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        try:
            if self.allow_ip_location:
                # Automatic mode must take precedence over remembered manual choices.
                lat, lon, city = self.service.locate("", True)
            elif self.location:
                lat = float(self.location["latitude"])
                lon = float(self.location["longitude"])
                city = str(self.location["label"])
            else:
                lat, lon, city = self.service.locate(self.manual_city, self.allow_ip_location)
            self._emit(self.signals.result, self.service.fetch(lat, lon, city))
        except Exception as exc:
            self._emit(self.signals.error, str(exc))
        finally:
            self._emit(self.signals.finished)

    @staticmethod
    def _emit(signal, *args):
        try:
            signal.emit(*args)
        except RuntimeError:
            # The UI may already be gone; daemon workers must then exit quietly.
            pass
