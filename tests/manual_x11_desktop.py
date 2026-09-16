"""Real compositor regression check (briefly toggles Show Desktop).

Run from the project root: QT_QPA_PLATFORM=xcb python tests/manual_x11_desktop.py
Uses temporary settings, synthetic weather and a solid test background; no network.
Saves only the test widget's screen region, never a full-desktop screenshot.
"""
import ctypes
import re
import select
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QApplication, QWidget
import weather_widget_v6.config as config
from weather_widget_v6.widget import PremiumWeatherWidget
from test_v6 import sample_weather


class Data(ctypes.Union):
    _fields_ = [("l", ctypes.c_long * 5), ("b", ctypes.c_char * 20)]


class Message(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int), ("serial", ctypes.c_ulong),
                ("send_event", ctypes.c_int), ("display", ctypes.c_void_p),
                ("window", ctypes.c_ulong), ("message_type", ctypes.c_ulong),
                ("format", ctypes.c_int), ("data", Data)]


class Event(ctypes.Union):
    _fields_ = [("client", Message), ("pad", ctypes.c_long * 24)]


def property_text(window, name):
    target = ["-root"] if window is None else ["-id", hex(window)]
    return subprocess.check_output(["xprop", *target, name], text=True, timeout=2)


class NormalWindowFixture:
    """Use a separate app: KWin may restack windows sharing a Qt client leader."""
    def __init__(self):
        code = """
import sys
from PyQt6.QtCore import QSocketNotifier
from PyQt6.QtWidgets import QApplication, QWidget
app = QApplication([])
app.setQuitOnLastWindowClosed(False)
window = QWidget()
window.setWindowTitle('Normal window stacking test')
window.setGeometry(60, 60, 460, 610)
window.setStyleSheet('background: #203050')
window.show()
def command(*_args):
    value = sys.stdin.readline().strip()
    if value == 'show':
        window.show()
    elif value == 'hide':
        window.hide()
    else:
        app.quit()
    print(int(window.winId()), flush=True)
notifier = QSocketNotifier(sys.stdin.fileno(), QSocketNotifier.Type.Read)
notifier.activated.connect(command)
print(int(window.winId()), flush=True)
app.exec()
"""
        self.process = subprocess.Popen(
            [sys.executable, "-c", code], stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, text=True,
        )
        self.window_id = int(self.process.stdout.readline())

    def winId(self):
        return self.window_id

    def _send(self, command):
        self.process.stdin.write(command + "\n")
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 3)[0]:
            raise RuntimeError("Normal-window fixture did not acknowledge " + command)
        # A hide/show round trip may recreate Qt's native window. Validate its
        # current ID instead of accidentally checking a withdrawn old window.
        self.window_id = int(self.process.stdout.readline())

    def show(self):
        self._send("show")

    def hide(self):
        self._send("hide")

    def close(self):
        try:
            self._send("quit")
            self.process.communicate(timeout=3)
        except (BrokenPipeError, subprocess.TimeoutExpired):
            self.process.terminate()
            self.process.communicate(timeout=3)


def main():
    app = QApplication([])
    if app.platformName() != "xcb":
        raise SystemExit("This integration check requires an actual X11/XCB session.")
    app.setQuitOnLastWindowClosed(False)
    x = ctypes.CDLL("libX11.so.6")
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
    x.XDefaultRootWindow.restype = ctypes.c_ulong
    x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x.XInternAtom.restype = ctypes.c_ulong
    x.XSendEvent.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_long, ctypes.POINTER(Event)]
    x.XFlush.argtypes = [ctypes.c_void_p]
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x.XOpenDisplay(None)
    if not display:
        raise SystemExit("Cannot open X11 display")
    root = x.XDefaultRootWindow(display)
    original = int(property_text(None, "_NET_SHOWING_DESKTOP").split("=")[-1])

    def show_desktop(value):
        event = Event()
        event.client.type, event.client.display = 33, display
        event.client.window = root
        event.client.message_type = x.XInternAtom(display, b"_NET_SHOWING_DESKTOP", 0)
        event.client.format = 32
        event.client.data.l[0] = value
        x.XSendEvent(display, root, 0, (1 << 19) | (1 << 20), ctypes.byref(event))
        x.XFlush(display)

    errors = []
    captures = Path(tempfile.mkdtemp(prefix="weather-compositor-captures-"))
    with tempfile.TemporaryDirectory(prefix="weather-compositor-settings-") as directory:
        config.APP_DIR = Path(directory)
        config.SETTINGS_FILE = config.APP_DIR / "settings.json"
        config.CACHE_FILE = config.APP_DIR / "cache.json"
        backdrop = QWidget()
        backdrop.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        backdrop.setAttribute(Qt.WidgetAttribute.WA_X11NetWmWindowTypeDesktop)
        backdrop.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        backdrop.setStyleSheet("background: #864022")
        backdrop.setGeometry(40, 40, 500, 650)
        backdrop.show()
        widget = PremiumWeatherWidget()
        widget.startup_timer.stop()
        widget.weather_timer.stop()
        widget.settings["animations"] = False
        widget.weather = sample_weather()
        widget.setWindowTitle("Weather transparency regression test")
        widget.move(80, 80)
        widget.show()
        normal = NormalWindowFixture()

        def check(label, showing, transparent=False):
            try:
                ids = [int(v, 16) for v in re.findall(r"0x[0-9a-f]+", property_text(None, "_NET_CLIENT_LIST_STACKING"))]
                wid = int(widget.winId())
                kind = property_text(wid, "_NET_WM_WINDOW_TYPE")
                state = property_text(wid, "_NET_WM_STATE")
                assert "_NET_WM_WINDOW_TYPE_DOCK" in kind, kind
                assert "_NET_WM_WINDOW_TYPE_DESKTOP" not in kind, kind
                assert "_NET_WM_STATE_BELOW" in state, state
                assert "_NET_WM_STATE_ABOVE" not in state, state
                assert ids.index(int(backdrop.winId())) < ids.index(wid), "Behind desktop background"
                assert "_NET_WM_STATE_HIDDEN" not in state, "Widget hidden"
                assert int(property_text(None, "_NET_SHOWING_DESKTOP").split("=")[-1]) == showing
                if not showing:
                    assert ids.index(wid) < ids.index(int(normal.winId())), "Above normal windows"
                else:
                    pixmap = widget.screen().grabWindow(0, widget.x(), widget.y(), widget.width(), widget.height())
                    image = pixmap.toImage()
                    image.save(str(captures / f"{label}.png"))
                    scale = pixmap.devicePixelRatio()
                    points = [(2, 2), (widget.width() - 3, widget.height() - 3)]
                    if transparent:
                        points.append((widget.width() - 12, 160))
                    for px, py in points:
                        color = image.pixelColor(round(px * scale), round(py * scale))
                        actual = color.getRgb()[:3]
                        expected = (134, 64, 34)
                        assert max(abs(a - b) for a, b in zip(actual, expected)) <= 3, f"Transparency at {px},{py}: {actual}, expected {expected}"
                print(label, "PASS", flush=True)
            except Exception as exc:
                errors.append(str(exc))
                print(label, "FAIL:", exc, flush=True)

        def expand():
            widget.expanded = True
            widget.current_height = widget.target_height = float(widget.EXPANDED)
            widget.resize(widget.WIDTH, widget.EXPANDED)
            widget.update()

        def remove_background():
            widget.settings["opacity"] = 0.0
            widget.update()

        motion_frames = []

        def check_motion(label, changed=None):
            try:
                assert int(property_text(None, "_NET_SHOWING_DESKTOP").split("=")[-1]) == 1, "Desktop changed during animation check"
                image = widget.screen().grabWindow(
                    0, widget.x() + 25, widget.y() + 82, 76, 76
                ).toImage()
                image.save(str(captures / f"{label}.png"))
                # A foreign window or a compositor transition must not count as
                # weather motion. This corner lies outside the weather symbol.
                actual = image.pixelColor(0, image.height() - 1).getRgb()[:3]
                assert max(abs(a - b) for a, b in zip(actual, (134, 64, 34))) <= 3, "Animation capture was obscured"
                if changed is not None:
                    assert (image != motion_frames[-1]) == changed, "Unexpected animation frame change"
                motion_frames.append(image)
                print(label, "PASS", flush=True)
            except Exception as exc:
                errors.append(str(exc))
                print(label, "FAIL:", exc, flush=True)

        def enable_motion(enabled):
            widget.settings["animations"] = enabled
            widget.repaint()

        show_desktop(0)
        QTimer.singleShot(700, lambda: check("normal", 0))
        # Exercise the widget's actual maintenance path. A raw raise_() is not
        # used by the app and can temporarily promote a dock on some WMs.
        QTimer.singleShot(900, widget.maintain_desktop_state)
        QTimer.singleShot(1400, lambda: check("maintained", 0))
        QTimer.singleShot(1600, lambda: show_desktop(1))
        # Remove the normal fixture from the alpha reference after testing its
        # stacking relationship with the widget.
        QTimer.singleShot(1800, normal.hide)
        QTimer.singleShot(2800, lambda: check("collapsed", 1))
        QTimer.singleShot(3000, expand)
        QTimer.singleShot(3800, lambda: check("expanded", 1))
        QTimer.singleShot(4000, remove_background)
        QTimer.singleShot(4600, lambda: check("transparent", 1, True))
        QTimer.singleShot(4800, lambda: enable_motion(True))
        QTimer.singleShot(5200, lambda: check_motion("motion-first"))
        QTimer.singleShot(6200, lambda: check_motion("motion-second", True))
        QTimer.singleShot(6400, lambda: enable_motion(False))
        # Let the compositor present the final static frame before comparing.
        QTimer.singleShot(8000, lambda: check_motion("motion-disabled-first"))
        QTimer.singleShot(9400, lambda: check_motion("motion-disabled-second", False))
        QTimer.singleShot(9600, lambda: show_desktop(0))
        QTimer.singleShot(9700, normal.show)
        QTimer.singleShot(10400, lambda: check("restored", 0))
        QTimer.singleShot(10600, app.quit)
        try:
            app.exec()
        finally:
            show_desktop(original)
            widget.close()
            normal.close()
            backdrop.close()
            x.XCloseDisplay(display)
    print("Cropped test captures:", captures)
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
