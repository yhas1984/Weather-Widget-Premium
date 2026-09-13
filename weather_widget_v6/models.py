from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass(slots=True)
class HourlyForecast:
    time: datetime
    temperature: float
    apparent_temperature: float
    precipitation_probability: int
    weather_code: int
    is_day: bool


@dataclass(slots=True)
class DailyForecast:
    date: datetime
    temperature_max: float
    temperature_min: float
    precipitation_probability_max: int
    weather_code: int
    sunrise: Optional[datetime] = None
    sunset: Optional[datetime] = None

    @property
    def temp_max(self) -> float:
        """Compatibility alias used by the V6 renderer."""
        return self.temperature_max

    @property
    def temp_min(self) -> float:
        """Compatibility alias used by the V6 renderer."""
        return self.temperature_min


@dataclass(slots=True)
class WeatherData:
    city: str
    latitude: float
    longitude: float
    temperature: float
    apparent_temperature: float
    humidity: int
    wind_speed: float
    pressure: float
    cloud_cover: int
    precipitation: float
    precipitation_probability: int
    weather_code: int
    is_day: bool
    timezone: str
    updated_at: datetime
    hourly: list[HourlyForecast] = field(default_factory=list)
    daily: list[DailyForecast] = field(default_factory=list)
    source: str = "Open-Meteo"
    stale: bool = False
    observed_at: Optional[datetime] = None
    temperature_unit: str = "°C"
    wind_speed_unit: str = "km/h"
    precipitation_unit: str = "mm"

    @property
    def age_minutes(self) -> int:
        updated = self.updated_at
        if updated.tzinfo is None:
            updated = updated.astimezone()
        return max(0, int((datetime.now().astimezone() - updated.astimezone()).total_seconds() // 60))

    def to_dict(self) -> dict[str, Any]:
        return {
            "city": self.city,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "temperature": self.temperature,
            "apparent_temperature": self.apparent_temperature,
            "humidity": self.humidity,
            "wind_speed": self.wind_speed,
            "pressure": self.pressure,
            "cloud_cover": self.cloud_cover,
            "precipitation": self.precipitation,
            "precipitation_probability": self.precipitation_probability,
            "weather_code": self.weather_code,
            "is_day": self.is_day,
            "timezone": self.timezone,
            "updated_at": self.updated_at.isoformat(),
            "observed_at": self.observed_at.isoformat() if self.observed_at else None,
            "temperature_unit": self.temperature_unit,
            "wind_speed_unit": self.wind_speed_unit,
            "precipitation_unit": self.precipitation_unit,
            "hourly": [
                {
                    "time": item.time.isoformat(),
                    "temperature": item.temperature,
                    "apparent_temperature": item.apparent_temperature,
                    "precipitation_probability": item.precipitation_probability,
                    "weather_code": item.weather_code,
                    "is_day": item.is_day,
                }
                for item in self.hourly
            ],
            "daily": [
                {
                    "date": item.date.isoformat(),
                    "temperature_max": item.temperature_max,
                    "temperature_min": item.temperature_min,
                    "precipitation_probability_max": item.precipitation_probability_max,
                    "weather_code": item.weather_code,
                    "sunrise": item.sunrise.isoformat() if item.sunrise else None,
                    "sunset": item.sunset.isoformat() if item.sunset else None,
                }
                for item in self.daily
            ],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WeatherData":
        hourly = [
            HourlyForecast(
                time=datetime.fromisoformat(item["time"]),
                temperature=float(item["temperature"]),
                apparent_temperature=float(item["apparent_temperature"]),
                precipitation_probability=int(item["precipitation_probability"]),
                weather_code=int(item["weather_code"]),
                is_day=bool(item["is_day"]),
            )
            for item in payload.get("hourly", [])
        ]
        daily = [
            DailyForecast(
                date=datetime.fromisoformat(item["date"]),
                temperature_max=float(item["temperature_max"]),
                temperature_min=float(item["temperature_min"]),
                precipitation_probability_max=int(item["precipitation_probability_max"]),
                weather_code=int(item["weather_code"]),
                sunrise=datetime.fromisoformat(item["sunrise"]) if item.get("sunrise") else None,
                sunset=datetime.fromisoformat(item["sunset"]) if item.get("sunset") else None,
            )
            for item in payload.get("daily", [])
        ]
        return cls(
            city=str(payload["city"]),
            latitude=float(payload["latitude"]),
            longitude=float(payload["longitude"]),
            temperature=float(payload["temperature"]),
            apparent_temperature=float(payload["apparent_temperature"]),
            humidity=int(payload["humidity"]),
            wind_speed=float(payload["wind_speed"]),
            pressure=float(payload["pressure"]),
            cloud_cover=int(payload["cloud_cover"]),
            precipitation=float(payload["precipitation"]),
            precipitation_probability=int(payload["precipitation_probability"]),
            weather_code=int(payload["weather_code"]),
            is_day=bool(payload["is_day"]),
            timezone=str(payload.get("timezone", "auto")),
            updated_at=datetime.fromisoformat(payload["updated_at"]),
            hourly=hourly,
            daily=daily,
            source=str(payload.get("source", "Open-Meteo")),
            stale=True,
            observed_at=datetime.fromisoformat(payload["observed_at"]) if payload.get("observed_at") else None,
            temperature_unit=str(payload.get("temperature_unit", "°C")),
            wind_speed_unit=str(payload.get("wind_speed_unit", "km/h")),
            precipitation_unit=str(payload.get("precipitation_unit", "mm")),
        )
