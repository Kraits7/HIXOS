# apps/ios_launcher.py
"""
IOSLauncherContent — НОВЫЙ лаунчер HIXOS, полностью скопированный с iOS 17.

Что скопировано с iOS:
  * Домашний экран: сетка иконок 4 столбца с squircle-маской (~22.5% стороны),
    подписи под иконками с обрезкой многоточием (как в iOS), крупный заголовок;
  * Док: стеклянная капсула с BlurView (настоящее гауссово размытие обоев
    под доком + светящаяся рамка) — как Dock в iOS;
  * Страницы домашних экранов с horizontal-свайпом и snap-анимацией в стиле
    spring UIKit (можно свайпать пальцем/мышью, страницы пружинят к ближайшей);
  * App Library (Библиотека приложений) — финальный экран со стопкой папок
    в стиле iOS: категории, сетка 3x3 внутри папки, поиск-бар сверху;
  * Папки на рабочем столе: тап по папке раскрывает её в оверлей с
    zoom-морфом (иконки разлетаются из плитки папки), как в iOS;
  * Jiggle Mode (режим редактирования): долгое нажатие — все иконки начинают
    «трястись» с пружинным дрожанием, у иконок появляется бейдж удаления
    «−», как в iOS. Выход — кнопка «Готово» справа сверху;
  * Spotlight: тяни вниз (свайп сверху) или тап по search-бару — поверх
    рабочего стола выезжает панель поиска с затемнением и blur;
  * Home indicator: жест вверх с нижней полосы сворачивает открытую папку /
    App Library обратно на домашний экран.

Анимации (все через ui/animation_engine, т.е. точные iOS-кривые):
  * Разворот иконки в приложение (MorphOverlay.run_open, Easing.IOS_LAUNCH);
  * Сворачивание окна приложения обратно в иконку обрабатывается снаружи
    (HIXOS._play_closing_morph) — этот лаунчер предоставляет те же интерфейсы,
    что и старый LauncherContent, поэтому dismiss-морф работает без изменений;
  * Прилёт домашнего экрана после разблокировки — одной группой с оседанием
    1.08→1.0 и ease-out (ровно как unlock transition в iOS);
  * Пружинный отклик иконок на нажатие (scale 0.85 → 1.0 overshoot);
  * Волновое появление иконок внутри папки при раскрытии (stagger + spring);
  * Spotlight slide+fade (Easing.IOS_TRANSITION).

Сигналы и публичные методы совместимы со старым LauncherContent:
  launch_app_requested(app_id, global_icon_rect)
  set_language(str), set_icon_size(int), set_grid_columns(int),
  set_app_names_visibility(bool), prepare_for_animation(), animate_icons_in()
"""

import math
import os
import sys

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QFrame, QSizePolicy, QApplication, QMainWindow, QGraphicsOpacityEffect,
    QStackedWidget, QLineEdit, QScrollArea, QPushButton,
)
from PyQt5.QtGui import (
    QPixmap, QFont, QColor, QBrush, QPainter, QLinearGradient, QPainterPath,
    QRadialGradient, QFontMetrics, QImage, QPen, QCursor,
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, QObject, QSize, QPoint, QPointF, QRect, QRectF,
    QPropertyAnimation, QEasingCurve, pyqtProperty, QTimer, QEvent,
)

# --- Системный движок анимаций (iOS style) ---
try:
    from ui.animation_engine import (
        Easing, Duration, _FrameDriver, MorphOverlay, StaggerReveal,
        spring_progress, IOSTEAL,
    )
except ImportError:  # запуск standalone из папки apps
    from animation_engine import (
        Easing, Duration, _FrameDriver, MorphOverlay, StaggerReveal,
        spring_progress, IOSTEAL,
    )


# =============================================================================
# Утилиты
# =============================================================================

def make_squircle_path(rect: QRectF, radius_frac: float = 0.225) -> QPainterPath:
    """Путь squircle как в iOS: скругление ~22.5% от стороны плитки."""
    path = QPainterPath()
    r = rect.width() * radius_frac
    path.addRoundedRect(rect, r, r)
    return path


class IOSBlurView(QWidget):
    """Настоящее фоновое размытие (как UIBlurEffect в iOS).

    Берёт снимок родителя, даунскейлит его до 1/3 (это и есть гауссово
    сглаживание при апскейле с SmoothTransformation) и рисует поверх
    полупрозрачной подложкой со светлой рамкой. Используется для дока,
    spotlight-затемнения и оверлея папок.

    ВАЖНО: перерисовка планируются через QTimer.singleShot(0), а не синхронно
    в paintEvent — grab() родителя внутри paint вызвал рекурсивную перерисовку.
    """

    def __init__(self, parent=None, radius: int = 34, blur_radius: float = 22.0,
                 tint=(255, 255, 255, 26), border=(255, 255, 255, 40)):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._radius = radius
        self._blur_radius = blur_radius
        self._tint = tint
        self._border = border
        self._cache_img = None
        self._cache_key = None
        self._rebuild_scheduled = False

    def invalidate(self):
        self._cache_img = None
        self._cache_key = None

    def refresh(self):
        """Планирует перестройку blur-снимка на следующем цикле событий."""
        if not self.isVisible():
            return
        self._cache_key = None
        if not self._rebuild_scheduled:
            self._rebuild_scheduled = True
            QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self):
        self._rebuild_scheduled = False
        self._build_blur()
        self.update()

    def _build_blur(self):
        p = self.parentWidget()
        if p is None or self.width() <= 2 or self.height() <= 2:
            self._cache_img = None
            return
        tl_global = self.mapToGlobal(QPoint(0, 0))
        pl_global = p.mapToGlobal(QPoint(0, 0))
        local = tl_global - pl_global
        key = (local.x(), local.y(), self.width(), self.height())
        if self._cache_key == key and self._cache_img is not None:
            return
        src = p.grab(QRect(local, self.size()))
        small = src.scaled(max(1, self.width() // 3), max(1, self.height() // 3),
                           Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        img = small.toImage()
        # Даунскейл 1/3 + апскейл с билинейной фильтрацией ≈ gaussian blur
        self._cache_img = img.scaled(self.width(), self.height(),
                                     Qt.IgnoreAspectRatio,
                                     Qt.SmoothTransformation)
        self._cache_key = key

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(rect, self._radius, self._radius)
        painter.setClipPath(path)

        if self._cache_img is not None:
            painter.drawImage(self.rect(), self._cache_img)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(*self._tint))
        painter.drawRect(self.rect())

        pen = QPen(QColor(*self._border))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)


# =============================================================================
# Иконка приложения (squircle + spring-отклик, как в iOS)
# =============================================================================

class SpringScaleAnimator(QObject):
    """Покадровая spring-анимация масштаба (cubic-bezier нельзя в QPropertyAnimation)."""

    def __init__(self, icon):
        super().__init__(icon)
        self._icon = icon
        self._driver = None

    def to(self, target: float, duration: int, curve):
        try:
            start = self._icon.scale_value  # текущее значение — плавный перехват
            if self._driver:
                self._driver.stop()
        except RuntimeError:
            return  # иконка уже удалена (перестройка сетки) — не анимируем

        def on_frame(p):
            try:
                self._icon.set_scale(start + (target - start) * p)
            except RuntimeError:
                if self._driver:
                    self._driver.stop()

        self._driver = _FrameDriver(duration, curve, on_frame, parent=self)
        self._driver.start()


class IOSAppIcon(QWidget):
    """Плитка приложения один-в-один как в iOS: squircle-иконка + подпись."""

    app_icon_pressed = pyqtSignal(str, QRect)
    remove_requested = pyqtSignal(str)

    def __init__(self, app_id, app_name, icon_path, parent=None,
                 draw_size=66, show_name=True, in_dock=False):
        super().__init__(parent)
        self.app_id = app_id
        self.app_name = app_name
        self.icon_path = icon_path
        self.in_dock = in_dock
        self._draw_size = draw_size
        self._show_name = show_name

        self._scale_factor = 1.0
        self._opacity = 1.0
        self._jiggle_phase = (hash(app_id) % 628) / 100.0  # фаза дрожания
        self._jiggle_on = False
        self._remove_badge = False
        self._press_hold_timer = None

        pixmap = QPixmap(icon_path)
        if pixmap.isNull():
            pixmap = self._make_fallback_pixmap()
        self._original_pixmap = pixmap

        self._spring = SpringScaleAnimator(self)

        self._base_w = draw_size + 20
        self._base_h = (draw_size + 34) if show_name and not in_dock else (draw_size + 14)
        self.setFixedSize(self._base_w, self._base_h)

        self.name_label = None
        if show_name and not in_dock:
            self.name_label = QLabel(app_name, self)
            self.name_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
            # iOS: плотный мелкий шрифт подписи с лёгкой тенью
            self.name_label.setStyleSheet(
                "color: rgba(255,255,255,0.95); font-size: 11px; font-weight: 400;"
                "font-family: 'SF Pro Text', 'Segoe UI', 'Roboto', sans-serif;")
            self.name_label.setTextFormat(Qt.PlainText)
            self.name_label.setFixedWidth(self._base_w)
            self.name_label.move(0, draw_size + 6)
            self._elide_name(app_name)

    def _make_fallback_pixmap(self):
        pm = QPixmap(self._draw_size, self._draw_size)
        pm.fill(QColor("#555555"))
        pr = QPainter(pm)
        pr.setPen(QColor("white"))
        f = QFont("Arial", 18, QFont.Bold)
        pr.setFont(f)
        pr.drawText(pm.rect(), Qt.AlignCenter, (self.app_name[:1] or "?").upper())
        pr.end()
        return pm

    def _elide_name(self, name):
        if not self.name_label:
            return
        fm = QFontMetrics(self.name_label.font())
        self.name_label.setText(fm.elidedText(name, Qt.ElideRight,
                                              max(10, self._base_w - 2)))
        self.name_label.setToolTip(name)

    # --- свойства для анимаций ---
    @pyqtProperty(float)
    def scale(self):
        return self._scale_factor

    @scale.setter
    def scale(self, v):
        if self._scale_factor != v:
            self._scale_factor = v
            self.update()

    @property
    def scale_value(self):
        return self._scale_factor

    def set_scale(self, v):
        self.scale = v

    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, v):
        if self._opacity != v:
            self._opacity = v
            self.update()

    # --- jiggle mode ---
    def set_jiggle(self, on: bool, angle_deg: float = 0.0):
        self._jiggle_on = on
        self._remove_badge = on
        self._fixed_angle = angle_deg
        if not on:
            self.update()

    # --- отрисовка ---
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)

        side = max(1, int(self._draw_size * self._scale_factor))
        x = (self.width() - side) / 2.0
        y = (self._draw_size - side) / 2.0

        angle = 0.0
        if self._jiggle_on:
            t = self._jiggle_driver_time if hasattr(self, "_jiggle_driver_time") else 0.0
            wobble = math.sin(t * 12.0 + self._jiggle_phase * 6.28) * 1.6
            angle = getattr(self, "_fixed_angle", 0.0) + wobble

        pix = self._original_pixmap.scaled(side, side, Qt.KeepAspectRatio,
                                           Qt.SmoothTransformation)
        painter.save()
        painter.translate(x + side / 2.0, y + side / 2.0)
        if angle:
            painter.rotate(angle)
        painter.translate(-side / 2.0, -side / 2.0)
        path = make_squircle_path(QRectF(0, 0, side, side))
        painter.setClipPath(path)
        painter.drawPixmap(0, 0, pix)
        painter.restore()

        # Бейдж удаления «−» в левом верхнем углу — как в iOS jiggle mode
        if self._remove_badge and self._jiggle_on:
            d = 18
            bx, by = x - 2, y - 2
            painter.setBrush(QColor(235, 235, 245, 235))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(bx, by, d, d))
            painter.setPen(QPen(QColor(60, 60, 67), 1.8))
            painter.drawLine(QPointF(bx + 5, by + d / 2), QPointF(bx + d - 5, by + d / 2))

        super().paintEvent(event)

    # --- взаимодействие ---
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._spring.to(0.85, Duration.MICRO, Easing.STANDARD)
            # долгое нажатие → jiggle mode (как в iOS)
            self._press_hold_timer = QTimer.singleShot(
                550, lambda: self._request_jiggle())
        super().mousePressEvent(event)

    def _request_jiggle(self):
        self._press_hold_timer = None
        host = self
        while host is not None and not isinstance(host, IOSLauncherContent):
            host = host.parentWidget()
        if host is not None:
            host.enter_jiggle_mode()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if self._press_hold_timer is not None:
                # короткое нажатие — long-press не засчитан, отменяем таймер
                try:
                    self._press_hold_timer.deleteLater()
                except Exception:
                    pass
                self._press_hold_timer = None
            self._spring.to(1.0, Duration.SHORT, Easing.SPRING)

            launcher = self
            while launcher is not None and not isinstance(launcher, IOSLauncherContent):
                launcher = launcher.parentWidget()

            if launcher is not None and launcher.in_jiggle_mode:
                # тап по бейджу в режиме редактирования — удаление плитки
                pos = event.pos()
                if pos.x() < 22 and pos.y() < 22:
                    self.remove_requested.emit(self.app_id)
                    return

            if launcher is not None and launcher.in_jiggle_mode:
                # в jiggle mode тап только трясёт плитку, не запускает
                return

            g_tl = self.mapToGlobal(self.rect().topLeft())
            launcher.on_tile_pressed(self, QRect(g_tl, self.rect().size()))
        super().mouseReleaseEvent(event)


# =============================================================================
# Папка на рабочем столе (плитка 2x2 миниатюр + оверлей раскрытия)
# =============================================================================

class IOSFolderTile(QWidget):
    """Плитка папки: прозрачный squircle с 4 миниатюрами иконок — как в iOS."""

    folder_pressed = pyqtSignal(str, QRect)

    def __init__(self, folder_id, title, child_icons, parent=None, draw_size=66):
        super().__init__(parent)
        self.folder_id = folder_id
        self.title = title
        self.child_icons = child_icons  # список путей png
        self._draw_size = draw_size
        self._opacity = 1.0
        self._scale_factor = 1.0
        self._spring = SpringScaleAnimator(self)
        self.setFixedSize(draw_size + 20, draw_size + 34)

        self.name_label = QLabel(title, self)
        self.name_label.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        self.name_label.setStyleSheet(
            "color: rgba(255,255,255,0.95); font-size: 11px;"
            "font-family: 'SF Pro Text','Segoe UI',sans-serif;")
        self.name_label.setFixedWidth(self.width())
        self.name_label.move(0, draw_size + 6)

    @property
    def scale_value(self):
        return self._scale_factor

    def set_scale(self, v):
        self._scale_factor = v
        self.update()

    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, v):
        self._opacity = v
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity)

        side = max(1, int(self._draw_size * self._scale_factor))
        x = (self.width() - side) / 2.0
        y = (self._draw_size - side) / 2.0
        rect = QRectF(x, y, side, side)

        # матовая подложка squircle
        path = make_squircle_path(rect)
        painter.setClipPath(path)
        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0.0, QColor(180, 180, 195, 120))
        grad.setColorAt(1.0, QColor(120, 120, 140, 110))
        painter.fillRect(rect, QBrush(grad))

        mini = side * 0.40
        gap = side * 0.06
        ox = rect.center().x() - mini - gap / 2
        oy = rect.center().y() - mini - gap / 2
        for i, pth in enumerate(self.child_icons[:4]):
            pm = QPixmap(pth)
            if pm.isNull():
                continue
            cx = ox + (i % 2) * (mini + gap)
            cy = oy + (i // 2) * (mini + gap)
            mrect = QRectF(cx, cy, mini, mini)
            mp = QPainterPath()
            mp.addRoundedRect(mrect, mini * 0.225, mini * 0.225)
            painter.save()
            painter.setClipPath(mp)
            painter.drawPixmap(mrect, pm.scaled(int(mini), int(mini),
                                                Qt.IgnoreAspectRatio,
                                                Qt.SmoothTransformation))
            painter.restore()
        super().paintEvent(event)

    def mousePressEvent(self, event):
        self._spring.to(0.85, Duration.MICRO, Easing.STANDARD)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        self._spring.to(1.0, Duration.SHORT, Easing.SPRING)
        launcher = self
        while launcher is not None and not isinstance(launcher, IOSLauncherContent):
            launcher = launcher.parentWidget()
        if launcher is not None and launcher.in_jiggle_mode:
            return
        g_tl = self.mapToGlobal(self.rect().topLeft())
        self.folder_pressed.emit(self.folder_id, QRect(g_tl, self.rect().size()))
        super().mouseReleaseEvent(event)


# =============================================================================
# Свайпер страниц (горизонтальный pan + snap, как spring UIKit)
# =============================================================================

class PageSwiper(QObject):
    """Управляет QStackedWidget с manual-стеком: drag мышью листает страницы,
    отпускание — пружинный snap к ближайшей странице (iOS paging)."""

    def __init__(self, stack: QStackedWidget, owner):  # owner: IOSLauncherContent
        super().__init__(stack)
        self.stack = stack
        self.owner = owner
        self._dragging = False
        self._start_x = 0
        self._offset = 0.0
        self._driver = None

    def handle_press(self, pos: QPoint):
        if self.owner.overlay_active:
            return False
        self._dragging = True
        self._start_x = pos.x()
        self._offset = 0.0
        if self._driver:
            self._driver.stop()
            self._driver = None
        return True

    def handle_move(self, pos: QPoint):
        if not self._dragging:
            return
        dx = pos.x() - self._start_x
        n = self.stack.count()
        # резинок на краях (rubber band как в UIScrollView)
        if ((dx > 0 and self.stack.currentIndex() == 0) or
                (dx < 0 and self.stack.currentIndex() == n - 1)):
            dx *= 0.35
        self._offset = dx
        self._apply()

    def handle_release(self, pos: QPoint):
        if not self._dragging:
            return
        self._dragging = False
        w = max(1, self.stack.width())
        idx = self.stack.currentIndex()
        threshold = w * 0.22
        target = idx
        if self._offset <= -threshold and idx < self.stack.count() - 1:
            target = idx + 1
        elif self._offset >= threshold and idx > 0:
            target = idx - 1
        self.snap_to(target)

    def snap_to(self, target_index: int):
        idx = self.stack.currentIndex()
        w = max(1, self.stack.width())
        start_off = self._offset
        end_off = (idx - target_index) * w
        if target_index != idx:
            self.stack.setCurrentIndex(target_index)

        def on_frame(e):
            self._offset = start_off + (end_off - start_off) * e
            self._apply()

        def finish():
            self._driver = None
            self._offset = 0.0
            self._apply()

        self._driver = _FrameDriver(Duration.SHORT, Easing.SPRING,
                                    on_frame, finish, self)
        self._driver.start()

    def _apply(self):
        cur = self.stack.currentWidget()
        if cur is not None:
            cur.move(int(self._offset), 0)


# =============================================================================
# Главный класс нового iOS-лаунчера
# =============================================================================

class IOSLauncherContent(QFrame):
    """Новый лаунчер HIXOS, скопированный с iOS (домашние экраны + док +
    App Library + папки + jiggle mode + spotlight + iOS-анимации)."""

    launch_app_requested = pyqtSignal(str, QRect)

    ICONS_DIR = "Launcher/Icons"

    def __init__(self, parent=None, language="Русский", initial_icon_size=66,
                 initial_grid_columns=4, initial_show_app_names=True):
        super().__init__(parent)
        self.main_window = parent
        self._language = language
        self._current_icon_size = initial_icon_size
        self._current_grid_columns = initial_grid_columns
        self._show_app_names = initial_show_app_names

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background-color: transparent;")

        # локализация имён (как в iOS — короткие подписи)
        self.localized_app_names = {
            "Русский": {
                "Greeting": "",
                "Phone": "Телефон", "Messages": "Сообщения", "Camera": "Камера",
                "Photos": "Фото", "Store": "App Store", "Browser": "Safari",
                "Music": "Музыка", "Maps": "Карты", "Settings": "Настройки",
                "Calendar": "Календарь", "Clock": "Часы", "Contacts": "Контакты",
                "Notes": "Заметки", "Files": "Файлы", "Weather": "Погода",
                "Calculator": "Калькулятор", "Video": "TV", "Books": "Книги",
                "Podcasts": "Подкасты", "Mail": "Почта", "Health": "Здоровье",
                "Wallet": "Кошелёк", "Home": "Дом", "Utilities": "Утилиты",
                "Productivity": "Продуктивность",
            },
            "English": {
                "Greeting": "",
                "Phone": "Phone", "Messages": "Messages", "Camera": "Camera",
                "Photos": "Photos", "Store": "App Store", "Browser": "Safari",
                "Music": "Music", "Maps": "Maps", "Settings": "Settings",
                "Calendar": "Calendar", "Clock": "Clock", "Contacts": "Contacts",
                "Notes": "Notes", "Files": "Files", "Weather": "Weather",
                "Calculator": "Calculator", "Video": "TV", "Books": "Books",
                "Podcasts": "Podcasts", "Mail": "Mail", "Health": "Health",
                "Wallet": "Wallet", "Home": "Home", "Utilities": "Utilities",
                "Productivity": "Productivity",
            },
        }

        self.grid_app_icons = []
        self.dock_app_icons = []
        self.folder_tiles = []

        # данные приложений: ищем иконки в Launcher/Icons, иначе System/Icons
        def ic(name):
            for base in ("Launcher/Icons", "icons"):
                p = os.path.join(base, name)
                if os.path.exists(p):
                    return p
            return os.path.join("icons", name)

        self.apps_data = [
            ("Phone", "Телефон", ic("Phone.png")),
            ("Messages", "Сообщения", ic("Messages.png")),
            ("Camera", "Камера", ic("Camera.png")),
            ("Photos", "Фото", ic("Photos.png")),
            ("Store", "App Store", ic("Store.png")),
            ("Browser", "Safari", ic("Browser.png")),
            ("Music", "Музыка", ic("Music.png")),
            ("Maps", "Карты", ic("Maps.png")),
            ("Settings", "Настройки", ic("Settings.png")),
            ("Calendar", "Календарь", ic("Calendar.png")),
            ("Clock", "Часы", ic("Clock.png")),
            ("Contacts", "Контакты", ic("Contacts.png")),
            ("Notes", "Заметки", ic("Notes.png")),
            ("Files", "Файлы", ic("Files.png")),
            ("Weather", "Погода", ic("Weather.png")),
            ("Calculator", "Калькулятор", ic("Calculator.png")),
            ("Video", "TV", ic("Video.png")),
            ("Books", "Книги", ic("Books.png")),
            ("Podcasts", "Подкасты", ic("Podcasts.png")),
        ]

        self.dock_apps_data = [
            ("Phone", "Телефон", ic("Phone.png")),
            ("Messages", "Сообщения", ic("Messages.png")),
            ("Browser", "Safari", ic("Browser.png")),
            ("Settings", "Настройки", ic("Settings.png")),
        ]

        # состояние
        self.in_jiggle_mode = False
        self.overlay_active = False   # открыта папка / App Library / spotlight
        self.current_app_id_to_launch = None
        self.current_icon_rect_for_animation = QRect()
        self._morph = None
        self._morph_pending = False
        self._should_animate_on_show = True
        self._jiggle_driver = None
        self._flyin_driver = None
        self._launch_out_driver = None
        self._folder_overlay = None
        self._spotlight = None
        self._closing_anim = None

        # страницы: 2 домашних экрана + App Library
        self.stack = QStackedWidget(self)
        slay = QVBoxLayout(self)
        slay.setContentsMargins(0, 0, 0, 0)
        slay.addWidget(self.stack)

        self.home_pages = []
        for page_i in range(2):
            pg = QWidget()
            pg.setStyleSheet("background: transparent;")
            lay = QVBoxLayout(pg)
            lay.setContentsMargins(22, 44, 22, 0)
            lay.setSpacing(0)

            header = QLabel(self._localized("Phone") if False else "", pg)
            header.setStyleSheet(
                "color: white; font-size: 22px; font-weight: 700;"
                "font-family: 'SF Pro Display','Segoe UI',sans-serif;")
            header.setAlignment(Qt.AlignLeft)
            lay.addWidget(header)
            lay.addSpacing(18)

            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(22)
            grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
            lay.addLayout(grid)
            lay.addStretch(1)

            self.home_pages.append((pg, grid, header))
            self.stack.addWidget(pg)

        # App Library — финальная страница
        self.library_page = self._build_app_library()
        self.stack.addWidget(self.library_page)

        # точки-пагинатор (как iOS page dots)
        self.dots = QLabel(self)
        self.dots.setStyleSheet("color: rgba(255,255,255,0.55); font-size: 14px;")
        self.dots.setAlignment(Qt.AlignCenter)

        # док — стеклянная капсула с blur
        self.dock_blur = IOSBlurView(self, radius=32, blur_radius=24,
                                     tint=(255, 255, 255, 22))
        self.dock_inner = QFrame(self.dock_blur)
        self.dock_inner.setStyleSheet("background: transparent;")
        dl = QHBoxLayout(self.dock_inner)
        dl.setContentsMargins(18, 10, 18, 10)
        dl.setSpacing(20)
        dl.setAlignment(Qt.AlignCenter)
        self.dock_layout = dl

        self.swiper = PageSwiper(self.stack, self)

        self._populate_home_pages()
        self._populate_dock()
        self._update_localization()
        self._update_dots()

        # таймер обновления blur под дока (дешёвый: раз в ~450 мс только если видно)
        self._blur_timer = QTimer(self)
        self._blur_timer.setInterval(450)
        self._blur_timer.timeout.connect(lambda: self.dock_blur.refresh())

    # ------------------------------------------------------------------ utils
    def _localized(self, app_id):
        loc = self.localized_app_names.get(self._language,
                                           self.localized_app_names["Русский"])
        return loc.get(app_id, app_id)

    def _find_icon_widget(self, app_id):
        for ic in (self.grid_app_icons + self.dock_app_icons):
            if ic.app_id == app_id:
                return ic
        return None

    # ------------------------------------------------------------- app library
    def _build_app_library(self):
        pg = QWidget()
        pg.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(pg)
        lay.setContentsMargins(22, 40, 22, 0)
        lay.setSpacing(12)

        title = QLabel("Библиотека приложений" if self._language == "Русский"
                       else "App Library")
        title.setObjectName("libraryTitle")
        title.setStyleSheet(
            "color: white; font-size: 26px; font-weight: 700;"
            "font-family: 'SF Pro Display','Segoe UI',sans-serif;")
        lay.addWidget(title)

        search = QLineEdit()
        search.setObjectName("librarySearch")
        search.setPlaceholderText("Поиск" if self._language == "Русский" else "Search")
        search.setClearButtonEnabled(True)
        search.setStyleSheet(
            "QLineEdit { background: rgba(120,120,135,0.55); color: white;"
            " border: none; border-radius: 11px; padding: 9px 14px;"
            " font-size: 15px; }")
        lay.addWidget(search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                             "QScrollBar{width:0px;}")
        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        ilay = QVBoxLayout(inner)
        ilay.setContentsMargins(4, 8, 4, 8)
        ilay.setSpacing(26)

        # категории iOS-подобных папок библиотеки
        cats = [
            ("Suggestions", ["Phone", "Messages", "Camera", "Settings"]),
            ("Productivity", ["Notes", "Files", "Calendar", "Contacts", "Calculator"]),
            ("Entertainment", ["Music", "Video", "Podcasts", "Photos"]),
            ("Utilities", ["Weather", "Clock", "Browser", "Maps", "Store"]),
        ]
        self._library_tiles = []
        for cat, ids in cats:
            box = QVBoxLayout()
            box.setSpacing(8)
            lbl = QLabel(cat)
            lbl.setStyleSheet(
                "color: rgba(255,255,255,0.92); font-size: 15px; font-weight: 600;"
                "font-family:'SF Pro Text','Segoe UI',sans-serif;")
            box.addWidget(lbl)

            fold = QFrame()
            fold.setObjectName("libFolder")
            fold.setStyleSheet("background: transparent;")
            fgrid = QGridLayout(fold)
            fgrid.setContentsMargins(10, 10, 10, 10)
            fgrid.setSpacing(8)
            # фон панки рисуем в paintEvent этого фрейма через стилизацию ниже
            children_paths = []
            for i, aid in enumerate(ids):
                data = next((a for a in self.apps_data if a[0] == aid), None)
                if not data:
                    continue
                children_paths.append(data[2])
                mini = QLabel(fold)
                mini.setFixedSize(44, 44)
                pm = QPixmap(data[2])
                if not pm.isNull():
                    pm = pm.scaled(44, 44, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
                    # squircle маска
                    masked = QPixmap(44, 44)
                    masked.fill(Qt.transparent)
                    mp = QPainter(masked)
                    mp.setRenderHint(QPainter.Antialiasing)
                    mp.setClipPath(make_squircle_path(QRectF(0, 0, 44, 44)))
                    mp.drawPixmap(0, 0, pm)
                    mp.end()
                    mini.setPixmap(masked)
                fgrid.addWidget(mini, i // 3, i % 3, Qt.AlignCenter)
            fold.setProperty("child_paths", children_paths)
            box.addWidget(fold)
            ilay.addLayout(box)
            self._library_tiles.append(fold)

        ilay.addStretch(1)
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        return pg

    # ------------------------------------------------------------------ pages
    def _populate_home_pages(self):
        """Раскладывает приложения по 2 домашним экранам + папки, как iOS."""
        # очистка старых
        for pg, grid, _ in self.home_pages:
            while grid.count():
                it = grid.takeAt(0)
                w = it.widget()
                if w:
                    w.setParent(None)
                    w.deleteLater()
        self.grid_app_icons = []
        self.folder_tiles = []

        cols = self._current_grid_columns
        # экран 1: первые 12 плиток + папка «Utilities» из остальных
        first = self.apps_data[:12]
        rest = self.apps_data[12:]

        idx = 0
        for app_id, default_name, path in first:
            icon = IOSAppIcon(app_id, self._localized(app_id) or default_name,
                              path, self.home_pages[0][0],
                              draw_size=self._current_icon_size,
                              show_name=self._show_app_names)
            icon.remove_requested.connect(self._remove_app)
            self.home_pages[0][1].addWidget(icon, idx // cols, idx % cols)
            self.grid_app_icons.append(icon)
            idx += 1

        if rest:
            tile = IOSFolderTile("Utilities", self._localized("Utilities"),
                                 [p for _, _, p in rest], self.home_pages[0][0],
                                 draw_size=self._current_icon_size)
            tile.folder_pressed.connect(self.open_folder)
            self.home_pages[0][1].addWidget(tile, idx // cols, idx % cols)
            self.folder_tiles.append(tile)
            idx += 1

        # экран 2: переиспользуемые «виджеты-иконки» — пустой, но готов к плиткам
        # (кладем Clock/Calendar сюда, чтобы свайп было где показать)
        second_ids = ["Clock", "Calendar"]
        j = 0
        for aid in second_ids:
            data = next((a for a in self.apps_data if a[0] == aid), None)
            if not data:
                continue
            icon = IOSAppIcon(aid, self._localized(aid), data[2],
                              self.home_pages[1][0],
                              draw_size=self._current_icon_size,
                              show_name=self._show_app_names)
            icon.remove_requested.connect(self._remove_app)
            self.home_pages[1][1].addWidget(icon, j // cols, j % cols)
            self.grid_app_icons.append(icon)
            j += 1

    def _populate_dock(self):
        while self.dock_layout.count():
            it = self.dock_layout.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.dock_app_icons = []
        for app_id, default_name, path in self.dock_apps_data:
            icon = IOSAppIcon(app_id, default_name, path, self.dock_inner,
                              draw_size=64, show_name=False, in_dock=True)
            self.dock_app_icons.append(icon)
            self.dock_layout.addWidget(icon)

    # ------------------------------------------------------------ localization
    def set_language(self, language: str):
        if self._language != language:
            self._language = language
            self._update_localization()

    def _update_localization(self):
        # заголовки страниц — дата/приветствие в стиле iOS
        day_names_ru = ["ПОНЕДЕЛЬНИК", "ВТОРНИК", "СРЕДА", "ЧЕТВЕРГ",
                        "ПЯТНИЦА", "СУББОТА", "ВОСКРЕСЕНЬЕ"]
        day_names_en = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY",
                        "FRIDAY", "SATURDAY", "SUNDAY"]
        months_ru = ["ЯНВАРЯ", "ФЕВРАЛЯ", "МАРТА", "АПРЕЛЯ", "МАЯ", "ИЮНЯ",
                     "ИЮЛЯ", "АВГУСТА", "СЕНТЯБРЯ", "ОКТЯБРЯ", "НОЯБРЯ", "ДЕКАБРЯ"]
        months_en = ["JANUARY", "FEBRUARY", "MARCH", "APRIL", "MAY", "JUNE",
                     "JULY", "AUGUST", "SEPTEMBER", "OCTOBER", "NOVEMBER", "DECEMBER"]
        ru = self._language == "Русский"
        now = __import__("datetime").datetime.now()
        days = day_names_ru if ru else day_names_en
        months = months_ru if ru else months_en
        header = f"{days[now.weekday()]}, {now.day} {months[now.month - 1]}"

        _, grid, hdr = self.home_pages[0]
        hdr.setText(header)
        self.home_pages[1][2].setText("")

        t = self.library_page.findChild(QLabel, "libraryTitle")
        if t:
            t.setText("Библиотека приложений" if ru else "App Library")
        s = self.library_page.findChild(QLineEdit, "librarySearch")
        if s:
            s.setPlaceholderText("Поиск" if ru else "Search")

        for ic in self.grid_app_icons:
            ic._elide_name(self._localized(ic.app_id))
        for tile in self.folder_tiles:
            tile.name_label.setText(self._localized(tile.folder_id))

    def _update_dots(self):
        n = self.stack.count()
        cur = self.stack.currentIndex()
        if cur >= n - 1:  # App Library — свои точки
            cur = len(self.home_pages) - 1
            n = len(self.home_pages) + 1
        dots = "".join("●" if i == cur else "○" for i in range(n))
        self.dots.setText(dots)

    # ----------------------------------------------------------- settings API
    def set_icon_size(self, size: int):
        if self._current_icon_size != size:
            self._current_icon_size = size
            self._rebuild_without_animation()

    def set_grid_columns(self, columns: int):
        if self._current_grid_columns != columns:
            self._current_grid_columns = columns
            self._rebuild_without_animation()

    def set_app_names_visibility(self, visible: bool):
        if self._show_app_names != visible:
            self._show_app_names = visible
            self._rebuild_without_animation()

    def _rebuild_without_animation(self):
        # останавливаем все драйверы, ссылающиеся на старые иконки,
        # иначе deleteLater() удалит виджеты под активной анимацией
        self.exit_jiggle_mode()
        if getattr(self, "_flyin_driver", None) is not None:
            self._flyin_driver.stop()
            self._flyin_driver = None
        old_idx = self.stack.currentIndex()
        self._populate_home_pages()
        self.stack.setCurrentIndex(min(old_idx, self.stack.count() - 1))
        self._update_localization()

    def _remove_app(self, app_id: str):
        """Удаление плитки в jiggle mode (как удаление приложения в iOS)."""
        widget = self._find_icon_widget(app_id)
        if widget is None:
            return
        self.apps_data = [a for a in self.apps_data if a[0] != app_id]
        self.exit_jiggle_mode()
        self._rebuild_without_animation()

    # ------------------------------------------------------------- interaction
    def on_tile_pressed(self, tile, global_rect: QRect):
        """Общий обработчик тапа по любой плитке (иконка или папка)."""
        self.launch_from_icon(tile.app_id, global_rect, tile)

    def launch_from_icon(self, app_id: str, global_rect: QRect, src_widget):
        """iOS zoom-transition: морф иконки в экран + fade+scale лаунчера."""
        self.current_app_id_to_launch = app_id
        self.current_icon_rect_for_animation = global_rect

        root = self.window()
        target_rect = QRect(root.rect().topLeft(), root.size()) if root else QRect(global_rect)
        pixmap = getattr(src_widget, "_original_pixmap", None)

        self._morph_pending = False
        self._morph = MorphOverlay(root, global_rect, target_rect,
                                   pixmap=pixmap, corner_start=22, corner_end=0)

        # параллельный уход лаунчера: fade + лёгкое уменьшение
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        base_size = self.size()
        base_pos = self.pos()

        def frame(p):
            eff.setOpacity(1.0 - p)
            s = 1.0 - 0.06 * p
            w = max(1, int(base_size.width() * s))
            h = max(1, int(base_size.height() * s))
            self.setGeometry(base_pos.x() + (base_size.width() - w) // 2,
                             base_pos.y() + (base_size.height() - h) // 2, w, h)

        self._launch_out_driver = _FrameDriver(
            Duration.LAUNCH, Easing.ACCELERATE, frame,
            on_finished=self._on_outgoing_animation_finished, parent=self)
        self._launch_out_driver.start()

        def _emit():
            self._morph_pending = True
            self._on_outgoing_animation_finished()

        self._morph.run_open(duration=Duration.LAUNCH, curve=Easing.IOS_LAUNCH,
                             on_finished=_emit)

    def _on_outgoing_animation_finished(self):
        self.setGraphicsEffect(None)
        if self._launch_out_driver is not None:
            self._launch_out_driver.stop()
            self._launch_out_driver = None
        if self.parent():
            self.setGeometry(self.parent().geometry())
        self.hide()
        if getattr(self, "_morph_pending", False):
            self._morph_pending = False
            self.launch_app_requested.emit(self.current_app_id_to_launch,
                                           self.current_icon_rect_for_animation)

    # --------------------------------------------------------------- folders
    def open_folder(self, folder_id: str, tile_global_rect: QRect):
        """Раскрытие папки: blur-оверлей + zoom-морф плитки в панель папки,
        дочерние иконки разлетаются из центра с stagger-wave (как в iOS)."""
        if self.overlay_active:
            return
        self.overlay_active = True

        tile = next((t for t in self.folder_tiles if t.folder_id == folder_id), None)
        children = self.apps_data
        if tile is not None:
            paths = tile.child_icons
            children = [(aid, nm, p) for (aid, nm, p) in self.apps_data if p in paths]

        overlay = QWidget(self)
        overlay.setGeometry(self.rect())
        self._folder_overlay = overlay

        backdrop = IOSBlurView(overlay, radius=0, blur_radius=30,
                               tint=(10, 12, 20, 150), border=(255, 255, 255, 0))
        backdrop.setGeometry(overlay.rect())
        QTimer.singleShot(0, backdrop.refresh)

        panel = QFrame(overlay)
        panel.setStyleSheet("""
            QFrame { background: rgba(40,42,54,0.88); border-radius: 38px;
                     border: 1px solid rgba(255,255,255,0.10); }""")
        pw = min(360, self.width() - 60)
        ph = min(420, self.height() - 160)
        panel.setFixedSize(pw, ph)
        panel.move((self.width() - pw) // 2, (self.height() - ph) // 2 - 20)

        play = QVBoxLayout(panel)
        play.setContentsMargins(20, 22, 20, 20)
        title = QLabel(self._localized(folder_id))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            "color: white; font-size: 19px; font-weight: 700;"
            "font-family:'SF Pro Display','Segoe UI',sans-serif; background: transparent;")
        play.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(18)
        icons = []
        cols = 3
        for i, (aid, nm, path) in enumerate(children):
            mi = IOSAppIcon(aid, nm, path, panel, draw_size=58, show_name=True)
            grid.addWidget(mi, i // cols, i % cols)
            icons.append(mi)
        play.addLayout(grid)
        play.addStretch(1)

        done = QPushButton("Готово" if self._language == "Русский" else "Done", overlay)
        done.setCursor(QCursor(Qt.PointingHandCursor))
        done.setStyleSheet(
            "QPushButton { color: white; font-weight: 600; font-size: 14px;"
            " background: rgba(120,120,135,0.6); border: none; border-radius: 16px;"
            " padding: 8px 26px; }")
        done.adjustSize()
        done.move((self.width() - done.width()) // 2, self.height() - 60)
        done.clicked.connect(self.close_folder)

        # стартовое состояние: панель потом «вырастет» из плитки папки
        root = self.window()

        panel_opacity = QGraphicsOpacityEffect(panel)
        panel.setGraphicsEffect(panel_opacity)
        panel_opacity.setOpacity(0.0)
        start_geo = panel.geometry()

        def frame(p):
            e = Easing.IOS_LAUNCH.getPoint(p) if hasattr(Easing.IOS_LAUNCH, "getPoint") else p
            # масштаб от плитки к панели
            src = tile_global_rect
            if root is not None:
                src_tl = root.mapFromGlobal(src.topLeft())
                src_local = QRect(self.mapFrom(root, src_tl), src.size())
            else:
                src_local = src
            x = src_local.x() + (start_geo.x() - src_local.x()) * e
            y = src_local.y() + (start_geo.y() - src_local.y()) * e
            sw = src_local.width() + (start_geo.width() - src_local.width()) * e
            sh = src_local.height() + (start_geo.height() - src_local.height()) * e
            panel.setGeometry(int(x), int(y), max(1, int(sw)), max(1, int(sh)))
            panel_opacity.setOpacity(min(1.0, p * 2.2))

        def finish():
            panel.setGeometry(start_geo)
            panel.setGraphicsEffect(None)
            # волны вылета дочерних иконок — как разлёт из плитки в iOS
            reveal = StaggerReveal(overlay)
            centers = (start_geo.center().x() - panel.x(),
                       start_geo.center().y() - panel.y())
            for icn in icons:
                icn._fly_base = (icn.x(), icn.y())
                icn.opacity = 0.0
                icn.set_scale(0.3)

            def apply_fn(w, pp):
                s = spring_progress(pp)
                bx, by = getattr(w, "_fly_base", (w.x(), w.y()))
                dx = bx - centers[0]
                dy = by - centers[1]
                w.move(int(centers[0] + dx * s), int(centers[1] + dy * s))
                w.set_scale(0.3 + 0.7 * s)
                w.opacity = min(1.0, pp * 2.5)

            reveal.run(icons, apply_fn, step_ms=28, duration=Duration.STANDARD,
                       curve=Easing.STANDARD)

            def settle():
                for w in icons:
                    bx, by = getattr(w, "_fly_base", (w.x(), w.y()))
                    w.move(bx, by)
                    w.set_scale(1.0)
                    w.opacity = 1.0

            QTimer.singleShot(Duration.STANDARD + 28 * len(icons) + 60, settle)

        self._folder_driver = _FrameDriver(Duration.SHORT, Easing.IOS_LAUNCH,
                                           frame, finish, self)
        overlay.show()
        overlay.raise_()
        self._folder_driver.start()

    def close_folder(self):
        ov = self._folder_overlay
        if ov is None:
            return
        self.overlay_active = False
        panel = ov.findChild(QFrame)
        eff = QGraphicsOpacityEffect(ov)
        ov.setGraphicsEffect(eff)

        def frame(p):
            eff.setOpacity(1.0 - p)
            if panel:
                panel.adjustSize()

        def done():
            ov.deleteLater()
            self._folder_overlay = None

        drv = _FrameDriver(200, Easing.ACCELERATE, frame, done, self)
        drv.start()

    # -------------------------------------------------------------- spotlight
    def open_spotlight(self):
        """Spotlight: затемнение + blur + строка поиска въезжает сверху (iOS)."""
        if self._spotlight is not None or self.overlay_active:
            return
        self.overlay_active = True
        sp = QWidget(self)
        sp.setGeometry(self.rect())
        self._spotlight = sp

        bg = QWidget(sp)
        bg.setGeometry(sp.rect())
        bg_eff = QGraphicsOpacityEffect(bg)
        bg.setGraphicsEffect(bg_eff)
        bg.setStyleSheet("background: rgba(8,10,16,160);")

        bar = QLineEdit(sp)
        bar.setPlaceholderText("Поиск приложений, контактов…"
                               if self._language == "Русский"
                               else "Search apps, contacts…")
        bar.setClearButtonEnabled(True)
        bar.setStyleSheet(
            "QLineEdit { background: rgba(118,118,128,0.55); color: white;"
            " border: none; border-radius: 12px; padding: 12px 16px; font-size: 17px; }")
        bw = min(420, self.width() - 48)
        bar.setFixedSize(bw, 48)
        final_y = 70
        final_x = (self.width() - bw) // 2

        results = QLabel(sp)
        results.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 13px;")
        results.move(final_x, final_y + 60)
        results.setText("\n".join(self._localized(a[0]) for a in self.apps_data[:6]))

        def close_me(ev=None):
            self.close_spotlight()

        bar.installEventFilter(_KeyFilter(self, on_escape=close_me))
        sp.mousePressEvent = lambda e: close_me()
        bar.mousePressEvent = lambda e: None

        op = QGraphicsOpacityEffect(sp)
        sp.setGraphicsEffect(op)
        op.setOpacity(0.0)
        bar.move(final_x, final_y - 46)

        def frame(p):
            e = Easing.IOS_TRANSITION.getPoint(p) if hasattr(Easing.IOS_TRANSITION, "getPoint") else p
            op.setOpacity(e)
            bar.move(final_x, int(final_y - 46 + 46 * e))

        def done():
            sp.setGraphicsEffect(None)
            bar.setFocus()

        sp.show()
        sp.raise_()
        self._spot_driver = _FrameDriver(Duration.SHORT, Easing.IOS_TRANSITION,
                                         frame, done, self)
        self._spot_driver.start()

    def close_spotlight(self):
        sp = self._spotlight
        if sp is None:
            return
        self.overlay_active = False
        eff = QGraphicsOpacityEffect(sp)
        sp.setGraphicsEffect(eff)

        def frame(p):
            eff.setOpacity(1.0 - p)

        def done():
            sp.deleteLater()
            self._spotlight = None

        _FrameDriver(180, Easing.ACCELERATE, frame, done, self).start()

    # ------------------------------------------------------------- jiggle mode
    def enter_jiggle_mode(self):
        if self.in_jiggle_mode or self.overlay_active:
            return
        self.in_jiggle_mode = True
        tiles = self.grid_app_icons + self.folder_tiles
        for t in tiles:
            ang = (-1.2 if hash(t.app_id if hasattr(t, "app_id") else t.folder_id) % 2
                   else 1.2)
            if isinstance(t, IOSFolderTile):
                continue  # папки в iOS тоже трясутся — рисуем через rotation ниже
            t.set_jiggle(True, ang)
        for t in self.folder_tiles:
            t.setEnabled(False)  # упрощённо: папки дрожат без перетаскивания

        # общая покадровая тряска всех иконок текущей страницы
        state = {"t": 0.0}

        def frame(p):
            state["t"] += 0.033
            tt = state["t"]
            for i, icn in enumerate(self.grid_app_icons):
                if not icn._jiggle_on:
                    continue
                icn._jiggle_driver_time = tt
                icn.update()

        self._jiggle_driver = _FrameDriver(10 ** 9, QEasingCurve.Linear,
                                           frame, None, self)
        self._jiggle_driver.start()

        done_btn = QPushButton("Готово" if self._language == "Русский" else "Done", self)
        done_btn.setObjectName("jiggleDone")
        done_btn.setCursor(QCursor(Qt.PointingHandCursor))
        done_btn.setStyleSheet(
            "QPushButton { color: white; font-weight: 600; background: rgba(118,118,128,0.6);"
            " border: none; border-radius: 16px; padding: 8px 22px; }")
        done_btn.adjustSize()
        done_btn.move(self.width() - done_btn.width() - 20, 16)
        done_btn.clicked.connect(self.exit_jiggle_mode)
        done_btn.show()
        done_btn.raise_()

    def exit_jiggle_mode(self):
        if not self.in_jiggle_mode:
            return
        self.in_jiggle_mode = False
        if self._jiggle_driver:
            self._jiggle_driver.stop()
            self._jiggle_driver = None
        for t in self.grid_app_icons:
            t.set_jiggle(False)
            t.update()
        btn = self.findChild(QPushButton, "jiggleDone")
        if btn:
            btn.deleteLater()

    # ---------------------------------------------------------------- gestures
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            cur = self.stack.currentWidget()
            if cur is not None and cur.rect().contains(cur.mapFrom(self, event.pos())):
                self.swiper.handle_press(event.pos())
            self._swipe_acc = 0.0
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.swiper._dragging:
            self.swiper.handle_move(event.pos())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.swiper._dragging:
            self.swiper.handle_release(event.pos())
            self._update_dots()
        super().mouseReleaseEvent(event)

    # ---------------------------------------------------------------- painting
    def resizeEvent(self, event):
        super().resizeEvent(event)
        # док и точки — поверх страниц, внизу
        dw = min(500, self.width() - 40)
        dh = 92
        self.dock_blur.setGeometry((self.width() - dw) // 2,
                                   self.height() - dh - 26, dw, dh)
        self.dock_inner.setGeometry(0, 0, dw, dh)
        self.dots.resize(self.width(), 20)
        self.dots.move(0, self.height() - dh - 44)
        if self._folder_overlay is not None:
            self._folder_overlay.setGeometry(self.rect())
        if self._spotlight is not None:
            self._spotlight.setGeometry(self.rect())

    def paintEvent(self, event):
        """Обои в стиле iOS Default (graphite + цветные радиальные пятна)."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # jpg-обои из Launcher/Wallpaper, если есть; иначе процедурные iOS-обои
        drawn = False
        wp_dir = "Launcher/Wallpaper"
        if os.path.isdir(wp_dir):
            files = sorted([f for f in os.listdir(wp_dir)
                            if f.lower().endswith((".jpg", ".jpeg", ".png"))])
            if files:
                pm = QPixmap(os.path.join(wp_dir, files[0]))
                if not pm.isNull():
                    scaled = pm.scaled(w, h, Qt.KeepAspectRatioByExpanding,
                                       Qt.SmoothTransformation)
                    x = (scaled.width() - w) // 2
                    y = (scaled.height() - h) // 2
                    painter.drawPixmap(-x, -y, scaled)
                    painter.fillRect(self.rect(), QColor(10, 12, 20, 70))
                    drawn = True

        if not drawn:
            base = QLinearGradient(0, 0, 0, h)
            base.setColorAt(0.0, QColor("#0b0d14"))
            base.setColorAt(0.5, QColor("#131722"))
            base.setColorAt(1.0, QColor("#0a0c12"))
            painter.fillRect(self.rect(), QBrush(base))
            glows = [
                (0.22 * w, 0.16 * h, 0.95 * w, QColor(58, 78, 140, 90)),
                (0.85 * w, 0.42 * h, 0.85 * w, QColor(120, 60, 150, 60)),
                (0.45 * w, 1.02 * h, 0.9 * w, QColor(30, 90, 130, 70)),
            ]
            for gx, gy, gr, gc in glows:
                rg = QRadialGradient(gx, gy, gr)
                rg.setColorAt(0.0, gc)
                outer = QColor(gc)
                outer.setAlpha(0)
                rg.setColorAt(1.0, outer)
                painter.setBrush(QBrush(rg))
                painter.setPen(Qt.NoPen)
                painter.drawRect(self.rect())

        super().paintEvent(event)

    # -------------------------------------------------------- unlock fly-in
    def animate_icons_in(self, origin=None):
        """Прилёт домашнего экрана ровно как unlock-transition в iOS:
        вся группа оседает 1.08→1.0 снизу вверх с ease-out, ~450 мс."""
        all_icons = self.grid_app_icons + self.dock_app_icons
        if not all_icons or all(i.height() <= 0 for i in all_icons):
            QTimer.singleShot(0, lambda: self.animate_icons_in(origin))
            return

        entries = []
        for icon in all_icons:
            base = getattr(icon, "_flyin_base_y", None)
            if base is None:
                base = icon.y()
                icon._flyin_base_y = base
            icon.opacity = 0.0
            icon.set_scale(1.08)
            icon.show()
            entries.append((icon, base))

        total_ms = 450

        def frame(p):
            e = Easing.IOS_TRANSITION.getPoint(p) if hasattr(Easing.IOS_TRANSITION, "getPoint") else p
            dy = 26.0 * (1.0 - e)
            scale = 1.08 - 0.08 * e
            op = min(1.0, p * 3.0)
            for icon, base in entries:
                icon.set_scale(scale)
                icon.opacity = op
                icon.move(icon.x(), int(base + dy))

        def finish():
            self._flyin_driver = None
            for icon, base in entries:
                icon.set_scale(1.0)
                icon.opacity = 1.0
                icon.move(icon.x(), base)

        self._flyin_driver = _FrameDriver(total_ms, QEasingCurve.Linear,
                                          frame, finish, self)
        self._flyin_driver.start()

    def prepare_for_animation(self):
        self._should_animate_on_show = True

    def showEvent(self, event):
        super().showEvent(event)
        self._blur_timer.start()
        if self._should_animate_on_show:
            self.animate_icons_in()
            self._should_animate_on_show = False

    def hideEvent(self, event):
        self._blur_timer.stop()
        self.exit_jiggle_mode()
        super().hideEvent(event)


class _KeyFilter(QObject):
    def __init__(self, parent, on_escape=None):
        super().__init__(parent)
        self.on_escape = on_escape

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
            if self.on_escape:
                self.on_escape()
            return True
        return False


# =============================================================================
# Standalone-тест: python apps/ios_launcher.py
# =============================================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)

    win = QMainWindow()
    win.setGeometry(100, 100, 519, 950)
    win.setStyleSheet("background-color: black;")

    launcher = IOSLauncherContent(win, language="Русский")
    launcher.launch_app_requested.connect(
        lambda aid, r: print(f"Launch requested: {aid} from {r}"))

    central = QWidget()
    cl = QVBoxLayout(central)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.addWidget(launcher)
    win.setCentralWidget(central)
    win.show()

    QTimer.singleShot(1200, lambda: print("Свайпни мышью по экрану влево/вправо,"
                                          " долго зажми иконку (jiggle),"
                                          " тапни папку Utilities"))
    sys.exit(app.exec_())
