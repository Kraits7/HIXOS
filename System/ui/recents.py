# ui/recents.py — Экран недавних приложений в стиле iOS 16 (App Switcher).
#
# Карточки приложений уходят вниз «лентой» (staggered slide-up + fade),
# по тапу карточка spring-раскрывается обратно в приложение,
# по кнопке ✕ карточка схлопывается на месте. Жестов нет — только кнопки/тапы.

from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QRectF
from PyQt5.QtGui import (
    QColor, QPainter, QPainterPath, QPen, QBrush, QFont, QFontMetrics, QPixmap,
    QLinearGradient
)
from PyQt5.QtWidgets import (
    QWidget, QPushButton, QLabel, QScrollArea, QFrame,
    QVBoxLayout, QHBoxLayout
)

try:
    from ui.animation_engine import Easing, Duration, _FrameDriver, spring_progress
except ImportError:
    from animation_engine import Easing, Duration, _FrameDriver, spring_progress


def _rounded_pixmap(src: QPixmap, radius: int) -> QPixmap:
    """Обрезка pixmap по скруглённым углам (squircle-карточка iOS)."""
    w, h = src.width(), src.height()
    out = QPixmap(w, h)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, src)
    p.end()
    return out


class DelayedFrameDriver(_FrameDriver):
    """_FrameDriver с отложенным стартом (каскадные заходы карточек)."""

    def __init__(self, delay_ms, duration_ms, curve, on_frame,
                 on_finished=None, parent=None):
        super().__init__(duration_ms, curve, on_frame, on_finished, parent)
        self._delay = max(0, int(delay_ms))

    def start(self):
        if self._delay > 0:
            QTimer.singleShot(self._delay, self._start_now)
        else:
            self._start_now()

    def _start_now(self):
        super().start()


class RecentsCard(QFrame):
    """Одна карточка недавнего приложения: превью + иконка + название + ✕."""

    card_clicked = pyqtSignal(str)      # app_id
    card_closed = pyqtSignal(str)       # app_id

    CARD_W = 300
    CARD_H = 470
    RADIUS = 26

    def __init__(self, app_id: str, name: str, icon_pixmap: QPixmap,
                 snapshot: QPixmap, parent=None):
        super().__init__(parent)
        self.app_id = app_id
        self._press_p = 0.0
        self._close_p = 1.0            # 1 = полностью видна, 0 = схлопнута
        self._drivers = []

        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.PointingHandCursor)

        # Превью окна (снимок страницы) во всю карточку
        self.preview = QLabel(self)
        self.preview.setGeometry(0, 0, self.CARD_W, self.CARD_H)
        if snapshot is not None and not snapshot.isNull():
            scaled = snapshot.scaled(self.CARD_W, self.CARD_H,
                                     Qt.KeepAspectRatioByExpanding,
                                     Qt.SmoothTransformation)
            self.preview.setPixmap(_rounded_pixmap(scaled, self.RADIUS))

        # Затемняющий градиент снизу (читаемость подписи) — рисуем в paintEvent

        # Иконка + название приложения
        self.icon_badge = QLabel(self)
        badge_size = 44
        self.icon_badge.setGeometry(18, self.CARD_H - 78, badge_size, badge_size)
        if icon_pixmap is not None and not icon_pixmap.isNull():
            self.icon_badge.setPixmap(icon_pixmap.scaled(
                badge_size, badge_size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.icon_badge.setStyleSheet("border-radius: 12px;")

        self.name_label = QLabel(name, self)
        self.name_label.setGeometry(72, self.CARD_H - 74, self.CARD_W - 110, 40)
        self.name_label.setStyleSheet(
            "color: rgba(255,255,255,0.95); font-size: 15px; font-weight: 600;"
            "background: transparent;")
        f = QFont()
        f.setPixelSize(15)
        fm = QFontMetrics(f)
        self.name_label.setText(fm.elidedText(name, Qt.ElideRight, self.CARD_W - 118))

        # Кнопка закрыть
        self.close_btn = QPushButton("✕", self)
        self.close_btn.setGeometry(self.CARD_W - 52, 12, 36, 36)
        self.close_btn.setCursor(Qt.PointingHandCursor)
        self.close_btn.setStyleSheet(
            "QPushButton{background-color: rgba(120,120,135,0.55); color: white;"
            "border: none; border-radius: 18px; font-size: 15px; font-weight: 700;}"
            "QPushButton:pressed{background-color: rgba(120,120,135,0.9);}")
        self.close_btn.clicked.connect(lambda: self._on_close_clicked())

    # ------------------------------------------------------------------
    def _on_close_clicked(self):
        self.card_closed.emit(self.app_id)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start_press_fx()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        inside = self.rect().contains(event.pos())
        if inside and self._press_p > 0.0:
            self.card_clicked.emit(self.app_id)
        super().mouseReleaseEvent(event)

    def _start_press_fx(self):
        def frame(p):
            self._press_p = 1.0 - p
            self.update()
        d = _FrameDriver(140, Easing.STANDARD, frame, None, parent=self)
        self._drivers.append(d)
        d.start()

    def play_open_anim(self, index: int, base_delay_ms: int = 90):
        """Spring-заход карточки снизу вверх с каскадной задержкой."""
        self._close_p = 0.0

        def frame(p):
            s = spring_progress(p)
            self._close_p = min(1.0, max(0.0, s))
            self.update()

        def done():
            self._close_p = 1.0
            self.update()

        d = DelayedFrameDriver(base_delay_ms * index, 430, Easing.STANDARD,
                               frame, done, parent=self)
        self._drivers.append(d)
        d.start()

    def play_close_anim(self, on_finished=None):
        """Схлопывание карточки (scale+fade к центру) при удалении из списка."""
        start = self._close_p

        def frame(p):
            e = p * p  # accelerate in
            self._close_p = start * (1.0 - e)
            self.update()

        def done():
            self._close_p = 0.0
            if on_finished:
                on_finished()

        d = _FrameDriver(220, Easing.ACCELERATE, frame, done, parent=self)
        self._drivers.append(d)
        d.start()

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._close_p <= 0.001:
            p.end()
            return

        cx = self.width() / 2.0
        cy = self.height() / 2.0
        scale = 0.82 + 0.18 * self._close_p
        dy = (1.0 - self._close_p) * 70.0

        p.translate(cx, cy)
        p.scale(scale, scale)
        p.translate(-cx, -cy + dy)
        p.setOpacity(self._close_p)

        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)

        # фон под превью (если снимка нет)
        p.fillPath(path, QColor("#1c1e24"))
        p.setClipPath(path)
        p.drawPixmap(0, 0, self.preview.pixmap() or QPixmap(1, 1))

        # нижний градиент для читаемости подписи
        grad = QLinearGradient(0, self.height() - 110, 0, self.height())
        grad.setColorAt(0, QColor(0, 0, 0, 0))
        grad.setColorAt(1, QColor(0, 0, 0, 150))
        p.fillRect(QRectF(0, self.height() - 110, self.width(), 110), QBrush(grad))

        # press затемнение
        if self._press_p > 0.001:
            p.fillRect(rect, QColor(0, 0, 0, int(60 * self._press_p)))

        p.setClipping(False)
        # стеклянная рамка
        pen = QPen(QColor(255, 255, 255, 40))
        pen.setWidthF(1.2)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()


from PyQt5.QtWidgets import QScrollArea  # noqa: E402  (уже импортирован выше, повтор безопасен)


class RecentsOverlay(QWidget):
    """Полноэкранный оверлей недавних приложений поверх стека страниц."""

    app_resumed = pyqtSignal(str)         # app_id
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self._bg_alpha = 0.0
        self._cards = []
        self._drivers = []
        self.hide()

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 30, 0, 24)
        v.setSpacing(0)

        title = QLabel("Недавние", self)
        title.setAlignment(Qt.AlignHCenter)
        title.setStyleSheet(
            "color: rgba(255,255,255,0.92); font-size: 22px; font-weight: 700;"
            "background: transparent;")
        v.addWidget(title)
        v.addSpacing(14)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollbarAlwaysOff)
        self.scroll.setStyleSheet("QScrollArea{background: transparent;} QWidget{background: transparent;}")
        v.addWidget(self.scroll, 1)

        self.container = QFrame()
        self.container.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.container)
        self.cards_layout.setContentsMargins(28, 6, 28, 6)
        self.cards_layout.setSpacing(26)
        self.cards_layout.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.scroll.setWidget(self.container)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 12, 0, 0)
        btn_row.addStretch(1)
        self.clear_button = QPushButton("Очистить всё", self)
        self.clear_button.setCursor(Qt.PointingHandCursor)
        self.clear_button.setStyleSheet(
            "QPushButton{background-color: rgba(255,255,255,0.12); color: white;"
            "border: none; border-radius: 16px; padding: 10px 26px;"
            "font-size: 14px; font-weight: 600; backdrop-filter: blur(10px);}"
            "QPushButton:pressed{background-color: rgba(255,255,255,0.22);}")
        self.clear_button.clicked.connect(self._clear_all)
        btn_row.addWidget(self.clear_button)
        btn_row.addStretch(1)
        v.addLayout(btn_row)

    # ------------------------------------------------------------------
    def set_sessions(self, sessions):
        """sessions: список dict(app_id, name, icon: QPixmap|None, snapshot: QPixmap|None)."""
        for c in self._cards:
            c.deleteLater()
        self._cards.clear()

        for s in sessions:
            card = RecentsCard(s["app_id"], s["name"], s.get("icon"), s.get("snapshot"),
                               self.container)
            card.card_clicked.connect(self._on_card_clicked)
            card.card_closed.connect(self._on_card_closed)
            self.cards_layout.addWidget(card)
            self._cards.append(card)

    def has_cards(self):
        return len([c for c in self._cards if c.isVisible()]) > 0

    def _on_card_clicked(self, app_id):
        self.play_dismiss_anim()
        self.app_resumed.emit(app_id)

    def _on_card_closed(self, app_id):
        for c in self._cards:
            if c.app_id == app_id:
                def gone(c=c):
                    c.hide()
                    c.deleteLater()
                    try:
                        self._cards.remove(c)
                    except ValueError:
                        pass
                    if not self.has_cards():
                        self.play_dismiss_anim()
                c.play_close_anim(on_finished=gone)
                break

    def _clear_all(self):
        if not self._cards:
            self.play_dismiss_anim()
            return
        remaining = list(self._cards)
        for i, c in enumerate(remaining):
            def gone(c=c):
                c.hide()
                c.deleteLater()
                try:
                    self._cards.remove(c)
                except ValueError:
                    pass
            c.play_close_anim(on_finished=gone)
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(240 + 60 * len(remaining), self.play_dismiss_anim)

    # ------------------------------------------------------------------
    def play_show_anim(self):
        self.show()
        self.raise_()
        self._bg_alpha = 0.0

        def frame(p):
            self._bg_alpha = p
            self.update()

        d = _FrameDriver(260, Easing.STANDARD, frame, None, parent=self)
        self._drivers.append(d)
        d.start()
        for i, c in enumerate(self._cards):
            c.show()
            c.play_open_anim(i)

    def play_dismiss_anim(self):
        start = self._bg_alpha

        def frame(p):
            self._bg_alpha = start * (1.0 - p)
            self.update()

        def done():
            self.hide()
            self.dismissed.emit()

        d = _FrameDriver(220, Easing.ACCELERATE, frame, done, parent=self)
        self._drivers.append(d)
        d.start()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.play_dismiss_anim()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):
        if self._bg_alpha <= 0.001:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # тёмное «блюровое» стекло iOS App Switcher
        p.fillRect(self.rect(), QColor(8, 10, 16, int(215 * self._bg_alpha)))
        p.end()
