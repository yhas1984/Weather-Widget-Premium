from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication


def session_backend() -> str:
    name = (QGuiApplication.platformName() or "unknown").lower()
    if "wayland" in name:
        return "wayland"
    if "xcb" in name or name in {"x11", "dxcb"}:
        return "x11"
    return name


def configure_desktop_window(widget) -> None:
    """Configure a translucent, below-applications surface before mapping it."""
    flags = (Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
             | Qt.WindowType.WindowStaysOnBottomHint)
    if session_backend() == "x11":
        # KWin treats DESKTOP surfaces as opaque even with an ARGB visual.
        # DOCK preserves alpha and survives Show Desktop; BELOW is essential
        # to keep it underneath applications instead of in the normal panel layer.
        # Qt sends BOTH hints before mapping. Never overwrite _NET_WM_STATE with
        # xprop after showing: the WM owns it and can discard that late write.
        widget.setAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDock, True)
    # On Wayland retain the best-effort Qt bottom hint, without forcing XCB.
    widget.setWindowFlags(flags)


def restack_desktop_window(widget) -> None:
    # The WM's below-applications layer still sits above the desktop background.
    # Do not periodically raise the widget or steal activation from another app.
    if not widget.isActiveWindow():
        widget.lower()
