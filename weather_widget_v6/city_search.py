from __future__ import annotations

import threading

from PyQt6.QtCore import QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .service import WeatherService


class SearchSignals(QObject):
    result = pyqtSignal(int, object)
    error = pyqtSignal(int, str)


class CitySearchWorker:
    def __init__(self, request_id: int, query: str):
        self.request_id = request_id
        self.query = query
        self.signals = SearchSignals()
        self.thread = threading.Thread(target=self.run, name="city-search", daemon=True)

    def start(self):
        self.thread.start()

    def run(self):
        try:
            results = WeatherService(timeout=8).geocode(self.query, count=8)
            self._emit(self.signals.result, self.request_id, results)
        except Exception as exc:
            self._emit(self.signals.error, self.request_id, str(exc))

    @staticmethod
    def _emit(signal, *args):
        try:
            signal.emit(*args)
        except RuntimeError:
            pass


class CitySearchDialog(QDialog):
    def __init__(
        self,
        parent=None,
        current_city: str = "",
        favorites: list[str] | None = None,
        theme_name: str = "Atmospheric",
        appearance: dict | None = None,
        background_opacity: float = .55,
    ):
        super().__init__(parent)
        self.setWindowTitle("Buscar ubicación")
        self.setFixedSize(520, 560)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.selected_location: dict | None = None
        self.theme_name = theme_name
        self.appearance = appearance or {
            "surface": (15, 27, 46), "end": (9, 15, 29),
            "text": (247, 250, 255), "muted": (194, 210, 229), "accent": (111, 202, 255),
        }
        self.background_opacity = background_opacity
        self.request_id = 0
        self.workers: set[CitySearchWorker] = set()

        eyebrow = QLabel("UBICACIÓN")
        eyebrow.setObjectName("eyebrow")
        title = QLabel("Elige tu ciudad")
        title.setObjectName("title")
        hint = QLabel("Encuentra el lugar exacto para recibir una previsión precisa.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        self.search = QLineEdit(current_city)
        self.search.setPlaceholderText("Ej. Valencia, Torrent, Madrid…")
        self.search.setClearButtonEnabled(True)
        self.status = QLabel("")
        self.status.setObjectName("status")
        self.results = QListWidget()
        self.results.setAlternatingRowColors(False)
        self.results.setUniformItemSizes(True)
        self.results.itemSelectionChanged.connect(self._selection_changed)
        self.results.itemDoubleClicked.connect(lambda _item: self._accept_selection())

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.rejected.connect(self.reject)
        self.use_button = QPushButton("Usar esta ubicación")
        self.use_button.setObjectName("primary")
        self.use_button.setEnabled(False)
        self.use_button.clicked.connect(self._accept_selection)
        buttons.addButton(self.use_button, QDialogButtonBox.ButtonRole.AcceptRole)

        panel = QFrame()
        panel.setObjectName("panel")
        shadow = QGraphicsDropShadowEffect(panel)
        shadow.setBlurRadius(38)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 150))
        panel.setGraphicsEffect(shadow)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(30, 28, 30, 26)
        panel_layout.setSpacing(10)
        panel_layout.addWidget(eyebrow)
        panel_layout.addWidget(title)
        panel_layout.addWidget(hint)
        panel_layout.addSpacing(10)
        panel_layout.addWidget(self.search)
        panel_layout.addSpacing(4)
        panel_layout.addWidget(self.status)
        panel_layout.addWidget(self.results, 1)
        panel_layout.addSpacing(8)
        panel_layout.addWidget(buttons)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(panel)

        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.setInterval(350)
        self.debounce.timeout.connect(self._search_now)
        self.search.textChanged.connect(self._query_changed)
        self.search.returnPressed.connect(self._return_pressed)
        self._apply_style()
        self._show_favorites(favorites or [])
        self.search.selectAll()
        self.search.setFocus()

    def _apply_style(self):
        surface = self.appearance["surface"]
        end = self.appearance["end"]
        text = self.appearance["text"]
        muted = self.appearance["muted"]
        accent = self.appearance["accent"]
        panel_alpha = round(255 * (.78 + min(.9, max(0.0, self.background_opacity)) * .20))
        surface_css = f"rgba({surface[0]},{surface[1]},{surface[2]},{panel_alpha})"
        end_css = f"rgba({end[0]},{end[1]},{end[2]},{min(255, panel_alpha + 8)})"
        text_css = f"rgb({text[0]},{text[1]},{text[2]})"
        muted_css = f"rgb({muted[0]},{muted[1]},{muted[2]})"
        accent_css = f"rgb({accent[0]},{accent[1]},{accent[2]})"
        light_surface = sum(surface) > 620
        control_css = "rgba(255,255,255,175)" if light_surface else "rgba(7,14,23,145)"
        control_focus_css = "rgba(255,255,255,225)" if light_surface else "rgba(8,17,28,190)"
        neutral_css = "rgba(18,43,62,14)" if light_surface else "rgba(255,255,255,10)"
        border_css = "rgba(30,64,88,52)" if light_surface else "rgba(180,220,248,55)"
        self.setProperty("weatherTheme", self.theme_name)
        self.setStyleSheet(f"""
            QDialog {{ background: transparent; color: #f7faff; }}
            QFrame#panel {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                           stop:0 {surface_css}, stop:0.52 {surface_css}, stop:1 {end_css});
                           border: 1px solid {border_css}; border-radius: 26px; }}
            QLabel {{ background: transparent; border: 0; }}
            QLabel#eyebrow {{ color: {accent_css}; font-size: 10px; font-weight: 700; letter-spacing: 2px; }}
            QLabel#title {{ color: {text_css}; font-size: 25px; font-weight: 650; }}
            QLabel#hint {{ color: {muted_css}; font-size: 12px; }}
            QLabel#status {{ color: {accent_css}; font-size: 11px; font-weight: 600; padding: 3px 2px; }}
            QLineEdit {{ min-height: 28px; background: {control_css};
                        border: 1px solid {border_css}; border-radius: 14px;
                        padding: 10px 14px; color: {text_css}; font-size: 14px;
                        selection-background-color: #3b91c5; }}
            QLineEdit:focus {{ background: {control_focus_css}; border-color: {accent_css}; }}
            QListWidget {{ background: transparent; border: 0; outline: 0; padding: 0; }}
            QListWidget::item {{ padding: 9px 14px; margin: 3px 0; border-radius: 13px;
                                color: {text_css}; border: 1px solid transparent; }}
            QListWidget::item:hover {{ background: rgba(255,255,255,15); border-color: rgba(255,255,255,20); }}
            QListWidget::item:selected {{ background: rgba({accent[0]},{accent[1]},{accent[2]},65); border-color: rgba({accent[0]},{accent[1]},{accent[2]},125); color: {text_css}; }}
            QPushButton {{ min-height: 20px; border: 1px solid rgba(157,190,218,50); border-radius: 12px;
                          padding: 9px 16px; background: {neutral_css}; color: {muted_css}; }}
            QPushButton:hover {{ background: rgba(255,255,255,20); color: white; }}
            QPushButton#primary {{ background: {accent_css}; border-color: rgba(255,255,255,100); color: #07131d; font-weight: 700; }}
            QPushButton#primary:hover {{ border-color: rgba(255,255,255,180); }}
            QPushButton:disabled {{ color: #5f7181; background: rgba(255,255,255,5); border-color: rgba(255,255,255,12); }}
        """)

    def _show_favorites(self, favorites: list[str]):
        self.results.clear()
        clean = [str(city).strip() for city in favorites if str(city).strip()]
        if not clean:
            self.status.setText("Escribe al menos dos caracteres para buscar.")
            return
        self.status.setText("Ciudades frecuentes")
        for city in clean:
            item = QListWidgetItem(f"{city}\nAcceso rápido")
            item.setSizeHint(QSize(0, 58))
            item.setData(Qt.ItemDataRole.UserRole, {"query": city, "label": city})
            self.results.addItem(item)

    def _query_changed(self, text: str):
        self.selected_location = None
        self.use_button.setEnabled(False)
        self.debounce.stop()
        if len(text.strip()) < 2:
            self.results.clear()
            self.status.setText("Escribe al menos dos caracteres para buscar.")
            return
        self.status.setText("Esperando…")
        self.debounce.start()

    def _search_now(self):
        query = self.search.text().strip()
        if len(query) < 2:
            return
        self.request_id += 1
        worker = CitySearchWorker(self.request_id, query)
        self.workers.add(worker)
        worker.signals.result.connect(lambda request_id, results, current=worker: self._show_results(current, request_id, results))
        worker.signals.error.connect(lambda request_id, message, current=worker: self._show_error(current, request_id, message))
        self.status.setText("Buscando ubicaciones…")
        worker.start()

    def _show_results(self, worker: CitySearchWorker, request_id: int, results: list[dict]):
        self.workers.discard(worker)
        if request_id != self.request_id:
            return
        self.results.clear()
        for result in results:
            if result.get("latitude") is None or result.get("longitude") is None:
                continue
            parts = [result.get("name"), result.get("admin1"), result.get("country")]
            primary = str(result.get("name") or self.search.text().strip())
            secondary = " · ".join(str(part) for part in parts[1:] if part) or "Ubicación encontrada"
            location = {
                "latitude": float(result["latitude"]),
                "longitude": float(result["longitude"]),
                "label": ", ".join(str(part) for part in parts[:2] if part),
                "query": str(result.get("name") or self.search.text().strip()),
                "timezone": str(result.get("timezone") or "auto"),
                "country_code": str(result.get("country_code") or ""),
                "geonames_id": result.get("id"),
            }
            item = QListWidgetItem(f"{primary}\n{secondary}")
            item.setSizeHint(QSize(0, 62))
            item.setToolTip(f"{location['latitude']:.3f}, {location['longitude']:.3f}")
            item.setData(Qt.ItemDataRole.UserRole, location)
            self.results.addItem(item)
        count = self.results.count()
        self.status.setText(f"{count} resultado{'s' if count != 1 else ''}" if count else "No encontramos esa ubicación.")
        if count:
            self.results.setCurrentRow(0)

    def _show_error(self, worker: CitySearchWorker, request_id: int, _message: str):
        self.workers.discard(worker)
        if request_id == self.request_id:
            self.results.clear()
            self.status.setText("No se pudo buscar. Comprueba tu conexión e inténtalo de nuevo.")

    def _selection_changed(self):
        item = self.results.currentItem()
        self.selected_location = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.use_button.setEnabled(self.selected_location is not None)

    def _return_pressed(self):
        if self.results.currentItem() and self.selected_location:
            self._accept_selection()
        else:
            self.debounce.stop()
            self._search_now()

    def _accept_selection(self):
        if self.selected_location:
            self.accept()
