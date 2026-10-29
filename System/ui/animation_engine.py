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


def _clamp01(v: float) -> float:
    return 0.0 if v < 0.0 else (1.0 if v > 1.0 else v)


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    """C1-непрерывный blend между фазами (гладкая S-кривая с нулевыми
    производными на концах). Именно отсутствие таких blend-ов создавало
    изломы скорости в точках переключения фаз detach/squeeze/landing."""
    t = _clamp01((x - edge0) / max(1e-6, edge1 - edge0))
    return t * t * (3.0 - 2.0 * t)


def _curve_value(curve, p: float) -> float:
    """Универсальное вычисление значения easing-кривой (CubicBezierCurve или QEasingCurve)."""
    try:
        if hasattr(curve, "getPoint"):
            return curve.getPoint(p)
        if isinstance(curve, QEasingCurve):
            return curve.valueForProgress(p)
    except Exception:
        pass
    return p


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

    # Точная кривая «сжатия окна в иконку» как в iOS App Switcher home-swipe:
    # почти мгновенный старт (палец уже отпустил), затем долгое мягкое торможение.
    # Это эталонный cubic-bezier(0.32, 0.72, 0, 1) из UIKit interactive transitions.
    IOS_DISMISS = _bezier(0.32, 0.72, 0.0, 1.0, QEasingCurve.InOutCubic)

    # Эталонная кривая открытия приложения в iOS (spring timing по умолчанию):
    # быстрый уверенный старт + долгое экспоненциальное торможение без overshoot
    IOS_LAUNCH = _bezier(0.40, 0.00, 0.12, 1.0, QEasingCurve.OutQuart)

    # Отдельная кривая для фазы посадки в слот (spring cushion)
    IOS_LAND = _bezier(0.30, 0.90, 0.25, 1.0, QEasingCurve.OutQuart)

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
    """Покадровый драйвер с защитой от пропуска КАДРОВ, но без рассинхрона часов.

    Две проблемы решены одновременно:
      * Тяжёлый первый кадр (grab() окна, переключение QStackedWidget на 50–80 мс)
        больше не «съедает» стартовую фазу анимации — первый реальный интервал
        заменяется на один кадр;
      * Жёсткий clamp дельты (16.5 мс) полностью убран: из-за него при любой
        просадке кадров виртуальные часы отстаивали от реальных и анимация
        визуально «лагала» — 590 мс превращались в секунду и более. Теперь
        время идёт синхронно с часами системы, а длинный пропуск компенсируется
        одним догоняющим шагом (catch-up cap = 34 мс), который не перескакивает
        сразу несколько фаз анимации.
    """

    MAX_CATCH_UP_MS = 34.0   # максимум «догоняющего» шага за кадр (~2 кадра 60FPS)

    def __init__(self, duration_ms: int, curve, on_frame: Callable[[float], None],
                 on_finished: Optional[Callable[[], None]] = None, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.PreciseTimer)
        self._timer.setInterval(16)  # ~60 FPS — нативная частота vsync, меньше нагрузки
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
        if self._last_real_ms == 0:
            # Первый тик после тяжёлой операции запуска (grab / смена страницы):
            # считаем его обычным кадром, чтобы анимация не началась с «телепорта».
            self._last_real_ms = now
            return

        raw_dt = float(max(1, now - self._last_real_ms))
        self._last_real_ms = now

        # Синхронно с реальным временем, но с ограничением догоняющего шага:
        # 2 кадра при просадке — плавно, а не мгновенный скачок через все фазы.
        dt = min(raw_dt, self.MAX_CATCH_UP_MS)
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

    def stop(self, emit_finished: bool = False):
        was_active = self._timer.isActive()
        self._timer.stop()
        if emit_finished and was_active and self._on_finished:
            self._on_finished()

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

      2. ЗАКРЫТИЕ (run_close, 590 мс — 5 детальных iOS-фаз):
         - Фаза 1 (Detach, 0..14%): окно ОТДЕЛЯЕТСЯ от краёв экрана — появляется
           зазор сверху/снизу, углы скругляются до карточных 28px, из-под окна
           проступает слегка размытый и притемнённый рабочий стол, тень вырастает
           от нулевой к «парящей»;
         - Фаза 2 (Squeeze & Focus, 14..38%): фирменный iOS-эффект — кадр окна
           схлопывается по вертикали (высота растёт медленнее ширины), фокус
           смещается к верхней трети, контент сверху остаётся читаемым;
         - Фаза 3 (Arc Flight, 38..76%): полёт по кубической Безье-дуге к иконке
           с независимыми осями X/Y, инерционным упреждением по горизонтали,
           диагональным бликом по стеклу и непрерывным морфом пропорций 9:16 → 1:1;
         - Фаза 4 (Cross-Dissolve, 60..92%): пока карточка ещё летит, снимок окна
           перекрёстно растворяется в настоящей иконке приложения (маска squircle
           22.5%, как на рабочем столе) + стеклянная вуаль;
         - Фаза 5 (Landing, 84..100%): пружинная посадка 0.93x → 1.0x точно в слот,
           импульс света по контуру иконки, финальный pop иконочного масштаба.
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
        """Возвращает (cur_rect, corner_radius, elevation_k) для iOS-открытия окна (p: 0 -> 1).

        Полностью непрерывная C1-геометрия без изломов скорости:
          * траектория центра — плавная дуга с синусным подбросом;
          * ширина и высота расходятся по РАЗНЫМ кривым (фирменный squash->stretch
            морф iOS: сначала разгоняется ширина, высоту «догоняет»);
          * радиус скругления в середине полёта превышает финальный (карточка
            «распухает»), затем плавно стекает к углу экрана;
          * scale overshoot на посадке отсутствует — точный iOS spring.
        """
        ix, iy = self._icon_rect.x(), self._icon_rect.y()
        iw, ih = self._icon_rect.width(), self._icon_rect.height()
        tx, ty = self._target_rect.x(), self._target_rect.y()
        tw, th = self._target_rect.width(), self._target_rect.height()

        icx, icy = ix + iw * 0.5, iy + ih * 0.5
        tcx, tcy = tx + tw * 0.5, ty + th * 0.5

        # ---- Морф размеров: ширина опережает высоту (squash -> stretch) ----
        # Кривые с НУЛЕВОЙ стартовой скоростью (линейный множитель p в начале):
        # квадратные корни вида sqrt(p) имеют бесконечную производную при p=0 —
        # именно они давали микрорывок размера в первом же кадре открытия.
        pw = min(1.0, (p * (0.62 + 0.38 * p)) ** 0.5)
        ph = min(1.0, (p * (0.46 + 0.54 * p)) ** 0.5)
        # Финальные 6% — smoothstep-доводка точно в геометрию окна (без скачка)
        lock = _smoothstep(0.94, 1.0, p)
        pw = pw + (1.0 - pw) * lock
        ph = ph + (1.0 - ph) * lock

        w = iw + (tw - iw) * pw
        h = ih + (th - ih) * ph

        # ---- Траектория центра: независимые оси + мягкая дуга ----
        # Все три компонента начинаются со скоростью ~0 (множитель p внутри),
        # поэтому первый кадр открытия не содержит «телепорта» по позиции.
        px = min(1.0, p * (0.55 + 0.45 * p))
        py = min(1.0, p * (0.42 + 0.58 * p))
        # Подброс вверх в первой половине полёта (sin-арка, нулевая на концах)
        arc_dy = -16.0 * math.sin(p * math.pi) * (1.0 - p * 0.4) * px
        # Боковое хлыстовое упреждение — карточка слегка проскакивает по X
        whip = 8.0 * math.sin(p * math.pi) * (1.0 - p) * px
        dir_x = 1.0 if tcx >= icx else -1.0

        cx = icx + (tcx - icx) * px + whip * dir_x
        cy = icy + (tcy - icy) * py + arc_dy

        # ---- Радиус: squircle иконки -> карточный всплеск -> угол окна ----
        card_arch = 12.0 * math.sin(_clamp01(p * 1.15) * math.pi) * px
        base_r = self._corner_start + (self._corner_end - self._corner_start) * (p * (0.7 + 0.3 * p))
        r = min(min(w, h) * 0.46, base_r + card_arch)

        # ---- Тень парения: рождается при отрыве, гаснет к посадке ----
        elevation = math.sin(math.pow(_clamp01(p), 1.25) * math.pi) ** 0.7

        return QRectF(cx - w * 0.5, cy - h * 0.5, w, h), max(2.0, r), elevation

    def _compute_close_geometry(self, t: float) -> Tuple[QRectF, float, float]:
        """Возвращает (cur_rect, corner_radius, elevation_k) для iOS-закрытия окна.

        КЛЮЧЕВОЕ ОТЛИЧИЕ ОТ ПРЕДЫДУЩЕЙ ВЕРСИИ (починка «рывка» на старте):
        все фазы (detach / squeeze / полёт / landing) теперь смешиваются через
        C1-непрерывные smoothstep-окна вместо жёстких `if t > X` и ступенчатых
        нормализаций. Скорость изменения каждой координаты непрерывна по всему
        пути — ни в одной точке переключения фаз геометрическая производная не
        скачет, поэтому глазом не видно ни телепортов, ни подтормаживаний.

        Фазы (плавно перекрывающиеся): Detach 0..0.22 | Squeeze 0.10..0.55
              Arc Flight 0.10..0.90 | Landing cushion 0.80..1.0
        t = 0.0 -> полноэкранное окно;  t = 1.0 -> посадка в слот иконки.
        """
        ix, iy = self._icon_rect.x(), self._icon_rect.y()
        iw, ih = self._icon_rect.width(), self._icon_rect.height()
        tx, ty = self._target_rect.x(), self._target_rect.y()
        tw, th = self._target_rect.width(), self._target_rect.height()

        icx, icy = ix + iw * 0.5, iy + ih * 0.5
        tcy = ty + th * 0.5

        # Полноэкранный ли стартовый кадр (тогда уместен detach-gap).
        full_screen_start = (self._closing and tw >= iw * 1.6
                             and abs(tw - self.width()) < tw * 0.25)

        # ================= Фаза 1: DETACH (плавный отрыв от краёв) ==========
        # Окно ещё почти полноэкранное, но уже ОТРЫВАЕТСЯ от краёв экрана:
        # зазор по периметру растёт по smoothstep (нулевые скорость на обоих
        # концах интервала — никакого излома при входе/выходе из фазы).
        detach_e = _smoothstep(0.0, 0.22, t)
        detach_gap = 14.0 * detach_e          # визуальный зазор карточки от края экрана
        detach_lift = -6.0 * detach_e         # микро-подъём вверх при отрыве

        # ================= Общая траектория центра =================
        # Движение начинается сразу с t=0 (без offset-фазы — именно она
        # создавала паузу, а затем догоняющий рывок), но стартует с ОКОЛО
        # нулевой скорости: ease_move = 1-(1-t)^3.2 имеет производную ~0 при
        # t=0 и мягко разгоняется — ровно как release velocity в UIKit после
        # отпускания home-swipe.
        # ================= Общая траектория центра =================
        # Движение начинается сразу с t=0 (без offset-фазы — именно она
        # создавала паузу, а затем догоняющий рывок), но стартует с ОКОЛО
        # нулевой скорости: ease_move = 1-(1-t)^3.2 имеет производную ~0 при
        # t=0 и мягко разгоняется — ровно как release velocity в UIKit после
        # отпускания home-swipe.
        ease_move = 1.0 - (1.0 - t) ** 3.2
        move_t = _clamp01(ease_move)

        # Независимые оси: горизонталь слегка опережает вертикаль — центр
        # описывает естественную дугу, как в home-swipe UIKit.
        px = min(1.0, move_t ** 0.80)
        py = min(1.0, move_t ** 1.10)

        # Дуга полёта: подброс вверх в первой половине и плавное снижение к слоту.
        # Умножение на move_t, а не на сырое t, гарантирует нулевую производную
        # арки на обоих концах пути (arc' = arc'_base * ease_move' -> 0 при t=0/1).
        arc_lift = -24.0 * math.sin(move_t * math.pi) * (1.0 - move_t * 0.35) * move_t
        # Лёгкое боковое «хлыстовое» упреждение (whip) — карточка проскакивает
        # по горизонтали на ~3% пути назад, как инертный объект iOS
        whip_x = 9.0 * math.sin(min(1.0, move_t * 1.2) * math.pi) * (1.0 - move_t) * move_t

        cx = tx + tw * 0.5 + (icx - (tx + tw * 0.5)) * px + whip_x * (1.0 if icx >= tx + tw * 0.5 else -1.0)
        cy = tcy + (icy - tcy) * py + arc_lift + detach_lift * move_t

        # ================= Фаза 2: SQUEEZE (морф размеров) ==================
        # Фирменный iOS-эффект: ширина и высота схлопываются с РАЗНОЙ скоростью.
        # size_t = чистая t (ОБЯЗАТЕЛЬНО без собственного easing!) — весь timing
        # задаёт единственный драйвер-кривая IOS_DISMISS. Двойной easing
        # (кривая поверх smoothstep) делал середину анимации неестественно быстрой,
        # а финал — вязким: это и был видимый «рывок» после отрыва окна.
        size_t = t
        pw = size_t ** 0.90                    # ширина уходит плавно-быстро
        ph = size_t ** 0.72                    # высота догоняет чуть быстрее (squash->release)

        w = tw + (iw - tw) * pw
        h = th + (ih - th) * ph

        # Z-gap фазы отрыва: первые кадры окно чуть меньше экрана со всех сторон.
        # gap-обрезка ПЛАВНО растворяется к t=0.30 (gk -> 0), а не обрывается на
        # 14% — раньше именно это abrupt-выключение давало заметный щелчок размера.
        if full_screen_start:
            gk = 1.0 - _smoothstep(0.14, 0.30, t)
            shrink = detach_gap * 2.0 * gk
            w = min(w, tw - shrink)
            h = min(h, th - shrink)

        # ================= Фаза 5: LANDING (spring cushion 0.80..1.0) =======
        # Карточка сжимается до ~0.93x и распружинивается ровно в 1.0x слота.
        # sin-несущая равна 0 на обоих концах интервала => вход в cushion и
        # выход из него абсолютно непрерывны (производная тоже).
        land_phase = _clamp01((t - 0.80) / 0.20)
        cushion = (1.0
                   - 0.065 * math.sin(land_phase * math.pi)
                   + 0.016 * math.sin(2.0 * land_phase * math.pi) * (1.0 - land_phase))
        w *= cushion
        h *= cushion

        # ================= Скругление углов =================
        # 6px экран -> всплеск до карточных ~28px в середине -> радиус squircle.
        # card_arch гасится smoothstep-ом к концу пути, чтобы финальный радиус
        # совпадал с маской настоящей иконки лаунчера (22.5% стороны).
        arch_env = math.sin(_clamp01(t * 1.22) * math.pi) * (1.0 - _smoothstep(0.78, 1.0, t))
        card_arch = 18.0 * arch_env
        base_r = self._corner_end + (self._corner_start - self._corner_end) * (t ** 0.5)
        r = min(min(w, h) * 0.46, base_r + card_arch + detach_gap * 0.9 * (1.0 - _smoothstep(0.5, 0.8, t)))

        # Высота парения (сила тени): стремительно растёт при отрыве,
        # плато в полёте, мягко гаснет при посадке (smoothstep, не линейно)
        rise = detach_e * 0.85
        flight = math.sin(_smoothstep(0.02, 0.98, t) * math.pi) ** 0.6
        elevation = max(rise, flight) * (1.0 - _smoothstep(0.86, 1.0, t))

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
        """Отрисовка захода в приложение (p: 0.0 -> 1.0) в стиле iOS zoom transition.

        Все alpha-переходы построены на smoothstep — ни один слой не включается
        и не выключается резко, поэтому дорожка яркости каждого пикселя непрерывна.
        """
        cur_rect, r, elevation = self._compute_open_geometry(p)
        iw, ih = self._icon_rect.width(), self._icon_rect.height()

        # 1. Притемнение рабочего стола: растёт плавно (iOS затемняет home
        #    ровно настолько, насколько окно оторвалось от слота)
        backdrop_alpha = int(125 * _smoothstep(0.0, 0.85, p))
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

        # Если есть реальный снимок целевого окна — cross-dissolve из иконки
        # в интерфейс: snap проявляется по smoothstep (плавная производная
        # яркости), а не линейным порогом с резким «включением» на 18%.
        if has_snap:
            snap_alpha = _smoothstep(0.16, 0.78, p)
            if snap_alpha > 0.01:
                painter.setOpacity(snap_alpha)
                snap_w = cur_rect.width()
                snap_h = self._target_rect.height() * (snap_w / max(1.0, self._target_rect.width()))
                painter.drawPixmap(
                    QRectF(cur_rect.x(), cur_rect.y(), snap_w, max(cur_rect.height(), snap_h)),
                    self._snapshot,
                    QRectF(self._snapshot.rect())
                )

        # Отрисовка иконки приложения в центре растущей карточки (OriginOS splash).
        # В реальном iOS логотип НЕ растворяется полностью до конца анимации —
        # он уходит в 0 только в самый финал, поэтому держим его дольше.
        if has_icon:
            base_side = min(iw, ih) * 0.90
            # Иконка плавно вырастает в 1.48 раза в центре карточки
            side = base_side * (1.0 + 0.48 * (p ** 0.7))
            px = cur_rect.center().x() - side * 0.5
            py = cur_rect.center().y() - side * 0.5

            icon_alpha = 1.0 - 0.92 * _smoothstep(0.52, 0.96, p)
            painter.setOpacity(icon_alpha)
            painter.drawPixmap(
                QRectF(px, py, side, side),
                self._pixmap,
                QRectF(self._pixmap.rect())
            )

        painter.restore()

        # 4. Стеклянный кант и диагональный блик
        self._draw_glass_rim_and_sheen(painter, cur_rect, clip_path, r, elevation, p)

    def _draw_close_backdrop(self, painter: QPainter, t: float):
        """Фон за закрывающимся окном.

        В iOS домашний экран во время dismiss НЕ затемняется на всю анимацию:
        яркость возвращается постепенно — сначала быстро (окно уже оторвалось),
        затем плавно до нуля к концу полёта.
        """
        if t <= 0.02:
            return
        # Нелинейное высветление: к t=0.35 остаётся ~40% затемнения, к 0.8 — почти чисто
        dim_k = max(0.0, (1.0 - t) ** 2.1)
        alpha = int(110 * dim_k)
        if alpha > 1:
            painter.fillRect(self.rect(), QColor(6, 8, 14, alpha))

    def _draw_landing_glow(self, painter: QPainter, cur_rect: QRectF, r: float, t: float):
        """Импульс света вокруг слота иконки при посадке (iOS landing glow).

        Двойной контур: широкая мягкая аура акцентного цвета + тонкий белый кант,
        разворачивающиеся по синусоиде 0.74..1.0.
        """
        if t < 0.74 or t > 1.0:
            return
        pulse_t = (t - 0.74) / 0.26
        wave = math.sin(pulse_t * math.pi)
        # Мягкая внешняя аура (radial-имитация двумя широкими полупрозрачными кольцами)
        for pad_k, pen_w, base_a in ((1.0, 5.0, 26), (0.55, 2.2, 48), (0.2, 1.4, 90)):
            glow_pad = 9.0 * wave * pad_k + 1.0
            glow_rect = cur_rect.adjusted(-glow_pad, -glow_pad, glow_pad, glow_pad)
            color = QColor(255, 255, 255, int(base_a * wave))
            pen = QPen(color, pen_w)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(glow_rect, r + glow_pad, r + glow_pad)

    def _draw_squircle_icon(self, painter: QPainter, rect_f: QRectF, pix: QPixmap,
                            alpha: float, scale_pop: float = 1.0):
        """Рисует иконку с фирменным iOS-squircle маской (22.5% стороны) —
        точно так же, как AppIcon рисует её на рабочем столе, поэтому финальный
        кадр морфа бесшовно совпадает с настоящей иконкой лаунчера."""
        if alpha <= 0.01 or pix is None or pix.isNull():
            return
        side = min(rect_f.width(), rect_f.height()) * 0.92 * scale_pop
        target = QRectF(rect_f.center().x() - side * 0.5,
                        rect_f.center().y() - side * 0.5, side, side)
        path = QPainterPath()
        path.addRoundedRect(target, side * 0.225, side * 0.225)
        painter.save()
        painter.setOpacity(alpha)
        painter.setClipPath(path)
        painter.drawPixmap(target, pix, QRectF(pix.rect()))
        painter.restore()

    def _paint_close(self, painter: QPainter, t: float):
        """Детальная покадровая отрисовка iOS-выхода из приложения.

        Каждый alpha/position-слой смешивается smoothstep-ом: ни один слой не
        вспыхивает и не гаснет ступенькой — яркость пикселей меняется непрерывно.
        """
        cur_rect, r, elevation = self._compute_close_geometry(t)
        tw = max(1.0, self._target_rect.width())
        th = max(1.0, self._target_rect.height())

        has_snap = self._snapshot is not None and not self._snapshot.isNull()
        has_icon = self._pixmap is not None and not self._pixmap.isNull()

        # ---- Master opacity: карточка полностью непрозрачна весь полёт
        # и растворяется лишь на последних 8% — когда она уже внутри слота.
        # smoothstep вместо линейного обрыва: последние кадры уходят в ноль
        # без «ступеньки» яркости. ----
        master_opacity = 1.0 - _smoothstep(0.92, 1.0, t)

        # ================= Фаза 1: фон и тень =================
        self._draw_close_backdrop(painter, t)

        # Импульс посадки рисуется ПОД карточкой, чтобы контур «выглядывал» из-за краёв
        self._draw_landing_glow(painter, cur_rect, r, t)

        # Глубокая многослойная тень парения
        self._draw_elevation_shadow(painter, cur_rect, r, elevation)

        # ================= Морфинг формы карточки =================
        clip_path = QPainterPath()
        clip_path.addRoundedRect(cur_rect, r, r)

        painter.save()
        painter.setClipPath(clip_path)
        painter.setOpacity(master_opacity)

        # Стеклянная подложка (видна только если нет снимка окна)
        if not has_snap:
            self._draw_stylized_window_interior(painter, cur_rect, 1.0 - t * 0.7)

        # ---- Кадр окна: строго пропорциональный scale без сплющивания UI.
        # Фокус смещается к верхней трети (шапка приложения остаётся читаемой),
        # как в реальном iOS home-swipe, где контент «прижимается» к верху карточки.
        if has_snap:
            scale_ratio = max(cur_rect.width() / tw, cur_rect.height() / th * 0.62)
            snap_w = tw * scale_ratio
            snap_h = th * scale_ratio
            snap_x = cur_rect.center().x() - snap_w * 0.5
            # Плавный уход фокуса вверх (smoothstep, а не `min(1, t*1.4)` с изломом на 71%)
            focus_top_k = 0.12 + 0.30 * _smoothstep(0.0, 0.72, t)
            snap_y = cur_rect.y() - (snap_h - cur_rect.height()) * focus_top_k

            # Cross-Dissolve: снимок перекрёстно растворяется в иконке (симметрично
            # появлению иконки — сумма их вкладов почти постоянна).
            icon_appear = _smoothstep(0.50, 0.88, t) if has_icon else 0.0
            snap_alpha = 1.0 - icon_appear * 0.96

            painter.setOpacity(master_opacity * snap_alpha)
            painter.drawPixmap(
                QRectF(snap_x, snap_y, snap_w, snap_h),
                self._snapshot,
                QRectF(self._snapshot.rect())
            )

            # Стеклянная вуаль: лёгкое холодное затемнение сверху вниз на подлёте,
            # имитирует уменьшение экспозиции «далёкой» карточки
            veil = _smoothstep(0.30, 0.85, t)
            if veil > 0.01:
                veil_grad = QLinearGradient(cur_rect.topLeft(), cur_rect.bottomLeft())
                veil_grad.setColorAt(0.0, QColor(16, 20, 30, int(30 * veil)))
                veil_grad.setColorAt(1.0, QColor(10, 12, 20, int(72 * veil)))
                painter.setOpacity(master_opacity)
                painter.fillRect(cur_rect, veil_grad)

        # ---- Иконка приложения: проявляется через встречный cross-dissolve.
        # Растёт чуть больше карточки (fill_k) и делает финальный pop при посадке.
        if has_icon:
            if has_snap:
                icon_appear = _smoothstep(0.50, 0.88, t)
            else:
                icon_appear = _smoothstep(0.10, 0.45, t)
            # Посадочный pop: 1.0 -> 1.06 -> 1.0 в фазе cushion (0.86..1.0).
            # sin-несущая нулевая на концах => pop начинается и заканчивается без щелчка.
            pop_t = _clamp01((t - 0.86) / 0.14)
            pop = 1.0 + 0.06 * math.sin(pop_t * math.pi)
            self._draw_squircle_icon(painter, cur_rect, self._pixmap,
                                     master_opacity * icon_appear, pop)

        painter.restore()

        # ================= Стекло: блик + спекулярный кант =================
        painter.setOpacity(master_opacity)
        # Блик проходит по стеклу ровно один раз за полёт (sweep = eased t)
        sweep = _curve_value(Easing.IOS_DISMISS, t)
        self._draw_glass_rim_and_sheen(painter, cur_rect, clip_path, r, elevation, sweep)

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
            curve or Easing.IOS_LAUNCH,
            self.set_progress,
            self._finish,
            self
        )
        self.raise_()
        self.show()
        self.update()
        self._driver.start()

    def run_close(self, duration: int = Duration.DISMISS, curve=None, on_finished=None):
        """Детальное 5-фазное iOS-сворачивание окна обратно в иконку."""
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
            curve or Easing.IOS_DISMISS,
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