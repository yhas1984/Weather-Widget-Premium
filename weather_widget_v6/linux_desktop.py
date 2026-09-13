from __future__ import annotations

import shutil
import subprocess

from PyQt6.QtGui import QGuiApplication


def session_backend() -> str:
    name = (QGuiApplication.platformName() or "unknown").lower()
    if "wayland" in name:
        return "wayland"
    if "xcb" in name or name in {"x11", "dxcb"}:
        return "x11"
    return name


def apply_x11_widget_hints(window_id: int) -> bool:
    """Keep the widget visible without placing it behind the desktop shell."""
    if session_backend() != "x11" or not shutil.which("xprop"):
        return False
    window = str(window_id)
    commands = (
        ("xprop", "-id", window, "-f", "_NET_WM_WINDOW_TYPE", "32a", "-set", "_NET_WM_WINDOW_TYPE", "_NET_WM_WINDOW_TYPE_DOCK"),
        ("xprop", "-id", window, "-f", "_NET_WM_STATE", "32a", "-set", "_NET_WM_STATE", "_NET_WM_STATE_BELOW, _NET_WM_STATE_SKIP_TASKBAR, _NET_WM_STATE_SKIP_PAGER, _NET_WM_STATE_STICKY"),
    )
    try:
        for command in commands:
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False
