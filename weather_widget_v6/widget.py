from __future__ import annotations

import math
import random

from PyQt6.QtCore import QElapsedTimer, QEvent, QPoint, QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QDialog, QMainWindow, QMenu

from .city_search import CitySearchDialog
from .conditions import condition
from .config import load_cache, load_settings, save_cache, save_settings
from .linux_desktop import apply_x11_widget_hints, session_backend
from .models import WeatherData
from .service import WeatherService
from .weather_icons import draw_weather_icon
from .worker import WeatherWorker


class PremiumWeatherWidget(QMainWindow):
    COLLAPSED, EXPANDED, WIDTH = 216, 556, 392
    DAY_NAMES = ("Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom")
    THEMES = {
        "Atmospheric": {"surface": (15, 27, 46), "end": (9, 15, 29), "text": (247, 250, 255), "muted": (194, 210, 229), "accent": (111, 202, 255)},
        "Glass": {"surface": (51, 67, 88), "end": (24, 33, 48), "text": (251, 252, 255), "muted": (211, 221, 234), "accent": (151, 222, 255)},
        "Minimal": {"surface": (20, 23, 30), "end": (12, 14, 19), "text": (246, 247, 250), "muted": (184, 189, 200), "accent": (220, 224, 232)},
        "Pearl": {"surface": (246, 249, 252), "end": (218, 228, 238), "text": (23, 36, 50), "muted": (72, 91, 110), "accent": (38, 132, 188)},
    }

    def __init__(self):
        super().__init__()
        self.settings = load_settings()
        self.service = WeatherService(units=self.settings.get("units", "metric"))
        self.workers = set()
        self.weather = self._cached_weather()
        self.loading = False
        self.refresh_again = False
        self.offline_message = f"Datos guardados · hace {self.weather.age_minutes} min" if self.weather else ""
        self.expanded = False
        self.current_height = self.target_height = float(self.COLLAPSED)
        self.drag_origin = self.press_global = QPoint()
        self.dragging = self.closing = self.menu_open = False
        self.phase = 0.0
        self.clock = QElapsedTimer()
        self.clock.start()
        self.particles = [{"x": random.random(), "y": random.random(), "speed": random.uniform(.035, .095), "size": random.uniform(1.2, 3.0), "depth": random.random()} for _ in range(34)]

        self.setWindowTitle("Weather Widget Premium")
        self.resize(self.WIDTH, self.COLLAPSED)
        self.setMinimumWidth(360)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnBottomHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAutoFillBackground(False)
        dock_attr = getattr(Qt.WidgetAttribute, "WA_X11NetWmWindowTypeDock", None)
        if session_backend() == "x11" and dock_attr is not None:
            self.setAttribute(dock_attr, True)

        screen = self.screen().availableGeometry()
        saved = self.settings.get("position")
        if isinstance(saved, list) and len(saved) == 2:
            self.move(int(saved[0]), int(saved[1]))
        else:
            self.move(screen.right() - self.width() - 28, screen.bottom() - self.height() - 28)

        self.weather_timer = QTimer(self)
        self.weather_timer.timeout.connect(self.refresh_weather)
        self.weather_timer.start(max(5, int(self.settings.get("update_minutes", 15))) * 60_000)
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.animate)
        self.animation_timer.start(33)
        self.position_timer = QTimer(self)
        self.position_timer.timeout.connect(self.maintain_desktop_state)
        self.position_timer.start(1500)
        QTimer.singleShot(0, self._apply_platform_hints)
        self.startup_timer = QTimer(self)
        self.startup_timer.setSingleShot(True)
        self.startup_timer.timeout.connect(self.refresh_weather)
        self.startup_timer.start(150)

    def _cached_weather(self):
        payload = load_cache(self.settings.get("location"), self.settings.get("units", "metric"))
        try:
            return WeatherData.from_dict(payload) if payload else None
        except (KeyError, TypeError, ValueError):
            return None

    def _safe_save_settings(self):
        try:
            save_settings(self.settings)
        except OSError:
            self.offline_message = "No se pudo guardar la configuración"

    def _apply_platform_hints(self):
        if session_backend() == "x11":
            apply_x11_widget_hints(int(self.winId()))
        self.lower()

    def maintain_desktop_state(self):
        if self.closing or self.dragging or self.menu_open:
            return
        if self.isMinimized():
            self.setWindowState(Qt.WindowState.WindowNoState)
        if not self.isVisible():
            self.show()
        if not self.isActiveWindow():
            self.lower()

    def refresh_weather(self):
        if self.loading or self.closing:
            self.refresh_again = self.loading and not self.closing
            return
        if self.startup_timer.isActive():
            self.startup_timer.stop()
        self.loading = True
        self.offline_message = ""
        worker = WeatherWorker(
            self.service,
            self.settings.get("manual_city", ""),
            self.settings.get("location"),
            bool(self.settings.get("auto_location", True)),
        )
        worker.signals.result.connect(self.on_weather)
        worker.signals.error.connect(self.on_weather_error)
        self.workers.add(worker)
        worker.signals.finished.connect(lambda current=worker: self.on_worker_finished(current))
        worker.start()
        self.update()

    def on_weather(self, weather):
        expected_imperial = self.settings.get("units") == "imperial"
        if (weather.temperature_unit == "°F") != expected_imperial:
            return
        self.weather, self.offline_message = weather, ""
        try:
            save_cache(weather.to_dict())
        except OSError:
            pass
        self.update()

    def on_weather_error(self, message: str):
        if self.weather:
            self.weather.stale = True
            self.offline_message = f"Sin conexión · datos de hace {self.weather.age_minutes} min"
        elif "ubicación" in message.lower() or "elige una ciudad" in message.lower():
            self.offline_message = "Elige una ciudad desde el menú"
        else:
            self.offline_message = "No se pudo actualizar el clima"
        self.update()

    def on_worker_finished(self, worker=None):
        self.workers.discard(worker)
        self.loading = False
        refresh_again, self.refresh_again = self.refresh_again, False
        if self.closing:
            QTimer.singleShot(0, self.close)
        elif refresh_again:
            QTimer.singleShot(0, self.refresh_weather)
        self.update()

    def animate(self):
        elapsed = min(.1, self.clock.restart() / 1000)
        animations = bool(self.settings.get("animations", True))
        if animations and self.isVisible():
            self.phase = (self.phase + elapsed * .72) % (math.pi * 2)
            for particle in self.particles:
                particle["y"] += particle["speed"] * elapsed
                if particle["y"] > 1.08:
                    particle["y"], particle["x"] = -.05, random.random()
        delta = self.target_height - self.current_height
        if abs(delta) > .35:
            self.current_height += delta * min(1.0, elapsed * 10.5) if animations else delta
            self.resize(self.width(), round(self.current_height))
        elif delta:
            self.current_height = self.target_height
            self.resize(self.width(), round(self.current_height))
        if animations or delta:
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_origin = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.press_global = event.globalPosition().toPoint()
            self.dragging = False
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            if (event.globalPosition().toPoint() - self.press_global).manhattanLength() > 5:
                self.dragging = True
                self.move(event.globalPosition().toPoint() - self.drag_origin)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.dragging:
                self.settings["position"] = [self.x(), self.y()]
                self._safe_save_settings()
            else:
                self.expanded = not self.expanded
                self.target_height = float(self.EXPANDED if self.expanded else self.COLLAPSED)
            self.dragging = False
            event.accept()

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        refresh, city = menu.addAction("Actualizar ahora"), menu.addAction("Cambiar ciudad…")
        menu.addSeparator()
        theme_menu = menu.addMenu("Apariencia")
        themes = {theme_menu.addAction(name): name for name in self.THEMES}
        for action, name in themes.items():
            action.setCheckable(True)
            action.setChecked(self.settings.get("theme") == name)
        transparency_menu = menu.addMenu("Opacidad del fondo")
        transparencies = {}
        current = float(self.settings.get("opacity", .55))
        for label, opacity in (("0% · Sin fondo", 0.0), ("35% · Etéreo", .35), ("50% · Ligero", .5), ("65% · Equilibrado", .65), ("80% · Sólido", .8)):
            action = transparency_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(abs(current - opacity) < .03)
            transparencies[action] = opacity
        animation = menu.addAction("Animaciones")
        animation.setCheckable(True)
        animation.setChecked(bool(self.settings.get("animations", True)))
        units_menu = menu.addMenu("Unidades")
        unit_actions = {}
        for label, value in (("Métricas · °C, km/h", "metric"), ("Imperiales · °F, mph", "imperial")):
            action = units_menu.addAction(label)
            action.setCheckable(True)
            action.setChecked(self.settings.get("units", "metric") == value)
            unit_actions[action] = value
        auto_location = menu.addAction("Ubicación automática por IP")
        auto_location.setCheckable(True)
        auto_location.setChecked(bool(self.settings.get("auto_location", True)))
        menu.addSeparator()
        attribution = menu.addAction("Datos: Open-Meteo · GeoNames")
        attribution.setEnabled(False)
        menu.addSeparator()
        quit_action = menu.addAction("Salir")
        self.menu_open = True
        chosen = menu.exec(event.globalPos())
        self.menu_open = False
        if chosen == refresh:
            self.refresh_weather()
        elif chosen == city:
            self.change_city()
        elif chosen in themes:
            self.settings["theme"] = themes[chosen]
            self._safe_save_settings(); self.update()
        elif chosen in transparencies:
            self.settings["opacity"] = transparencies[chosen]
            self._safe_save_settings(); self.update()
        elif chosen == animation:
            self.settings["animations"] = animation.isChecked()
            self._safe_save_settings(); self.update()
        elif chosen in unit_actions:
            self.settings["units"] = unit_actions[chosen]
            self.service = WeatherService(units=self.settings["units"])
            self.weather = self._cached_weather()
            self.offline_message = f"Datos guardados · hace {self.weather.age_minutes} min" if self.weather else ""
            self._safe_save_settings(); self.refresh_weather(); self.update()
        elif chosen == auto_location:
            self.settings["auto_location"] = auto_location.isChecked()
            self._safe_save_settings()
            if self.settings["auto_location"] and not self.settings.get("location"):
                self.refresh_weather()
        elif chosen == quit_action:
            self.close()

    def change_city(self):
        dialog = CitySearchDialog(
            self,
            current_city=self.settings.get("manual_city", ""),
            favorites=self.settings.get("favorites", []),
            theme_name=self.settings.get("theme", "Atmospheric"),
            appearance=self.palette(),
            background_opacity=float(self.settings.get("opacity", .55)),
        )
        if dialog.exec() == QDialog.DialogCode.Accepted and dialog.selected_location:
            location = dialog.selected_location
            self.settings["manual_city"] = str(location.get("query") or location["label"])
            if "latitude" in location and "longitude" in location:
                self.settings["location"] = location
            else:
                self.settings["location"] = None
            self._safe_save_settings()
            self.refresh_weather()

    def hideEvent(self, event):
        super().hideEvent(event)
        if not self.closing:
            QTimer.singleShot(0, self.maintain_desktop_state)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized() and not self.closing:
            QTimer.singleShot(0, self.maintain_desktop_state)

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(0, self._apply_platform_hints)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        card = QRectF(7, 7, self.width() - 14, self.height() - 14)
        self.draw_card(painter, card)
        if not self.weather:
            self.draw_loading(painter); return
        self.draw_atmosphere(painter, card)
        self.draw_header(painter); self.draw_hero(painter)
        if self.current_height > 260:
            painter.setOpacity(min(1.0, max(0.0, (self.current_height - 250) / 72)))
            self.draw_hourly(painter); self.draw_details(painter)
            if self.current_height > 410:
                self.draw_daily(painter)
            painter.setOpacity(1)

    def palette(self):
        return self.THEMES.get(self.settings.get("theme", "Atmospheric"), self.THEMES["Atmospheric"])

    def color(self, key, alpha=255):
        if self.settings.get("theme") == "Pearl" and key in {"text", "muted"}:
            alpha = max(alpha, 215)
        return QColor(*self.palette()[key], alpha)

    def temperature_color(self, temperature: float, alpha: int = 245) -> QColor:
        if self.settings.get("units") == "imperial":
            temperature = (temperature - 32) * 5 / 9
        if self.settings.get("theme") == "Pearl":
            if temperature <= 0:
                rgb = (28, 103, 174)
            elif temperature <= 10:
                rgb = (0, 125, 154)
            elif temperature <= 20:
                rgb = (22, 126, 99)
            elif temperature <= 28:
                rgb = (32, 50, 68)
            elif temperature <= 35:
                rgb = (184, 103, 0)
            else:
                rgb = (190, 55, 35)
        else:
            if temperature <= 0:
                rgb = (132, 196, 255)
            elif temperature <= 10:
                rgb = (118, 218, 245)
            elif temperature <= 20:
                rgb = (166, 230, 213)
            elif temperature <= 28:
                rgb = (247, 246, 238)
            elif temperature <= 35:
                rgb = (255, 201, 102)
            else:
                rgb = (255, 132, 105)
        return QColor(*rgb, alpha)

    def surface_alpha(self, alpha: int) -> int:
        """Scale decorative surfaces only; text and icons remain fully legible."""
        opacity = min(.9, max(0.0, float(self.settings.get("opacity", .55))))
        return round(alpha * opacity / .55) if opacity < .55 else alpha

    def surface_tint(self, alpha: int) -> QColor:
        base = (18, 43, 62) if self.settings.get("theme") == "Pearl" else (255, 255, 255)
        return QColor(*base, self.surface_alpha(alpha))

    def paint_weather_icon(self, painter, rect, code, is_day=True):
        draw_weather_icon(
            painter, rect, code, is_day,
            self.color("accent", 240), self.color("text", 242), self.color("muted", 225),
        )

    def draw_card(self, painter, rect):
        colors, theme = self.palette(), self.settings.get("theme", "Atmospheric")
        opacity = min(.9, max(0.0, float(self.settings.get("opacity", .55))))
        if opacity == 0:
            return
        alpha = round(255 * opacity * (.84 if theme == "Glass" else 1))
        start = colors["surface"]
        if theme == "Atmospheric" and self.weather:
            _, kind = condition(self.weather.weather_code)
            start = {"clear": (30, 89, 142), "partly": (36, 75, 111), "cloudy": (50, 64, 80), "fog": (70, 80, 89), "rain": (28, 57, 82), "drizzle": (35, 64, 85), "snow": (65, 96, 122), "storm": (42, 35, 68)}.get(kind, start)
            if not self.weather.is_day:
                start = tuple(max(9, round(value * .48)) for value in start)
        path = QPainterPath(); path.addRoundedRect(rect, 28, 28)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomRight())
        gradient.setColorAt(0, QColor(*start, alpha)); gradient.setColorAt(1, QColor(*colors["end"], min(240, alpha + 16)))
        painter.fillPath(path, gradient)
        highlight = QLinearGradient(rect.topLeft(), QPointF(rect.left(), rect.top() + 90))
        highlight.setColorAt(0, QColor(255, 255, 255, 28 if theme in ("Glass", "Pearl") else 18)); highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.fillPath(path, highlight)
        border = QColor(30, 64, 88, 48) if theme == "Pearl" else QColor(255, 255, 255, 56 if theme == "Glass" else 38)
        painter.setPen(QPen(border, 1)); painter.drawPath(path)

    def draw_atmosphere(self, painter, rect):
        if self.settings.get("theme") != "Atmospheric" or not self.settings.get("animations", True) or float(self.settings.get("opacity", .55)) == 0: return
        _, kind = condition(self.weather.weather_code)
        painter.save(); clip = QPainterPath(); clip.addRoundedRect(rect, 28, 28); painter.setClipPath(clip)
        if kind == "clear":
            glow = QRadialGradient(rect.right() - 58, rect.top() + 48, 125)
            glow.setColorAt(0, QColor(255, 205, 110, 50 if self.weather.is_day else 13)); glow.setColorAt(1, QColor(255, 205, 110, 0)); painter.fillRect(rect, glow)
        elif kind in ("rain", "drizzle", "storm"):
            painter.setPen(QPen(QColor(185, 215, 255, 50), 1.2))
            for particle in self.particles[:22]:
                x, y = rect.left() + particle["x"] * rect.width(), rect.top() + particle["y"] * rect.height()
                painter.drawLine(QPointF(x, y), QPointF(x - 4, y + 13 + 7 * particle["depth"]))
        elif kind == "snow":
            painter.setPen(Qt.PenStyle.NoPen)
            for particle in self.particles:
                x = rect.left() + ((particle["x"] + math.sin(self.phase + particle["y"] * 8) * .015) % 1) * rect.width(); y = rect.top() + particle["y"] * rect.height()
                painter.setBrush(QColor(255, 255, 255, round(45 + 90 * particle["depth"]))); painter.drawEllipse(QPointF(x, y), particle["size"], particle["size"])
        painter.restore()

    def draw_header(self, painter):
        painter.setPen(self.color("text", 244)); painter.setFont(QFont("Inter", 12, QFont.Weight.DemiBold))
        city = painter.fontMetrics().elidedText(self.weather.city.split(",")[0], Qt.TextElideMode.ElideRight, self.width() - 92); painter.drawText(28, 40, city)
        painter.setFont(QFont("Inter", 8)); painter.setPen(self.color("muted", 180))
        status = "Actualizando…" if self.loading else (self.offline_message or f"Actualizado hace {self.weather.age_minutes} min"); painter.drawText(28, 59, status)
        painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(self.color("accent", 210 if self.loading else 150)); painter.drawEllipse(QPointF(self.width() - 31, 37), 4.5, 4.5)

    def draw_hero(self, painter):
        self.paint_weather_icon(painter, QRectF(25, 82, 76, 76), self.weather.weather_code, self.weather.is_day)
        painter.setPen(self.temperature_color(self.weather.temperature, 248)); painter.setFont(QFont("Inter", 43, QFont.Weight.DemiBold)); painter.drawText(119, 128, f"{round(self.weather.temperature)}°")
        desc, _ = condition(self.weather.weather_code); painter.setFont(QFont("Inter", 10, QFont.Weight.Medium)); painter.setPen(self.color("muted", 220)); painter.drawText(122, 151, desc)
        painter.setFont(QFont("Inter", 9)); painter.setPen(self.color("muted", 180))
        summary = f"Sensación {round(self.weather.apparent_temperature)}°  ·  Próx. hora {self.weather.precipitation_probability}%  ·  Viento {round(self.weather.wind_speed)} {self.weather.wind_speed_unit}"
        painter.drawText(28, 190, painter.fontMetrics().elidedText(summary, Qt.TextElideMode.ElideRight, self.width() - 56))

    def draw_hourly(self, painter):
        items = self.weather.hourly[:6]
        if not items: return
        top = 246; painter.setFont(QFont("Inter", 8, QFont.Weight.DemiBold)); painter.setPen(self.color("muted", 165)); painter.drawText(28, top, "PRÓXIMAS HORAS")
        width = (self.width() - 48) / len(items)
        for index, item in enumerate(items):
            x = 24 + index * width
            if index == 0:
                painter.setBrush(self.surface_tint(20)); painter.setPen(QPen(self.surface_tint(23), 1)); painter.drawRoundedRect(QRectF(x, top + 12, width - 4, 86), 14, 14)
            painter.setPen(self.color("muted", 195)); painter.setFont(QFont("Inter", 8)); painter.drawText(QRectF(x, top + 19, width - 4, 14), Qt.AlignmentFlag.AlignCenter, "Ahora" if index == 0 else item.time.strftime("%Hh"))
            self.paint_weather_icon(painter, QRectF(x + (width - 34) / 2, top + 37, 34, 34), item.weather_code, item.is_day)
            painter.setPen(self.temperature_color(item.temperature, 235)); painter.setFont(QFont("Inter", 9, QFont.Weight.DemiBold)); painter.drawText(QRectF(x, top + 75, width - 4, 16), Qt.AlignmentFlag.AlignCenter, f"{round(item.temperature)}°")

    def draw_details(self, painter):
        y = 373; metrics = (("HUMEDAD", f"{self.weather.humidity}%"), ("PROB. 1 H", f"{self.weather.precipitation_probability}%"), ("VIENTO", f"{round(self.weather.wind_speed)} {self.weather.wind_speed_unit}")); width = (self.width() - 52) / 3
        for index, (label, value) in enumerate(metrics):
            x = 24 + index * width; painter.setBrush(self.surface_tint(13)); painter.setPen(QPen(self.surface_tint(21), 1)); painter.drawRoundedRect(QRectF(x, y - 15, width - 7, 55), 14, 14)
            painter.setPen(self.color("muted", 155)); painter.setFont(QFont("Inter", 7, QFont.Weight.Medium)); painter.drawText(QRectF(x + 9, y - 4, width - 24, 13), label)
            painter.setPen(self.color("text", 225)); painter.setFont(QFont("Inter", 9, QFont.Weight.DemiBold)); painter.drawText(QRectF(x + 9, y + 14, width - 18, 17), value)

    def draw_daily(self, painter):
        items = self.weather.daily[:5]
        if not items: return
        top = 455; painter.setPen(self.color("muted", 165)); painter.setFont(QFont("Inter", 8, QFont.Weight.DemiBold)); painter.drawText(28, top, "PRÓXIMOS DÍAS"); width = (self.width() - 48) / len(items)
        for index, item in enumerate(items):
            x = 24 + index * width; day = "Hoy" if index == 0 else self.DAY_NAMES[item.date.weekday()]
            painter.setPen(self.color("muted", 195)); painter.setFont(QFont("Inter", 8, QFont.Weight.Medium)); painter.drawText(QRectF(x, top + 10, width, 14), Qt.AlignmentFlag.AlignCenter, day)
            self.paint_weather_icon(painter, QRectF(x + (width - 30) / 2, top + 25, 30, 30), item.weather_code, True)
            painter.setFont(QFont("Inter", 8, QFont.Weight.DemiBold)); painter.setPen(self.temperature_color(item.temp_max, 235)); painter.drawText(QRectF(x, top + 53, width / 2 + 5, 15), Qt.AlignmentFlag.AlignRight, f"{round(item.temp_max)}°")
            painter.setPen(self.temperature_color(item.temp_min, 175)); painter.drawText(QRectF(x + width / 2 + 8, top + 53, width / 2 - 8, 15), Qt.AlignmentFlag.AlignLeft, f"{round(item.temp_min)}°")

    def draw_loading(self, painter):
        painter.setPen(self.color("text", 230)); painter.setFont(QFont("Inter", 13, QFont.Weight.DemiBold)); painter.drawText(28, 56, "Weather Premium")
        painter.setPen(self.color("muted", 170)); painter.setFont(QFont("Inter", 9)); painter.drawText(28, 81, self.offline_message or "Preparando el tiempo…")
        painter.setPen(QPen(self.color("accent", 220), 3, cap=Qt.PenCapStyle.RoundCap)); painter.drawArc(QRectF(29, 110, 34, 34), int((self.phase * 180 / math.pi) * 16), 245 * 16)

    def closeEvent(self, event):
        self.closing = True
        self.startup_timer.stop()
        self.settings["position"] = [self.x(), self.y()]
        self._safe_save_settings()
        event.accept()
