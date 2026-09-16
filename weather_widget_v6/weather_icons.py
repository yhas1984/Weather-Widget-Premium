from __future__ import annotations

import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

from .conditions import condition


def draw_weather_icon(
    painter: QPainter,
    rect: QRectF,
    weather_code: int,
    is_day: bool = True,
    accent: QColor | None = None,
    foreground: QColor | None = None,
    cloud_color: QColor | None = None,
    phase: float | None = None,
) -> None:
    """Draw a vector symbol; an optional phase animates only its weather shapes."""
    _, kind = condition(weather_code)
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    scale = min(rect.width(), rect.height()) / 64.0
    painter.translate(rect.center())
    painter.scale(scale, scale)
    painter.translate(-32, -32)

    white = foreground or QColor(241, 247, 255, 242)
    muted = cloud_color or QColor(185, 207, 229, 225)
    blue = accent or QColor(103, 190, 255, 235)
    warm = QColor(255, 201, 102, 245)
    motion = phase is not None
    phase = phase % (2 * math.pi) if motion else 0.0
    drift_x = 2.2 * math.sin(phase) if motion else 0.0
    drift_y = 1.2 * math.sin(phase * 2) if motion else 0.0
    # A quarter turn per cloud cycle (~35 seconds per revolution). The eight
    # equal rays make the phase wrap seamless, without reversing the rotation.
    sun_angle = math.degrees(phase) / 4 if motion else 0.0
    moon_angle = 9 * math.sin(phase) if motion else 0.0

    if kind == "clear":
        if is_day:
            _draw_sun(painter, QPointF(32, 32), 13, warm, sun_angle)
        else:
            _draw_moon(painter, white, angle=moon_angle)
    elif kind == "partly":
        if is_day:
            _draw_sun(painter, QPointF(23, 23), 10, warm, sun_angle)
        else:
            _draw_moon(painter, white, QPointF(-8, -8), moon_angle)
        if motion:
            # Move across the sun/moon, not just around a stationary position.
            # The cosine eases both turns and keeps the entire cloud in bounds.
            cover = (1 - math.cos(phase)) / 2
            cloud = QColor(muted)
            cloud.setAlpha(255)  # Occlude the sun instead of letting its rays bleed through.
            _draw_cloud(painter, cloud, 5 - 16 * cover, 8 - 15 * cover)
        else:
            _draw_cloud(painter, muted, 5, 8)
    elif kind == "fog":
        _draw_cloud(painter, muted, 1 + drift_x, -4 + drift_y)
        painter.setPen(QPen(white, 3, cap=Qt.PenCapStyle.RoundCap))
        for y, inset in ((43, 5), (51, 10), (59, 6)):
            shift = 2.5 * math.sin(phase + y) if motion else 0.0
            painter.drawLine(QPointF(12 + inset + shift, y), QPointF(52 - inset + shift, y))
    elif kind in ("rain", "drizzle", "storm"):
        _draw_cloud(painter, muted, 1 + drift_x, -5 + drift_y)
        for index, x in enumerate((21, 32, 43)):
            drop = QColor(blue)
            progress = (phase / (2 * math.pi) * 3 + index / 3) % 1
            offset = (progress - .5) * 8 if motion else 0.0
            if motion:
                # Fade at the wrap point, so droplets never jump back visibly.
                drop.setAlpha(round(blue.alpha() * math.sin(math.pi * progress) ** 2))
            painter.setPen(QPen(drop, 3, cap=Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(x + 2, 43 + offset), QPointF(x - 2, (52 if kind == "drizzle" else 56) + offset))
        if kind == "storm":
            bolt = QPainterPath(QPointF(34, 39))
            bolt.lineTo(27, 51)
            bolt.lineTo(34, 50)
            bolt.lineTo(29, 61)
            bolt.lineTo(44, 46)
            bolt.lineTo(36, 47)
            bolt.closeSubpath()
            painter.fillPath(bolt, warm)
    elif kind == "snow":
        _draw_cloud(painter, muted, 1 + drift_x, -6 + drift_y)
        painter.setPen(QPen(white, 2, cap=Qt.PenCapStyle.RoundCap))
        for x in (22, 34, 46):
            painter.save()
            if motion:
                painter.translate(1.5 * math.sin(phase + x), 2 * math.sin(phase + x / 6))
            painter.drawLine(QPointF(x, 45), QPointF(x, 57))
            painter.drawLine(QPointF(x - 4, 49), QPointF(x + 4, 53))
            painter.drawLine(QPointF(x + 4, 49), QPointF(x - 4, 53))
            painter.restore()
    else:
        _draw_cloud(painter, muted, drift_x, drift_y)
    painter.restore()


def _draw_sun(painter: QPainter, center: QPointF, radius: float, color: QColor, angle: float = 0) -> None:
    painter.save()
    painter.translate(center)
    painter.rotate(angle)
    painter.translate(-center)
    painter.setPen(QPen(color, 2.5, cap=Qt.PenCapStyle.RoundCap))
    for index in range(8):
        theta = index * math.pi / 4
        dx, dy = math.cos(theta), math.sin(theta)
        start = QPointF(center.x() + dx * (radius + 5), center.y() + dy * (radius + 5))
        end = QPointF(center.x() + dx * (radius + 10), center.y() + dy * (radius + 10))
        painter.drawLine(start, end)
    glow = QRadialGradient(center, radius)
    glow.setColorAt(0, QColor(255, 225, 150, color.alpha()))
    glow.setColorAt(1, color)
    painter.setPen(QPen(QColor(255, 236, 190, 210), 1))
    painter.setBrush(glow)
    painter.drawEllipse(center, radius, radius)
    painter.restore()


def _draw_moon(painter: QPainter, color: QColor, offset: QPointF = QPointF(), angle: float = 0) -> None:
    painter.save()
    center = QPointF(32 + offset.x(), 32 + offset.y())
    painter.translate(center)
    painter.rotate(angle)
    painter.translate(-center)
    outer = QPainterPath()
    outer.addEllipse(QPointF(32 + offset.x(), 32 + offset.y()), 16, 16)
    cut = QPainterPath()
    cut.addEllipse(QPointF(39 + offset.x(), 26 + offset.y()), 15, 15)
    painter.fillPath(outer.subtracted(cut), color)
    painter.restore()


def _draw_cloud(painter: QPainter, color: QColor, dx: float = 0, dy: float = 0) -> None:
    cloud = QPainterPath()
    cloud.moveTo(13 + dx, 40 + dy)
    cloud.cubicTo(9 + dx, 33 + dy, 15 + dx, 27 + dy, 22 + dx, 28 + dy)
    cloud.cubicTo(25 + dx, 18 + dy, 42 + dx, 17 + dy, 46 + dx, 29 + dy)
    cloud.cubicTo(57 + dx, 28 + dy, 61 + dx, 43 + dy, 51 + dx, 47 + dy)
    cloud.lineTo(21 + dx, 47 + dy)
    cloud.cubicTo(15 + dx, 47 + dy, 11 + dx, 44 + dy, 13 + dx, 40 + dy)
    cloud.closeSubpath()
    outline = QColor(color)
    outline.setAlpha(min(210, color.alpha()))
    painter.setPen(QPen(outline, 1.2))
    painter.setBrush(color)
    painter.drawPath(cloud)
