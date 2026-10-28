# apps/oobe.py — v2. Новый OOBE в стиле iOS 17 / OxygenOS setup:
#  • крупная «proximity»-типографика, много воздуха, тонкие разделители;
#  • выбор — не радиокнопки и комбобоксы, а карточки-плитки с press-feedback;
#  • push/pop переходы страниц через движок анимаций системы (PageSwipe);
#  • прогресс-бар из точек, активная точка плавно расширяется (spring);
#  • финальная страница — большой чекмар с spring-pop + мягкий fade текста.
import sys
import os

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QStackedWidget, QLineEdit, QApplication, QMessageBox, QTextBrowser,
    QFrame, QSizePolicy, QGraphicsOpacityEffect, QScrollArea
)
from PyQt5.QtCore import (
    Qt, pyqtSignal, pyqtProperty, QObject, QTimer, QRect, QPoint, QSize,
    QPropertyAnimation, QEasingCurve
)
from PyQt5.QtGui import QFont, QColor, QPainter, QPen, QBrush, QPixmap

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
BG = "#0b0d12"              # почти чёрный с синим подтоном (iOS setup)
CARD = "rgba(255,255,255,0.06)"
CARD_SELECTED = "rgba(10,132,255,0.18)"
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "rgba(255,255,255,0.55)"


def global_qss():
    return f"""
    QWidget {{
        background-color: {BG};
        color: {TEXT_PRIMARY};
        font-family: "Inter", "SF Pro Display", "Segoe UI", "Roboto", sans-serif;
    }}
    QLabel#pageTitle {{
        font-size: 32px;
        font-weight: 800;
        letter-spacing: -0.5px;
        color: {TEXT_PRIMARY};
    }}
    QLabel#pageSubtitle {{
        font-size: 16px;
        color: {TEXT_SECONDARY};
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
        background-color: {ACCENT};
        color: white;
        border: none;
        border-radius: 16px;
        padding: 16px 20px;
        font-size: 17px;
        font-weight: 700;
    }}
    QPushButton#primaryButton:hover {{
        background-color: #0a74e0;
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

    def set_selected(self, sel: bool):
        if self._selected == sel:
            return
        self._selected = sel
        self._update_check_style()
        anim = animate(self, b"hl", self._hl, 1.0 if sel else 0.0,
                       Duration.SHORT, Easing.STANDARD, self)
        anim.start()

    def is_selected(self):
        return self._selected

    def mousePressEvent(self, event):
        a = animate(self, b"hl", self._hl, max(0.0, self._hl * 0.55) + 0.12,
                    Duration.MICRO, Easing.STANDARD, self)
        a.start()
        self.clicked_tile.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect().adjusted(1, 1, -1, -1)
        base = QColor(CARD_SELECTED) if self._selected else QColor(CARD)
        # press/hover добавляет яркости
        glow = int(self._hl * 26)
        col = QColor(base)
        col.setRed(min(255, col.red() + glow))
        col.setGreen(min(255, col.green() + glow))
        col.setBlue(min(255, col.blue() + glow))
        p.setPen(QPen(QColor(ACCENT) if self._selected else QColor("rgba(255,255,255,0.08)"),
                      1.6 if self._selected else 1.0))
        p.setBrush(QBrush(col))
        p.drawRoundedRect(r, 16, 16)
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


class BaseOOBEPage(QWidget):
    """Общий каркас страницы: отступы, заголовок/подзаголовок, место под контент
    и нижняя кнопка действия. Появление контента — spring-прилёт (iOS style)."""

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
        """Spring-прилёт содержимого страницы снизу (как экраны iOS setup)."""
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

        for idx, w in enumerate(targets):
            eff = QGraphicsOpacityEffect(w)
            w.setGraphicsEffect(eff)
            base_y = w.y()
            off = 0.06 + idx * 0.05

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
            drv = _FrameDriver(420, QEasingCurve.Linear, frame_fn, done_fn, self)
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
    """Управляет страницами OOBE: стек + PageSwipe push/pop + точки прогресса."""

    oobe_finished = pyqtSignal(str, str, str)

    def __init__(self, parent=None, current_language="Русский",
                 initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON,
                 user_data_manager=None):
        super().__init__(parent)
        self.main_window = parent
        self._current_language = current_language
        self._current_navigation_mode = initial_navigation_mode
        self.user_data_manager = user_data_manager
        self._username = ""

        self.setStyleSheet(global_qss())

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        # --- шапка: точки прогресса + ссылка «Назад» скрыта, только точки ---
        self.top_bar = QHBoxLayout()
        self.top_bar.setContentsMargins(28, 22, 28, 6)
        self.top_bar.addStretch(1)
        self.progress_dots = []
        num_pages = 5
        for i in range(num_pages):
            dot = QFrame(self)
            dot.setFixedSize(8, 8)
            dot.setStyleSheet("background-color: rgba(255,255,255,0.18); border-radius: 4px;")
            self.progress_dots.append(dot)
            self.top_bar.addWidget(dot)
            if i != num_pages - 1:
                self.top_bar.addSpacing(8)
        self.top_bar.addStretch(1)
        v.addLayout(self.top_bar)

        self.stacked_pages = QStackedWidget(self)
        v.addWidget(self.stacked_pages, 1)

        self.welcome_page = WelcomeLanguagePage(oobe=self, current_language=current_language)
        self.eula_page = EULAPage(oobe=self)
        self.user_setup_page = UserSetupPage(oobe=self)
        self.navigation_choice_page = NavigationChoicePage(
            oobe=self, initial_navigation_mode=initial_navigation_mode)
        self.final_page = FinalOOBEPage(oobe=self)

        for pg in (self.welcome_page, self.eula_page, self.user_setup_page,
                   self.navigation_choice_page, self.final_page):
            self.stacked_pages.addWidget(pg)

        self.welcome_page.next_page_requested.connect(self._next_page)
        self.eula_page.next_page_requested.connect(self._next_page)
        self.eula_page.prev_page_requested.connect(self._prev_page)
        self.user_setup_page.next_page_requested.connect(self._next_page)
        self.user_setup_page.prev_page_requested.connect(self._prev_page)
        self.navigation_choice_page.next_page_requested.connect(self._next_page)
        self.navigation_choice_page.prev_page_requested.connect(self._prev_page)
        self.final_page.finish_oobe_requested.connect(self._handle_oobe_finish)

        self._swipe = PageSwipe(self.stacked_pages)
        self.stacked_pages.setCurrentIndex(0)
        self._animating = False
        self._update_progress_indicator(0)
        QTimer.singleShot(120, self.welcome_page.reveal_widgets)

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
        for i, dot in enumerate(self.progress_dots):
            if i == index:
                dot.setFixedSize(22, 8)
                dot.setStyleSheet(f"background-color: {ACCENT}; border-radius: 4px;")
            elif i < index:
                dot.setFixedSize(8, 8)
                dot.setStyleSheet("background-color: rgba(255,255,255,0.45); border-radius: 4px;")
            else:
                dot.setFixedSize(8, 8)
                dot.setStyleSheet("background-color: rgba(255,255,255,0.18); border-radius: 4px;")

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
