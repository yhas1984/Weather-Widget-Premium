from __future__ import annotations

from datetime import datetime
import math
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .models import DailyForecast, HourlyForecast, WeatherData

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
IP_LOCATION_URL = "https://ipapi.co/json/"


class LocationUnavailableError(RuntimeError):
    """Raised when no trustworthy location can be determined."""


class WeatherService:
    VALID_UNITS = {"metric", "imperial"}

    def __init__(
        self,
        timeout: int | tuple[int, int] = (4, 12),
        units: str = "metric",
        session: requests.Session | None = None,
    ):
        self.timeout = timeout
        self.units = units if units in self.VALID_UNITS else "metric"
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "WeatherWidgetPremium/6.0"})
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.6,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=4)
        self.session.mount("https://", adapter)

    def geocode(self, city: str, count: int = 5) -> list[dict]:
        query = str(city).strip()
        if len(query) < 2:
            return []
        response = self.session.get(
            GEOCODING_URL,
            params={"name": query, "count": min(100, max(1, int(count))), "language": "es", "format": "json"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = self._json_object(response, "geocodificación")
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise ValueError("Respuesta de geocodificación incompleta: results")
        return [item for item in results if isinstance(item, dict)]

    def locate(self, manual_city: str = "", allow_ip_location: bool = True) -> tuple[float, float, str]:
        query = str(manual_city).strip()
        if query:
            results = self.geocode(query, 1)
            if not results:
                raise LocationUnavailableError(f"No se encontró la ubicación «{query}»")
            item = results[0]
            lat = self._number(item, "latitude", minimum=-90, maximum=90)
            lon = self._number(item, "longitude", minimum=-180, maximum=180)
            label = ", ".join(filter(None, [str(item.get("name") or "").strip(), str(item.get("admin1") or "").strip()]))
            return lat, lon, label or query

        if not allow_ip_location:
            raise LocationUnavailableError("Elige una ciudad o activa la ubicación automática")

        try:
            response = self.session.get(IP_LOCATION_URL, timeout=self.timeout)
            response.raise_for_status()
            data = self._json_object(response, "ubicación automática")
            lat = self._number(data, "latitude", minimum=-90, maximum=90)
            lon = self._number(data, "longitude", minimum=-180, maximum=180)
            city = str(data.get("city") or "Ubicación actual").strip()
            return lat, lon, city
        except (requests.RequestException, TypeError, ValueError) as exc:
            raise LocationUnavailableError(
                "No se pudo determinar la ubicación. Elige una ciudad manualmente."
            ) from exc

    def fetch(self, lat: float, lon: float, city: str) -> WeatherData:
        latitude = self._coordinate(lat, "latitud", -90, 90)
        longitude = self._coordinate(lon, "longitud", -180, 180)
        current_fields = ",".join([
            "temperature_2m", "apparent_temperature", "relative_humidity_2m",
            "precipitation", "weather_code", "cloud_cover", "surface_pressure",
            "wind_speed_10m", "is_day",
        ])
        hourly_fields = ",".join([
            "temperature_2m", "apparent_temperature", "precipitation_probability",
            "weather_code", "is_day",
        ])
        daily_fields = ",".join([
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_probability_max", "sunrise", "sunset",
        ])
        params: dict[str, Any] = {
            "latitude": latitude,
            "longitude": longitude,
            "current": current_fields,
            "hourly": hourly_fields,
            "daily": daily_fields,
            "forecast_hours": 12,
            "forecast_days": 5,
            "timezone": "auto",
            "temperature_unit": "fahrenheit" if self.units == "imperial" else "celsius",
            "wind_speed_unit": "mph" if self.units == "imperial" else "kmh",
            "precipitation_unit": "inch" if self.units == "imperial" else "mm",
        }
        response = self.session.get(FORECAST_URL, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = self._json_object(response, "Open-Meteo")
        current = self._mapping(payload, "current")
        hourly = self._mapping(payload, "hourly")
        daily = self._mapping(payload, "daily")
        current_units = self._mapping(payload, "current_units")

        hourly_times = self._list(hourly, "time")
        if not hourly_times:
            raise ValueError("Open-Meteo no devolvió previsión horaria")
        current_time = self._datetime(current.get("time"), "current.time")
        parsed_hourly_times = [self._datetime(value, "hourly.time") for value in hourly_times]
        now_index = min(range(len(parsed_hourly_times)), key=lambda i: abs(parsed_hourly_times[i] - current_time))
        hourly_keys = (
            "temperature_2m", "apparent_temperature", "precipitation_probability",
            "weather_code", "is_day",
        )
        hourly_limit = min(len(parsed_hourly_times), *(len(self._list(hourly, key)) for key in hourly_keys))
        hourly_items = []
        for i in range(now_index, min(now_index + 12, hourly_limit)):
            hourly_items.append(HourlyForecast(
                time=parsed_hourly_times[i],
                temperature=self._number_at(hourly, "temperature_2m", i),
                apparent_temperature=self._number_at(hourly, "apparent_temperature", i),
                precipitation_probability=self._percent_at(hourly, "precipitation_probability", i),
                weather_code=self._integer_at(hourly, "weather_code", i),
                is_day=bool(self._integer_at(hourly, "is_day", i, minimum=0, maximum=1)),
            ))
        if not hourly_items:
            raise ValueError("Open-Meteo no devolvió horas utilizables")

        daily_times = self._list(daily, "time")
        daily_keys = (
            "weather_code", "temperature_2m_max", "temperature_2m_min",
            "precipitation_probability_max", "sunrise", "sunset",
        )
        daily_limit = min(len(daily_times), *(len(self._list(daily, key)) for key in daily_keys), 5)
        daily_items = []
        for i in range(daily_limit):
            daily_items.append(DailyForecast(
                date=self._datetime(daily_times[i], "daily.time"),
                temperature_max=self._number_at(daily, "temperature_2m_max", i),
                temperature_min=self._number_at(daily, "temperature_2m_min", i),
                precipitation_probability_max=self._percent_at(daily, "precipitation_probability_max", i),
                weather_code=self._integer_at(daily, "weather_code", i),
                sunrise=self._optional_datetime(self._list(daily, "sunrise")[i], "daily.sunrise"),
                sunset=self._optional_datetime(self._list(daily, "sunset")[i], "daily.sunset"),
            ))
        if not daily_items:
            raise ValueError("Open-Meteo no devolvió días utilizables")

        return WeatherData(
            city=str(city).strip() or "Ubicación seleccionada",
            latitude=latitude,
            longitude=longitude,
            temperature=self._number(current, "temperature_2m"),
            apparent_temperature=self._number(current, "apparent_temperature"),
            humidity=self._integer(current, "relative_humidity_2m", minimum=0, maximum=100),
            wind_speed=self._number(current, "wind_speed_10m", minimum=0),
            pressure=self._number(current, "surface_pressure", minimum=0),
            cloud_cover=self._integer(current, "cloud_cover", minimum=0, maximum=100),
            precipitation=self._number(current, "precipitation", minimum=0),
            precipitation_probability=hourly_items[0].precipitation_probability,
            weather_code=self._integer(current, "weather_code"),
            is_day=bool(self._integer(current, "is_day", minimum=0, maximum=1)),
            timezone=str(payload.get("timezone") or "auto"),
            updated_at=datetime.now().astimezone(),
            hourly=hourly_items,
            daily=daily_items,
            observed_at=current_time,
            temperature_unit=str(current_units.get("temperature_2m") or ("°F" if self.units == "imperial" else "°C")),
            wind_speed_unit=self._wind_unit(current_units.get("wind_speed_10m")),
            precipitation_unit=str(current_units.get("precipitation") or ("inch" if self.units == "imperial" else "mm")),
        )

    @staticmethod
    def _json_object(response: requests.Response, source: str) -> dict:
        try:
            payload = response.json()
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{source} devolvió JSON inválido") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"Respuesta de {source} inválida")
        if payload.get("error"):
            raise ValueError(str(payload.get("reason") or f"Error devuelto por {source}"))
        return payload

    @staticmethod
    def _mapping(payload: dict, key: str) -> dict:
        value = payload.get(key)
        if not isinstance(value, dict):
            raise ValueError(f"Respuesta de Open-Meteo incompleta: {key}")
        return value

    @staticmethod
    def _list(payload: dict, key: str) -> list:
        value = payload.get(key)
        if not isinstance(value, list):
            raise ValueError(f"Respuesta de Open-Meteo incompleta: {key}")
        return value

    @classmethod
    def _number(cls, payload: dict, key: str, minimum: float | None = None, maximum: float | None = None) -> float:
        value = payload.get(key)
        if isinstance(value, bool):
            raise ValueError(f"Open-Meteo devolvió un valor inválido para {key}")
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Open-Meteo devolvió un valor inválido para {key}") from exc
        if not math.isfinite(number) or minimum is not None and number < minimum or maximum is not None and number > maximum:
            raise ValueError(f"Open-Meteo devolvió un valor fuera de rango para {key}")
        return number

    @classmethod
    def _integer(cls, payload: dict, key: str, minimum: int | None = None, maximum: int | None = None) -> int:
        number = cls._number(payload, key, minimum, maximum)
        if not number.is_integer():
            raise ValueError(f"Open-Meteo devolvió un entero inválido para {key}")
        return int(number)

    @classmethod
    def _number_at(cls, payload: dict, key: str, index: int) -> float:
        return cls._number({key: cls._list(payload, key)[index]}, key)

    @classmethod
    def _integer_at(cls, payload: dict, key: str, index: int, minimum: int | None = None, maximum: int | None = None) -> int:
        return cls._integer({key: cls._list(payload, key)[index]}, key, minimum, maximum)

    @classmethod
    def _percent_at(cls, payload: dict, key: str, index: int) -> int:
        value = cls._list(payload, key)[index]
        if value is None:
            return 0
        return cls._integer({key: value}, key, 0, 100)

    @staticmethod
    def _datetime(value: Any, key: str) -> datetime:
        try:
            return datetime.fromisoformat(str(value))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Open-Meteo devolvió una fecha inválida para {key}") from exc

    @classmethod
    def _optional_datetime(cls, value: Any, key: str) -> datetime | None:
        return None if value in (None, "") else cls._datetime(value, key)

    @staticmethod
    def _coordinate(value: Any, label: str, minimum: float, maximum: float) -> float:
        try:
            coordinate = float(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"La {label} no es válida") from exc
        if not math.isfinite(coordinate) or not minimum <= coordinate <= maximum:
            raise ValueError(f"La {label} está fuera de rango")
        return coordinate

    def _wind_unit(self, value: Any) -> str:
        unit = str(value or "").strip()
        if self.units == "imperial" and unit in {"", "mp/h", "mph"}:
            return "mph"
        return unit or "km/h"
