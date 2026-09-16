from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile

CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
DEFAULT_APP_DIR = CONFIG_HOME / "weather-widget-premium"
LEGACY_V6_APP_DIR = CONFIG_HOME / "weather-widget"
APP_DIR = DEFAULT_APP_DIR
SETTINGS_FILE = APP_DIR / "settings.json"
CACHE_FILE = APP_DIR / "cache.json"
CONFIG_VERSION = 3
CACHE_VERSION = 2
MAX_CACHE_AGE = timedelta(hours=24)
MAX_CACHE_ENTRIES = 8
VALID_THEMES = {"Atmospheric", "Glass", "Minimal", "Pearl"}

DEFAULT_SETTINGS = {
    "config_version": CONFIG_VERSION,
    "manual_city": "",
    "location": None,
    "last_auto_location": None,
    "favorites": ["Valencia", "Madrid", "Barcelona"],
    "theme": "Atmospheric",
    "units": "metric",
    "auto_location": True,
    "update_minutes": 15,
    "animations": True,
    "opacity": 0.55,
    "compact": False,
    "position": None,
}


def _ensure_dir() -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    if APP_DIR != DEFAULT_APP_DIR:
        return
    # V6 originally shared the generic weather-widget directory. Copy its data
    # once so Premium starts independently without discarding user preferences.
    for name, destination in (("settings.json", SETTINGS_FILE), ("cache.json", CACHE_FILE)):
        source = LEGACY_V6_APP_DIR / name
        if not destination.exists() and source.is_file():
            try:
                shutil.copy2(source, destination)
            except OSError:
                pass


def load_settings() -> dict:
    _ensure_dir()
    data = DEFAULT_SETTINGS.copy()
    loaded = {}
    try:
        if SETTINGS_FILE.exists():
            loaded = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
    except (OSError, ValueError, TypeError):
        loaded = {}

    # V1 stored an almost opaque 0.92 value. Migrate existing installs once
    # so V6 actually looks like a glass/translucent desktop widget.
    try:
        version = int(loaded.get("config_version", 1)) if isinstance(loaded, dict) else 1
    except (TypeError, ValueError):
        version = 1
    if version < 2:
        data["opacity"] = 0.55
    if version < CONFIG_VERSION:
        data["config_version"] = CONFIG_VERSION
        try:
            save_settings(data)
        except OSError:
            pass

    try:
        data["opacity"] = min(0.90, max(0.0, float(data.get("opacity", 0.55))))
    except (TypeError, ValueError):
        data["opacity"] = 0.55
    try:
        data["update_minutes"] = min(180, max(5, int(data.get("update_minutes", 15))))
    except (TypeError, ValueError):
        data["update_minutes"] = 15
    if data.get("theme") not in VALID_THEMES:
        data["theme"] = "Atmospheric"
    if data.get("units") not in {"metric", "imperial"}:
        data["units"] = "metric"
    data["auto_location"] = bool(data.get("auto_location", True))
    data["manual_city"] = str(data.get("manual_city") or "").strip()
    data["animations"] = bool(data.get("animations", True))
    position = data.get("position")
    if not (isinstance(position, list) and len(position) == 2 and all(isinstance(value, (int, float)) for value in position)):
        data["position"] = None
    for key in ("location", "last_auto_location"):
        location = data.get(key)
        if not (
            isinstance(location, dict)
            and isinstance(location.get("latitude"), (int, float))
            and isinstance(location.get("longitude"), (int, float))
            and isinstance(location.get("label"), str)
        ):
            data[key] = None
    return data


def save_settings(settings: dict) -> None:
    _ensure_dir()
    payload = {**settings, "config_version": CONFIG_VERSION}
    _atomic_json_write(SETTINGS_FILE, payload)


def cache_key(location: dict | None = None, units: str = "metric") -> str | None:
    if not isinstance(location, dict):
        return None
    try:
        lat = float(location["latitude"])
        lon = float(location["longitude"])
    except (KeyError, TypeError, ValueError):
        return None
    return f"{lat:.4f},{lon:.4f}:{units if units in {'metric', 'imperial'} else 'metric'}"


def load_cache(location: dict | None = None, units: str = "metric") -> dict | None:
    _ensure_dir()
    try:
        if CACHE_FILE.exists():
            payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return None
            if payload.get("cache_version") == CACHE_VERSION and isinstance(payload.get("entries"), dict):
                key = cache_key(location, units)
                candidates = (
                    [payload["entries"].get(key)]
                    if key
                    else [item for name, item in payload["entries"].items() if name.endswith(f":{units}")]
                )
                valid = [item for item in candidates if _cache_is_fresh(item)]
                return max(valid, key=_cache_timestamp) if valid else None
            # Backwards compatibility for the original single-location cache.
            legacy_units = "imperial" if str(payload.get("temperature_unit", "")).upper() == "°F" else "metric"
            return payload if legacy_units == units and _cache_is_fresh(payload) else None
    except (OSError, ValueError, TypeError):
        pass
    return None


def save_cache(payload: dict) -> None:
    _ensure_dir()
    if not isinstance(payload, dict):
        raise TypeError("La caché meteorológica debe ser un objeto")
    units = "imperial" if str(payload.get("temperature_unit", "")).upper() == "°F" else "metric"
    key = cache_key(payload, units)
    if not key:
        raise ValueError("La caché meteorológica no contiene coordenadas válidas")
    entries = {}
    try:
        if CACHE_FILE.exists():
            current = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if isinstance(current, dict) and current.get("cache_version") == CACHE_VERSION and isinstance(current.get("entries"), dict):
                entries = {name: item for name, item in current["entries"].items() if _cache_is_fresh(item)}
    except (OSError, ValueError, TypeError):
        entries = {}
    entries[key] = payload
    ordered = sorted(entries.items(), key=lambda pair: _cache_timestamp(pair[1]), reverse=True)
    _atomic_json_write(CACHE_FILE, {"cache_version": CACHE_VERSION, "entries": dict(ordered[:MAX_CACHE_ENTRIES])})


def _cache_timestamp(payload: object) -> datetime:
    if not isinstance(payload, dict):
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        value = datetime.fromisoformat(str(payload["updated_at"]))
        return value if value.tzinfo else value.astimezone()
    except (KeyError, TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def _cache_is_fresh(payload: object) -> bool:
    timestamp = _cache_timestamp(payload)
    age = datetime.now(timezone.utc) - timestamp.astimezone(timezone.utc)
    return timedelta(0) <= age <= MAX_CACHE_AGE


def _atomic_json_write(path: Path, payload: dict) -> None:
    """Replace a JSON file atomically so a crash cannot leave partial data."""
    temp_name = None
    try:
        with NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
        ) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temp_name = handle.name
        os.replace(temp_name, path)
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
