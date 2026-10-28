# ui/statusbar.py
"""Статус-бар HIXOS в стиле iOS 16.

Оформление:
  * полностью прозрачный фон — контент страницы просвечивает сквозь бар;
  * слева — время (как на iPhone, жирное, по левому краю);
  * справа — нарисованные векторные иконки: сотовая сеть (4 столбика),
    Wi-Fi и батарея со «сочным» уровнем заряда;
  * цвета автоматически инвертируются под светлый/тёмный фон страницы;
  * публичный API совместим со старым кодом (set_is_light_background,
    time_updated, layout-обёртка).
"""
import math
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtGui import QPixmap, QFont, QPainter, QColor, QPen, QBrush, QPainterPath
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, pyqtSignal, QRectF


class _IconWidget(QWidget):
    """Векторная иконка статус-бара, рисуемая вручную (без внешних png)."""

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.color = QColor("#FFFFFF")
        if kind == "signal":
            self.setFixedSize(18, 12)
        elif kind == "wifi":
            self.setFixedSize(17, 12)
        else:  # battery
            self.setFixedSize(27, 13)
        self._level = 0.82
        self.setAttribute(Qt.WA_TranslucentBackground)

    def set_level(self, level: float):
        self._level = max(0.0, min(1.0, level))
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        c = QColor(self.color)
        pen = QPen(c)
        pen.setCapStyle(Qt.RoundCap)

        if self.kind == "signal":
            # 4 столбика растущей высоты (iOS cellular bars)
            w, h = self.width(), self.height()
            bar_w = 3.0
            gap = (w - bar_w * 4) / 3.0
            heights = [0.38, 0.58, 0.78, 1.0]
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            for i, hr in enumerate(heights):
                bh = h * hr
                x = i * (bar_w + gap)
                path = QPainterPath()
                path.addRoundedRect(QRectF(x, h - bh, bar_w, bh), 1.1, 1.1)
                p.drawPath(path)

        elif self.kind == "wifi":
            # Три дуги + точка — фирменный значок Wi-Fi iOS
            cx = self.width() / 2.0
            cy = self.height() - 1.5
            p.setBrush(Qt.NoBrush)
            radii = [10.5, 7.0, 3.6]
            widths = [1.9, 1.8, 1.7]
            for r, lw in zip(radii, widths):
                pen.setWidthF(lw)
                pen.setColor(c)
                p.setPen(pen)
                rect = QRectF(cx - r, cy - r, 2 * r, 2 * r)
                span = 90 * 16  # сектор сверху, от -45° до +45° относительно вертикали
                p.drawArc(rect, 60 * 16, span)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(c))
            dot_r = 1.7
            p.drawEllipse(QRectF(cx - dot_r, cy - dot_r * 1.6, dot_r * 2, dot_r * 2))

        else:  # battery
            w, h = self.width(), self.height()
            body_rect = QRectF(0.5, 0.5, w - 4.0, h - 1.0)
            # Контейнер батареи
            pen.setWidthF(1.1)
            pen.setColor(QColor(c.red(), c.green(), c.blue(), 150))
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            path = QPainterPath()
            path.addRoundedRect(body_rect, 3.6, 3.6)
            p.drawPath(path)
            # Справа — «ножка»
            nub = QRectF(w - 2.6, h / 2.0 - 2.0, 1.6, 4.0)
            p.setPen(Qt.NoPen)
            p.setBrush(QBrush(QColor(c.red(), c.green(), c.blue(), 150)))
            np_ = QPainterPath()
            np_.addRoundedRect(nub, 1.0, 1.0)
            p.drawPath(np_)
            # Заряд
            inset = 2.2
            fill_w = (body_rect.width() - inset * 2) * self._level
            if fill_w > 0.5:
                fill_col = QColor("#FF3B30") if self._level <= 0.2 else QColor(c.name())
                p.setBrush(QBrush(fill_col))
                fp = QPainterPath()
                fp.addRoundedRect(QRectF(body_rect.left() + inset,
                                         body_rect.top() + inset,
                                         fill_w,
                                         body_rect.height() - inset * 2), 2.0, 2.0)
                p.drawPath(fp)
        p.end()


class StatusBarWidget(QWidget):
    time_updated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.is_light_background = False  # светлый фон страницы -> тёмные чернила
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._ink = QColor("#FFFFFF")

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(14, 0, 12, 0)
        self.layout.setSpacing(6)

        # Время — слева, как на iPhone
        self.time_label = QLabel("00:00")
        f = QFont("SF Pro Display")
        f.setPointSize(12)
        f.setWeight(QFont.Black)
        f.setStyleStrategy(QFont.PreferAntialias)
        self.time_label.setFont(f)
        self.layout.addWidget(self.time_label, alignment=Qt.AlignVCenter | Qt.AlignLeft)

        self.layout.addStretch(1)

        # Иконки справа: сигнал, Wi-Fi, батарея
        self.signal_icon = _IconWidget("signal", self)
        self.wifi_icon_label = _IconWidget("wifi", self)  # имя сохранено для совместимости
        self.battery_icon = _IconWidget("battery", self)
        self.layout.addWidget(self.signal_icon, alignment=Qt.AlignVCenter)
        self.layout.addWidget(self.wifi_icon_label, alignment=Qt.AlignVCenter)
        self.layout.addWidget(self.battery_icon, alignment=Qt.AlignVCenter)

        # Батарея в процентах — маленькая подпись рядом с иконкой
        self.battery_label = QLabel("82%")
        bf = QFont("SF Pro Display")
        bf.setPointSize(10)
        bf.setWeight(QFont.Bold)
        self.battery_label.setFont(bf)
        self.battery_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.layout.addWidget(self.battery_label, alignment=Qt.AlignVCenter)

        self._apply_ink()

        self.setup_timers()
        self._update_time()
        self._update_battery_status()

    # ------------------------------------------------------------------
    def setup_timers(self):
        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self._update_time)
        self.time_timer.start(1000)

        self.battery_timer = QTimer(self)
        self.battery_timer.timeout.connect(self._update_battery_status)
        self.battery_timer.start(60000)

    def _update_time(self):
        current_time = QTime.currentTime().toString("HH:mm")
        self.time_label.setText(current_time)
        self.time_updated.emit(current_time)

    def _update_battery_status(self):
        # Симуляция уровня заряда (в реальной системе — из API питания)
        try:
            from PyQt5.Qt import QSysInfo  # noqa: F401  (placeholder hook)
        except Exception:
            pass
        level = 0.82
        percent = int(round(level * 100))
        self.battery_icon.set_level(level)
        self.battery_label.setText(f"{percent}%")
        self._apply_ink()

    def _get_style_sheet(self):
        return ""  # всё рисуется напрямую, QSS не нужен

    def set_is_light_background(self, is_light: bool):
        """Светлый фон страницы -> тёмные чернила статус-бара, и наоборот."""
        if self.is_light_background != is_light:
            self.is_light_background = is_light
            self._apply_ink()

    def _apply_ink(self):
        color = "#000000" if self.is_light_background else "#FFFFFF"
        alpha = 200 if self.is_light_background else 235
        self._ink = QColor(color)
        self._ink.setAlpha(alpha)
        self.time_label.setStyleSheet(
            f"color: {color}; background: transparent; font-weight: 800; font-size: 13px;")
        self.battery_label.setStyleSheet(
            f"color: {color}; background: transparent; font-weight: 600; font-size: 11px;")
        for ic in (self.signal_icon, self.wifi_icon_label, self.battery_icon):
            ic.color = QColor(color)
            ic.update()
        self.update()
