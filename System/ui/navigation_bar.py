# ui/navigation_bar.py
"""Панель навигации HIXOS в стиле iOS 16.

Два режима (совместимые со старым API):
  * NAVIGATION_MODE_THREE_BUTTON — «классическая» строка, но в iOS-стиле:
    тонкие векторные глифы (chevron / домик / квадрат-недавние), нажатие
    подсвечивается мягкой скруглённой плашкой;
  * NAVIGATION_MODE_GESTURES — вместо кнопок фирменный iOS home indicator:
    тёмная/светлая «капсула» по центру, свайпы по панели распознаются как
    Назад / Домой / Недавние.

Панель полностью прозрачная (glass) — контент страницы просвечивает,
как в iOS 16 поверх обоев лаунчера.
"""
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QLabel, QApplication, QMainWindow,
    QFrame, QSizePolicy, QGraphicsOpacityEffect
)
from PyQt5.QtGui import QColor, QFont, QIcon, QTransform, QPainter, QPen, QBrush, QPainterPath, QPixmap
from PyQt5.QtCore import (
    Qt, pyqtSignal, pyqtProperty, QSize, QRect, QRectF, QPointF, QTimer, QEvent, QPropertyAnimation
)

try:
    from ui.animation_engine import Easing, Duration, _FrameDriver
except ImportError:
    from animation_engine import Easing, Duration, _FrameDriver

# --- Константы режима навигации ---
NAVIGATION_MODE_THREE_BUTTON = "three_button"
NAVIGATION_MODE_GESTURES = "gestures"


def _make_glyph(kind: str, color: QColor, size: int = 22) -> QPixmap:
    """Рисует векторный глиф кнопки (chevron/back, house/home, square/recents)."""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = size / 22.0
    pen = QPen(color)
    pen.setWidthF(max(1.6, 1.9 * s))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)

    if kind == "back":
        # Тонкий шеврон «<»
        path = QPainterPath(QPointF(13.5 * s, 5.5 * s))
        path.lineTo(7.0 * s, 11.0 * s)
        path.lineTo(13.5 * s, 16.5 * s)
        p.drawPath(path)
    elif kind == "home":
        # Домик iOS: крыша + стены
        path = QPainterPath(QPointF(4.0 * s, 10.5 * s))
        path.lineTo(11.0 * s, 4.5 * s)
        path.lineTo(18.0 * s, 10.5 * s)
        p.drawPath(path)
        body = QPainterPath(QPointF(6.0 * s, 9.5 * s))
        body.lineTo(6.0 * s, 17.5 * s)
        body.lineTo(16.0 * s, 17.5 * s)
        body.lineTo(16.0 * s, 9.5 * s)
        p.drawPath(body)
        # Дверца
        door = QPainterPath(QPointF(9.6 * s, 17.5 * s))
        door.lineTo(9.6 * s, 13.2 * s)
        door.lineTo(12.4 * s, 13.2 * s)
        door.lineTo(12.4 * s, 17.5 * s)
        p.drawPath(door)
    else:  # recents
        # Скруглённый квадрат — «недавние»
        r = QRectF(5.0 * s, 5.0 * s, 12.0 * s, 12.0 * s)
        path = QPainterPath()
        path.addRoundedRect(r, 3.4 * s, 3.4 * s)
        p.drawPath(path)
    p.end()
    return pm


class _NavButton(QPushButton):
    """Кнопка с PNG-глифом и мягким pill-подсвечиванием при нажатии."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self._kind = kind
        self._ink = QColor("#FFFFFF")
        self._press_p = 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(64, 34)
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")
        self._refresh_icon()
        self.pressed.connect(self._start_press_fx)

    def set_ink(self, color: QColor):
        if color.name() != self._ink.name():
            self._ink = QColor(color)
            self._refresh_icon()

    def _refresh_icon(self):
        pm = _make_glyph(self._kind, self._ink, 22)
        self.setIcon(QIcon(pm))
        self.setIconSize(QSize(22, 22))

    def _start_press_fx(self):
        self._press_anim = QPropertyAnimation(self, b"pressP", self)
        self._press_anim.setDuration(Duration.MICRO)
        self._press_anim.setStartValue(self._press_p)
        self._press_anim.setEndValue(1.0)
        self._press_anim.setEasingCurve(Easing.DECELERATE)
        self._press_anim.start()

    @pyqtProperty(float)
    def pressP(self):
        return self._press_p

    @pressP.setter
    def pressP(self, v):
        self._press_p = v
        self.update()

    def paintEvent(self, event):
        # фон-плашка при нажатии
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        if self._press_p > 0.01:
            a = int(70 * self._press_p)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(255, 255, 255, a) if self._ink.lightness() < 128
                              else QColor(0, 0, 0, a)))
            inset = 3.0
            path = QPainterPath()
            path.addRoundedRect(QRectF(inset, inset,
                                       self.width() - inset * 2,
                                       self.height() - inset * 2),
                                (self.height() - inset * 2) / 2.0,
                                (self.height() - inset * 2) / 2.0)
            p.drawPath(path)
        p.end()
        super().paintEvent(event)




class NavigationBarWidget(QFrame):
    # Сигналы для навигационных действий
    home_button_pressed = pyqtSignal()
    back_button_pressed = pyqtSignal()
    recent_button_pressed = pyqtSignal()

    HEIGHT_THREE = 40
    HEIGHT_GESTURE = 26

    def __init__(self, parent=None, initial_mode=NAVIGATION_MODE_THREE_BUTTON):
        super().__init__(parent)
        self.setContentsMargins(0, 0, 0, 0)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.current_mode = initial_mode

        # Жесты
        self._touch_start_pos = QPointF()
        self._touch_last_pos = QPointF()
        self._is_touch_active = False
        self._gesture_threshold = 30
        self._long_press_timer = QTimer(self)
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer_threshold = 500

        self.setAttribute(Qt.WA_AcceptTouchEvents)

        self._ink = QColor("#FFFFFF")

        self.init_ui()
        self.set_navigation_mode(self.current_mode)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def init_ui(self):
        # Три кнопки в линию (iOS-style glyphs)
        self.back_button = _NavButton("back", self)
        self.home_button = _NavButton("home", self)
        self.recent_button = _NavButton("recents", self)

        self.back_button.setObjectName("BackButton")
        self.home_button.setObjectName("HomeButton")
        self.recent_button.setObjectName("RecentButton")

        self.back_button.clicked.connect(self.back_button_pressed.emit)
        self.home_button.clicked.connect(self.home_button_pressed.emit)
        self.recent_button.clicked.connect(self.recent_button_pressed.emit)

        self.main_layout.addStretch(2)
        self.main_layout.addWidget(self.back_button, alignment=Qt.AlignCenter)
        self.main_layout.addStretch(3)
        self.main_layout.addWidget(self.home_button, alignment=Qt.AlignCenter)
        self.main_layout.addStretch(3)
        self.main_layout.addWidget(self.recent_button, alignment=Qt.AlignCenter)
        self.main_layout.addStretch(2)

        # Home indicator (режим жестов) — рисуется в paintEvent, виджет-заглушка
        # для fade-анимации появления
        self._indicator_w = 140.0
        self._indicator_alpha = 0.0

    # ------------------------------------------------------------------
    def set_navigation_mode(self, mode: str):
        """Три кнопки либо home-indicator с поддержкой свайпов."""
        self.current_mode = mode
        if mode == NAVIGATION_MODE_THREE_BUTTON:
            self.setFixedHeight(self.HEIGHT_THREE)
            self.back_button.show()
            self.home_button.show()
            self.recent_button.show()
            self._fade_indicator(0.0)
            self.removeEventFilter(self)
        elif mode == NAVIGATION_MODE_GESTURES:
            self.setFixedHeight(self.HEIGHT_GESTURE)
            self.back_button.hide()
            self.home_button.hide()
            self.recent_button.hide()
            self.installEventFilter(self)
            self._fade_indicator(1.0)
        else:
            self.set_navigation_mode(NAVIGATION_MODE_THREE_BUTTON)
        self.update()

    def update_language(self, language: str):
        """Глифы не зависят от языка — метод оставлен для совместимости."""
        self.update()

    def set_is_light_background(self, is_light: bool):
        """Инвертирует чернила панели под светлый/тёмный фон (стекло iOS)."""
        color = QColor("#000000") if is_light else QColor("#FFFFFF")
        color.setAlpha(210 if is_light else 235)
        self._ink = color
        for b in (self.back_button, self.home_button, self.recent_button):
            b.set_ink(color)
        self.update()

    def _fade_indicator(self, target: float):
        self._ind_target = target
        if not hasattr(self, "_ind_driver"):
            self._ind_driver = None

        start = self._indicator_alpha

        def frame(p):
            self._indicator_alpha = start + (target - start) * p
            self.update()

        self._ind_driver = _FrameDriver(260, Easing.STANDARD, frame, None, parent=self)
        self._ind_driver.start()

    # ------------------------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.current_mode != NAVIGATION_MODE_GESTURES and self._indicator_alpha <= 0.01:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        alpha = self._indicator_alpha
        if alpha > 0.01:
            ink = QColor(self._ink)
            ink.setAlpha(int(ink.alpha() * alpha))
            h = 5.0
            w = self._indicator_w
            rect = QRectF((self.width() - w) / 2.0,
                          self.height() - h - 6.0, w, h)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(ink))
            path = QPainterPath()
            path.addRoundedRect(rect, h / 2.0, h / 2.0)
            p.drawPath(path)
        p.end()

    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        """Поддержка мыши в режиме жестов (для десктоп-теста)."""
        if self.current_mode == NAVIGATION_MODE_GESTURES:
            self._touch_start_pos = QPointF(event.pos())
            self._touch_last_pos = QPointF(event.pos())
            self._is_touch_active = True
            self._long_press_timer.singleShot(
                self._long_press_timer_threshold, self._on_long_press_timeout)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.current_mode == NAVIGATION_MODE_GESTURES and self._is_touch_active:
            cur = QPointF(event.pos())
            dx = cur.x() - self._touch_start_pos.x()
            dy = cur.y() - self._touch_start_pos.y()
            if abs(dx) > self._gesture_threshold / 2 or abs(dy) > self._gesture_threshold / 2:
                self._long_press_timer.stop()
            self._touch_last_pos = cur
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.current_mode == NAVIGATION_MODE_GESTURES and self._is_touch_active:
            self._is_touch_active = False
            self._long_press_timer.stop()
            self._recognize_swipe(QPointF(event.pos()))
        super().mouseReleaseEvent(event)

    def _recognize_swipe(self, end_pos: QPointF):
        delta_x = end_pos.x() - self._touch_start_pos.x()
        delta_y = end_pos.y() - self._touch_start_pos.y()
        if abs(delta_x) > self._gesture_threshold or abs(delta_y) > self._gesture_threshold:
            if abs(delta_x) > abs(delta_y):
                if delta_x > self._gesture_threshold:
                    print("Gesture: Swipe Right (Recent)")
                    self.recent_button_pressed.emit()
                elif delta_x < -self._gesture_threshold:
                    print("Gesture: Swipe Left (Back)")
                    self.back_button_pressed.emit()
            else:
                if delta_y < -self._gesture_threshold:
                    print("Gesture: Swipe Up (Home)")
                    self.home_button_pressed.emit()

    def eventFilter(self, obj, event):
        if obj == self and self.current_mode == NAVIGATION_MODE_GESTURES:
            if event.type() in (QEvent.TouchBegin, QEvent.TouchUpdate,
                               QEvent.TouchEnd, QEvent.TouchCancel):
                return self.touchEvent(event)
        return super().eventFilter(obj, event)

    def touchEvent(self, event):
        touch_points = event.touchPoints()
        if not touch_points:
            return False
        primary = touch_points[0]
        if event.type() == QEvent.TouchBegin:
            self._touch_start_pos = QPointF(primary.pos())
            self._touch_last_pos = QPointF(primary.pos())
            self._is_touch_active = True
            self._long_press_timer.singleShot(
                self._long_press_timer_threshold, self._on_long_press_timeout)
            return True
        elif event.type() == QEvent.TouchUpdate:
            if self._is_touch_active:
                cur = QPointF(primary.pos())
                dx = cur.x() - self._touch_start_pos.x()
                dy = cur.y() - self._touch_start_pos.y()
                if abs(dx) > self._gesture_threshold / 2 or abs(dy) > self._gesture_threshold / 2:
                    self._long_press_timer.stop()
                self._touch_last_pos = cur
                return True
        elif event.type() in (QEvent.TouchEnd, QEvent.TouchCancel):
            if self._is_touch_active:
                self._is_touch_active = False
                self._long_press_timer.stop()
                self._recognize_swipe(QPointF(primary.pos()))
            return True
        return super().event(event) if hasattr(super(), "touchEvent") else False

    def _on_long_press_timeout(self):
        if self._is_touch_active:
            # Долгое удержание на индикаторе = недавние приложения (как на iPhone)
            self.recent_button_pressed.emit()


# Пример использования (запуск файла напрямую)
if __name__ == "__main__":
    import sys
    app = QApplication(sys.argv)
    main_window = QMainWindow()
    main_window.setGeometry(100, 100, 400, 800)

    central_container = QWidget()
    main_window.setCentralWidget(central_container)
    from PyQt5.QtWidgets import QVBoxLayout
    main_layout = QVBoxLayout(central_container)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    top_content = QLabel("Приложение или контент")
    top_content.setAlignment(Qt.AlignCenter)
    top_content.setStyleSheet("background-color: #555; color: white; font-size: 20px;")
    main_layout.addWidget(top_content, 1)

    nav_bar = NavigationBarWidget(main_window, initial_mode=NAVIGATION_MODE_THREE_BUTTON)
    nav_bar.home_button_pressed.connect(lambda: print("Home!"))
    nav_bar.back_button_pressed.connect(lambda: print("Back!"))
    nav_bar.recent_button_pressed.connect(lambda: print("Recent!"))
    main_layout.addWidget(nav_bar, alignment=Qt.AlignBottom)

    mode_toggle_button = QPushButton("Переключить режим навигации")
    mode_toggle_button.clicked.connect(
        lambda: nav_bar.set_navigation_mode(
            NAVIGATION_MODE_GESTURES if nav_bar.current_mode == NAVIGATION_MODE_THREE_BUTTON
            else NAVIGATION_MODE_THREE_BUTTON))
    main_layout.addWidget(mode_toggle_button, alignment=Qt.AlignCenter)

    main_window.show()
    sys.exit(app.exec_())
