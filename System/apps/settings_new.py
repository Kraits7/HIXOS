# apps/settings.py — редизайн v2 в стиле iOS Settings / OxygenOS:
#  • крупный заголовок-«проксимити», сгруппированные rounded-карточки;
#  • строки с иконками-кружками (цветные, как в iOS), chevron «›»;
#  • iOS-style switch вместо чекбоксов, сегмент-контролы вместо комбобоксов;
#  • push/pop подстраниц через PageSwipe, press-подсветка строк;
#  • поиск-поле сверху (фильтрует строки) — как в iOS 17.
import sys
import os
import json
import requests

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QApplication, QMessageBox,
    QStackedWidget, QLineEdit, QComboBox, QSpinBox, QGraphicsOpacityEffect
)
from PyQt5.QtGui import QFont, QPixmap, QColor, QPainter, QPen, QBrush
from PyQt5.QtCore import (Qt, pyqtSignal, pyqtProperty, QSize, QTimer,
                          QThread, QObject, QPropertyAnimation, QEasingCurve,
                          QRect, QPoint, QPointF)

from ui.navigation_bar import NAVIGATION_MODE_THREE_BUTTON, NAVIGATION_MODE_GESTURES

try:
    from ui.animation_engine import (
        Easing, Duration, PageSwipe, animate, _FrameDriver,
        spring_progress, fly_in_transform,
    )
except ImportError:
    from animation_engine import (
        Easing, Duration, PageSwipe, animate, _FrameDriver,
        spring_progress, fly_in_transform,
    )

GITHUB_UPDATE_JSON_URL = "https://raw.githubusercontent.com/username/repo/main/update.json"

# ---------- палитра ----------
BG          = "#0b0d12"
CARD_BG     = "#161a22"
ROW_HOVER   = "rgba(255,255,255,0.045)"
ACCENT      = "#0A84FF"
GREEN       = "#30D158"
TEXT_PRI    = "#FFFFFF"
TEXT_SEC    = "rgba(255,255,255,0.55)"
SEP         = "rgba(255,255,255,0.07)"


class UpdateChecker(QThread):
    update_check_finished = pyqtSignal(bool, str, str)

    def __init__(self, current_version: str):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            response = requests.get(GITHUB_UPDATE_JSON_URL, timeout=6)
            response.raise_for_status()
            update_info = response.json()
            latest_version_str = update_info.get("latest_version")
            if not latest_version_str:
                self.update_check_finished.emit(False, "", "Не удалось найти 'latest_version' в update.json.")
                return
            if latest_version_str > self.current_version:
                self.update_check_finished.emit(True, latest_version_str, "")
            else:
                self.update_check_finished.emit(False, "", "Обновлений не найдено.")
        except requests.exceptions.RequestException as e:
            self.update_check_finished.emit(False, "", f"Ошибка сети при проверке обновлений: {e}")
        except json.JSONDecodeError as e:
            self.update_check_finished.emit(False, "", f"Ошибка парсинга update.json: {e}")
        except Exception as e:
            self.update_check_finished.emit(False, "", f"Неизвестная ошибка при проверке обновлений: {e}")


class UpdateDownloader(QThread):
    download_progress = pyqtSignal(int)
    download_finished = pyqtSignal(bool, str)

    def __init__(self, new_version: str):
        super().__init__()
        self.new_version = new_version

    def run(self):
        try:
            for i in range(0, 101, 10):
                self.download_progress.emit(i)
                self.msleep(150)
            self.download_finished.emit(True, "")
        except Exception as e:
            self.download_finished.emit(False, str(e))


# ---------- виджеты ----------
class SwitchControl(QWidget):
    """iOS-style переключатель с spring-анимацией бегунка."""
    toggled = pyqtSignal(bool)

    def __init__(self, checked=False, parent=None):
        super().__init__(parent)
        self._on = checked
        self._knob = 1.0 if checked else 0.0   # анимируемое 0..1
        self.setFixedSize(51, 31)
        self.setCursor(Qt.PointingHandCursor)
        self._anim = None

    @pyqtProperty(float)
    def knob(self):
        return self._knob

    @knob.setter
    def knob(self, v):
        self._knob = v
        self.update()

    def is_checked(self):
        return self._on

    def set_checked(self, v: bool, emit=True):
        if self._on == v:
            return
        self._on = v
        if self._anim:
            self._anim.stop()
        self._anim = animate(self, b"knob", self._knob, 1.0 if v else 0.0,
                             Duration.SHORT, Easing.SPRING, self)
        self._anim.start()
        if emit:
            self.toggled.emit(v)

    def mousePressEvent(self, event):
        self.set_checked(not self._on)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRect(0, 0, 51, 31)
        # фон: серый -> зелёный по ходу анимации
        off_c, on_c = QColor("#39393d"), QColor(GREEN)
        col = QColor(off_c.red() + int((on_c.red() - off_c.red()) * self._knob),
                     off_c.green() + int((on_c.green() - off_c.green()) * self._knob),
                     off_c.blue() + int((on_c.blue() - off_c.blue()) * self._knob))
        p.setPen(Qt.NoPen)
        p.setBrush(col)
        p.drawRoundedRect(r, 15.5, 15.5)
        # бегунок
        kx = 2 + self._knob * (51 - 27 - 2)
        p.setBrush(QColor("white"))
        p.drawEllipse(QPointF(kx + 12.5, 15.5), 11.5, 11.5)
        p.end()


class SegmentControl(QWidget):
    """iOS-сегмент с плавно скользящей пилюлей выбранного сегмента."""
    selected_changed = pyqtSignal(int)

    def __init__(self, items, current=0, parent=None):
        super().__init__(parent)
        self.items = list(items)
        self._idx = current
        self._pill = float(current)  # анимируемая позиция пилюли
        self.setFixedHeight(36)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._anim = None

    @pyqtProperty(float)
    def pill(self):
        return self._pill

    @pill.setter
    def pill(self, v):
        self._pill = v
        self.update()

    def set_index(self, i, emit=True):
        if i == self._idx:
            return
        self._idx = i
        if self._anim:
            self._anim.stop()
        self._anim = animate(self, b"pill", self._pill, float(i),
                             Duration.SHORT, Easing.STANDARD, self)
        self._anim.start()
        if emit:
            self.selected_changed.emit(i)

    def current_index(self):
        return self._idx

    def mousePressEvent(self, event):
        n = max(1, len(self.items))
        w = self.width() / n
        i = min(n - 1, max(0, int(event.pos().x() / w)))
        self.set_index(i)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        rectf = QRect(0, 0, self.width(), 36).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QColor("rgba(255,255,255,0.06)"))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(rectf, 9, 9)
        n = max(1, len(self.items))
        seg_w = (self.width() - 4) / n
        px = 2 + self._pill * seg_w
        p.setBrush(QColor("#48484c"))
        p.drawRoundedRect(QRect(int(px), 2, int(seg_w), 32), 8, 8)
        # тексты
        p.setFont(QFont("Inter", 11, QFont.DemiBold))
        for i, txt in enumerate(self.items):
            r = QRect(int(2 + i * seg_w), 0, int(seg_w), 36)
            p.setPen(QColor(TEXT_PRI) if i == self._idx else QColor(TEXT_SEC))
            p.drawText(r, Qt.AlignCenter, txt)
        p.end()


class IconBadge(QLabel):
    """Цветной кружок с эмодзи-глифом слева от строки — как иконки iOS Settings."""
    def __init__(self, glyph: str, color: str, parent=None):
        super().__init__(glyph, parent)
        self.setFixedSize(30, 30)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            f"background-color: {color}; border-radius: 8px;"
            "font-size: 15px; color: white;")


class SettingsRow(QFrame):
    """Строка карточки настроек: badge + title (+ value/spacer + chevron или аксессуар).
    Плавная press/hover-подсветка через анимируемое свойство.
    Клик работает и по всей строке, и по кликабельному аксессуару (кнопке)."""
    row_clicked = pyqtSignal()

    def __init__(self, title: str, glyph: str = "", color: str = ACCENT,
                 accessory=None, value_text: str = "", selectable=True, parent=None):
        super().__init__(parent)
        self._title_key = title
        self._hl = 0.0
        self._selectable = selectable
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(52)
        self.setCursor(Qt.PointingHandCursor if selectable else Qt.ArrowCursor)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 14, 0)
        lay.setSpacing(12)

        if glyph:
            self.badge = IconBadge(glyph, color, self)
            lay.addWidget(self.badge)

        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(f"font-size: 16px; color: {TEXT_PRI}; background: transparent;")
        lay.addWidget(self.title_label)
        lay.addStretch(1)

        if value_text:
            self.value_label = QLabel(value_text)
            self.value_label.setStyleSheet(f"font-size: 15px; color: {TEXT_SEC}; background: transparent;")
            lay.addWidget(self.value_label)

        if accessory is not None:
            lay.addWidget(accessory)
            # клик по аксессуару-кнопке должен работать как клик по строке
            if isinstance(accessory, QPushButton):
                accessory.clicked.connect(self.row_clicked.emit)
        elif selectable:
            chev = QLabel("›")
            chev.setStyleSheet(f"font-size: 24px; color: rgba(255,255,255,0.28); background: transparent;")
            lay.addWidget(chev)

    @pyqtProperty(float)
    def hl(self):
        return self._hl

    @hl.setter
    def hl(self, v):
        self._hl = v
        self.update()

    def enterEvent(self, e):
        if self._selectable:
            animate(self, b"hl", self._hl, 0.35, Duration.SHORT, Easing.STANDARD, self).start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        animate(self, b"hl", self._hl, 0.0, Duration.SHORT, Easing.ACCELERATE, self).start()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if self._selectable:
            animate(self, b"hl", self._hl, 0.8, Duration.MICRO, Easing.STANDARD, self).start()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._selectable:
            animate(self, b"hl", self._hl, 0.35 if self.rect().contains(e.pos()) else 0.0,
                    Duration.SHORT, Easing.STANDARD, self).start()
            if self.rect().contains(e.pos()):
                self.row_clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._hl > 0.001:
            p.fillRect(self.rect(), QColor(255, 255, 255, int(self._hl * 26)))
        p.end()
        super().paintEvent(event)


class Card(QFrame):
    """Округлённая карточка-группа строк с тонкими разделителями (iOS grouped)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.inner = QVBoxLayout(self)
        self.inner.setContentsMargins(0, 0, 0, 0)
        self.inner.setSpacing(0)
        self.setStyleSheet(f"Card {{ background-color: {CARD_BG}; border-radius: 18px; }}")

    def add_row(self, row: QWidget, last: bool = False):
        if self.inner.count() > 0:
            sep = QFrame(self)
            sep.setFixedHeight(1)
            sep.setStyleSheet(f"background-color: {SEP}; margin-left: 56px;")
            self.inner.addWidget(sep)
        self.inner.addWidget(row)
        return row


class SubPageHeader(QWidget):
    """Шапка подстраницы: кнопка назад + заголовок."""
    back_pressed = pyqtSignal()

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 14, 0)
        self.back_btn = QPushButton("‹  Назад")
        self.back_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {ACCENT};"
            "font-size: 17px; font-weight: 600; padding: 8px; }"
            f"QPushButton:hover {{ color: #4da3ff; }}")
        self.back_btn.setCursor(Qt.PointingHandCursor)
        self.back_btn.clicked.connect(self.back_pressed.emit)
        lay.addWidget(self.back_btn)
        lay.addStretch(1)

    def retranslate(self, back_text: str):
        self.back_btn.setText(f"‹  {back_text}")


# ---------- подстраницы ----------
class BaseSettingsSubPage(QWidget):
    back_to_main_settings_requested = pyqtSignal()
    language_selected = pyqtSignal(str)
    navigation_mode_selected = pyqtSignal(str)

    def __init__(self, parent=None, settings_content_instance=None, title=""):
        super().__init__(parent)
        self.settings_content_instance = settings_content_instance
        self.v = QVBoxLayout(self)
        self.v.setContentsMargins(16, 8, 16, 20)
        self.v.setSpacing(14)
        self.header = SubPageHeader(title, self)
        self.header.back_pressed.connect(self.back_to_main_settings_requested.emit)
        self.v.addWidget(self.header)
        self.big_title = QLabel(title)
        self.big_title.setStyleSheet(
            f"font-size: 28px; font-weight: 800; color: {TEXT_PRI}; background: transparent;")
        self.v.addWidget(self.big_title)
        self.body = QVBoxLayout()
        self.body.setSpacing(14)
        self.v.addLayout(self.body)
        self.v.addStretch(1)


class LanguageSettingsPage(BaseSettingsSubPage):
    LANGS = ["Русский", "English", "Deutsch", "Français"]

    def __init__(self, parent=None, settings_content_instance=None, current_language="Русский"):
        super().__init__(parent, settings_content_instance,
                         settings_content_instance.tr("Language & Region"))
        card = Card(self)
        for i, lang in enumerate(self.LANGS):
            acc = QLabel("✓")
            acc.setStyleSheet(f"color: {ACCENT}; font-size: 18px; font-weight: bold; background: transparent;")
            row = SettingsRow(lang, glyph=self._flag(i), color="#5E5CE6",
                              accessory=acc, parent=card)
            acc.setVisible(lang == current_language)
            row.row_clicked.connect(lambda l=lang, a=acc: self._pick(l, a))
            card.add_row(row)
        self.body.addWidget(card)
        self._cards = card

    @staticmethod
    def _flag(i):
        return ["🇷🇺", "🇬🇧", "🇩🇪", "🇫🇷"][i] if 0 <= i < 4 else "🌐"

    def _pick(self, lang, acc_label):
        # снять галки со всех
        for item in self._cards.inner.children():
            pass
        for i in range(self._cards.inner.count()):
            w = self._cards.inner.itemAt(i).widget()
            if isinstance(w, SettingsRow):
                for j in range(w.layout().count()):
                    ww = w.layout().itemAt(j).widget()
                    if isinstance(ww, QLabel) and ww.text() == "✓":
                        ww.setVisible(False)
        acc_label.setVisible(True)
        self.language_selected.emit(lang)


class NavigationSettingsPage(BaseSettingsSubPage):
    MODES = [NAVIGATION_MODE_THREE_BUTTON, NAVIGATION_MODE_GESTURES]

    def __init__(self, parent=None, settings_content_instance=None,
                 initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON):
        super().__init__(parent, settings_content_instance,
                         settings_content_instance.tr("Navigation Mode"))
        loc = settings_content_instance.localized_texts.get(
            settings_content_instance._language, {})
        self._selected = initial_navigation_mode

        hint = QLabel(settings_content_instance.tr("Choose Navigation Mode"))
        hint.setStyleSheet(f"color: {TEXT_SEC}; font-size: 14px; background: transparent;")
        self.body.addWidget(hint)

        card = Card(self)
        # галка создаётся сразу и передаётся как accessory (как в LanguagePage)
        self.acc_buttons = QLabel("✓")
        self.acc_buttons.setStyleSheet(
            f"color: {ACCENT}; font-size: 18px; font-weight:bold; background: transparent;")
        self.card_buttons = SettingsRow(
            loc.get("Three Buttons", "Три кнопки"),
            glyph="▤", color="#FF9F0A", accessory=self.acc_buttons,
            selectable=False, parent=card)
        self.card_gestures = SettingsRow(
            loc.get("Gestures", "Жесты"),
            glyph="↔", color=GREEN,
            accessory=None, selectable=False, parent=card)
        # для жеста заводим свою галку отдельно (нужна ссылка для show/hide)
        self.acc_gestures = QLabel("✓")
        self.acc_gestures.setStyleSheet(
            f"color: {ACCENT}; font-size: 18px; font-weight:bold; background: transparent;")
        self.card_gestures.layout().insertWidget(
            self.card_gestures.layout().count() - 1, self.acc_gestures)
        # клики по всей строке
        self.card_buttons.row_clicked.connect(lambda: self._pick(0))
        self.card_gestures.row_clicked.connect(lambda: self._pick(1))
        card.add_row(self.card_buttons)
        card.add_row(self.card_gestures)
        self.body.addWidget(card)
        self._pick(MODES.index(initial_navigation_mode) if initial_navigation_mode in self.MODES else 0,
                   emit=False)

    def _pick(self, i, emit=True):
        self._selected = self.MODES[i]
        self.acc_buttons.setVisible(i == 0)
        self.acc_gestures.setVisible(i == 1)
        if emit:
            self.navigation_mode_selected.emit(self._selected)

    def update_localization(self, language: str):
        loc = self.settings_content_instance.localized_texts.get(language, {})
        self.header.retranslate(loc.get("Back", "Назад"))
        self.big_title.setText(loc.get("Navigation Mode", "Режим Навигации"))
        self.card_buttons.title_label.setText(loc.get("Three Buttons", "Три кнопки"))
        self.card_gestures.title_label.setText(loc.get("Gestures", "Жесты"))


class LauncherSettingsPage(BaseSettingsSubPage):
    icon_size_changed = pyqtSignal(int)
    grid_columns_changed = pyqtSignal(int)
    app_names_visibility_changed = pyqtSignal(bool)

    def __init__(self, parent=None, settings_content_instance=None):
        super().__init__(parent, settings_content_instance,
                         settings_content_instance.tr("Launcher Settings"))
        self._icon_size = 70
        self._columns = 4
        self._show_names = True

        card = Card(self)

        # размер иконок — сегмент S/M/L
        loc = settings_content_instance.localized_texts.get(settings_content_instance._language, {})
        self.size_row = SettingsRow(loc.get("Icon Size", "Размер иконок"),
                                    glyph="◉", color="#FF375F", selectable=False, parent=card)
        self.size_seg = SegmentControl(["S", "M", "L"], current=1)
        self.size_seg.selected_changed.connect(self._on_size_seg)
        self.size_row.layout().insertWidget(self.size_row.layout().count() - 1, self.size_seg)
        card.add_row(self.size_row)

        # столбцы
        self.cols_row = SettingsRow(loc.get("Grid Columns", "Столбцов в сетке"),
                                    glyph="▦", color=ACCENT, selectable=False, parent=card)
        self.cols_seg = SegmentControl(["3", "4", "5"], current=1)
        self.cols_seg.selected_changed.connect(self._on_cols_seg)
        self.cols_row.layout().insertWidget(self.cols_row.layout().count() - 1, self.cols_seg)
        card.add_row(self.cols_row)

        # показ названий
        self.names_row = SettingsRow(loc.get("Show App Names", "Показывать названия"),
                                     glyph="Aa", color=GREEN, selectable=False, parent=card)
        self.names_switch = SwitchControl(checked=True)
        self.names_switch.toggled.connect(self._on_names_switch)
        self.names_row.layout().insertWidget(self.names_row.layout().count() - 1, self.names_switch)
        card.add_row(self.names_row)

        self.body.addWidget(card)

    def _on_size_seg(self, i):
        self._icon_size = [56, 70, 88][i]
        self.icon_size_changed.emit(self._icon_size)

    def _on_cols_seg(self, i):
        self._columns = 3 + i
        self.grid_columns_changed.emit(self._columns)

    def _on_names_switch(self, checked: bool):
        self._show_names = checked
        self.app_names_visibility_changed.emit(checked)

    def update_localization(self, language: str):
        loc = self.settings_content_instance.localized_texts.get(language, {})
        self.header.retranslate(loc.get("Back", "Назад"))
        self.big_title.setText(loc.get("Launcher Settings", "Настройки Лаунчера"))
        self.size_row.title_label.setText(loc.get("Icon Size", "Размер иконок"))
        self.cols_row.title_label.setText(loc.get("Grid Columns", "Столбцов в сетке"))
        self.names_row.title_label.setText(loc.get("Show App Names", "Показывать названия"))


# ---------- главный экран ----------
class SettingsContent(QFrame):
    go_back_to_launcher_requested = pyqtSignal()
    language_changed = pyqtSignal(str)
    navigation_mode_changed = pyqtSignal(str)
    system_restart_requested = pyqtSignal(str)
    launcher_icon_size_changed = pyqtSignal(int)
    launcher_grid_columns_changed = pyqtSignal(int)
    launcher_app_names_visibility_changed = pyqtSignal(bool)

    def __init__(self, parent=None, current_language="Русский", system_version="1.0.0",
                 initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON, user_data_manager=None):
        super().__init__(parent)
        self.main_window = parent
        self._language = current_language
        self._system_version = system_version
        self._current_navigation_mode = initial_navigation_mode
        self.user_data_manager = user_data_manager
        self.current_new_version = None
        self.update_checker_thread = None
        self.update_downloader_thread = None

        self.setStyleSheet(f"background-color: {BG};")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.localized_texts = {
            "Русский": {
                "Settings": "Настройки",
                "General": "Основные",
                "About": "О системе",
                "Language & Region": "Язык и регион",
                "Navigation Mode": "Навигация",
                "Launcher Settings": "Рабочий стол",
                "System Version": "Версия системы",
                "Check for Updates": "Проверить обновления",
                "Back to Launcher": "На рабочий стол",
                "Choose Language": "Выберите язык системы.",
                "Choose Navigation Mode": "Как управлять системой: кнопки или жесты.",
                "Three Buttons": "Три кнопки",
                "Gestures": "Жесты",
                "Icon Size": "Размер иконок",
                "Grid Columns": "Столбцов в сетке",
                "Show App Names": "Подписи под иконками",
                "Search": "Поиск",
                "Storage": "Хранилище",
                "Battery": "Батарея",
                "Wallpaper": "Обои",
                "Coming soon": "скоро",
                "UpdatingTitle": "Обновления",
                "CheckingUpdates": "Проверяем обновления…",
                "NoUpdates": "Обновлений нет — система актуальна.",
                "UpdatesAvailable": "Доступна версия {new_version}. Обновить?",
                "UpdateFailed": "Не удалось проверить обновления: {error}",
                "UpdatingSystem": "Обновление системы…",
                "UpdateSuccessful": "Обновлено до {new_version}! Перезапустите HIX OS.",
                "UpdateFailedGeneric": "Ошибка обновления. Попробуйте снова.",
                "ConfirmUpdate": "Подтверждение",
                "UpdateCancelled": "Обновление отменено.",
                "Back": "Назад",
            },
            "English": {
                "Settings": "Settings",
                "General": "General",
                "About": "About",
                "Language & Region": "Language & Region",
                "Navigation Mode": "Navigation",
                "Launcher Settings": "Home Screen",
                "System Version": "System Version",
                "Check for Updates": "Check for Updates",
                "Back to Launcher": "Back to Home",
                "Choose Language": "Choose the system language.",
                "Choose Navigation Mode": "Buttons or gestures — how you navigate.",
                "Three Buttons": "Three Buttons",
                "Gestures": "Gestures",
                "Icon Size": "Icon Size",
                "Grid Columns": "Grid Columns",
                "Show App Names": "Icon Labels",
                "Search": "Search",
                "Storage": "Storage",
                "Battery": "Battery",
                "Wallpaper": "Wallpaper",
                "Coming soon": "soon",
                "UpdatingTitle": "Updates",
                "CheckingUpdates": "Checking for updates…",
                "NoUpdates": "Your software is up to date.",
                "UpdatesAvailable": "Version {new_version} is available. Update now?",
                "UpdateFailed": "Couldn't check for updates: {error}",
                "UpdatingSystem": "Updating system…",
                "UpdateSuccessful": "Updated to {new_version}! Restart HIX OS.",
                "UpdateFailedGeneric": "Update failed. Try again.",
                "ConfirmUpdate": "Confirm",
                "UpdateCancelled": "Update cancelled.",
                "Back": "Back",
            },
        }

        self.stacked_pages = QStackedWidget(self)
        mv = QVBoxLayout(self)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.addWidget(self.stacked_pages)

        # --- главная страница ---
        self.main_settings_page = QWidget()
        mlay = QVBoxLayout(self.main_settings_page)
        mlay.setContentsMargins(16, 10, 16, 16)
        mlay.setSpacing(14)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(f"🔍  {self.tr('Search')}")
        self.search_input.setFixedHeight(40)
        self.search_input.setStyleSheet(
            f"QLineEdit {{ background: {CARD_BG}; border: none; border-radius: 12px;"
            "padding: 8px 14px; color: white; font-size: 15px; }")
        self.search_input.textChanged.connect(self._filter_rows)
        mlay.addWidget(self.search_input)

        self.big_title = QLabel(self.tr("Settings"))
        self.big_title.setStyleSheet(
            f"font-size: 32px; font-weight: 800; color: {TEXT_PRI}; background: transparent;")
        mlay.addWidget(self.big_title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setContentsMargins(0, 0, 6, 0)
        self.scroll_layout.setSpacing(18)
        scroll.setWidget(self.scroll_content)
        mlay.addWidget(scroll, 1)

        self.all_rows = []  # (row_widget, search_keys)

        # группа «Основные»
        g1 = self._group_title(self.tr("General"))
        card1 = Card()
        r_lang = SettingsRow(self.tr("Language & Region"), glyph="🌐", color="#5E5CE6", parent=card1)
        r_lang.row_clicked.connect(lambda: self._push_subpage(self.language_page))
        card1.add_row(r_lang)
        r_nav = SettingsRow(self.tr("Navigation Mode"), glyph="▤", color="#FF9F0A", parent=card1)
        r_nav.row_clicked.connect(lambda: self._push_subpage(self.navigation_page))
        card1.add_row(r_nav)
        r_ls = SettingsRow(self.tr("Launcher Settings"), glyph="⌂", color=ACCENT, parent=card1)
        r_ls.row_clicked.connect(lambda: self._push_subpage(self.launcher_page))
        card1.add_row(r_ls)
        r_wall = SettingsRow(self.tr("Wallpaper"), glyph="🖼", color="#32ADE6",
                             value_text=self.tr("Coming soon"), selectable=False, parent=card1)
        card1.add_row(r_wall)
        self.scroll_layout.addWidget(g1)
        self.scroll_layout.addWidget(card1)
        self.all_rows += [(r_lang, "language язык region регион"),
                          (r_nav, "navigation навигация buttons жесты gestures"),
                          (r_ls, "launcher лаунчер desktop рабочий стол icon иконк"),
                          (r_wall, "wallpaper обои")]

        # группа «О системе»
        g2 = self._group_title(self.tr("About"))
        card2 = Card()
        self.system_version_label_value = QLabel(self._system_version)
        self.system_version_label_value.setStyleSheet(
            f"font-size: 15px; color: {TEXT_SEC}; background: transparent;")
        r_ver = SettingsRow(self.tr("System Version"), glyph="ⓘ", color="#8E8E93",
                            accessory=self.system_version_label_value,
                            selectable=False, parent=card2)
        card2.add_row(r_ver)
        self.check_for_updates_button = QPushButton(self.tr("Check for Updates"))
        self.check_for_updates_button.setStyleSheet(
            f"QPushButton {{ background: transparent; border: none; color: {ACCENT};"
            "font-size: 16px; }"
            "QPushButton:disabled { color: rgba(255,255,255,0.3); }")
        self.check_for_updates_button.setCursor(Qt.PointingHandCursor)
        self.check_for_updates_button.clicked.connect(self._check_for_updates)
        r_upd = SettingsRow(self.tr("Check for Updates"), glyph="⟳", color=GREEN,
                            accessory=self.check_for_updates_button,
                            selectable=False, parent=card2)
        # для этой строки клик = тоже проверка
        r_upd.row_clicked.connect(self._check_for_updates)
        card2.add_row(r_upd)
        self.scroll_layout.addWidget(g2)
        self.scroll_layout.addWidget(card2)
        self.all_rows += [(r_ver, "version версия"),
                          (r_upd, "update обновление check проверка")]

        self.scroll_layout.addStretch(1)

        self.stacked_pages.addWidget(self.main_settings_page)

        # --- подстраницы ---
        self.language_page = LanguageSettingsPage(self, settings_content_instance=self,
                                                  current_language=self._language)
        self.navigation_page = NavigationSettingsPage(self, settings_content_instance=self,
                                                      initial_navigation_mode=self._current_navigation_mode)
        self.launcher_page = LauncherSettingsPage(self, settings_content_instance=self)
        for pg in (self.language_page, self.navigation_page, self.launcher_page):
            self.stacked_pages.addWidget(pg)

        self._page_swipe = PageSwipe(self.stacked_pages)

        self.language_page.back_to_main_settings_requested.connect(self._pop_to_main)
        self.navigation_page.back_to_main_settings_requested.connect(self._pop_to_main)
        self.launcher_page.back_to_main_settings_requested.connect(self._pop_to_main)
        self.language_page.language_selected.connect(self._on_language_selected_from_subpage)
        self.navigation_page.navigation_mode_selected.connect(self._on_navigation_mode_selected_from_subpage)
        self.launcher_page.icon_size_changed.connect(self.launcher_icon_size_changed.emit)
        self.launcher_page.grid_columns_changed.connect(self.launcher_grid_columns_changed.emit)
        self.launcher_page.app_names_visibility_changed.connect(self.launcher_app_names_visibility_changed.emit)

        self.stacked_pages.setCurrentWidget(self.main_settings_page)

    # ---------- helpers ----------
    def tr(self, key):
        return self.localized_texts.get(self._language, {}).get(key, key)

    def _group_title(self, text):
        lbl = QLabel(text.upper())
        lbl.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {TEXT_SEC};"
            "letter-spacing: 0.6px; background: transparent; margin-left: 4px;")
        return lbl

    def _filter_rows(self, query: str):
        q = query.strip().lower()
        # прячем строки карточек по ключам
        for row, keys in self.all_rows:
            visible = (not q) or q in keys or q in row.title_label.text().lower()
            row.setVisible(visible)
        # разделители и заголовки групп: грубо — если все строки карточки скрыты, скрываем карточку
        for i in range(self.scroll_layout.count()):
            w = self.scroll_layout.itemAt(i).widget()
            if isinstance(w, Card):
                any_vis = False
                for j in range(w.inner.count()):
                    ww = w.inner.itemAt(j).widget()
                    if isinstance(ww, SettingsRow) and ww.isVisible():
                        any_vis = True
                w.setVisible(any_vis or not q)
            elif isinstance(w, QLabel) and not q:
                w.setVisible(True)

    # ---------- навигация ----------
    def _push_subpage(self, page):
        if self.stacked_pages.currentWidget() is page:
            return
        self._page_swipe.transition_to(page, direction="forward",
                                       duration=Duration.SHORT + 80)

    def _pop_to_main(self):
        if self.stacked_pages.currentWidget() is self.main_settings_page:
            return
        self._page_swipe.transition_to(self.main_settings_page, direction="backward",
                                       duration=Duration.SHORT + 80)

    def _show_main_settings_page(self):
        self._pop_to_main()

    # ---------- события выбора ----------
    def _on_language_selected_from_subpage(self, new_language: str):
        if new_language != self._language:
            self._language = new_language
            self._update_localization()
            self.language_changed.emit(new_language)

    def _on_navigation_mode_selected_from_subpage(self, new_mode: str):
        if new_mode != self._current_navigation_mode:
            self._current_navigation_mode = new_mode
            self.navigation_mode_changed.emit(new_mode)

    # ---------- обновления ----------
    def _check_for_updates(self):
        self.check_for_updates_button.setEnabled(False)
        self._show_message_box(self.tr("UpdatingTitle"), self.tr("CheckingUpdates"),
                               QMessageBox.Information, modal=True)
        self.update_checker_thread = UpdateChecker(self._system_version)
        self.update_checker_thread.update_check_finished.connect(self._on_update_check_finished)
        self.update_checker_thread.start()

    def _on_update_check_finished(self, update_available: bool, new_version: str, error_message: str):
        self.check_for_updates_button.setEnabled(True)
        if update_available:
            self.current_new_version = new_version
            reply = self._show_message_box(
                self.tr("ConfirmUpdate"),
                self.tr("UpdatesAvailable").format(new_version=new_version),
                QMessageBox.Question, standard_buttons=QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                self._initiate_update_download()
            else:
                self._show_message_box(self.tr("UpdatingTitle"), self.tr("UpdateCancelled"),
                                       QMessageBox.Information)
        else:
            if error_message:
                self._show_message_box(self.tr("UpdatingTitle"),
                                       self.tr("UpdateFailed").format(error=error_message),
                                       QMessageBox.Critical)
            else:
                self._show_message_box(self.tr("UpdatingTitle"), self.tr("NoUpdates"),
                                       QMessageBox.Information)

    def _initiate_update_download(self):
        self.check_for_updates_button.setEnabled(False)
        self._show_message_box(self.tr("UpdatingTitle"), self.tr("UpdatingSystem"),
                               QMessageBox.Information, modal=True)
        self.update_downloader_thread = UpdateDownloader(self.current_new_version)
        self.update_downloader_thread.download_finished.connect(self._on_update_download_finished)
        self.update_downloader_thread.start()

    def _on_update_download_finished(self, success: bool, error_message: str):
        self.check_for_updates_button.setEnabled(True)
        if success:
            self._system_version = self.current_new_version
            self.system_version_label_value.setText(self._system_version)
            self.system_restart_requested.emit(self._system_version)
            self._show_message_box(self.tr("UpdatingTitle"),
                                   self.tr("UpdateSuccessful").format(new_version=self._system_version),
                                   QMessageBox.Information)
        else:
            self._show_message_box(self.tr("UpdatingTitle"),
                                   self.tr("UpdateFailedGeneric") + f" ({error_message})",
                                   QMessageBox.Critical)

    def _show_message_box(self, title, text, icon, standard_buttons=QMessageBox.Ok,
                          modal=False, timeout=0):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setText(text)
        box.setIcon(icon)
        box.setStandardButtons(standard_buttons)
        if modal:
            box.setWindowModality(Qt.ApplicationModal)
        if timeout > 0:
            QTimer.singleShot(timeout, box.close)
        return box.exec_()

    # ---------- API совместимости ----------
    def set_initial_preferences(self, language: str, navigation_mode: str, system_version: str):
        self._language = language
        self._current_navigation_mode = navigation_mode
        self._system_version = system_version
        self.system_version_label_value.setText(system_version)
        self._update_localization()

    def _update_localization(self):
        self.big_title.setText(self.tr("Settings"))
        self.search_input.setPlaceholderText(f"🔍  {self.tr('Search')}")
        # группы
        labels = [self.scroll_layout.itemAt(i).widget()
                  for i in range(self.scroll_layout.count())]
        for lbl in labels:
            if isinstance(lbl, QLabel) and lbl.property("role") != "value":
                t = lbl.text()
                if t.upper() == self.localized_texts["Русский"]["General"].upper() or \
                   t.upper() == self.localized_texts["English"]["General"].upper():
                    lbl.setText(self.tr("General").upper())
                elif t.upper() == self.localized_texts["Русский"]["About"].upper() or \
                     t.upper() == self.localized_texts["English"]["About"].upper():
                    lbl.setText(self.tr("About").upper())
        # строки главной страницы
        for row, _keys in self.all_rows:
            base = {self.localized_texts["Русский"]["Language & Region"]: "Language & Region",
                    self.localized_texts["English"]["Language & Region"]: "Language & Region",
                    self.localized_texts["Русский"]["Navigation Mode"]: "Navigation Mode",
                    self.localized_texts["English"]["Navigation Mode"]: "Navigation Mode",
                    self.localized_texts["Русский"]["Launcher Settings"]: "Launcher Settings",
                    self.localized_texts["English"]["Launcher Settings"]: "Launcher Settings",
                    self.localized_texts["Русский"]["System Version"]: "System Version",
                    self.localized_texts["English"]["System Version"]: "System Version",
                    self.localized_texts["Русский"]["Check for Updates"]: "Check for Updates",
                    self.localized_texts["English"]["Check for Updates"]: "Check for Updates",
                    self.localized_texts["Русский"]["Wallpaper"]: "Wallpaper",
                    self.localized_texts["English"]["Wallpaper"]: "Wallpaper"}.get(row.title_label.text())
            if base:
                row.title_label.setText(self.tr(base))
        self.check_for_updates_button.setText(self.tr("Check for Updates"))
        # подстраницы
        self.language_page.update_localization(self._language)
        self.navigation_page.update_localization(self._language)
        self.launcher_page.update_localization(self._language)
        self.update()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = QWidget()
    win.setGeometry(100, 100, 480, 900)
    sc = SettingsContent(current_language="Русский", system_version="1.0.0")
    lay = QVBoxLayout(win)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.addWidget(sc)
    win.show()
    sys.exit(app.exec_())
