# ui/animation_engine.py
"""
HIXOS Animation Engine — единственная система анимаций для всего рабочего стола.

Стиль: OxygenOS 13 / iOS 17 (на крайняк MIUI):
  * быстрые, но мягкие переходы (200-450 мс);
  * фирменная кривая OnePlus — «precise deceleration» (OutQuint / OutExpo);
  * spring-подобный возврат с лёгким overshoot при отпускании иконок;
  * staggered-появление иконок сетки волной (как в launcher'ах);
  * открытие приложений через morph-анимацию: иконка разворачивается в окно
    (iOS-style zoom transition), закрытие — сворачивание обратно в иконку;
  * параллельные cross-fade + scale, никаких «прыгающих» последовательностей.

Здесь же — палитра акцентов (OxygenOS green / iOS blue) и общие easing-профили.
Все модули системы (launcher, HIXOS, lockscreen, settings) импортируют движок
отсюда, чтобы анимации были консистентными во всей ОС.
"""

from PyQt5.QtCore import QEasingCurve, QObject, QPropertyAnimation, pyqtProperty, QTimer, QRect, QPoint, Qt
from PyQt5.QtWidgets import QWidget
from PyQt5.QtGui import QPixmap, QPainter

# --- Палитра акцентов OxygenOS / iOS (используется UI-компонентами) ---
OXYGREEN = "#00D1A0"      # фирменный акцент OxygenOS 13
IOSTEAL = "#0A84FF"       # акцент iOS (тёмная тема)


class CubicBezierCurve(QEasingCurve):
    """Настоящая cubic-bezier кривая (x1,y1,x2,y2) — как в CSS/iOS/Android.

    QEasingCurve в Qt5 не умеетпроизвольные Безье-профили, поэтому считаем
    y(t) численно: по x решаем через binary search, затем берем y.
    Это даёт точные профили вида cubic-bezier(0.05, 0.7, 0.1, 1.0).
    """

    def __init__(self, x1: float, y1: float, x2: float, y2: float):
        super().__init__(QEasingCurve.Linear)  # базовый тип значения не использует
        self._x1, self._y1, self._x2, self._y2 = x1, y1, x2, y2

    @staticmethod
    def _comp(t: float, p1: float, p2: float) -> float:
        mt = 1.0 - t
        return 3 * mt * mt * t * p1 + 3 * mt * t * t * p2 + t * t * t

    def getPoint(self, progress: float) -> float:
        if progress <= 0.0:
            return 0.0
        if progress >= 1.0:
            return 1.0
        lo, hi = 0.0, 1.0
        for _ in range(24):  # binary search по x(t)
            mid = (lo + hi) / 2.0
            x = self._comp(mid, self._x1, self._x2)
            if x < progress:
                lo = mid
            else:
                hi = mid
        t = (lo + hi) / 2.0
        return self._comp(t, self._y1, self._y2)


def _bezier(x1, y1, x2, y2) -> CubicBezierCurve:
    return CubicBezierCurve(x1, y1, x2, y2)


class Easing:
    """Централизованные easing-кривые в стиле OxygenOS/iOS."""

    # Основная кривая системы — «precise deceleration».
    # Точный профиль Material/OnePlus: cubic-bezier(0.05, 0.7, 0.1, 1.0).
    STANDARD = _bezier(0.05, 0.7, 0.1, 1.0)

    # Резкое торможение — появление контента (аналог OutExpo).
    DECELERATE = QEasingCurve.OutExpo

    # Мягкое ускорение — уход объектов с экрана (fade-out, сворачивание).
    ACCELERATE = QEasingCurve.InQuad

    # Symmetric — морф-переходы (иконка <-> окно), shared element.
    MORPH = QEasingCurve.InOutQuart

    # iOS spring-подобный возврат с лёгким overshoot (cubic-bezier(0.34, 1.56, 0.64, 1)).
    SPRING = _bezier(0.34, 1.56, 0.64, 1.0)

    # iOS standard curve для полноэкранных транзишенов.
    IOS_TRANSITION = _bezier(0.4, 0.0, 0.2, 1.0)


class Duration:
    """Стандартные длительности (мс). iOS: micro 100-200, transitions 250-400."""

    MICRO = 140        # отклик на нажатие (press feedback)
    SHORT = 220        # мелкие state-переходы
    STANDARD = 320     # появление/скрытие контента
    TRANSITION = 420   # полноэкранные переходы (открытие приложения)
    LAUNCH = 450       # morph-разворот иконки в приложение
    DISMISS = 300      # сворачивание приложения в иконку
    STAGGER_STEP = 26  # шаг задержки между иконками в волне появления


def animate(target: QObject, prop: bytes, start, end,
            duration: int = Duration.STANDARD,
            curve: QEasingCurve = Easing.STANDARD,
            parent=None) -> QPropertyAnimation:
    """Фабрика property-анимаций — чтобы не дублировать boilerplate по всей системе."""
    anim = QPropertyAnimation(target, prop, parent if parent else target)
    anim.setDuration(int(duration))
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(curve)
    return anim


class _FrameDriver(QObject):
    """Драйвер покадровой анимации: гоняет 0->1 за duration и отдаёт
    прогресс через callback, применяя easing-кривую вручную.

    Нужно потому, что PyQt5 не позволяет использовать Python-подклассы
    QEasingCurve внутри QPropertyAnimation (кривая копируется на C++ сторону).
    """

    def __init__(self, duration_ms: int, curve, on_frame, on_finished=None, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60 FPS
        self._duration = max(duration_ms, 1)
        self._curve = curve
        self._on_frame = on_frame
        self._on_finished = on_finished
        self._elapsed = 0
        self._timer.timeout.connect(self._tick)

    def _tick(self):
        self._elapsed += self._timer.interval()
        p = min(self._elapsed / self._duration, 1.0)
        try:
            eased = self._curve.getPoint(p) if hasattr(self._curve, "getPoint") else self._curve.valueForProgress(p)
        except Exception:
            eased = p
        self._on_frame(eased)
        if p >= 1.0:
            self._timer.stop()
            if self._on_finished:
                self._on_finished()

    def start(self):
        self._elapsed = 0
        self._timer.start()

    def stop(self):
        self._timer.stop()


class MorphOverlay(QWidget):
    """iOS/OxygenOS-style morph-переход: иконка разворачивается в окно приложения.

    Рисует скруглённый прямоугольник с pixmap'ом иконки поверх всего,
    интерполируя геометрию от rect иконки до rect контейнера + радиус
    скругления (squircle -> rounded rect), как zoom transition в iOS.
    """

    def __init__(self, container: QWidget, icon_rect: QRect, target_rect: QRect,
                 pixmap: QPixmap = None, corner_start: int = 22, corner_end: int = 4):
        super().__init__(container)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setGeometry(container.rect())
        self.raise_()
        self._icon_rect = QRect(icon_rect)
        self._target_rect = QRect(target_rect)
        # Переводим глобальные координаты иконки в координаты контейнера
        tl = container.mapFromGlobal(self._icon_rect.topLeft())
        self._icon_rect.moveTo(tl)
        self._pixmap = pixmap
        self._corner_start = corner_start
        self._corner_end = corner_end
        self._progress = 0.0
        self._driver = None
        self._on_done = None

    def set_progress(self, p: float):
        self._progress = p
        self.update()

    def paintEvent(self, event):
        from PyQt5.QtGui import QPainterPath, QColor
        p = self._progress
        # Интерполяция геометрии (ease уже применён драйвером)
        x = self._icon_rect.x() + (self._target_rect.x() - self._icon_rect.x()) * p
        y = self._icon_rect.y() + (self._target_rect.y() - self._icon_rect.y()) * p
        w = self._icon_rect.width() + (self._target_rect.width() - self._icon_rect.width()) * p
        h = self._icon_rect.height() + (self._target_rect.height() - self._icon_rect.height()) * p
        r = self._corner_start + (self._corner_end - self._corner_start) * p

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)

        path = QPainterPath()
        path.addRoundedRect(float(x), float(y), max(w, 1), max(h, 1), float(r), float(r))
        painter.fillPath(path, QColor(30, 34, 44))

        if self._pixmap and not self._pixmap.isNull():
            side = min(w, h) * 0.86
            px = x + (w - side) / 2.0
            py = y + (h - side) / 2.0
            scaled = self._pixmap.scaled(int(side), int(side), Qt.KeepAspectRatio,
                                         Qt.SmoothTransformation)
            painter.drawPixmap(int(px), int(py), scaled)
        super().paintEvent(event)

    def run_open(self, duration: int = Duration.LAUNCH, curve=None, on_finished=None):
        """Иконка -> экран. on_finished вызывается по окончании."""
        self._on_done = on_finished
        self._driver = _FrameDriver(duration, curve or Easing.MORPH,
                                    self.set_progress, self._finish, self)
        self.show()
        self._driver.start()

    def run_close(self, duration: int = Duration.DISMISS, curve=None, on_finished=None):
        """Экран -> иконка (реверс)."""
        self._on_done = on_finished
        self._driver = _FrameDriver(duration, curve or Easing.MORPH,
                                    lambda p: self.set_progress(1.0 - p),
                                    self._finish, self)
        self.show()
        self._driver.start()

    def _finish(self):
        self.hide()
        self.deleteLater()
        if self._on_done:
            self._on_done()


class RippleButton(QObject):
    """Кастомный ripple-эффект в стиле OxygenOS (Material-like).

    Рисует расходящееся полупрозрачное кольцо/круг из точки нажатия поверх
    произвольного QWidget-хостa. Используется кнопками настроек, дока и т.д.
    """

    def __init__(self, host_widget):
        super().__init__(host_widget)
        self._host = host_widget
        self._progress = 0.0     # 0..1 — ход растекания
        self._alpha = 0.0        # затухание
        self._cx = 0
        self._cy = 0
        self._radius = 0.0
        self._color = (255, 255, 255)

        self._move_anim = QPropertyAnimation(self, b"progress", self)
        self._fade_anim = QPropertyAnimation(self, b"alpha", self)
        self._group = None

    @pyqtProperty(float)
    def progress(self):
        return self._progress

    @progress.setter
    def progress(self, v):
        self._progress = v
        self._host.update()

    @pyqtProperty(float)
    def alpha(self):
        return self._alpha

    @alpha.setter
    def alpha(self, v):
        self._alpha = v
        self._host.update()

    def trigger(self, x: int, y: int, color=(255, 255, 255)):
        """Запустить ripple из точки (x, y) в координатах хоста."""
        from PyQt5.QtCore import QRectF
        self._cx, self._cy = x, y
        self._color = color
        # Радиус — до самого дальнего угла виджета
        w, h = self._host.width(), self._host.height()
        self._radius = max(((max(x, w - x)) ** 2 + (max(y, h - y)) ** 2) ** 0.5, 1)

        self._move_anim.stop()
        self._fade_anim.stop()
        self._progress = 0.0
        self._alpha = 0.35
        self._move_anim.setDuration(420)
        self._move_anim.setStartValue(0.0)
        self._move_anim.setEndValue(1.0)
        self._move_anim.setEasingCurve(Easing.DECELERATE)
        self._fade_anim.setDuration(420)
        self._fade_anim.setStartValue(0.35)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(Easing.ACCELERATE)
        self._move_anim.start()
        self._fade_anim.start()

    def paint(self, painter):
        """Вызывается из paintEvent хоста (после основной отрисовки)."""
        from PyQt5.QtGui import QColor
        from PyQt5.QtCore import Qt as _Qt
        if self._alpha <= 0.001:
            return
        r = self._radius * (0.3 + 0.7 * self._progress)
        col = QColor(*self._color)
        col.setAlphaF(min(max(self._alpha, 0.0), 1.0))
        painter.save()
        painter.setBrush(col)
        painter.setPen(_Qt.NoPen)
        painter.drawEllipse(int(self._cx - r), int(self._cy - r),
                            int(2 * r), int(2 * r))
        painter.restore()


class PageTransition(QObject):
    """Готовый cross-fade + scale переход между страницами в стиле iOS/OxygenOS.

    usage:
        pt = PageTransition(container_widget)
        pt.slide_in(target_widget, direction="up")     # снизу вверх, как iOS modal
        pt.fade_scale_in(target_widget)                # мягкое появление
    """

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self._running = []

    def fade_scale_in(self, widget, start_scale: float = 0.92,
                      duration: int = Duration.STANDARD):
        """Появление страницы: opacity 0->1 + scale start->1 (iOS-style)."""
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        from PyQt5.QtCore import QRect
        widget.show()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        fade = QPropertyAnimation(effect, b"opacity", widget)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(Easing.STANDARD)

        geom = widget.geometry()
        cx = geom.center().x()
        cy = geom.center().y()
        w0 = int(geom.width() * start_scale)
        h0 = int(geom.height() * start_scale)
        start_rect = QRect(cx - w0 // 2, cy - h0 // 2, w0, h0)

        slide = QPropertyAnimation(widget, b"geometry", widget)
        slide.setDuration(duration)
        slide.setStartValue(start_rect)
        slide.setEndValue(geom)
        slide.setEasingCurve(Easing.STANDARD)

        def _cleanup():
            widget.setGraphicsEffect(None)

        fade.finished.connect(_cleanup)
        self._running = [fade, slide]
        fade.start(QPropertyAnimation.DeleteWhenStopped)
        slide.start(QPropertyAnimation.DeleteWhenStopped)

    def slide_in(self, widget, direction: str = "up",
                 distance: int = 60, duration: int = Duration.TRANSITION):
        """Появление со смещением + fade — как модальное окно iOS."""
        from PyQt5.QtWidgets import QGraphicsOpacityEffect
        widget.show()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        fade = QPropertyAnimation(effect, b"opacity", widget)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(Easing.IOS_TRANSITION)

        base = widget.pos()
        offsets = {
            "up": (0, distance),
            "down": (0, -distance),
            "left": (distance, 0),
            "right": (-distance, 0),
        }
        dx, dy = offsets.get(direction, (0, distance))
        start_pos = base + __import__("PyQt5.QtCore", fromlist=["QPoint"]).QPoint(dx, dy)

        move = QPropertyAnimation(widget, b"pos", widget)
        move.setDuration(duration)
        move.setStartValue(start_pos)
        move.setEndValue(base)
        move.setEasingCurve(Easing.IOS_TRANSITION)

        def _cleanup():
            widget.setGraphicsEffect(None)

        fade.finished.connect(_cleanup)
        self._running = [fade, move]
        fade.start(QPropertyAnimation.DeleteWhenStopped)
        move.start(QPropertyAnimation.DeleteWhenStopped)
