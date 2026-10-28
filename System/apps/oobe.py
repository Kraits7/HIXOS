# apps/oobe.py — v3. Fluid-OOBE в стиле iOS 18 / OriginOS 5:
#  • крупная «proximity»-типографика, много воздуха, тонкие разделители;
#  • выбор — не радиокнопки и комбобоксы, а карточки-плитки с press-feedback;
#  • push/pop переходы страниц через движок анимаций системы (PageSwipe);
#  • FLUID: фон — медленный «живой» mesh-градиент (accent-подсветка дышит),
#    карточки — frosted glass поверх фона, hover/press — пружинный scale;
#  • FLUID: прогресс-бар — не точки, а непрерывная капсула: сегменты
#    плавно перетекут один в другой (spring width/opacity);
#  • FLUID: появление контента страницы — волна с параллаксом (стaggered
#    spring fly-in), на финале — концентрические ripple-кольца от чекмара;
#  • НОВЫЕ настройки: страница «Оформление лаунчера» (размер иконок,
#  • сетка, названия приложений) — сразу применяются к системе и
#    сохраняются через user_data_manager.
import sys
import os
import json
import math

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QStackedWidget, QLineEdit, QApplication, QMessageBox, QTextBrowser,
    QFrame, QSizePolicy, QGraphicsOpacityEffect, QScrollArea, QSlider,
    QButtonGroup
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, pyqtProperty, QObject, QTimer, QRect, QPoint, QSize,
    QPropertyAnimation, QEasingCurve, QPointF, QRectF
)
from PyQt5.QtGui import (
    QFont, QColor, QPainter, QPen, QBrush, QPixmap, QRadialGradient,
    QLinearGradient, QPainterPath
)

from ui.navigation_bar import NAVIGATION_MODE_THREE_BUTTON, NAVIGATION_MODE_GESTURES

try:
    from ui.animation_engine import (
        Easing, Duration, PageSwipe, _FrameDriver, animate,
        spring_progress, fly_in_transform,
    )
except ImportError:
    from animation_engine import (
        Easing, Duration, PageSwipe, _FrameDriver, animate,
        spring_progress, fly_in_transform,
    )


ACCENT = "#0A84FF"          # iOS dark-mode blue
ACCENT_2 = "#5E5CE6"        # фиолетовый — для mesh-подсветок фона
BG = "#0b0d12"              # почти чёрный с синим подтоном (iOS setup)
CARD = "rgba(255,255,255,0.06)"
CARD_SELECTED = "rgba(10,132,255,0.18)"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "rgba(255,255,255,0.55)"


class FluidBackground(QWidget):
    """FLUID: «живой» mesh-градиент фона. Несколько radial-пятен медленно
    дрейфуют по эллиптическим траекториям (синусоида по времени), поверх —
    лёгкий вертикальный затемняющий градиент. Дешёвая 60 FPS-анимация через
    общий _FrameDriver системы; при невидимости драйвер сам себя гасит."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._t = 0.0
        self._driver = None
        # (фаза, скорость, rx, ry, цвет, радиус-доля)
        self._blobs = [
            (0.0, 0.10, 0.34, 0.22, QColor(ACCENT), 0.72),
            (2.1, 0.07, 0.28, 0.30, QColor(ACCENT_2), 0.60),
            (4.2, 0.13, 0.22, 0.16, QColor("#00C7BE"), 0.42),
        ]

    def showEvent(self, event):
        super().showEvent(event)
        if self._driver is None:
            self._driver = _FrameDriver(10 ** 7, QEasingCurve.Linear,
                                        self._frame, parent=self)
            self._driver.start()

    def hideEvent(self, event):
        if self._driver is not None:
            self._driver.stop()
            self._driver = None
        super().hideEvent(event)

    def _frame(self, p):
        self._t += 1.0 / 60.0
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor(BG))
        cx, cy = w * 0.5, h * 0.42
        for phase, speed, rx, ry, col, rad in self._blobs:
            t = self._t * speed + phase
            bx = cx + math.cos(t) * w * rx
            by = cy + math.sin(t * 0.83) * h * ry
            r = max(w, h) * rad
            g = QRadialGradient(QPointF(bx, by), r)
            inner = QColor(col)
            inner.setAlpha(34)
            outer = QColor(col)
            outer.setAlpha(0)
            g.setColorAt(0.0, inner)
            g.setColorAt(1.0, outer)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(g))
            p.drawRect(self.rect())
        vg = QLinearGradient(0, 0, 0, h)
        top = QColor(BG); top.setAlpha(0)
        bot = QColor(BG); bot.setAlpha(150)
        vg.setColorAt(0.0, top)
        vg.setColorAt(1.0, bot)
        p.setBrush(QBrush(vg))
        p.drawRect(self.rect())
        p.end()


class GlassPanel(QFrame):
    """FLUID: frosted-glass панель (стеклянная капсула) под контентом
    страницы OOBE: полупрозрачный верхний блик, тонкая светящаяся кромка,
    мягкая тень. Радиус и блик анимируются вместе с press/hover плиток."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 22, 22)
        # тело стекла
        body = QLinearGradient(r.topLeft(), r.bottomLeft())
        body.setColorAt(0.0, QColor(255, 255, 255, 16))
        body.setColorAt(0.45, QColor(255, 255, 255, 8))
        body.setColorAt(1.0, QColor(255, 255, 255, 14))
        p.fillPath(path, QBrush(body))
        # диагональный блик
        sheen = QLinearGradient(r.topLeft(), r.center())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 22))
        sheen.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(sheen))
        # кромка
        p.setPen(QPen(QColor(255, 255, 255, 28), 1.2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()


class FluidSlider(QWidget):
    """FLUID: непрерывный ползунок в стиле iOS: стеклянная дорожка,
    accent-заполнение, круглый thumb с spring-масштабом при захвате."""

    value_changed = pyqtSignal(int)

    def __init__(self, minimum=40, maximum=100, value=70, parent=None):
        super().__init__(parent)
        self._min = minimum
        self._max = maximum
        self._value = value
        self._dragging = False
        self._thumb_scale = 1.0
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_value(self, v):
        v = max(self._min, min(self._max, int(v)))
        if v != self._value:
            self._value = v
            self.value_changed.emit(v)
            self.update()

    def value(self):
        return self._value

    def _pos_to_value(self, x):
        track_w = self.width() - self._track_h()
        frac = max(0.0, min(1.0, (x - self._track_h() / 2) /
                            max(1, track_w - self._track_h())))
        return self._min + frac * (self._max - self._min)

    def _track_h(self):
        return 8

    def _thumb_rect(self):
        h = self.height()
        frac = (self._value - self._min) / max(1, self._max - self._min)
        usable = self.width() - 24
        x = 12 + frac * usable
        s = 24 * self._thumb_scale
        return QRectF(x - s / 2, h / 2 - s / 2, s, s), x

    def mousePressEvent(self, event):
        self._dragging = True
        self._animate_thumb(1.18)
        self.set_value(round(self._pos_to_value(event.pos().x())))
        self.value_changed.emit(self._value)

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.set_value(round(self._pos_to_value(event.pos().x())))
            self.value_changed.emit(self._value)

    def mouseReleaseEvent(self, event):
        self._dragging = False
        self._animate_thumb(1.0)

    def _animate_thumb(self, target):
        anim = animate(self, b"thumbScale", self._thumb_scale, target,
                       Duration.SHORT, Easing.SPRING, self)
        anim.start()

    @pyqtProperty(float)
    def thumbScale(self):
        return self._thumb_scale

    @thumbScale.setter
    def thumbScale(self, v):
        self._thumb_scale = v
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        h = self.height()
        th = self._track_h()
        ty = (h - th) / 2
        # дорожка (стекло)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 26))
        p.drawRoundedRect(QRectF(0, ty, self.width(), th), th / 2, th / 2)
        thumb, x = self._thumb_rect()
        # заполнение
        fill = QLinearGradient(0, 0, self.width(), 0)
        fill.setColorAt(0, QColor(ACCENT))
        fill.setColorAt(1, QColor(ACCENT_2))
        p.setBrush(QBrush(fill))
        p.drawRoundedRect(QRectF(0, ty, max(th, x), th), th / 2, th / 2)
        # thumb с мягкой тенью
        p.setPen(QPen(QColor(0, 0, 0, 90), 3))
        p.setBrush(QColor("white"))
        p.drawEllipse(thumb)
        p.end()


class FluidSwitch(QWidget):
    """FLUID: iOS-переключатель: capsule с плавной сменой цвета и
    spring-перелётом бегунка."""

    toggled = pyqtSignal(bool)

    def __init__(self, checked=True, parent=None):
        super().__init__(parent)
        self._checked = checked
        self._knob = 1.0 if checked else 0.0
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(58, 34)

    def isChecked(self):
        return self._checked

    def set_checked(self, v: bool, emit=False):
        if self._checked == v:
            return
        self._checked = v
        anim = animate(self, b"knob", self._knob, 1.0 if v else 0.0,
                       Duration.SHORT, Easing.SPRING, self)
        anim.start()
        if emit:
            self.toggled.emit(v)

    @pyqtProperty(float)
    def knob(self):
        return self._knob

    @knob.setter
    def knob(self, v):
        self._knob = v
        self.update()

    def mousePressEvent(self, event):
        self.set_checked(not self._checked, emit=True)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = r.height() / 2
        # цвет дорожки интерполируется вместе с бегунком (fluid state-change)
        k = self._knob if self._checked else 1.0 - self._knob
        off_col = QColor(255, 255, 255, 34)
        on_col = QColor(ACCENT)
        track = QColor(off_col)
        track.setRed(int(off_col.red() + (on_col.red() - off_col.red()) * k))
        track.setGreen(int(off_col.green() + (on_col.green() - off_col.green()) * k))
        track.setBlue(int(off_col.blue() + (on_col.blue() - off_col.blue()) * k))
        a_on = 34 + int((255 - 34) * k)
        track.setAlpha(a_on)
        p.setPen(QPen(QColor(255, 255, 255, 26), 1))
        p.setBrush(track)
        p.drawRoundedRect(r, radius, radius)
        d = r.height() - 8
        x = r.left() + 4 + (r.width() - 8 - d) * self._knob
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("white"))
        p.drawEllipse(QRectF(x, r.top() + 4, d, d))
        p.end()


def global_qss():
    return f"""
    QWidget {{
        background-color: transparent;
        color: {TEXT_PRIMARY};
        font-family: "Inter", "SF Pro Display", "Segoe UI", "Roboto", sans-serif;
    }}
    QLabel#pageTitle {{
        font-size: 32px;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: {TEXT_PRIMARY};
        background: transparent;
    }}
    QLabel#pageSubtitle {{
        font-size: 16px;
        color: {TEXT_SECONDARY};
        background: transparent;
    }}
    QLineEdit {{
        border: none;
        border-radius: 14px;
        padding: 16px 18px;
        background-color: {CARD};
        color: white;
        font-size: 17px;
        selection-background-color: {ACCENT};
    }}
    QLineEdit:focus {{
        background-color: rgba(255,255,255,0.09);
    }}
    QTextBrowser {{
        background-color: rgba(255,255,255,0.04);
        border: none;
        border-radius: 16px;
        padding: 14px;
        color: rgba(255,255,255,0.75);
        font-size: 13px;
    }}
    QPushButton#primaryButton {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 {ACCENT}, stop:1 #3D8BFF);
        color: white;
        border: none;
        border-radius: 16px;
        padding: 16px 20px;
        font-size: 17px;
        font-weight: 700;
    }}
    QPushButton#primaryButton:hover {{
        background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
            stop:0 #0a74e0, stop:1 #2f7ce8);
    }}
    QPushButton#primaryButton:pressed {{
        background-color: #0860bb;
    }}
    QPushButton#primaryButton:disabled {{
        background-color: rgba(255,255,255,0.08);
        color: rgba(255,255,255,0.3);
    }}
    QPushButton#textLink {{
        background: transparent;
        border: none;
        color: {ACCENT};
        font-size: 16px;
        font-weight: 600;
        padding: 12px;
    }}
    QPushButton#textLink:hover {{
        color: #4da3ff;
    }}
    QLabel#settingName {{
        font-size: 16px;
        font-weight: 600;
        color: {TEXT_PRIMARY};
        background: transparent;
    }}
    QLabel#settingValue {{
        font-size: 14px;
        font-variant: normal;
        color: {ACCENT};
        background: transparent;
    }}
    """


class TileCard(QFrame):
    """Карточка-плитка выбора (как «Wi-Fi / Язык» в iOS setup):
    заголовок, подпись, справа — индикатор selected (галочка в круге),
    плавный press-scale и анимированная подсветка при выборе."""

    clicked_tile = pyqtSignal()

    def __init__(self, title: str, subtitle: str = "", parent=None):
        super().__init__(parent)
        self._selected = False
        self._hl = 0.0            # 0..1 highlight progress (анимируемое свойство)
        self._scale = 1.0         # FLUID: spring press/hover scale
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(66 if subtitle else 56)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 16, 12)
        lay.setSpacing(12)

        txt = QVBoxLayout()
        txt.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"font-size: 17px; font-weight: 600; color: {TEXT_PRIMARY}; background: transparent;")
        txt.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setStyleSheet(f"font-size: 13px; color: {TEXT_SECONDARY}; background: transparent;")
            txt.addWidget(s)
        lay.addLayout(txt)
        lay.addStretch(1)

        self.check = QLabel("✓", self)
        self.check.setFixedSize(24, 24)
        self.check.setAlignment(Qt.AlignCenter)
        self._update_check_style()
        lay.addWidget(self.check)

    def _update_check_style(self):
        if self._selected:
            self.check.setStyleSheet(
                f"background-color: {ACCENT}; color: white; border-radius: 12px;"
                "font-size: 14px; font-weight: bold;")
        else:
            self.check.setStyleSheet(
                "background-color: transparent; color: transparent;"
                "border: 2px solid rgba(255,255,255,0.18); border-radius: 12px;")

    @pyqtProperty(float)
    def hl(self):
        return self._hl

    @hl.setter
    def hl(self, v):
        self._hl = v
        self.update()

    @pyqtProperty(float)
    def tileScale(self):
        return self._scale

    @tileScale.setter
    def tileScale(self, v):
        self._scale = v
        self.update()

    def _animate_scale(self, target, dur=None):
        anim = animate(self, b"tileScale", self._scale, target,
                       dur or Duration.SHORT, Easing.SPRING, self)
        anim.start()

    def set_selected(self, sel: bool):
        if self._selected == sel:
            return
        self._selected = sel
        self._update_check_style()
        anim = animate(self, b"hl", self._hl, 1.0 if sel else 0.0,
                       Duration.SHORT, Easing.STANDARD, self)
        anim.start()
        # FLUID: selection «отпружинивает» карточку (pop-confirm)
        if sel:
            self._animate_scale(1.025, Duration.SHORT)
            QTimer.singleShot(Duration.SHORT, lambda: self._animate_scale(1.0))

    def is_selected(self):
        return self._selected

    def enterEvent(self, event):
        self._animate_scale(1.012)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._animate_scale(1.0)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        a = animate(self, b"hl", self._hl, max(0.0, self._hl * 0.55) + 0.12,
                    Duration.MICRO, Easing.STANDARD, self)
        a.start()
        self._animate_scale(0.972, Duration.MICRO)   # FLUID press-squish
        self.clicked_tile.emit()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        inside = self.rect().contains(event.pos())
        self._animate_scale(1.012 if inside else 1.0)
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        # FLUID: spring-scale вокруг центра карточки
        if abs(self._scale - 1.0) > 0.001:
            c = QRectF(self.rect()).center()
            p.translate(c)
            p.scale(self._scale, self._scale)
            p.translate(-c)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        base = QColor(CARD_SELECTED) if self._selected else QColor(CARD)
        glow = int(self._hl * 26)
        col = QColor(base)
        col.setRed(min(255, col.red() + glow))
        col.setGreen(min(255, col.green() + glow))
        col.setBlue(min(255, col.blue() + glow))
        path = QPainterPath()
        path.addRoundedRect(r, 16, 16)
        p.setPen(Qt.NoPen)
        p.fillPath(path, QBrush(col))
        # верхний стеклянный блик
        sheen = QLinearGradient(r.topLeft(), r.bottomLeft())
        sheen.setColorAt(0.0, QColor(255, 255, 255, 14))
        sheen.setColorAt(0.5, QColor(255, 255, 255, 0))
        p.fillPath(path, QBrush(sheen))
        if self._selected:
            pen_col = QColor(ACCENT)
            pen_col.setAlpha(int(120 + 135 * min(1.0, self._hl)))
            p.setPen(QPen(pen_col, 1.6))
        else:
            p.setPen(QPen(QColor(255, 255, 255, 20), 1.0))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()
        super().paintEvent(event)


class TileGroup(QObject):
    """Эксклюзивная группа TileCard (как QButtonGroup для плиток)."""

    selection_changed = pyqtSignal(object)  # выбранная карточка

    def __init__(self, cards, parent=None):
        super().__init__(parent)
        self.cards = list(cards)
        self._current = None
        for c in self.cards:
            c.clicked_tile.connect(lambda card=c: self._select(card))

    def _select(self, card):
        if self._current is card:
            return
        self._current = card
        for c in self.cards:
            c.set_selected(c is card)
        self.selection_changed.emit(card)

    def select_by_index(self, i):
        if 0 <= i < len(self.cards):
            self._select(self.cards[i])

    def current_index(self):
        if self._current in self.cards:
            return self.cards.index(self._current)
        return -1


class BaseOOBEPage(GlassPanel):
    """Общий каркас страницы: стеклянная панель поверх fluid-фона,
    заголовок/подзаголовок, место под контент и нижняя кнопка действия.
    FLUID: появление контента — волна spring-прилётов с параллаксом."""

    next_page_requested = pyqtSignal()
    prev_page_requested = pyqtSignal()
    finish_oobe_requested = pyqtSignal(str, str, str)

    def __init__(self, parent=None, oobe=None):
        super().__init__(parent)
        self.oobe = oobe
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(28, 10, 28, 24)
        self.root.setSpacing(0)

        self.header_box = QVBoxLayout()
        self.header_box.setSpacing(6)
        self.title_label = QLabel("")
        self.title_label.setObjectName("pageTitle")
        self.subtitle_label = QLabel("")
        self.subtitle_label.setObjectName("pageSubtitle")
        self.subtitle_label.setWordWrap(True)
        self.header_box.addWidget(self.title_label)
        self.header_box.addWidget(self.subtitle_label)
        self.root.addLayout(self.header_box)
        self.root.addSpacing(26)

        self.content_box = QVBoxLayout()
        self.content_box.setSpacing(10)
        self.root.addLayout(self.content_box)
        self.root.addStretch(1)

        self.footer_box = QVBoxLayout()
        self.footer_box.setSpacing(4)
        self.root.addLayout(self.footer_box)

    def set_title(self, title, subtitle=""):
        self.title_label.setText(title)
        self.subtitle_label.setText(subtitle)
        self.subtitle_label.setVisible(bool(subtitle))

    def add_primary_button(self, text, handler, object_name="primaryButton"):
        btn = QPushButton(text)
        btn.setObjectName(object_name)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(54)
        btn.clicked.connect(handler)
        self.footer_box.addWidget(btn)
        return btn

    def add_secondary_link(self, text, handler):
        btn = QPushButton(text)
        btn.setObjectName("textLink")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(handler)
        self.footer_box.addWidget(btn)
        return btn

    def reveal_widgets(self):
        """FLUID: волна spring-прилётов снизу с параллаксом — элементы выше
        по списку прилетают раньше и «медленнее», создавая эффект глубины."""
        targets = []
        for i in range(self.content_box.count()):
            item = self.content_box.itemAt(i)
            w = item.widget()
            if w is not None:
                targets.append(w)
        for lbl in (self.title_label, self.subtitle_label):
            if lbl.isVisible():
                targets.insert(0, lbl) if lbl is self.title_label else targets.append(lbl)
        footer = [self.footer_box.itemAt(i).widget()
                  for i in range(self.footer_box.count())
                  if self.footer_box.itemAt(i) and self.footer_box.itemAt(i).widget()]
        targets.extend(footer)

        drivers = getattr(self, "_reveal_drivers", [])
        for d in drivers:
            d.stop()
        self._reveal_drivers = []

        n = max(1, len(targets))
        for idx, w in enumerate(targets):
            eff = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(eff)
            base_y = w.y()
            # параллакс: дальние (нижние) элементы стартуют позже и летят дальше
            off = 0.04 + idx * min(0.055, 0.62 / n)

            def make(widget, effect, by, o):
                def frame(p):
                    lp = max(0.0, min(1.0, (p - o) / max(1e-6, 1.0 - o)))
                    dy, scale, opacity = fly_in_transform(lp)
                    effect.setOpacity(opacity)
                    widget.move(widget.x(), int(by + dy))
                def done(widget=widget, by=by):
                    widget.setGraphicsEffect(None)
                    widget.move(widget.x(), by)
                return frame, done

            frame_fn, done_fn = make(w, eff, base_y, off)
            drv = _FrameDriver(480, QEasingCurve.Linear, frame_fn, done_fn, self)
            drv.start()
            self._reveal_drivers.append(drv)


class WelcomeLanguagePage(BaseOOBEPage):
    def __init__(self, parent=None, oobe=None, current_language="Русский"):
        super().__init__(parent, oobe)
        self.set_title("Добро пожаловать",
                       "Это HIX OS. Выберите язык — его можно будет сменить\nв Настройках в любой момент.")

        langs = ["Русский", "English", "Deutsch", "Français"]
        subs = ["Russian", "Английский", "Немецкий", "Французский"]
        cards = []
        for name, sub in zip(langs, subs):
            c = TileCard(name, sub, self)
            self.content_box.addWidget(c)
            cards.append(c)
        self.group = TileGroup(cards, self)
        try:
            self.group.select_by_index(langs.index(current_language))
        except ValueError:
            self.group.select_by_index(0)

        self.add_primary_button("Продолжить", self.next_page_requested.emit)

    def get_selected_language(self):
        idx = self.group.current_index()
        return ["Русский", "English", "Deutsch", "Français"][max(0, idx)]


class EULAPage(BaseOOBEPage):
    def __init__(self, parent=None, oobe=None):
        super().__init__(parent, oobe)
        self.set_title("Лицензионное соглашение",
                       "Коротко: система бесплатна, предоставляется «как есть»,\n"
                       "вы можете использовать её для любых личных целей.")

        eula_text = (
            "HIX OS License Agreement\n\n"
            "1. Лицензия. Вам предоставляется неисключительная лицензия на использование HIX OS.\n"
            "2. Ограничения. Запрещено продавать систему под видом собственной.\n"
            "3. Гарантии. Система предоставляется «как есть», без гарантий.\n"
            "4. Ответственность. Авторы не несут ответственности за убытки от использования.\n"
            "5. Изменения. Условия могут обновляться вместе с новыми версиями.\n\n"
            "Нажимая «Принять», вы соглашаетесь с этими условиями."
        )
        self.eula_viewer = QTextBrowser(self)
        self.eula_viewer.setPlainText(eula_text)
        self.eula_viewer.setFixedHeight(220)
        self.content_box.addWidget(self.eula_viewer)

        accept_card_hint = QLabel("Прокрутите текст, чтобы разблокировать кнопку")
        accept_card_hint.setObjectName("pageSubtitle")
        accept_card_hint.setAlignment(Qt.AlignCenter)
        self.content_box.addWidget(accept_card_hint)
        self.hint_label = accept_card_hint

        self.next_button = self.add_primary_button("Принять", self.next_page_requested.emit)
        self.back_link = self.add_secondary_link("Назад", self.prev_page_requested.emit)

        self.next_button.setEnabled(False)
        self.eula_viewer.verticalScrollBar().rangeChanged.connect(self._on_range)
        self.eula_viewer.verticalScrollBar().valueChanged.connect(self._on_scroll)

    def _on_range(self, mn, mx):
        self._max_scroll = mx

    def _on_scroll(self, v):
        if v >= getattr(self, "_max_scroll", 1) - 4:
            if not self.next_button.isEnabled():
                self.next_button.setEnabled(True)
                self.hint_label.setText("Спасибо! Можно продолжать →")

    def showEvent(self, event):
        super().showEvent(event)
        # если контент короче области — сразу принимаем
        QTimer.singleShot(60, lambda: (
            self.next_button.setEnabled(True)
            if self.eula_viewer.verticalScrollBar().maximum() == 0 else None))


class UserSetupPage(BaseOOBEPage):
    def __init__(self, parent=None, oobe=None):
        super().__init__(parent, oobe)
        self._username = ""
        self.set_title("Как к вам обращаться?",
                       "Имя появится на экране блокировки и в приветствии рабочего стола.")

        self.avatar = QLabel(self)
        self.avatar.setFixedSize(88, 88)
        self.avatar.setAlignment(Qt.AlignCenter)
        self.avatar.setStyleSheet(
            f"background-color: linear-gradient(#0A84FF,#5E5CE6);"
            "border-radius: 44px; font-size: 34px; font-weight: 800; color: white;")
        av_wrap = QHBoxLayout()
        av_wrap.addStretch(1)
        av_wrap.addWidget(self.avatar)
        av_wrap.addStretch(1)
        self.content_box.addLayout(av_wrap)
        self.content_box.addSpacing(8)

        self.username_input = QLineEdit(self)
        self.username_input.setPlaceholderText("Введите имя…")
        self.username_input.setAlignment(Qt.AlignCenter)
        self.username_input.textChanged.connect(self._on_text)
        self.content_box.addWidget(self.username_input)

        self.next_button = self.add_primary_button("Создать профиль", self.next_page_requested.emit)
        self.next_button.setEnabled(False)
        self.add_secondary_link("Назад", self.prev_page_requested.emit)

    def _on_text(self, text):
        self._username = text.strip()
        self.next_button.setEnabled(bool(self._username))
        self.avatar.setText(self._username[0].upper() if self._username else "")

    def get_username(self):
        return self._username


class NavigationChoicePage(BaseOOBEPage):
    def __init__(self, parent=None, oobe=None, initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON):
        super().__init__(parent, oobe)
        self.set_title("Выберите навигацию",
                       "Три кнопки — классика Android. Жесты — больше места\nпод контент и свайпы, как в современных смартфонах.")

        self.card_buttons = TileCard(
            "Три кнопки", "Назад · Домой · Недавние", self)
        self.card_gestures = TileCard(
            "Жесты", "Свайпы от краёв и снизу", self)
        self.content_box.addWidget(self.card_buttons)
        self.content_box.addWidget(self.card_gestures)

        self.group = TileGroup([self.card_buttons, self.card_gestures], self)
        self._modes = [NAVIGATION_MODE_THREE_BUTTON, NAVIGATION_MODE_GESTURES]
        self.group.select_by_index(
            self._modes.index(initial_navigation_mode)
            if initial_navigation_mode in self._modes else 0)

        self.add_primary_button("Продолжить", self.next_page_requested.emit)
        self.add_secondary_link("Назад", self.prev_page_requested.emit)

    def get_selected_navigation_mode(self):
        idx = self.group.current_index()
        return self._modes[max(0, idx)]


class LauncherStylePage(BaseOOBEPage):
    """НОВЫЕ настройки в OOBE: оформление лаунчера. Fluid-виджеты:
    непрерывный слайдер размера иконок, сегмент-пилюли для сетки,
    iOS-переключатель названий. Изменения применяются к системе сразу."""

    def __init__(self, parent=None, oobe=None,
                 initial_icon_size=70, initial_columns=4, initial_show_names=True):
        super().__init__(parent, oobe)
        self.set_title("Оформление лаунчера",
                       "Настройте сетку приложений под себя — эти параметры\n"
                       "в любой момент можно изменить в Настройках.")

        self._icon_size = max(40, min(100, int(initial_icon_size)))
        self._columns = initial_columns if initial_columns in (3, 4, 5) else 4
        self._show_names = bool(initial_show_names)

        # --- Размер иконок: fluid-слайдер + живое значение ---
        size_card = QFrame(self)
        size_card.setStyleSheet(
            "QFrame { background-color: rgba(255,255,255,0.05);"
            " border-radius: 16px; }")
        sc_lay = QVBoxLayout(size_card)
        sc_lay.setContentsMargins(18, 14, 18, 14)
        sc_lay.setSpacing(8)
        row = QHBoxLayout()
        name = QLabel("Размер иконок")
        name.setObjectName("settingName")
        row.addWidget(name)
        row.addStretch(1)
        self.size_value_label = QLabel(f"{self._icon_size} px")
        self.size_value_label.setObjectName("settingValue")
        row.addWidget(self.size_value_label)
        sc_lay.addLayout(row)
        self.icon_size_slider = FluidSlider(40, 100, self._icon_size, size_card)
        self.icon_size_slider.value_changed.connect(self._on_icon_size)
        sc_lay.addWidget(self.icon_size_slider)
        self.content_box.addWidget(size_card)

        # --- Столбцы сетки: сегмент-пилюля ---
        grid_card = QFrame(self)
        grid_card.setStyleSheet(
            "QFrame { background-color: rgba(255,255,255,0.05);"
            " border-radius: 16px; }")
        gc_lay = QVBoxLayout(grid_card)
        gc_lay.setContentsMargins(18, 14, 18, 14)
        gc_lay.setSpacing(10)
        gname = QLabel("Столбцов в сетке")
        gname.setObjectName("settingName")
        gc_lay.addWidget(gname)
        seg_wrap = QHBoxLayout()
        seg_wrap.setSpacing(6)
        self._seg_buttons = []
        for col_val in (3, 4, 5):
            b = QPushButton(str(col_val))
            b.setCheckable(True)
            b.setChecked(col_val == self._columns)
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(40)
            b.setStyleSheet(self._segment_qss(b.isChecked()))
            b.clicked.connect(lambda _=False, cv=col_val: self._on_columns(cv))
            seg_wrap.addWidget(b)
            self._seg_buttons.append(b)
        gc_lay.addLayout(seg_wrap)
        self.content_box.addWidget(grid_card)

        # --- Названия приложений: fluid-switch ---
        names_card = QFrame(self)
        names_card.setStyleSheet(
            "QFrame { background-color: rgba(255,255,255,0.05);"
            " border-radius: 16px; }")
        nc_lay = QHBoxLayout(names_card)
        nc_lay.setContentsMargins(18, 12, 18, 12)
        nlabel = QLabel("Показывать названия приложений")
        nlabel.setObjectName("settingName")
        nc_lay.addWidget(nlabel)
        nc_lay.addStretch(1)
        self.names_switch = FluidSwitch(self._show_names, names_card)
        self.names_switch.toggled.connect(self._on_names_toggled)
        nc_lay.addWidget(self.names_switch)
        self.content_box.addWidget(names_card)

        self.add_primary_button("Продолжить", self.next_page_requested.emit)
        self.add_secondary_link("Назад", self.prev_page_requested.emit)

    @staticmethod
    def _segment_qss(checked: bool) -> str:
        if checked:
            return (f"QPushButton {{ background-color: {ACCENT}; color: white;"
                    " border: none; border-radius: 13px; font-size: 16px;"
                    " font-weight: 700; }")
        return ("QPushButton { background-color: rgba(255,255,255,0.07);"
                " color: rgba(255,255,255,0.6); border: none;"
                " border-radius: 13px; font-size: 16px; font-weight: 600; }"
                " QPushButton:hover { background-color: rgba(255,255,255,0.11); }")

    def _apply_live(self, kind: str, value):
        """Мгновенное применение настройки к системе (fluid live-preview)."""
        oobe = self.oobe
        if oobe is None:
            return
        if kind == "icon_size":
            oobe._launcher_icon_size = value
        elif kind == "columns":
            oobe._launcher_grid_columns = value
        elif kind == "names":
            oobe._launcher_show_app_names = value
        oobe._apply_launcher_settings_to_system()

    def _on_icon_size(self, value: int):
        self._icon_size = value
        self.size_value_label.setText(f"{value} px")
        self._apply_live("icon_size", value)

    def _on_columns(self, value: int):
        self._columns = value
        for b, cv in zip(self._seg_buttons, (3, 4, 5)):
            b.setChecked(cv == value)
            b.setStyleSheet(self._segment_qss(cv == value))
        self._apply_live("columns", value)

    def _on_names_toggled(self, checked: bool):
        self._show_names = checked
        self._apply_live("names", checked)

    def get_launcher_settings(self):
        return self._icon_size, self._columns, self._show_names


class FinalOOBEPage(BaseOOBEPage):
    def __init__(self, parent=None, oobe=None):
        super().__init__(parent, oobe)
        self.set_title("Всё готово!", "")

        # Spring-pop чекмар
        self.check_circle = QLabel(self)
        self.check_circle.setFixedSize(110, 110)
        self.check_circle.setAlignment(Qt.AlignCenter)
        self.check_circle.setStyleSheet(
            f"background-color: {ACCENT}; color: white;"
            "border-radius: 55px; font-size: 54px; font-weight: 800;")
        self.check_circle.setText("✓")
        wrap = QHBoxLayout()
        wrap.addStretch(1)
        wrap.addWidget(self.check_circle)
        wrap.addStretch(1)
        self.content_box.addLayout(wrap)
        self.content_box.addSpacing(14)

        summary = QLabel("Профиль создан, система настроена.\nПриятного пользования HIX OS!")
        summary.setObjectName("pageSubtitle")
        summary.setAlignment(Qt.AlignCenter)
        self.content_box.addWidget(summary)

        self.add_primary_button(
            "Начать работу",
            lambda: self.finish_oobe_requested.emit(
                self.oobe._current_language,
                self.oobe._current_navigation_mode,
                self.oobe._username))

    def reveal_widgets(self):
        super().reveal_widgets()
        # отдельный pop для чекмара: scale 0 -> overshoot 1.15 -> 1
        self.check_circle.setGraphicsEffect(QGraphicsOpacityEffect(self.check_circle))
        driver = _FrameDriver(520, QEasingCurve.Linear, self._pop_frame,
                              on_finished=lambda: self.check_circle.setGraphicsEffect(None),
                              parent=self)
        self._pop_driver = driver
        driver.start()
        # FLUID: концентрические ripple-кольца, расходящиеся от чекмара
        self._rings = [0.0, 0.0, 0.0]
        ring_drv = _FrameDriver(1400, QEasingCurve.Linear, self._ring_frame,
                                parent=self)
        self._ring_driver = ring_drv
        ring_drv.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def _ring_frame(self, p):
        # три кольца со сдвигом фазы
        for i in range(3):
            lp = max(0.0, min(1.0, (p - i * 0.14) / 0.72))
            self._rings[i] = lp
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        rings = getattr(self, "_rings", None)
        if not rings:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        center = self.check_circle.geometry().center()
        base = self.check_circle.width() / 2.0
        for i, lp in enumerate(rings):
            if lp <= 0.0 or lp >= 1.0:
                continue
            radius = base + 130.0 * spring_progress(lp)
            alpha = int(70 * (1.0 - lp))
            pen = QPen(QColor(ACCENT))
            pen.setColor(QColor(10, 132, 255, alpha))
            pen.setWidthF(2.0 * (1.0 - lp) + 0.6)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QPointF(center), radius, radius)
        p.end()

    def _pop_frame(self, p):
        s = spring_progress(min(1.0, p * 1.15))
        scale = max(0.01, s)
        size = int(110 * min(scale, 1.15))
        self.check_circle.setFixedSize(size, size)
        self.check_circle.setStyleSheet(
            f"background-color: {ACCENT}; color: white;"
            f"border-radius: {size // 2}px; font-size: {int(size * 0.49)}px; font-weight: 800;")
        self.check_circle.graphicsEffect().setOpacity(min(1.0, p * 3))


class OOBEContent(QWidget):
    """Управляет страницами OOBE: fluid-фон + стек стеклянных страниц +
    PageSwipe push/pop + непрерывный капсульный прогресс-бар."""

    oobe_finished = pyqtSignal(str, str, str)
    # НОВЫЕ настройки лаунчера — применяются к системе сразу (live-preview)
    launcher_settings_changed = pyqtSignal(int, int, bool)  # size, columns, names

    def __init__(self, parent=None, current_language="Русский",
                 initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON,
                 user_data_manager=None,
                 initial_icon_size=70, initial_grid_columns=4,
                 initial_show_app_names=True):
        super().__init__(parent)
        self.main_window = parent
        self._current_language = current_language
        self._current_navigation_mode = initial_navigation_mode
        self.user_data_manager = user_data_manager
        self._username = ""
        # настройки лаунчера из OOBE
        self._launcher_icon_size = initial_icon_size
        self._launcher_grid_columns = initial_grid_columns
        self._launcher_show_app_names = initial_show_app_names

        self.setStyleSheet(global_qss())

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # --- FLUID: живой mesh-градиент на весь экран OOBE ---
        self.fluid_bg = FluidBackground(self)
        self.stacked_pages = QStackedWidget(self)   # создадим раньше по порядку
        v.addWidget(self.fluid_bg, 0)               # место займим ниже через raise/lower

        # фон лежит под всем контентом
        self.fluid_bg.lower()

        # --- шапка: непрерывный капсульный прогресс-бар ---
        self.top_bar = QHBoxLayout()
        self.top_bar.setContentsMargins(28, 22, 28, 10)
        self.top_bar.addStretch(1)
        num_pages = 6
        self.progress_capsule = QFrame(self)
        self.progress_capsule.setObjectName("progressCapsule")
        self.progress_capsule.setStyleSheet(
            "#progressCapsule { background-color: transparent; }")
        cap_lay = QHBoxLayout(self.progress_capsule)
        cap_lay.setContentsMargins(0, 0, 0, 0)
        cap_lay.setSpacing(5)
        self.progress_segments = []
        for i in range(num_pages):
            seg = QFrame(self.progress_capsule)
            seg.setFixedHeight(5)
            seg.setStyleSheet("background-color: rgba(255,255,255,0.16);"
                              " border-radius: 3px;")
            self.progress_segments.append(seg)
            cap_lay.addWidget(seg, 1 if i else 0)
        self.progress_capsule.setFixedWidth(190)
        self.top_bar.addWidget(self.progress_capsule)
        self.top_bar.addStretch(1)
        v.addLayout(self.top_bar)
        v.addWidget(self.stacked_pages, 1)

        self.welcome_page = WelcomeLanguagePage(oobe=self, current_language=current_language)
        self.eula_page = EULAPage(oobe=self)
        self.user_setup_page = UserSetupPage(oobe=self)
        self.navigation_choice_page = NavigationChoicePage(
            oobe=self, initial_navigation_mode=initial_navigation_mode)
        self.launcher_style_page = LauncherStylePage(
            oobe=self, initial_icon_size=initial_icon_size,
            initial_columns=initial_grid_columns,
            initial_show_names=initial_show_app_names)
        self.final_page = FinalOOBEPage(oobe=self)

        for pg in (self.welcome_page, self.eula_page, self.user_setup_page,
                   self.navigation_choice_page, self.launcher_style_page,
                   self.final_page):
            self.stacked_pages.addWidget(pg)

        self.welcome_page.next_page_requested.connect(self._next_page)
        self.eula_page.next_page_requested.connect(self._next_page)
        self.eula_page.prev_page_requested.connect(self._prev_page)
        self.user_setup_page.next_page_requested.connect(self._next_page)
        self.user_setup_page.prev_page_requested.connect(self._prev_page)
        self.navigation_choice_page.next_page_requested.connect(self._next_page)
        self.navigation_choice_page.prev_page_requested.connect(self._prev_page)
        self.launcher_style_page.next_page_requested.connect(self._next_page)
        self.launcher_style_page.prev_page_requested.connect(self._prev_page)
        self.final_page.finish_oobe_requested.connect(self._handle_oobe_finish)

        self._swipe = PageSwipe(self.stacked_pages)
        self.stacked_pages.setCurrentIndex(0)
        self._animating = False
        self._seg_anims = []
        self._update_progress_indicator(0)
        QTimer.singleShot(120, self.welcome_page.reveal_widgets)

    def resizeEvent(self, event):
        # fluid-фон всегда на весь экран, под остальным контентом
        self.fluid_bg.setGeometry(self.rect())
        self.fluid_bg.lower()
        super().resizeEvent(event)

    def _apply_launcher_settings_to_system(self):
        """Live-применение настроек лаунчера, выбранных в OOBE."""
        self.launcher_settings_changed.emit(
            self._launcher_icon_size, self._launcher_grid_columns,
            self._launcher_show_app_names)

    def _next_page(self):
        cur = self.stacked_pages.currentIndex()
        if self._animating or cur >= self.stacked_pages.count() - 1:
            return
        self._collect_from_page(cur)
        nxt = self.stacked_pages.widget(cur + 1)
        self._animating = True
        self._swipe.transition_to(nxt, direction="forward",
                                  duration=Duration.TRANSITION,
                                  on_finished=self._after_transition)

    def _prev_page(self):
        cur = self.stacked_pages.currentIndex()
        if self._animating or cur <= 0:
            return
        prev = self.stacked_pages.widget(cur - 1)
        self._animating = True
        self._swipe.transition_to(prev, direction="backward",
                                  duration=Duration.TRANSITION,
                                  on_finished=self._after_transition)

    def _after_transition(self):
        self._animating = False
        self._update_progress_indicator(self.stacked_pages.currentIndex())

    def _collect_from_page(self, index):
        if index == 0:
            self._current_language = self.welcome_page.get_selected_language()
        elif index == 2:
            self._username = self.user_setup_page.get_username()
        elif index == 3:
            self._current_navigation_mode = \
                self.navigation_choice_page.get_selected_navigation_mode()

    def _update_progress_indicator(self, index: int):
        """FLUID: непрерывная капсула — сегменты плавно перетекают по яркости
        и толщине (spring через движок анимаций системы)."""
        # spring-анимация толщины сегментов
        for anim in getattr(self, "_seg_anims", []):
            try:
                anim.stop()
            except RuntimeError:
                pass
        self._seg_anims = []
        for i, seg in enumerate(self.progress_segments):
            target_h = 9 if i == index else 5
            a = QPropertyAnimation(seg, b"minimumHeight", self)
            a.setDuration(Duration.TRANSITION // 2)
            a.setStartValue(seg.minimumHeight())
            a.setEndValue(target_h)
            a.setEasingCurve(Easing.SPRING)
            a.start(QPropertyAnimation.DeleteWhenStopped)
            self._seg_anims.append(a)
        # цвет сегментов — через property+style, перерисовывается сразу
        for i, seg in enumerate(self.progress_segments):
            if i == index:
                col = ACCENT
            elif i < index:
                col = "rgba(255,255,255,0.45)"
            else:
                col = "rgba(255,255,255,0.16)"
            seg.setStyleSheet(f"background-color: {col}; border-radius: 3px;")

    def _handle_oobe_finish(self, language, nav_mode, username):
        self._current_language = language
        self._current_navigation_mode = nav_mode
        self._username = username
        self.oobe_finished.emit(language, nav_mode, username)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = QWidget()
    window.setWindowTitle("HIXOS OOBE v2")
    window.setGeometry(100, 100, 480, 900)
    oobe = OOBEContent(window)
    oobe.oobe_finished.connect(lambda l, n, u: (
        QMessageBox.information(window, "OOBE завершено",
                                f"Язык: {l}\nНавигация: {n}\nПользователь: {u}"),
        window.close()))
    lay = QVBoxLayout(window)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(oobe)
    window.show()
    sys.exit(app.exec_())
