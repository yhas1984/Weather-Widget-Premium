from __future__ import annotations

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
) -> None:
    """Draw a consistent, font-independent weather symbol."""
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

    if kind == "clear":
        _draw_sun(painter, QPointF(32, 32), 13, warm) if is_day else _draw_moon(painter, white)
    elif kind == "partly":
        if is_day:
            _draw_sun(painter, QPointF(23, 23), 10, warm)
        else:
            _draw_moon(painter, white, QPointF(-8, -8))
        _draw_cloud(painter, muted, 5, 8)
    elif kind == "fog":
        _draw_cloud(painter, muted, 1, -4)
        painter.setPen(QPen(white, 3, cap=Qt.PenCapStyle.RoundCap))
        for y, inset in ((43, 5), (51, 10), (59, 6)):
            painter.drawLine(QPointF(12 + inset, y), QPointF(52 - inset, y))
    elif kind in ("rain", "drizzle", "storm"):
        _draw_cloud(painter, muted, 1, -5)
        painter.setPen(QPen(blue, 3, cap=Qt.PenCapStyle.RoundCap))
        for x in (21, 32, 43):
            painter.drawLine(QPointF(x + 2, 43), QPointF(x - 2, 52 if kind == "drizzle" else 56))
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
        _draw_cloud(painter, muted, 1, -6)
        painter.setPen(QPen(white, 2, cap=Qt.PenCapStyle.RoundCap))
        for x in (22, 34, 46):
            painter.drawLine(QPointF(x, 45), QPointF(x, 57))
            painter.drawLine(QPointF(x - 4, 49), QPointF(x + 4, 53))
            painter.drawLine(QPointF(x + 4, 49), QPointF(x - 4, 53))
    else:
        _draw_cloud(painter, muted)
    painter.restore()


def _draw_sun(painter: QPainter, center: QPointF, radius: float, color: QColor) -> None:
    painter.setPen(QPen(color, 2.5, cap=Qt.PenCapStyle.RoundCap))
    for dx, dy in ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)):
        start = QPointF(center.x() + dx * (radius + 5), center.y() + dy * (radius + 5))
        end = QPointF(center.x() + dx * (radius + 10), center.y() + dy * (radius + 10))
        painter.drawLine(start, end)
    glow = QRadialGradient(center, radius)
    glow.setColorAt(0, QColor(255, 225, 150, color.alpha()))
    glow.setColorAt(1, color)
    painter.setPen(QPen(QColor(255, 236, 190, 210), 1))
    painter.setBrush(glow)
    painter.drawEllipse(center, radius, radius)


def _draw_moon(painter: QPainter, color: QColor, offset: QPointF = QPointF()) -> None:
    outer = QPainterPath()
    outer.addEllipse(QPointF(32 + offset.x(), 32 + offset.y()), 16, 16)
    cut = QPainterPath()
    cut.addEllipse(QPointF(39 + offset.x(), 26 + offset.y()), 15, 15)
    painter.fillPath(outer.subtracted(cut), color)


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
