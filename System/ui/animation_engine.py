# ui/animation_engine.py
"""
HIXOS Animation Engine — система анимаций в стиле OriginOS 5 / HyperOS 2 / iOS 18.

Ключевые особенности:
  * Защита от пропуска кадров (Delta-Clamped FrameDriver): тяжёлые операции Qt
    в момент старта анимации (grab окна, переключение стека) не съедают первые кадры;
  * Детальный 3-фазный выход из приложения (run_close):
      1) Отрыв окна от краёв экрана в парящую карточку со скруглением углов и тенью;
      2) Полёт по параболической дуге с независимой интерполяцией X/Y и пропорций;
      3) Пружинная посадка (spring cushion) точно в слот иконки с бликом кромки;
  * Эластичный заход в приложение (run_open) с дуговой траекторией и glass-splash;
  * Безопасная работа с QLayout и QStackedWidget без слипания сетки и наслоений.
"""

import math
from typing import Callable, Optional, List, Tuple

from PyQt5.QtCore import (
    QEasingCurve, QObject, QPropertyAnimation, pyqtProperty,
    QTimer, QElapsedTimer, QRect, QRectF, QPoint, QPointF, Qt
)
from PyQt5.QtWidgets import QWidget, QGraphicsOpacityEffect
from PyQt5.QtGui import (
    QPixmap, QPainter, QPainterPath, QColor, QPen,
    QLinearGradient, QRadialGradient
)

# --- Палитра акцентов OxygenOS / OriginOS / iOS ---
OXYGREEN = "#00D1A0"      # фирменный акцент OxygenOS
IOSTEAL = "#0A84FF"       # акцент iOS (тёмная тема)


def _activate_widget_layouts(widget: Optional[QWidget]):
    """Принудительно пересчитывает QLayout у виджета и его контейнеров,
    чтобы до старта анимации все дочерние элементы имели финальные координаты."""
    if widget is None:
        return
    try:
        if widget.layout() is not None:
            widget.layout().activate()
        for child in widget.findChildren(QWidget):
            if child.layout() is not None:
                child.layout().activate()
    except RuntimeError:
        pass


class CubicBezierCurve(QEasingCurve):
    """Точная кривая cubic-bezier(x1, y1, x2, y2).

    В покадровом _FrameDriver считает точный полином Безье методом Ньютона-Рафсона,
    а для стандартного QPropertyAnimation имеет безопасный нативный профиль Qt.
    """

    def __init__(self, x1: float, y1: float, x2: float, y2: float,
                 qt_fallback: QEasingCurve.Type = QEasingCurve.OutCubic):
        super().__init__(qt_fallback)
        self._x1, self._y1, self._x2, self._y2 = x1, y1, x2, y2

    @staticmethod
    def _sample(t: float, p1: float, p2: float) -> float:
        mt = 1.0 - t
        return 3.0 * mt * mt * t * p1 + 3.0 * mt * t * t * p2 + t * t * t

    @staticmethod
    def _slope(t: float, p1: float, p2: float) -> float:
        mt = 1.0 - t
        return 3.0 * mt * mt * p1 + 6.0 * mt * t * (p2 - p1) + 3.0 * t * t * (1.0 - p2)

    def getPoint(self, progress: float) -> float:
        if progress <= 0.0:
            return 0.0
        if progress >= 1.0:
            return 1.0

        t = progress
        for _ in range(5):
            slope = self._slope(t, self._x1, self._x2)
            if abs(slope) < 1e-6:
                break
            x = self._sample(t, self._x1, self._x2) - progress
            t = max(0.0, min(1.0, t - x / slope))

        if abs(self._sample(t, self._x1, self._x2) - progress) > 1e-4:
            lo, hi = 0.0, 1.0
            for _ in range(14):
                mid = (lo + hi) * 0.5
                if self._sample(mid, self._x1, self._x2) < progress:
                    lo = mid
                else:
                    hi = mid
            t = (lo + hi) * 0.5

        return self._sample(t, self._y1, self._y2)


def _bezier(x1: float, y1: float, x2: float, y2: float,
            fallback: QEasingCurve.Type = QEasingCurve.OutCubic) -> CubicBezierCurve:
    return CubicBezierCurve(x1, y1, x2, y2, fallback)


class Easing:
    """Централизованные easing-кривые в стиле OriginOS 5 / HyperOS 2 / iOS 18."""

    # Основная сбалансированная кривая интерфейса
    STANDARD = _bezier(0.22, 0.82, 0.20, 1.0, QEasingCurve.OutQuart)

    # Плавное торможение для панелей и карточек
    DECELERATE = _bezier(0.20, 0.90, 0.24, 1.0, QEasingCurve.OutQuint)

    # Мягкое ускорение для скрытия элементов
    ACCELERATE = _bezier(0.32, 0.0, 0.78, 0.18, QEasingCurve.InQuad)

    # Заход в приложение (OriginOS / iOS): мягкий подхват иконки (без мгновенного
    # телепорта в первые 50 мс) + эластичное раскрытие в полноэкранное окно
    LAUNCH = _bezier(0.28, 0.08, 0.22, 1.0, QEasingCurve.InOutCubic)

    # Выход из приложения (HyperOS / iOS): плавный отрыв от краёв и мягкое притяжение в слот
    DISMISS = _bezier(0.24, 0.12, 0.20, 1.0, QEasingCurve.InOutCubic)

    # Универсальный профиль морфа
    MORPH = LAUNCH

    # Живой возврат с лёгким пружинным перелётом (overshoot)
    SPRING = _bezier(0.32, 1.38, 0.62, 1.0, QEasingCurve.OutBack)

    # Полноэкранный переход в стиле iOS
    IOS_TRANSITION = _bezier(0.28, 0.80, 0.20, 1.0, QEasingCurve.OutCubic)


class Duration:
    """Стандартные длительности (мс) по референсам iOS 18 / OriginOS 5 / HyperOS 2."""

    MICRO = 140        # отклик на нажатие
    SHORT = 230        # мелкие state-переходы
    STANDARD = 340     # появление/скрытие контента
    TRANSITION = 420   # переходы между страницами
    LAUNCH = 530       # разворот иконки в приложение (плавный и читаемый глазом)
    DISMISS = 590      # детальное сворачивание окна обратно в иконку
    STAGGER_STEP = 25  # шаг задержки между иконками в волне


def spring_progress(p: float, damping: float = 0.78) -> float:
    """Пружинное затухание с лёгким overshoot и точным приходом в 1.0."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    val = 1.0 - math.exp(-5.8 * p) * math.cos(damping * math.pi * p)
    if p > 0.86:
        blend = (p - 0.86) / 0.14
        return val * (1.0 - blend) + blend
    return val


def fly_in_transform(local_p: float) -> Tuple[float, float, float]:
    """Трансформация «прилёта» иконки при разблокировке (iOS / OriginOS unlock)."""
    if local_p <= 0.0:
        return 46.0, 0.85, 0.0
    if local_p >= 1.0:
        return 0.0, 1.0, 1.0
    s = spring_progress(local_p)
    dy = 46.0 * (1.0 - s)
    scale = 0.85 + 0.15 * s
    opacity = min(1.0, local_p * 2.5)
    return dy, scale, opacity


def animate(target: QObject, prop: bytes, start, end,
            duration: int = Duration.STANDARD,
            curve: QEasingCurve = Easing.STANDARD,
            parent=None) -> QPropertyAnimation:
    """Фабрика QPropertyAnimation."""
    anim = QPropertyAnimation(target, prop, parent if parent else target)
    anim.setDuration(max(1, int(duration)))
    anim.setStartValue(start)
    anim.setEndValue(end)
    anim.setEasingCurve(curve)
    return anim


class _FrameDriver(QObject):
    """Покадровый драйвер с защитой от пропуска кадров (Delta-Time Clamping).

    Если в момент старта анимации главный поток Qt занят (например, делает
    grab() окна или переключает QStackedWidget и тратит 50–80 мс), обычный
    таймер пропускает всю начальную фазу анимации.
    Этот драйвер ограничивает шаг времени за один кадр (max 16.5 мс), поэтому
    любая анимация гарантированно отрисовывает все свои фазы от 0.0 до 1.0.
    """

    def __init__(self, duration_ms: int, curve, on_frame: Callable[[float], None],
                 on_finished: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(10)  # ~100 FPS
        self._clock = QElapsedTimer()
        self._duration = max(int(duration_ms), 1)
        self._curve = curve
        self._on_frame = on_frame
        self._on_finished = on_finished
        self._virtual_elapsed = 0.0
        self._last_real_ms = 0
        self._timer.timeout.connect(self._tick)

    def _eval(self, p: float) -> float:
        try:
            if hasattr(self._curve, "getPoint"):
                return self._curve.getPoint(p)
            if isinstance(self._curve, QEasingCurve):
                return self._curve.valueForProgress(p)
        except Exception:
            pass
        return p

    def _tick(self):
        now = self._clock.elapsed()
        raw_dt = max(1, now - self._last_real_ms)
        self._last_real_ms = now

        # Ограничиваем скачок времени максимум 16.5 мс за кадр:
        # даже если Qt задумался при переключении окон, анимация не перескочит!
        dt = min(float(raw_dt), 16.5)
        self._virtual_elapsed += dt

        p = min(self._virtual_elapsed / self._duration, 1.0)
        eased = self._eval(p)
        self._on_frame(eased)

        if p >= 1.0:
            self._timer.stop()
            if self._on_finished:
                self._on_finished()

    def start(self):
        self._virtual_elapsed = 0.0
        self._last_real_ms = 0
        self._clock.start()
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def is_running(self) -> bool:
        return self._timer.isActive()


class MorphOverlay(QWidget):
    """Детальный морф-переход в стиле iOS 18 / OriginOS 5 / HyperOS 2.

    Поддерживает два детализированных сценария:
      1. ОТКРЫТИЕ (run_open, 530 мс):
         - Иконка плавно отрывается от рабочего стола, отбрасывая глубокую тень;
         - Центр карточки движется по естественной параболической дуге к центру экрана;
         - Пропорции эластично перетекают из квадрата иконки в формат окна;
         - Внутри карточки рисуется стеклянный градиент с мягким свечением вокруг
           логотипа приложения, который плавно уступает место интерфейсу окна.

      2. ЗАКРЫТИЕ (run_close, 590 мс — 3 фазы):
         - Фаза 1 (Detach & Pull-Back, 0..22%): окно отрывается от краёв экрана,
           уменьшаясь до парящей карточки (~82% экрана) со скруглением углов до 32px
           и глубокой тенью поверх проявляющегося рабочего стола;
         - Фаза 2 (Arc Flight & Aspect Morph, 22..88%): парящее окно летит по дуге
           к слоту иконки (с лёгким невесомым подбросом вверх, как в HyperOS 2),
           плавно меняя пропорции с 9:16 на квадрат squircle. По стеклу карточки
           проходит диагональный блик, а внутри без сплющивания виден интерфейс окна;
         - Фаза 3 (Spring Cushion & Landing Glow, 88..100%): карточка мягко пружинит
           в слоте иконки (0.94x -> 1.0x), подсвечивает контур иконки и бесшовно
           перетекает в настоящую иконку лаунчера.
    """

    def __init__(self, container: QWidget, icon_rect: QRect, target_rect: QRect,
                 pixmap: QPixmap = None, corner_start: int = 20, corner_end: int = 6,
                 snapshot: QPixmap = None, rects_local: bool = False):
        super().__init__(container)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_TranslucentBackground)
        try:
            self.setAttribute(Qt.WA_ForceActiveWindowsPainting, True)
        except AttributeError:
            pass

        self.setGeometry(container.rect())
        self._icon_rect = QRectF(icon_rect)
        self._target_rect = QRectF(target_rect)

        if not rects_local:
            tl = container.mapFromGlobal(icon_rect.topLeft())
            self._icon_rect.moveTo(QPointF(tl))
            if target_rect.topLeft() != QPoint(0, 0):
                t_tl = container.mapFromGlobal(target_rect.topLeft())
                self._target_rect.moveTo(QPointF(t_tl))
            else:
                self._target_rect = QRectF(container.rect())
        else:
            if self._target_rect.isNull():
                self._target_rect = QRectF(container.rect())

        # Страховка, если target_rect или icon_rect оказались пустыми
        if self._target_rect.width() <= 2 or self._target_rect.height() <= 2:
            self._target_rect = QRectF(container.rect())
        if self._icon_rect.width() <= 2 or self._icon_rect.height() <= 2:
            cw, ch = container.width() or 519, container.height() or 950
            self._icon_rect = QRectF(cw * 0.5 - 30.0, ch * 0.75 - 30.0, 60.0, 60.0)

        self._pixmap = pixmap
        self._snapshot = snapshot
        self._corner_start = float(corner_start)
        self._corner_end = float(corner_end)

        # _progress всегда отражает состояние раскрытия: 0.0 = иконка, 1.0 = полное окно
        self._progress = 0.0
        # _close_t: 0.0 (начало закрытия, полный экран) .. 1.0 (конец закрытия, в иконке)
        self._close_t = 0.0
        self._closing = False
        self._driver: Optional[_FrameDriver] = None
        self._on_done: Optional[Callable[[], None]] = None

    def set_progress(self, p: float):
        """Устанавливает прогресс (0.0 = иконка, 1.0 = окно)."""
        p_clamped = max(0.0, min(1.0, float(p)))
        self._progress = p_clamped
        if self._closing:
            self._close_t = 1.0 - p_clamped
        self.update()

    def _set_close_step(self, close_t: float):
        """Прямой шаг анимации закрытия: close_t идёт от 0.0 (экран) до 1.0 (иконка)."""
        t = max(0.0, min(1.0, float(close_t)))
        self._close_t = t
        self._progress = 1.0 - t
        self.update()

    # -------------------------------------------------------------------------
    # ГЕОМЕТРИЯ И ФИЗИКА ОТКРЫТИЯ / ЗАКРЫТИЯ (OriginOS / HyperOS / iOS)
    # -------------------------------------------------------------------------

    def _compute_open_geometry(self, p: float) -> Tuple[QRectF, float, float]:
        """Возвращает (cur_rect, corner_radius, elevation_k) для открытия окна (p: 0 -> 1)."""
        ix, iy = self._icon_rect.x(), self._icon_rect.y()
        iw, ih = self._icon_rect.width(), self._icon_rect.height()
        tx, ty = self._target_rect.x(), self._target_rect.y()
        tw, th = self._target_rect.width(), self._target_rect.height()

        icx, icy = ix + iw * 0.5, iy + ih * 0.5
        tcx, tcy = tx + tw * 0.5, ty + th * 0.5

        # Дуговая траектория центра: горизонталь выходит в центр экрана чуть быстрее вертикали
        px = p ** 0.76
        py = p ** 0.94
        # Лёгкий подъём вверх на старте (эффект всплытия иконки над столом)
        lift_dy = -14.0 * math.sin(p * math.pi) * (1.0 - p * 0.5)

        cx = icx + (tcx - icx) * px
        cy = icy + (tcy - icy) * py + lift_dy

        # Эластичное раскрытие размеров: сначала иконка превращается в карточку, затем в экран
        pw = p ** 0.88
        ph = p ** 0.96
        w = iw + (tw - iw) * pw
        h = ih + (th - ih) * ph

        # В середине полёта радиус скругления увеличивается до карточки (28px),
        # а при посадке в края экрана уменьшается до corner_end
        mid_boost = 10.0 * math.sin(p * math.pi)
        r = self._corner_start + (self._corner_end - self._corner_start) * (p ** 0.85) + mid_boost
        elevation = math.sin(p * math.pi)

        return QRectF(cx - w * 0.5, cy - h * 0.5, w, h), max(2.0, r), elevation

    def _compute_close_geometry(self, t: float) -> Tuple[QRectF, float, float]:
        """Возвращает (cur_rect, corner_radius, elevation_k) для 3-фазного закрытия (t: 0 -> 1).

        t = 0.0 -> полноэкранное окно;
        t = 1.0 -> посадка в слот иконки.
        """
        ix, iy = self._icon_rect.x(), self._icon_rect.y()
        iw, ih = self._icon_rect.width(), self._icon_rect.height()
        tx, ty = self._target_rect.x(), self._target_rect.y()
        tw, th = self._target_rect.width(), self._target_rect.height()

        icx, icy = ix + iw * 0.5, iy + ih * 0.5
        tcx, tcy = tx + tw * 0.5, ty + th * 0.5

        # 1. Траектория центра (cx, cy):
        # В первой фазе (0..0.18) окно отрывается от краёв почти в центре экрана,
        # затем по параболической дуге с лёгким подбросом летит в центр иконки
        move_t = max(0.0, min(1.0, (t - 0.06) / 0.90))
        # Плавная S-кривая с мягким торможением у слота иконки
        eased_move = 1.0 - (1.0 - move_t) ** 2.6
        px = min(1.0, eased_move ** 0.82)   # X быстрее выходит на линию иконки
        py = min(1.0, eased_move ** 1.05)   # Y плавно опускается по дуге

        # Невесомый подброс карточки вверх при отрыве от экрана (HyperOS / iOS gesture feel)
        arc_lift = -22.0 * math.sin(move_t * math.pi) * (1.0 - move_t * 0.4)

        cx = tcx + (icx - tcx) * px
        cy = tcy + (icy - tcy) * py + arc_lift

        # 2. Эластичное изменение размеров (w, h) и пропорций:
        # Ширина и высота уменьшаются с разной степенью кривизны, чтобы прямоугольное
        # окно 9:16 заранее превратилось в аккуратный квадратный squircle 1:1
        size_t = 1.0 - (1.0 - t) ** 2.35
        pw = min(1.0, size_t ** 0.85)
        ph = min(1.0, size_t ** 0.72)  # Высота подтягивается к квадрату быстрее!

        w = tw + (iw - tw) * pw
        h = th + (ih - th) * ph

        # 3. Пружинная амортизация (Spring Cushion) при посадке в слот (t = 0.82..1.0):
        # Карточка слегка сжимается до 0.93x размера иконки и мягко расправляется в 1.0x
        if t > 0.80:
            land_phase = (t - 0.80) / 0.20  # 0..1
            cushion = 1.0 - 0.065 * math.sin(land_phase * math.pi)
            w *= cushion
            h *= cushion

        # 4. Скругление углов:
        # В начале закрытия (t = 0..0.25) углы окна быстро скругляются с 6px до 32px
        # (эффект парящей карточки iOS/OriginOS), а к концу плавно приходят к радиусу иконки
        card_arch = 16.0 * math.sin(min(1.0, t * 1.15) * math.pi)
        base_r = self._corner_end + (self._corner_start - self._corner_end) * (t ** 0.55)
        r = min(min(w, h) * 0.46, base_r + card_arch)

        # Высота парения над столом для расчёта глубины тени
        elevation = math.sin(min(1.0, t * 1.08) * math.pi)
        return QRectF(cx - w * 0.5, cy - h * 0.5, w, h), max(2.0, r), elevation

    # -------------------------------------------------------------------------
    # ОТРИСОВКА КАДРА (PAINT EVENT)
    # -------------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        if self._closing:
            self._paint_close(painter, self._close_t)
        else:
            self._paint_open(painter, self._progress)

    def _draw_elevation_shadow(self, painter: QPainter, rect: QRectF, r: float, elevation: float):
        """Рисует мягкую многослойную тень под парящей карточкой окна."""
        if elevation <= 0.02:
            return
        for layer, (spread, dy, base_alpha) in enumerate(((4.0, 2.5, 58), (10.0, 6.0, 38), (18.0, 11.0, 20))):
            k = spread * (0.5 + 0.5 * elevation)
            s_rect = rect.adjusted(-k, -k + dy * elevation, k, k + dy * elevation)
            s_path = QPainterPath()
            s_path.addRoundedRect(s_rect, r + k * 0.45, r + k * 0.45)
            alpha = int(base_alpha * elevation)
            if alpha > 1:
                painter.fillPath(s_path, QColor(0, 0, 0, alpha))

    def _draw_stylized_window_interior(self, painter: QPainter, rect: QRectF, progress_open: float):
        """Если snapshot окна не передан, рисует детализированную стеклянную карточку
        окна (градиент, шапку и мягкие skeleton-блоки), чтобы окно выглядело живым."""
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0.0, QColor(34, 40, 54))
        grad.setColorAt(0.5, QColor(24, 28, 38))
        grad.setColorAt(1.0, QColor(18, 21, 30))
        painter.fillRect(rect, grad)

        # Мягкое радиальное свечение в центре карточки (OriginOS glass)
        rad = QRadialGradient(rect.center(), max(rect.width(), rect.height()) * 0.55)
        rad.setColorAt(0.0, QColor(10, 132, 255, int(38 * progress_open)))
        rad.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(rect, rad)

        # Деликатная имитация элементов интерфейса окна при большом размере карточки
        if progress_open > 0.25 and rect.width() > 110 and rect.height() > 140:
            ui_alpha = int(min(1.0, (progress_open - 0.25) / 0.55) * 28)
            w, h = rect.width(), rect.height()
            x, y = rect.x(), rect.y()
            # Верхний бар приложения
            header_h = min(42.0, h * 0.08)
            painter.fillRect(QRectF(x, y, w, header_h), QColor(255, 255, 255, int(ui_alpha * 0.6)))
            # Полупрозрачные карточки контента
            pad = w * 0.07
            card_w = w - pad * 2.0
            if card_w > 20:
                c1 = QPainterPath()
                c1.addRoundedRect(QRectF(x + pad, y + header_h + pad, card_w, h * 0.16), 10.0, 10.0)
                painter.fillPath(c1, QColor(255, 255, 255, ui_alpha))

    def _draw_glass_rim_and_sheen(self, painter: QPainter, rect: QRectF, clip_path: QPainterPath,
                                  r: float, flight_k: float, sweep_pos: float):
        """Рисует диагональный световой блик по стеклу и тонкий кант (HyperOS / iOS)."""
        if flight_k <= 0.02:
            return

        # 1. Диагональный световой блик по поверхности карточки во время полёта
        painter.save()
        painter.setClipPath(clip_path)
        sheen_x = rect.x() - rect.width() * 0.4 + rect.width() * 1.8 * sweep_pos
        sheen_grad = QLinearGradient(
            QPointF(sheen_x - rect.width() * 0.35, rect.top()),
            QPointF(sheen_x + rect.width() * 0.35, rect.bottom())
        )
        sheen_alpha = int(28 * flight_k)
        sheen_grad.setColorAt(0.0, QColor(255, 255, 255, 0))
        sheen_grad.setColorAt(0.5, QColor(255, 255, 255, sheen_alpha))
        sheen_grad.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.fillRect(rect, sheen_grad)
        painter.restore()

        # 2. Спекулярная стеклянная рамка (светлее сверху-слева, мягче снизу-справа)
        rim_grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        rim_grad.setColorAt(0.0, QColor(255, 255, 255, int(95 * flight_k)))
        rim_grad.setColorAt(0.5, QColor(255, 255, 255, int(40 * flight_k)))
        rim_grad.setColorAt(1.0, QColor(10, 132, 255, int(55 * flight_k)))
        pen = QPen(rim_grad, 1.35)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect.adjusted(0.6, 0.6, -0.6, -0.6), r, r)

    def _paint_open(self, painter: QPainter, p: float):
        """Отрисовка захода в приложение (p: 0.0 -> 1.0)."""
        cur_rect, r, elevation = self._compute_open_geometry(p)
        iw, ih = self._icon_rect.width(), self._icon_rect.height()

        # 1. Глубокое притемнение рабочего стола под растущим окном
        backdrop_alpha = int(125 * (p ** 0.75))
        if backdrop_alpha > 1:
            painter.fillRect(self.rect(), QColor(6, 8, 14, backdrop_alpha))

        # 2. Многослойная тень парения
        self._draw_elevation_shadow(painter, cur_rect, r, elevation)

        # 3. Тело карточки
        clip_path = QPainterPath()
        clip_path.addRoundedRect(cur_rect, r, r)

        painter.save()
        painter.setClipPath(clip_path)

        has_snap = self._snapshot is not None and not self._snapshot.isNull()
        has_icon = self._pixmap is not None and not self._pixmap.isNull()

        # Рисуем стеклянный фон окна
        self._draw_stylized_window_interior(painter, cur_rect, p)

        # Если есть реальный снимок целевого окна — плавно проявляем его во второй половине
        if has_snap and p > 0.18:
            snap_alpha = min(1.0, (p - 0.18) / 0.62)
            painter.setOpacity(snap_alpha)
            snap_w = cur_rect.width()
            snap_h = self._target_rect.height() * (snap_w / max(1.0, self._target_rect.width()))
            painter.drawPixmap(
                QRectF(cur_rect.x(), cur_rect.y(), snap_w, max(cur_rect.height(), snap_h)),
                self._snapshot,
                QRectF(self._snapshot.rect())
            )

        # Отрисовка иконки приложения в центре растущей карточки (OriginOS splash)
        if has_icon:
            base_side = min(iw, ih) * 0.90
            # Иконка плавно вырастает в 1.48 раза в центре карточки
            side = base_side * (1.0 + 0.48 * (p ** 0.7))
            px = cur_rect.center().x() - side * 0.5
            py = cur_rect.center().y() - side * 0.5

            # Иконка держит чёткость до 55% пути, затем мягко растворяется в окно
            icon_alpha = 1.0 - max(0.0, (p - 0.55) / 0.45) * 0.88
            painter.setOpacity(icon_alpha)
            painter.drawPixmap(
                QRectF(px, py, side, side),
                self._pixmap,
                QRectF(self._pixmap.rect())
            )

        painter.restore()

        # 4. Стеклянный кант и диагональный блик
        self._draw_glass_rim_and_sheen(painter, cur_rect, clip_path, r, elevation, p)

    def _paint_close(self, painter: QPainter, t: float):
        """Детальная отрисовка 3-фазного выхода из приложения (t: 0.0 -> 1.0)."""
        cur_rect, r, elevation = self._compute_close_geometry(t)
        tw = max(1.0, self._target_rect.width())
        th = max(1.0, self._target_rect.height())

        has_snap = self._snapshot is not None and not self._snapshot.isNull()
        has_icon = self._pixmap is not None and not self._pixmap.isNull()

        # Общая прозрачность держится 100% на всём пути полёта (0..86%)
        # и мягко растворяется только в самом конце (86..100%) прямо внутри слота иконки!
        master_opacity = 1.0
        if t > 0.86:
            master_opacity = max(0.0, 1.0 - (t - 0.86) / 0.14)
        painter.setOpacity(master_opacity)

        # 1. Плавное высветление затемнённого рабочего стола по мере сворачивания окна
        backdrop_alpha = int(120 * ((1.0 - t) ** 1.35))
        if backdrop_alpha > 1:
            painter.fillRect(self.rect(), QColor(6, 8, 14, backdrop_alpha))

        # 2. Световой импульс вокруг слота иконки при посадке (t = 0.72..0.98)
        if t > 0.72:
            pulse_t = (t - 0.72) / 0.28
            pulse_alpha = int(math.sin(pulse_t * math.pi) * 75)
            if pulse_alpha > 2:
                glow_pad = 6.0 * math.sin(pulse_t * math.pi)
                glow_rect = cur_rect.adjusted(-glow_pad, -glow_pad, glow_pad, glow_pad)
                glow_pen = QPen(QColor(255, 255, 255, pulse_alpha), 1.8)
                painter.setPen(glow_pen)
                painter.setBrush(Qt.NoBrush)
                painter.drawRoundedRect(glow_rect, r + glow_pad * 0.5, r + glow_pad * 0.5)

        # 3. Глубокая многослойная тень под парящим окном
        self._draw_elevation_shadow(painter, cur_rect, r, elevation)

        # 4. Маска скруглённой карточки (Squircle)
        clip_path = QPainterPath()
        clip_path.addRoundedRect(cur_rect, r, r)

        painter.save()
        painter.setClipPath(clip_path)

        # Базовая стеклянная подложка карточки
        self._draw_stylized_window_interior(painter, cur_rect, 1.0 - t * 0.7)

        # Отрисовка реального кадра закрываемого окна (snapshot)
        if has_snap:
            # Масштабируем кадр окна строго пропорционально, чтобы UI не сплющивался,
            # и плавно смещаем фокус к центральной/верхней части при сжатии в иконку
            scale_ratio = max(cur_rect.width() / tw, cur_rect.height() / th * 0.65)
            snap_w = tw * scale_ratio
            snap_h = th * scale_ratio
            snap_x = cur_rect.center().x() - snap_w * 0.5
            snap_y = cur_rect.y() - (snap_h - cur_rect.height()) * 0.15 * t

            snap_alpha = 1.0
            if has_icon and t > 0.42:
                snap_alpha = max(0.0, 1.0 - (t - 0.42) / 0.42)

            painter.setOpacity(master_opacity * snap_alpha)
            painter.drawPixmap(
                QRectF(snap_x, snap_y, snap_w, snap_h),
                self._snapshot,
                QRectF(self._snapshot.rect())
            )

            # Мягкая стеклянная вуаль поверх сжимающегося скриншота на подлёте к иконке
            if t > 0.35:
                veil_alpha = int(min(1.0, (t - 0.35) / 0.55) * 65)
                painter.fillRect(cur_rect, QColor(20, 24, 34, veil_alpha))

        # Если передана иконка — во второй половине полёта она плавно проявляется в центре карточки
        if has_icon:
            icon_appear = 1.0 if not has_snap else max(0.0, min(1.0, (t - 0.32) / 0.45))
            if icon_appear > 0.01:
                painter.setOpacity(master_opacity * icon_appear)
                # Иконка плавно заполняет squircle по мере приближения к слоту
                fill_k = 0.55 + 0.38 * (t ** 0.8)
                side = min(cur_rect.width(), cur_rect.height()) * fill_k
                px = cur_rect.center().x() - side * 0.5
                py = cur_rect.center().y() - side * 0.5
                painter.drawPixmap(
                    QRectF(px, py, side, side),
                    self._pixmap,
                    QRectF(self._pixmap.rect())
                )

        painter.restore()

        # 5. Диагональный блик по стеклу и спекулярный кант карточки
        painter.setOpacity(master_opacity)
        self._draw_glass_rim_and_sheen(painter, cur_rect, clip_path, r, elevation, t)

    # -------------------------------------------------------------------------
    # УПРАВЛЕНИЕ ЗАПУСКОМ АНИМАЦИЙ
    # -------------------------------------------------------------------------

    def run_open(self, duration: int = Duration.LAUNCH, curve=None, on_finished=None):
        """Плавный эластичный разворот иконки в окно приложения."""
        self._closing = False
        self._on_done = on_finished
        self._progress = 0.0
        self._close_t = 1.0
        if self._driver:
            self._driver.stop()

        # Гарантируем, что минимальная длительность не станет слишком короткой
        actual_dur = max(int(duration), 480)
        self._driver = _FrameDriver(
            actual_dur,
            curve or Easing.LAUNCH,
            self.set_progress,
            self._finish,
            self
        )
        self.raise_()
        self.show()
        self.update()
        self._driver.start()

    def run_close(self, duration: int = Duration.DISMISS, curve=None, on_finished=None):
        """Детальное 3-фазное сворачивание окна обратно в иконку (OriginOS / HyperOS / iOS)."""
        self._closing = True
        self._on_done = on_finished
        self._progress = 1.0
        self._close_t = 0.0
        if self._driver:
            self._driver.stop()

        # Если snapshot не был передан и пиктограмма тоже пустая — пробуем снять
        # текущий кадр контейнера до первого тика, чтобы карточка закрытия была с текстурой
        if (self._snapshot is None or self._snapshot.isNull()) and self.parentWidget() is not None:
            try:
                self.hide()
                self._snapshot = self.parentWidget().grab(self._target_rect.toRect())
                self.show()
            except Exception:
                pass

        actual_dur = max(int(duration), 540)
        self._driver = _FrameDriver(
            actual_dur,
            curve or Easing.DISMISS,
            self._set_close_step,
            self._finish,
            self
        )
        self.raise_()
        self.show()
        self.update()
        self._driver.start()

    def run_reverse_from_current(self, duration: int = Duration.DISMISS, curve=None, on_finished=None):
        """Плавный возврат прерванного морфа из текущей точки обратно в иконку."""
        self._closing = True
        self._on_done = on_finished
        start_close_t = 1.0 - self._progress
        if self._driver:
            self._driver.stop()

        remaining = max(0.25, 1.0 - start_close_t)
        actual_dur = max(240, int(duration * remaining))
        self._driver = _FrameDriver(
            actual_dur,
            curve or Easing.DISMISS,
            lambda eased: self._set_close_step(start_close_t + (1.0 - start_close_t) * eased),
            self._finish,
            self
        )
        self.raise_()
        self.show()
        self.update()
        self._driver.start()

    def _finish(self):
        self.hide()
        try:
            owner = self.parent()
            if owner is not None and getattr(owner, "_morph", None) is self:
                owner._morph = None
        except RuntimeError:
            pass
        self.deleteLater()
        if self._on_done:
            self._on_done()


class RippleButton(QObject):
    """Кастомный ripple-эффект в стиле OxygenOS (Material-like)."""

    def __init__(self, host_widget):
        super().__init__(host_widget)
        self._host = host_widget
        self._progress = 0.0
        self._alpha = 0.0
        self._cx = 0
        self._cy = 0
        self._radius = 0.0
        self._color = (255, 255, 255)

        self._move_anim = QPropertyAnimation(self, b"progress", self)
        self._fade_anim = QPropertyAnimation(self, b"alpha", self)

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
        self._cx, self._cy = x, y
        self._color = color
        w, h = self._host.width(), self._host.height()
        self._radius = max(((max(x, w - x)) ** 2 + (max(y, h - y)) ** 2) ** 0.5, 1)

        self._move_anim.stop()
        self._fade_anim.stop()
        self._progress = 0.0
        self._alpha = 0.32
        self._move_anim.setDuration(420)
        self._move_anim.setStartValue(0.0)
        self._move_anim.setEndValue(1.0)
        self._move_anim.setEasingCurve(Easing.DECELERATE)
        self._fade_anim.setDuration(440)
        self._fade_anim.setStartValue(0.32)
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(Easing.ACCELERATE)
        self._move_anim.start()
        self._fade_anim.start()

    def paint(self, painter):
        if self._alpha <= 0.001:
            return
        r = self._radius * (0.25 + 0.75 * self._progress)
        col = QColor(*self._color)
        col.setAlphaF(min(max(self._alpha, 0.0), 1.0))
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setBrush(col)
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(QPointF(self._cx, self._cy), r, r)
        painter.restore()


class PageTransition(QObject):
    """Cross-fade + сдвиг между страницами в стиле iOS / OriginOS."""

    def __init__(self, host):
        super().__init__(host)
        self._host = host
        self._running = []

    def fade_scale_in(self, widget, start_scale: float = 0.94,
                      duration: int = Duration.STANDARD):
        widget.show()
        _activate_widget_layouts(widget)

        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)

        fade = QPropertyAnimation(effect, b"opacity", widget)
        fade.setDuration(duration)
        fade.setStartValue(0.0)
        fade.setEndValue(1.0)
        fade.setEasingCurve(Easing.STANDARD)

        base = widget.pos()
        start_pos = QPoint(base.x(), base.y() + 26)
        slide = QPropertyAnimation(widget, b"pos", widget)
        slide.setDuration(duration)
        slide.setStartValue(start_pos)
        slide.setEndValue(base)
        slide.setEasingCurve(Easing.DECELERATE)

        def _cleanup():
            widget.move(base)
            widget.setGraphicsEffect(None)

        fade.finished.connect(_cleanup)
        self._running = [fade, slide]
        fade.start(QPropertyAnimation.DeleteWhenStopped)
        slide.start(QPropertyAnimation.DeleteWhenStopped)

    def slide_in(self, widget, direction: str = "up",
                 distance: int = 58, duration: int = Duration.TRANSITION):
        widget.show()
        _activate_widget_layouts(widget)

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
        start_pos = QPoint(base.x() + dx, base.y() + dy)

        move = QPropertyAnimation(widget, b"pos", widget)
        move.setDuration(duration)
        move.setStartValue(start_pos)
        move.setEndValue(base)
        move.setEasingCurve(Easing.IOS_TRANSITION)

        def _cleanup():
            widget.move(base)
            widget.setGraphicsEffect(None)

        fade.finished.connect(_cleanup)
        self._running = [fade, move]
        fade.start(QPropertyAnimation.DeleteWhenStopped)
        move.start(QPropertyAnimation.DeleteWhenStopped)


class PageSwipe(QObject):
    """Горизонтальный переход между страницами QStackedWidget без наслоения и багов сетки."""

    def __init__(self, stack):
        super().__init__(stack)
        self._stack = stack
        self._active_driver: Optional[_FrameDriver] = None
        self._abort_current: Optional[Callable[[], None]] = None

    def transition_to(self, target_widget, direction: str = "forward",
                      duration: int = Duration.TRANSITION, on_finished=None):
        if self._abort_current is not None:
            self._abort_current()

        current = self._stack.currentWidget()
        if current is target_widget or current is None:
            self._stack.setCurrentWidget(target_widget)
            _activate_widget_layouts(target_widget)
            if on_finished:
                on_finished()
            return

        geo = QRect(self._stack.rect())
        w = geo.width() or 519
        h = geo.height() or 950
        sign = 1 if direction == "forward" else -1

        out_pixmap = None
        if current.isVisible():
            try:
                out_pixmap = current.grab()
            except Exception:
                out_pixmap = None

        target_widget.setGeometry(geo)
        self._stack.setCurrentWidget(target_widget)
        _activate_widget_layouts(target_widget)

        ghost = None
        if out_pixmap is not None and not out_pixmap.isNull():
            ghost = QWidget(self._stack)
            ghost.setAttribute(Qt.WA_TransparentForMouseEvents)
            ghost.setAttribute(Qt.WA_NoSystemBackground)
            ghost.setAttribute(Qt.WA_TranslucentBackground)
            ghost.setGeometry(geo)
            ghost_opacity = [1.0]
            ghost_offset = [0.0]

            def _paint_ghost(ev):
                p_painter = QPainter(ghost)
                p_painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
                p_painter.setOpacity(ghost_opacity[0])
                p_painter.drawPixmap(int(ghost_offset[0]), 0, out_pixmap)

            ghost.paintEvent = _paint_ghost
            ghost.show()

        target_widget.raise_()

        eff_in = QGraphicsOpacityEffect(target_widget)
        eff_in.setOpacity(0.0)
        target_widget.setGraphicsEffect(eff_in)

        start_tx = geo.x() + int(sign * w * 0.42)
        end_tx = geo.x()
        target_widget.move(start_tx, geo.y())

        finished_flag = [False]

        def on_frame(p: float):
            if finished_flag[0]:
                return
            tx = int(start_tx + (end_tx - start_tx) * p)
            target_widget.move(tx, geo.y())
            eff_in.setOpacity(min(1.0, p * 1.45))

            if ghost is not None:
                ghost_offset[0] = -sign * w * 0.25 * p
                ghost_opacity[0] = max(0.0, 1.0 - p * 1.85)
                ghost.update()

        def cleanup(run_callback: bool = True):
            if finished_flag[0]:
                return
            finished_flag[0] = True
            self._abort_current = None
            if self._active_driver is not None:
                self._active_driver.stop()
                self._active_driver = None

            target_widget.setGraphicsEffect(None)
            target_widget.setGeometry(geo)

            if ghost is not None:
                ghost.hide()
                ghost.deleteLater()

            if run_callback and on_finished:
                on_finished()

        self._abort_current = lambda: cleanup(run_callback=False)
        driver = _FrameDriver(duration, Easing.IOS_TRANSITION, on_frame,
                              lambda: cleanup(run_callback=True), self)
        self._active_driver = driver
        driver.start()


class StaggerReveal(QObject):
    """Волновое (staggered) появление виджетов сетки без сбоя координат QLayout."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._drivers: List[_FrameDriver] = []
        self._timers: List[QTimer] = []

    def run(self, widgets, apply_fn, step_ms: int = Duration.STAGGER_STEP,
            duration: int = Duration.STANDARD, curve=Easing.STANDARD, delay_ms: int = 0):
        self.cancel()
        widget_list = list(widgets)
        if not widget_list:
            return

        parent_w = widget_list[0].parentWidget()
        if parent_w is not None:
            _activate_widget_layouts(parent_w)

        for i, wdg in enumerate(widget_list):
            def _make_step(w=wdg):
                layout_checked = [False]

                def _step(p: float):
                    if not layout_checked[0]:
                        layout_checked[0] = True
                        pw = w.parentWidget()
                        if pw is not None and pw.layout() is not None:
                            pw.layout().activate()
                    apply_fn(w, p)

                return _step

            d = _FrameDriver(duration, curve, _make_step(), parent=self)
            self._drivers.append(d)

            wait_ms = max(16, delay_ms + i * step_ms)
            t = QTimer(self)
            t.setSingleShot(True)
            t.setTimerType(Qt.PreciseTimer)
            t.timeout.connect(d.start)
            self._timers.append(t)
            t.start(wait_ms)

    def stop_all(self):
        self.cancel()

    def cancel(self):
        for t in self._timers:
            t.stop()
            t.deleteLater()
        self._timers.clear()

        for d in self._drivers:
            d.stop()
            d.deleteLater()
        self._drivers.clear()

    @staticmethod
    def wave_transform(index: int, columns: int, progress: float):
        row = index // max(1, columns)
        col = index % max(1, columns)
        offset = (row + col) * 0.12
        p = (progress - offset) / max(1e-6, 1.0 - offset)
        return max(0.0, min(1.0, p))