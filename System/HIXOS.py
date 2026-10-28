# Starter.py
import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QDesktopWidget,
    QMainWindow, QPushButton, QLineEdit, QHBoxLayout,
    QComboBox, QStackedWidget, QFrame, QSizePolicy, QSpacerItem,
    QGraphicsOpacityEffect, QRadioButton, QMessageBox
)
from PyQt5.QtGui import QPixmap, QTransform, QColor, QPainter, QPen, QBrush
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal, QTime, QPropertyAnimation, QEasingCurve, QRect, QRectF, QPoint, QParallelAnimationGroup, QEvent, QDate

# --- Системный движок анимаций (OxygenOS / iOS style) ---
try:
    from ui.animation_engine import Easing, Duration, PageSwipe, MorphOverlay, _FrameDriver
except ImportError:
    from animation_engine import Easing, Duration, PageSwipe, MorphOverlay, _FrameDriver

import os
import json # Import for JSON parsing
import uuid # For UUID generation

# Firebase imports (commented out to disable Firebase)
# from firebase_admin import credentials, initialize_app, firestore
# import firebase_admin 

# Imports of your applications and UI elements
from apps.launcher import LauncherContent
from ui.statusbar import StatusBarWidget
from apps.settings import SettingsContent
from apps.oobe import OOBEContent
from apps.lockscreen import LockScreenContent 
from apps.calculator import CalculatorContent
from apps.browser import BrowserContent # Import BrowserContent
from apps.camera import CameraContent # Import CameraContent


# IMPORT NavigationBarWidget
from ui.navigation_bar import NavigationBarWidget, NAVIGATION_MODE_THREE_BUTTON, NAVIGATION_MODE_GESTURES

# Экран недавних приложений (iOS App Switcher)
try:
    from ui.recents import RecentsOverlay
except ImportError:
    from recents import RecentsOverlay


# --- GLOBAL SETTINGS ---
APP_WIDTH = 519
APP_HEIGHT = 950
STATUS_BAR_HEIGHT = 30
NAVIGATION_BAR_HEIGHT = 40 # Height of the navigation bar (as in NavigationBarWidget)
SYSTEM_VERSION = "1.0.0" # Moved here to be global

# --- Firestore Global Variables (Provided by Canvas Environment) ---
# IMPORTANT: Do NOT change these variables. They are set by the environment.
app_id = "default-app-id"
firebase_config = "{}"
initial_auth_token = ""

# try:
#     if '__app_id' in globals():
#         app_id = __app_id
#     if '__firebase_config' in globals():
#         firebase_config = __firebase_config
#     if '__initial_auth_token' in globals():
#         initial_auth_token = __initial_auth_token
# except NameError:
#     print("Canvas environment variables not found. Using defaults for local testing.")

# --- User Data Manager Class (Modified to be a DummyDataManager) ---
# Original UserDataManager commented out
# class UserDataManager:
#     def __init__(self, db_client, app_id_val, user_id=None): 
#         self.db = db_client
#         self.app_id = app_id_val
#         self._user_id = user_id if user_id and user_id != "initializing_user" else None 
#         print(f"UserDataManager initialized with app_id: {self.app_id}, initial user_id: {self._user_id}")

#     @property
#     def user_id(self):
#         return self._user_id

#     @user_id.setter
#     def user_id(self, new_id):
#         if not new_id:
#             print("WARNING: Attempted to set user_id to None or empty. User ID must be a non-empty string.")
#             return
#         if self._user_id != new_id:
#             old_id = self._user_id
#             self._user_id = new_id
#             print(f"UserDataManager user_id updated from {old_id} to: {self._user_id}")

#     def get_user_doc_ref(self):
#         if not self.user_id:
#             raise ValueError("Cannot get user document reference: user_id is not set.")
#         return self.db.collection('artifacts').document(self.app_id).collection('users').document(self.user_id)

#     def load_user_data(self):
#         if not self.user_id:
#             print("Cannot load user data: user_id is not set. Returning empty data.")
#             return {}
#         print(f"Attempting to load data for user: {self.user_id}")
#         try:
#             doc_ref = self.get_user_doc_ref()
#             doc = doc_ref.get()
#             if doc.exists:
#                 data = doc.to_dict()
#                 print(f"Loaded user data: {data}")
#                 return data
#             else:
#                 print(f"No data found for user: {self.user_id}")
#                 return {}
#         except Exception as e:
#             print(f"Error loading user data for {self.user_id}: {e}")
#             return {}

#     def save_user_data(self, data):
#         if not self.user_id:
#             print("Cannot save user data: user_id is not set. Data not saved.")
#             return
#         print(f"Attempting to save data for user: {self.user_id} - {data}")
#         try:
#             doc_ref = self.get_user_doc_ref()
#             doc_ref.set(data)
#             print(f"User data saved successfully for {self.user_id}.")
#         except Exception as e:
#             print(f"Error saving user data for {self.user_id}: {e}")

# --- Dummy User Data Manager Class (always used now) ---
class DummyDataManager:
    def load_user_data(self): 
        print("DummyDataManager: Loading dummy data (no actual save/load).")
        # Return default values, as nothing is saved
        return {
            "username": "Пользователь", 
            "language": "Русский", 
            "navigation_mode": NAVIGATION_MODE_THREE_BUTTON, 
            "system_version": SYSTEM_VERSION,
            # Добавлены начальные настройки лаунчера для загрузки
            "launcher_icon_size": 70,
            "launcher_grid_columns": 4,
            "launcher_show_app_names": True
        }
    def save_user_data(self, data): 
        print(f"DummyDataManager: Saving dummy data (no actual save): {data}")
    @property
    def user_id(self): return "dummy_user_id"
    @user_id.setter
    def user_id(self, new_id): 
        print(f"DummyDataManager: User ID set to {new_id} (no actual save).")


# --- Content Classes ---

# Class for the boot screen
class BootScreenContent(QFrame):
    """Boot-экран в стиле iOS 16: чёрный фон, логотип по центру с плавным
    fade-in и тонкий кольцевой индикатор загрузки вокруг него.

    Финальный переход к OOBE («добро пожаловать»):
      1) прогресс дотягивается до 100%;
      2) логотип плавно исчезает (fade + лёгкое уменьшение);
      3) полоска загрузки «закручивается» — вытянутая капсула morph'ится
         в окружность и продолжает вращаться;
      4) появляется надпись «Добро пожаловать» (spring fade-up);
      5) оверлей затемняет экран и передаёт управление OOBE — кнопки
         настройки появляются уже там со своей анимацией."""

    PHASE_IDLE = 0
    PHASE_LOGO_OUT = 1
    PHASE_SPIN = 2
    PHASE_WELCOME = 3
    PHASE_HANDOFF = 4

    def __init__(self, parent=None, image_path='Boot.png'): 
        super().__init__(parent)
        self.main_window = parent
        self.image_path = image_path
        self.boot_timer = QTimer(self) 
        self._progress_value = 0.0
        self._phase = self.PHASE_IDLE
        self._spin_angle = 0.0
        self.init_ui()

    def _find_image(self):
        candidates = [
            self.image_path,
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'boot.png'),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Boot.png'),
            'boot.png', 'Boot.png',
        ]
        for c in candidates:
            if c and os.path.exists(c):
                return c
        return None

    def init_ui(self):
        self.setStyleSheet("background-color: #000000;")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addStretch(1)
        self.layout.addWidget(self.image_label, 3)
        self.layout.addStretch(2)

        img_path = self._find_image()
        if img_path:
            self._pixmap = QPixmap(img_path)
        else:
            self._pixmap = QPixmap()
        if not self._pixmap.isNull():
            self.image_label.setPixmap(self._pixmap.scaled(
                220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.image_label.setText("HIX OS")
            self.image_label.setStyleSheet("color: white; font-size: 34px; font-weight: 700;")

        # Тонкий прогресс-бар в стиле iOS boot
        self.progress_track = QFrame(self)
        self.progress_track.setFixedHeight(3)
        self.progress_track.setStyleSheet("background-color: rgba(255,255,255,0.12); border-radius: 1px;")
        self.progress_fill = QFrame(self.progress_track)
        self.progress_fill.setGeometry(0, 0, 0, 3)
        self.progress_fill.setStyleSheet("background-color: #FFFFFF; border-radius: 1px;")
        bottom = QVBoxLayout()
        bottom.setContentsMargins(90, 0, 90, 60)
        bottom.addWidget(self.progress_track)
        self.layout.addLayout(bottom)

        # --- Оверлей перехода к OOBE (рисуется вручную в paintEvent) ---
        self.welcome_label = QLabel("Добро пожаловать", self)
        self.welcome_label.setAlignment(Qt.AlignCenter)
        self.welcome_label.setStyleSheet(
            "color: white; font-size: 40px; font-weight: 800; letter-spacing: -1px;"
            "font-family: 'SF Pro Display', 'Segoe UI', 'Roboto', sans-serif;"
            "background: transparent;")
        self.welcome_label.setGeometry(0, int(self.height() * 0.30), self.width(), 60)
        wl_eff = QGraphicsOpacityEffect(self.welcome_label)
        wl_eff.setOpacity(0.0)
        self.welcome_label.setGraphicsEffect(wl_eff)
        self._welcome_eff = wl_eff
        self.welcome_label.hide()

        # Вторичный индикатор — маленькое кольцо под текстом «Добро пожаловать»
        self.sub_indicator = QFrame(self)
        self.sub_indicator.setFixedSize(26, 26)
        self._sub_angle = 0.0
        si_eff = QGraphicsOpacityEffect(self.sub_indicator)
        si_eff.setOpacity(0.0)
        self.sub_indicator.setGraphicsEffect(si_eff)
        self._sub_eff = si_eff
        self.sub_indicator.hide()

        self._overlay_opacity = 0.0     # opacity тёмного оверлея перехода
        self._morph_t = 0.0             # 0 = полоска, 1 = кольцо

        # Fade-in логотипа (spring feel через OUT_BACK)
        self._fade_eff = QGraphicsOpacityEffect(self.image_label)
        self.image_label.setGraphicsEffect(self._fade_eff)
        self._fade_anim = QPropertyAnimation(self._fade_eff, b"opacity", self)
        self._fade_anim.setDuration(900)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(Easing.DECELERATE)
        self._fade_anim.start()

        # Плавный недостижимый прогресс (как при реальной загрузке)
        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._tick_progress)
        self._progress_timer.start(80)

        self.boot_timer.singleShot(5000, self.start_initial_setup) 

    def _tick_progress(self):
        # ease-out кривая: быстро в начале, медленно к ~92%
        target = 0.92
        self._progress_value += (target - self._progress_value) * 0.045
        w = int(self.progress_track.width() * self._progress_value)
        self.progress_fill.setGeometry(0, 0, max(0, w), 3)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = int(self.progress_track.width() * self._progress_value)
        self.progress_fill.setGeometry(0, 0, max(0, w), 3)
        self.welcome_label.setGeometry(0, int(self.height() * 0.30), self.width(), 60)

    # ------------------------------------------------------------------
    # Переход Boot -> OOBE
    # ------------------------------------------------------------------
    def start_initial_setup(self):
        print("Boot screen finished. Transitioning to initial setup...")
        # Дотягиваем прогресс до конца и короткой паузой даём дорисоваться
        self._progress_timer.stop()
        self._progress_value = 1.0
        self.progress_fill.setGeometry(0, 0, self.progress_track.width(), 3)
        QTimer.singleShot(260, self._begin_transition)

    def _begin_transition(self):
        """Фаза 1: логотип исчезает (fade + мягкое уменьшение)."""
        if self._phase != self.PHASE_IDLE:
            return
        self._phase = self.PHASE_LOGO_OUT

        # Прячем обычный progress-бар — его роль перехватит морф-оверлей
        self.progress_track.hide()

        logo_base_size = self.image_label.size()
        logo_base_pos = self.image_label.pos()

        def logo_frame(p):
            self._fade_eff.setOpacity(1.0 - p)
            s = 1.0 - 0.12 * p
            w = max(1, int(logo_base_size.width() * s))
            h = max(1, int(logo_base_size.height() * s))
            self.image_label.setGeometry(
                logo_base_pos.x() + (logo_base_size.width() - w) // 2,
                logo_base_pos.y() + (logo_base_size.height() - h) // 2, w, h)

        def logo_done():
            self.image_label.hide()
            self._start_strip_morph()

        self._logo_out_driver = _FrameDriver(
            420, Easing.ACCELERATE, logo_frame, logo_done, parent=self)
        self._logo_out_driver.start()

    def _start_strip_morph(self):
        """Фаза 2: полоска загрузки закручивается в кольцо и вращается."""
        self._phase = self.PHASE_SPIN
        self.raise_()

        def morph_frame(p):
            self._morph_t = p

        def morph_done():
            self._show_welcome_text()

        self._morph_driver = _FrameDriver(
            560, Easing.STANDARD, morph_frame, morph_done, parent=self)
        self._morph_driver.start()

        # Непрерывное вращение индикатора всё время морфа и после него
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._tick_spin)
        self._spin_timer.start(16)

    def _tick_spin(self):
        self._spin_angle = (self._spin_angle + 9.0) % 360.0
        self.update()

    def _show_welcome_text(self):
        """Фаза 3: надпись «Добро пожаловать» выплывает с spring-подъёмом."""
        self._phase = self.PHASE_WELCOME
        self.welcome_label.show()
        base_y = self.welcome_label.y()

        def frame(p):
            s = spring_progress(p)
            self._welcome_eff.setOpacity(min(1.0, p * 2.4))
            self.welcome_label.move(self.welcome_label.x(), int(base_y + 26.0 * (1.0 - s)))

        def done():
            self.welcome_label.move(self.welcome_label.x(), base_y)

        self._welcome_driver = _FrameDriver(
            620, QEasingCurve.Linear, frame, done, parent=self)
        self._welcome_driver.start()

        self.boot_timer.singleShot(1500, self._handoff_to_oobe)

    def _handoff_to_oobe(self):
        """Фаза 4: затемнение оверлеем и переключение на OOBE.
        Кнопки и карточки настроек появляются уже внутри OOBE со своей
        stagger-анимацией (reveal_widgets)."""
        if self._phase != self.PHASE_WELCOME:
            return
        self._phase = self.PHASE_HANDOFF

        def fade_frame(p):
            self._overlay_opacity = p

        def fade_done():
            if self._spin_timer:
                self._spin_timer.stop()
            if self.main_window:
                self.main_window.on_boot_finished()

        self._handoff_driver = _FrameDriver(
            420, Easing.STANDARD, fade_frame, fade_done, parent=self)
        self._handoff_driver.start()

    # ------------------------------------------------------------------
    # Отрисовка морфа «полоска -> кольцо» и вращающегося индикатора
    # ------------------------------------------------------------------
    def paintEvent(self, event):
        super().paintEvent(event)
        if self._phase == self.PHASE_IDLE:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        cx = self.width() / 2.0
        track_w = float(max(1, self.width() - 180))

        # Тёмный оверлей поверх всего (кроме текста) при передаче экрана OOBE
        def paint_overlay():
            if self._overlay_opacity > 0.0:
                painter.fillRect(self.rect(), QColor(0, 0, 0, int(255 * self._overlay_opacity)))

        if self._phase == self.PHASE_LOGO_OUT:
            # Логотип ещё исчезает — индикатор не рисуем
            painter.end()
            return

        if self._phase == self.PHASE_HANDOFF:
            # Финальное затемнение к OOBE: spinner уже убран, только fade
            paint_overlay()
            painter.end()
            return

        t = self._morph_t
        # Морф «полоска -> кольцо»: ширина капсулы схлопывается в диаметр кольца,
        # высота 3px раздувается до того же диаметра, центр поднимается к середине.
        diameter = track_w * (1.0 - t) + 72.0 * t
        height = 3.0 * (1.0 - t) + diameter * t
        bottom_y = self.height() - 61.5
        center_y = bottom_y * (1.0 - t) + (self.height() * 0.40) * t
        radius_x = diameter / 2.0
        radius_y = height / 2.0

        # Дорожка (трек) — проявляется вместе с закручиванием
        if t > 0.02:
            pen_track = QPen(QColor(255, 255, 255, int(36 * t) + 10))
            pen_track.setWidthF(3.0)
            pen_track.setCapStyle(Qt.RoundCap)
            painter.setPen(pen_track)
            span_track = int(360 * 16 * min(1.0, t))
            painter.drawArc(QRectF(cx - radius_x, center_y - radius_y,
                                   diameter, height), 90 * 16, -span_track)

        # Вращающаяся дуга-индикатор (iOS spinner): в начале это короткая
        # «полоска», бегущая вдоль трека; к концу — треть окружности.
        arc_len = 90.0 + 130.0 * t
        start_angle = int((self._spin_angle - arc_len / 2.0) * 16)
        pen = QPen(QColor(255, 255, 255, 235))
        pen.setWidthF(3.0)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawArc(QRectF(cx - radius_x + 1.5, center_y - radius_y + 1.5,
                               max(1.0, diameter - 3.0), max(1.0, height - 3.0)),
                        start_angle, int(arc_len * 16))

        paint_overlay()
        painter.end()

# Example App 1
class App1Content(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.init_ui()
        self.setStyleSheet("background-color: #4CAF50; color: white;")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel("This is App 1!")
        label.setStyleSheet("font-size: 20px; color: white;")
        layout.addWidget(label)

        back_button = QPushButton("Back to Launcher")
        back_button.setStyleSheet("padding: 8px 15px; font-size: 14px; margin-top: 20px; background-color: #007AFF; color: white; border-radius: 8px;")
        back_button.clicked.connect(self.go_back_to_launcher)
        layout.addWidget(back_button)

    def go_back_to_launcher(self):
        if self.main_window:
            self.main_window.show_launcher_page(self.main_window.current_language)

# Example App 2
class App2Content(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.init_ui()
        self.setStyleSheet("background-color: #FFC107; color: black;")

    def init_ui(self):
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        label = QLabel("Hello from App 2!")
        label.setStyleSheet("font-size: 20px; color: black;")
        layout.addWidget(label)

        back_button = QPushButton("Back to Launcher")
        back_button.setStyleSheet("padding: 8px 15px; font-size: 14px; margin-top: 20px; background-color: #007AFF; color: white; border-radius: 8px;")
        back_button.clicked.connect(self.go_back_to_launcher)
        layout.addWidget(back_button)

    def go_back_to_launcher(self):
        if self.main_window:
            self.main_window.show_launcher_page(self.main_window.current_language)


# --- Main Window Class ---
class MainWindow(QMainWindow):
    # Phone power/lock states
    POWER_OFF = 0
    BOOTING = 1
    LOCKED = 2
    UNLOCKED = 3 # Launcher or app is active

    def __init__(self):
        super().__init__()
        self.setWindowTitle('HIXOS System')
        self.setGeometry(0, 0, APP_WIDTH, APP_HEIGHT)
        self.setFixedSize(self.size())
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        # Initial system preferences (will be loaded from user data or OOBE)
        self.current_language = "Русский"
        self.system_version = SYSTEM_VERSION 
        self.current_navigation_mode = NAVIGATION_MODE_THREE_BUTTON 
        self.current_username = None 
        # Добавлены начальные настройки лаунчера
        self.launcher_icon_size = 70
        self.launcher_grid_columns = 4
        self.launcher_show_app_names = True

        self.power_state = self.POWER_OFF # Initial state

        self.setStyleSheet("background-color: black;") 

        # --- Firebase Initialization (DISABLED) ---
        self.firebase_app = None 
        self.db = None 
        self.firebase_initialized_successfully = False

        # Force use DummyDataManager
        print("WARNING: User data persistence is disabled. Using DummyDataManager.")
        self.user_data_manager = DummyDataManager()


        self.central_container_widget = QWidget()
        self.setCentralWidget(self.central_container_widget)
        self.main_vertical_layout = QVBoxLayout(self.central_container_widget)
        self.main_vertical_layout.setContentsMargins(0, 0, 0, 0)
        self.main_vertical_layout.setSpacing(0)

        # Initialize StatusBarWidget and NavigationBarWidget as None
        self.status_bar_widget = None
        self.navigation_bar = None

        # Add stacked_widget first, it will take up the entire available area
        self.stacked_widget = QStackedWidget(self)
        self.main_vertical_layout.addWidget(self.stacked_widget, 1) 

        self.boot_page = BootScreenContent(self, image_path='Boot.png') 
        
        self.lock_screen_page = LockScreenContent(self, initial_username="Пользователь") 
        # Pass user_data_manager to OOBEContent
        self.setup_page = OOBEContent(self,
                                      current_language=self.current_language,
                                      initial_navigation_mode=self.current_navigation_mode,
                                      user_data_manager=self.user_data_manager) 
        # Pass launcher settings to LauncherContent
        self.launcher_page = LauncherContent(self, 
                                             self.current_language,
                                             initial_icon_size=self.launcher_icon_size,
                                             initial_grid_columns=self.launcher_grid_columns,
                                             initial_show_app_names=self.launcher_show_app_names)
        self.app1_page = App1Content(self)
        self.app2_page = App2Content(self)
        self.camera_page = CameraContent(self) # Initialize CameraContent
        self.calculator_page = CalculatorContent(self) 
        self.browser_page = BrowserContent(self) # Initialize BrowserContent
        
        # Pass user_data_manager and system_version to SettingsContent, and initial launcher settings
        self.settings_page = SettingsContent(self,
                                             current_language=self.current_language,
                                             system_version=self.system_version, 
                                             initial_navigation_mode=self.current_navigation_mode,
                                             user_data_manager=self.user_data_manager) 

        self.stacked_widget.addWidget(self.boot_page)
        self.stacked_widget.addWidget(self.lock_screen_page) 
        self.stacked_widget.addWidget(self.setup_page)
        self.stacked_widget.addWidget(self.launcher_page)
        self.stacked_widget.addWidget(self.app1_page)
        self.stacked_widget.addWidget(self.app2_page)
        self.stacked_widget.addWidget(self.camera_page) # Add CameraContent to stacked_widget
        self.stacked_widget.addWidget(self.calculator_page) 
        self.stacked_widget.addWidget(self.browser_page) 
        self.stacked_widget.addWidget(self.settings_page)

        # Движок swipe-переходов между страницами (OxygenOS shifting pages)
        self.page_swipe = PageSwipe(self.stacked_widget)
        self._closing_morph = None

        # --- Recents (недавние приложения, iOS App Switcher) ---
        # Стек сессий: [{"app_id", "page", "snapshot"}] — вершина = последняя.
        self.recents_stack = []
        self._recents_overlay = None
        self._oobe_blocked_toast = None
        self._final_launch_driver = None

        self.setFocusPolicy(Qt.StrongFocus)

        self.setup_connections()
        
        self.init_ui()
        self.center_window()
        
        self.show_boot_page() # Автоматический запуск бутскрина

        self.last_unlocked_page = None 


    def setup_connections(self):
        self.launcher_page.launch_app_requested.connect(self.show_app_page)
        self.settings_page.go_back_to_launcher_requested.connect(
            lambda: self.show_launcher_page(self.current_language)
        )
        self.settings_page.language_changed.connect(self.set_system_language_only)
        self.setup_page.oobe_finished.connect(self.finalize_oobe_setup)
        self.lock_screen_page.unlocked_requested.connect(self._on_lock_screen_unlocked)
        
        # Connect language change signal from settings
        self.settings_page.language_changed.connect(self.launcher_page.set_language) 

        # Connect return signal from calculator
        self.calculator_page.go_back_to_launcher_requested.connect(
            lambda: self.show_launcher_page(self.current_language)
        )
        
        # Connect return signal from browser
        self.browser_page.go_back_to_launcher_requested.connect(
            lambda: self.show_launcher_page(self.current_language)
        )

        # Connect return signal from camera
        self.camera_page.go_back_to_launcher_requested.connect(
            lambda: self.show_launcher_page(self.current_language)
        )
        
        # New connection for system restart signal from settings
        self.settings_page.system_restart_requested.connect(self._handle_system_restart_for_update)

        # НОВЫЕ ПОДКЛЮЧЕНИЯ для настроек лаунчера:
        self.settings_page.launcher_icon_size_changed.connect(self.on_launcher_icon_size_changed)
        self.settings_page.launcher_grid_columns_changed.connect(self.on_launcher_grid_columns_changed)
        self.settings_page.launcher_app_names_visibility_changed.connect(self.on_launcher_app_names_visibility_changed)


    def init_ui(self):
        pass

    def center_window(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

    def show_boot_page(self):
        self.power_state = self.BOOTING
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.boot_page))
        self.setFocusProxy(self.boot_page)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.show()

    def _post_boot_ui_init(self):
        if self.status_bar_widget is None: 
            self.status_bar_widget = StatusBarWidget(self)
            self.main_vertical_layout.insertWidget(0, self.status_bar_widget)
            self.stacked_widget.currentChanged.connect(self.update_status_bar_theme)
            print("StatusBarWidget initialized and added.")

        if self.navigation_bar is None: 
            self.navigation_bar = NavigationBarWidget(self, initial_mode=self.current_navigation_mode)
            self.main_vertical_layout.addWidget(self.navigation_bar)
            # Reconnect signals after navigation_bar initialization
            self.settings_page.navigation_mode_changed.connect(self.navigation_bar.set_navigation_mode)
            self.navigation_bar.home_button_pressed.connect(lambda: self.show_launcher_page(self.current_language))
            self.navigation_bar.back_button_pressed.connect(self._on_nav_back)
            self.navigation_bar.recent_button_pressed.connect(self._on_nav_recents)
            # Панель наследует чернила от статус-бара (стекло iOS)
            self.navigation_bar.set_is_light_background(
                getattr(self.status_bar_widget, "is_light_background", False))
            print("NavigationBarWidget initialized and added.")
        
        self.update_status_bar_theme(self.stacked_widget.currentIndex())


    def on_boot_finished(self):
        self._post_boot_ui_init() 

        user_data = self.user_data_manager.load_user_data() 
        
        loaded_username = user_data.get("username", "Пользователь") 
        loaded_language = user_data.get("language", "Русский") 
        loaded_nav_mode = user_data.get("navigation_mode", NAVIGATION_MODE_THREE_BUTTON) 
        loaded_system_version = user_data.get("system_version", SYSTEM_VERSION) 
        # Загрузка настроек лаунчера
        loaded_launcher_icon_size = user_data.get("launcher_icon_size", 70)
        loaded_launcher_grid_columns = user_data.get("launcher_grid_columns", 4)
        loaded_launcher_show_app_names = user_data.get("launcher_show_app_names", True)

        self.current_username = loaded_username
        self.user_data_manager.user_id = loaded_username 
        
        self.current_language = loaded_language
        self.current_navigation_mode = loaded_nav_mode
        self.system_version = loaded_system_version 
        self.launcher_icon_size = loaded_launcher_icon_size
        self.launcher_grid_columns = loaded_launcher_grid_columns
        self.launcher_show_app_names = loaded_launcher_show_app_names


        print(f"User data (dummy): language='{loaded_language}', navigation mode='{loaded_nav_mode}', version='{loaded_system_version}'.")
        print(f"Launcher settings (dummy): icon_size={loaded_launcher_icon_size}, grid_columns={loaded_launcher_grid_columns}, show_app_names={loaded_launcher_show_app_names}.")
        
        # OOBE is launched if the user is a 'dummy_user_id' AND the username is 'Пользователь'.
        # This simulates a first-time setup for a new (dummy) user.
        if self.user_data_manager.user_id == "dummy_user_id" and loaded_username == "Пользователь":
            print("User data not found or incomplete (dummy). Launching Out-of-Box Experience (OOBE).")
            # Совместимость со старым кодом HIXOS.py: подхватываем язык/навигацию,
            # если они были присвоены как атрибуты до показа страницы.
            self.setup_page.welcome_page.group.select_by_index(
                ["Русский", "English", "Deutsch", "Français"].index(
                    getattr(self.setup_page, "current_language", "Русский"))) \
                if getattr(self.setup_page, "current_language", None) else None
            nm = getattr(self.setup_page, "initial_navigation_mode", None)
            if nm:
                modes = [NAVIGATION_MODE_THREE_BUTTON, NAVIGATION_MODE_GESTURES]
                if nm in modes:
                    self.setup_page.navigation_choice_page.group.select_by_index(modes.index(nm))
            self.show_setup_page()
        else:
            print(f"Dummy data loaded. Transitioning to lock screen for user: {self.current_username}.")
            self.lock_screen_page.set_username(self.current_username) 
            self.settings_page.set_initial_preferences(
                self.current_language, 
                self.current_navigation_mode, 
                self.system_version
            ) # Pass system version
            # Инициализация лаунчера загруженными настройками
            self.launcher_page._current_icon_size = self.launcher_icon_size
            self.launcher_page._current_grid_columns = self.launcher_grid_columns
            self.launcher_page._show_app_names = self.launcher_show_app_names
            self.launcher_page._populate_grid_apps() # Перестроить сетку с новыми параметрами
            self.launcher_page._populate_dock_apps() # Перестроить док
            
            self.show_lock_screen_page() 

    def show_lock_screen_page(self):
        self.power_state = self.LOCKED
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.lock_screen_page))
        self._set_bars_ink(False)
        self.setFocusProxy(self.lock_screen_page)


    def _on_lock_screen_unlocked(self):
        """
        Called when the lock screen is unlocked.
        iOS-style unlock: локскрин не просто гаснет — он параллельно уезжает
        вверх (slide-up) и затухает, открывая рабочий стол.
        """
        self.power_state = self.UNLOCKED
        print(f"Screen unlocked. Starting animation and transitioning to launcher for user: {self.current_username}.")

        # Готовим лаунчер заранее, но показываем его ПОД локскрином сразу,
        # чтобы transition был непрерывным (как в iOS).
        self.launcher_page.prepare_for_animation()
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.launcher_page))
        self.launcher_page.show()
        self.launcher_page.lower()
        self.lock_screen_page.raise_()
        self.lock_screen_page.show()

        opacity_effect = QGraphicsOpacityEffect(self.lock_screen_page)
        self.lock_screen_page.setGraphicsEffect(opacity_effect)

        base_pos = self.lock_screen_page.pos()

        lock_screen_fade_out_animation = QPropertyAnimation(opacity_effect, b"opacity", self.lock_screen_page)
        lock_screen_fade_out_animation.setDuration(Duration.TRANSITION)
        lock_screen_fade_out_animation.setStartValue(1.0)
        lock_screen_fade_out_animation.setEndValue(0.0)
        lock_screen_fade_out_animation.setEasingCurve(Easing.IOS_TRANSITION)

        slide_up = QPropertyAnimation(self.lock_screen_page, b"pos", self.lock_screen_page)
        slide_up.setDuration(Duration.TRANSITION)
        slide_up.setStartValue(base_pos)
        slide_up.setEndValue(base_pos + QPoint(0, -int(self.height() * 0.18)))
        slide_up.setEasingCurve(Easing.IOS_TRANSITION)

        group = QParallelAnimationGroup(self)
        group.addAnimation(lock_screen_fade_out_animation)
        group.addAnimation(slide_up)
        group.finished.connect(self._start_launcher_animation)
        self._unlock_group = group
        group.start(QParallelAnimationGroup.DeleteWhenStopped)

    def _start_launcher_animation(self):
        """
        Called after the lock screen has fully faded out.
        Switches to the launcher and starts its appearance animation.
        """
        self.lock_screen_page.setGraphicsEffect(None)
        self.lock_screen_page.hide()

        # Prepare the launcher for animation
        self.launcher_page.prepare_for_animation() 

        self.show_launcher_page_without_animation_prep() 

        self.last_unlocked_page = self.launcher_page 


    def show_setup_page(self):
        self.power_state = self.UNLOCKED 
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.setup_page))
        self._set_bars_ink(True)
        self.setFocusProxy(self.setup_page)
        self.setWindowFlags(self.windowFlags() & ~Qt.FramelessWindowHint & ~Qt.WindowStaysOnTopHint)
        self.show()
        self.last_unlocked_page = self.setup_page 


    def show_launcher_page(self, selected_language: str): # Добавлен тип для selected_language
        self.power_state = self.UNLOCKED
        self.current_language = selected_language
        self.launcher_page.set_language(selected_language)
        self._return_to_launcher(animate=True)
        

    def show_launcher_page_without_animation_prep(self):
        self.power_state = self.UNLOCKED
        self._return_to_launcher(animate=False)

    def _return_to_launcher(self, animate: bool = True):
        """Возврат на рабочий стол. Если текущая страница — приложение,
        сначала проигрываем morph-сворачивание окна в его иконку (iOS dismiss),
        затем показываем лаунчер с волновым появлением иконок."""
        current = self.stacked_widget.currentWidget()
        is_app_page = (current is not None and current is not self.launcher_page
                       and current is not self.lock_screen_page
                       and current is not self.setup_page
                       and current is not self.boot_page)

        if animate and is_app_page:
            self._play_closing_morph(current)
            return

        self.launcher_page.show()
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.launcher_page))
        if animate:
            # волна иконок — только при разблокировке; при простом показе
            # лаунчер остаётся в покое (иконки уже на своих местах)
            self.launcher_page.prepare_for_animation()
        self._set_bars_ink(False)
        self.setFocusProxy(self.launcher_page)
        self.last_unlocked_page = self.launcher_page

    def _app_page_for_icon(self, ic):
        """Сопоставление app_id иконки лаунчера со страницей. Возвращает
        (page, created_placeholder). Для заглушек страница создаётся лениво,
        чтобы dismiss-морф работал и для неприкрученных приложений."""
        mapping = {
            "Phone": getattr(self, "app1_page", None),
            "Messages": getattr(self, "app2_page", None),
            "Camera": getattr(self, "camera_page", None),
            "Calculator": getattr(self, "calculator_page", None),
            "Browser": getattr(self, "browser_page", None),
            "Settings": getattr(self, "settings_page", None),
            "Photos": getattr(self, "app1_page", None),
            "Store": getattr(self, "app2_page", None),
        }
        page = mapping.get(ic.app_id)
        if page is not None:
            return page, False
        # Заглушка: ищем уже созданную temp-страницу или создаём новую
        for w in self.stacked_widget.findChildren(QWidget):
            if w.property("hixos_placeholder_app") == ic.app_id:
                return w, False
        temp = QWidget()
        temp.setProperty("hixos_placeholder_app", ic.app_id)
        temp.setStyleSheet("background-color: #1c1e24; color: white;")
        lay = QVBoxLayout(temp)
        lay.setAlignment(Qt.AlignCenter)
        label = QLabel(f"«{ic.app_id}»\nПриложение ещё не установлено")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 15px;")
        lay.addWidget(label)
        btn = QPushButton("Домой")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(
            "QPushButton{background-color:#007AFF;color:white;border:none;"
            "border-radius:10px;padding:10px 26px;font-weight:600;}"
            "QPushButton:pressed{background-color:#0062cc;}")
        btn.clicked.connect(lambda: self.show_launcher_page(self.current_language))
        blay = QHBoxLayout()
        blay.addStretch(1); blay.addWidget(btn); blay.addStretch(1)
        lay.addLayout(blay)
        self.stacked_widget.addWidget(temp)
        return temp, True

    def _find_icon_for_page(self, app_page):
        for ic in self.launcher_page.grid_app_icons + self.launcher_page.dock_app_icons:
            page, _ = self._app_page_for_icon(ic)
            if page is app_page:
                return ic
        return None

    def _reveal_launcher_after_dismiss(self):
        self._closing_morph = None
        self.launcher_page.show()
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.launcher_page))
        self._set_bars_ink(False)
        self.setFocusProxy(self.launcher_page)
        self.last_unlocked_page = self.launcher_page

    def _play_closing_morph(self, app_page):
        """iOS-style dismiss: окно приложения плавно сворачивается В СВОЮ ИКОНКУ,
        лаунчер всё время анимации виден под сворачивающимся окном."""
        icon = self._find_icon_for_page(app_page)
        if icon is None:
            # нет иконки — backward swipe без волны иконок
            self.launcher_page.show()
            self.page_swipe.transition_to(self.launcher_page, direction="backward",
                                          duration=Duration.TRANSITION,
                                          on_finished=self._reveal_launcher_after_dismiss)
            return

        # Лаунчер показываем СРАЗУ — он виден под уезжающим окном приложения
        self.launcher_page.show()
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.launcher_page))

        # Кадрируем окно приложения в pixmap поверх его фоновой подложки
        shot = app_page.grab()
        tl = app_page.mapTo(self, QPoint(0, 0))
        start_rect = QRect(tl, app_page.size())

        root = self
        # Локальные координаты корня окна: иконка и кадр приложения
        g_tl = icon.mapToGlobal(icon.rect().topLeft())
        start_icon_rect = QRect(root.mapFromGlobal(g_tl), icon.rect().size())

        morph = MorphOverlay(root, start_icon_rect, start_rect,
                             snapshot=shot, corner_start=22, corner_end=0,
                             rects_local=True)
        morph.set_progress(1.0)  # старт с полного экрана
        morph.raise_()
        self._closing_morph = morph

        # прячем реальное окно сразу — морф-оверлей дорисовывает тот же кадр
        app_page.hide()

        def done():
            self._reveal_launcher_after_dismiss()
            # приложение свёрнуто — обновляем его живой снимок в недавних
            self._record_session(app_page)

        # run_close идёт от прогресса 1->0, но у нас семантика та же:
        # экран -> иконка. Углы: 0 (экран) -> 22 (иконка) уже в параметрах.
        morph.run_close(duration=Duration.DISMISS, curve=Easing.STANDARD, on_finished=done)


    def show_app_page(self, app_id: str, icon_rect: QRect): 
        self.power_state = self.UNLOCKED
        target_page = None
        is_light_bg = False 

        if app_id == "Phone":
            target_page = self.app1_page
            is_light_bg = False 
        elif app_id == "Messages":
            target_page = self.app2_page
            is_light_bg = False
        elif app_id == "Camera":
            target_page = self.camera_page
            is_light_bg = False
        elif app_id == "Photos": 
            target_page = self.app1_page 
            is_light_bg = False
        elif app_id == "Store": 
            target_page = self.app2_page 
            is_light_bg = False
        elif app_id == "Calculator": 
            target_page = self.calculator_page
            is_light_bg = False
        elif app_id == "Browser": 
            target_page = self.browser_page
            is_light_bg = True # Browser has a light background
        elif app_id == "Settings":
            target_page = self.settings_page
            is_light_bg = False
        else:
            # Заглушка: переиспользуем/создаём temp-страницу, чтобы при выходе
            # из неё морф-dismiss тоже работал (раньше каждый запуск создавал
            # новую страницу и обратный переход падал).
            icon = None
            for ic in self.launcher_page.grid_app_icons + self.launcher_page.dock_app_icons:
                if ic.app_id == app_id:
                    icon = ic
                    break
            if icon is not None:
                target_page, _ = self._app_page_for_icon(icon)
            else:
                print(f"Error: Unknown application '{app_id}'. Creating temporary placeholder.")
                temp_app_page = QWidget()
                temp_app_page.setProperty("hixos_placeholder_app", app_id)
                temp_app_page.setStyleSheet("background-color: #1c1e24; color: white;")
                temp_layout = QVBoxLayout(temp_app_page)
                temp_layout.setAlignment(Qt.AlignCenter)
                lbl = QLabel(f"Приложение «{app_id}» ещё не установлено")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("color: rgba(255,255,255,0.75); font-size: 15px;")
                temp_layout.addWidget(lbl)

                close_button = QPushButton("Домой")
                close_button.setCursor(Qt.PointingHandCursor)
                close_button.setStyleSheet(
                    "QPushButton{background-color:#007AFF;color:white;border:none;"
                    "border-radius:10px;padding:10px 26px;font-weight:600;}"
                    "QPushButton:pressed{background-color:#0062cc;}")
                close_button.clicked.connect(lambda: self.show_launcher_page(self.current_language))
                blay = QHBoxLayout()
                blay.addStretch(1); blay.addWidget(close_button); blay.addStretch(1)
                temp_layout.addLayout(blay)

                self.stacked_widget.addWidget(temp_app_page)
                target_page = temp_app_page
            is_light_bg = False

        if target_page:
            if self.stacked_widget.indexOf(target_page) == -1:
                self.stacked_widget.addWidget(target_page)

            # Если морф-оверлей от лаунчера ещё жив (морфинг иконки в экран),
            # просто переключаем страницу под ним — без двойной анимации.
            morph_alive = (getattr(self.launcher_page, "_morph", None) is not None)

            self.stacked_widget.setCurrentWidget(target_page)
            target_page.show()
            target_page.setGraphicsEffect(None)
            # фиксируем сессию в недавних (снимок до morph-перекрытия надёжнее
            # делать здесь — страница уже отрисована)
            self._record_session(target_page)
            # Поднимаем живой морф над страницей приложения, чтобы анимация
            # разворота оставалась поверх до последнего кадра.
            if morph_alive and getattr(self.launcher_page, "_morph", None) is not None:
                self.launcher_page._morph.raise_()

            if not morph_alive:
                # Прямое открытие (не из лаунчера): iOS-style fade+scale вход
                from ui.animation_engine import PageTransition
                pt = PageTransition(self.stacked_widget)
                pt.fade_scale_in(target_page, start_scale=0.96, duration=Duration.TRANSITION)

            self._set_bars_ink(is_light_bg)
            self.setFocusProxy(target_page) 
            self.last_unlocked_page = target_page 
        else:
            print(f"Critical error: could not display page for '{app_id}'.")

    def set_system_language_only(self, language: str):
        self.current_language = language
        # self.user_data_manager.save_user_data(...) # Commented out to disable saving
        print(f"System language set to: {self.current_language} (not saved).")
        self.show_launcher_page(language)

    def _is_oobe_active(self):
        """OOBE активен, если страница настройки показана и ещё не завершена."""
        if self.stacked_widget.currentWidget() is not getattr(self, "setup_page", None):
            return False
        return not getattr(self.setup_page, "_finished", False)

    def _show_oobe_blocked_toast(self):
        """Мягкий iOS-алерт: нельзя выйти из настройки, пока она не завершена."""
        try:
            from ui.recents import DelayedFrameDriver  # тот же покадровый движок
        except ImportError:
            from recents import DelayedFrameDriver

        old_pair = self._oobe_blocked_toast
        if old_pair is not None:
            try:
                old_pair[0].deleteLater()
            except RuntimeError:
                pass
            self._oobe_blocked_toast = None

        toast = QLabel("Пройдите настройку до конца", self.central_container_widget)
        toast.setAlignment(Qt.AlignCenter)
        toast.setWordWrap(False)
        f = QFont()
        f.setPixelSize(13)
        f.setWeight(QFont.DemiBold)
        toast.setFont(f)
        fm_w = toast.fontMetrics().width(toast.text())
        tw = min(max(fm_w + 40, 200), self.width() - 40)
        th = 36
        start_y = int(self.height() * 0.72)
        end_y = start_y - 12
        toast.setGeometry((self.width() - tw) // 2, start_y, tw, th)
        toast.setStyleSheet(
            "QLabel{background-color: rgba(48,52,62,0.94); color: white;"
            "border-radius: 18px; border: 1px solid rgba(255,255,255,0.14);}")
        toast.setAttribute(Qt.WA_TransparentForMouseEvents)
        effect = QGraphicsOpacityEffect(toast)
        toast.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        toast.show()
        toast.raise_()
        self._oobe_blocked_toast = (toast, effect)

        def frame(p):
            if p < 0.28:
                e = spring_progress(p / 0.28)
            else:
                fade = max(0.0, (p - 0.72) / 0.28)
                e = 1.0 - fade
            effect.setOpacity(min(1.0, max(0.0, e * 1.0)))
            y = int(start_y + (end_y - start_y) * min(1.0, p / 0.28)) \
                if p < 0.72 else start_y
            toast.move((self.width() - tw) // 2, y)

        def done():
            if self._oobe_blocked_toast and self._oobe_blocked_toast[0] is toast:
                self._oobe_blocked_toast = None
            toast.deleteLater()

        driver = DelayedFrameDriver(0, 1500, QEasingCurve.Linear, frame, done, parent=self)
        driver.start()

    def _on_nav_back(self):
        """Кнопка «Назад» трёхкнопочной навигации (жестов нет — только кнопки)."""
        if self.power_state == self.BOOTING:
            return
        if self._recents_overlay is not None and self._recents_overlay.isVisible():
            self._recents_overlay.play_dismiss_anim()
            return
        if self._is_oobe_active():
            # В OOBE системная «назад» не работает — подсказка пройти настройку
            self._show_oobe_blocked_toast()
            return
        if self.power_state == self.LOCKED:
            return
        current = self.stacked_widget.currentWidget()
        if current is self.launcher_page:
            return  # уже дома
        if current in (self.app1_page, self.app2_page, self.camera_page,
                       self.calculator_page, self.browser_page, self.settings_page) or \
           current.property("hixos_placeholder_app") is not None:
            self.show_launcher_page(self.current_language)
        else:
            self.show_launcher_page(self.current_language)

    def _on_nav_recents(self):
        """Кнопка «Недавние»: открывает App Switcher (только кнопки, без жестов)."""
        if self.power_state == self.BOOTING:
            return
        if self._is_oobe_active():
            self._show_oobe_blocked_toast()
            return
        if self.power_state == self.LOCKED:
            return
        self._open_recents()

    # ------------------------------------------------------------------
    # RECENTS (iOS App Switcher)
    # ------------------------------------------------------------------
    def _app_pages(self):
        return [self.app1_page, self.app2_page, self.camera_page,
                self.calculator_page, self.browser_page, self.settings_page]

    def _display_name_for_app(self, app_id):
        locale = getattr(self.launcher_page, "localized_app_names", {})
        cur = locale.get(self.current_language, locale.get("Русский", {}))
        rus = locale.get("Русский", {})
        return cur.get(app_id, rus.get(app_id, app_id))

    def _record_session(self, app_page):
        """Снимок страницы в стек недавних (вершина стека = последняя)."""
        app_id = app_page.property("hixos_placeholder_app")
        if app_id is None:
            known = {id(self.app1_page): "Phone", id(self.app2_page): "Messages",
                     id(self.camera_page): "Camera", id(self.calculator_page): "Calculator",
                     id(self.browser_page): "Browser", id(self.settings_page): "Settings"}
            app_id = known.get(id(app_page))
        if app_id is None:
            return
        try:
            snapshot = app_page.grab()
        except Exception:
            snapshot = None
        # дедупликация: та же аппа уже на вершине — просто обновляем снимок
        if self.recents_stack and self.recents_stack[-1]["app_id"] == app_id:
            self.recents_stack[-1]["snapshot"] = snapshot
            return
        self.recents_stack.append({"app_id": app_id, "page": app_page, "snapshot": snapshot})
        # iOS держит ограниченное число карточек
        MAX_RECENTS = 8
        if len(self.recents_stack) > MAX_RECENTS:
            self.recents_stack = self.recents_stack[-MAX_RECENTS:]

    def _clear_session(self, app_page):
        self.recents_stack = [s for s in self.recents_stack if s["page"] is not app_page]

    def _open_recents(self):
        overlay = self._ensure_recents_overlay()
        sessions = []
        for s in reversed(self.recents_stack):  # последние сверху
            icon_pix = None
            ic = self._find_icon_by_app_id(s["app_id"])
            if ic is not None:
                icon_pix = ic._original_pixmap
            sessions.append({
                "app_id": s["app_id"],
                "name": self._display_name_for_app(s["app_id"]),
                "icon": icon_pix,
                "snapshot": s.get("snapshot"),
            })
        overlay.set_sessions(sessions)
        overlay.play_show_anim()
        # фон под оверлеем: если сейчас лаунчер — оставить, иначе прикроем стекло

    def _find_icon_by_app_id(self, app_id):
        for ic in self.launcher_page.grid_app_icons + self.launcher_page.dock_app_icons:
            if ic.app_id == app_id:
                return ic
        return None

    def _ensure_recents_overlay(self):
        if self._recents_overlay is None:
            self._recents_overlay = RecentsOverlay(self.central_container_widget)
            self._recents_overlay.setGeometry(self.central_container_widget.rect())
            self._recents_overlay.app_resumed.connect(self._resume_from_recents)
        else:
            self._recents_overlay.setGeometry(self.central_container_widget.rect())
        return self._recents_overlay

    def _resume_from_recents(self, app_id):
        target = None
        for s in self.recents_stack:
            if s["app_id"] == app_id:
                target = s["page"]
                break
        if target is None:
            return
        current = self.stacked_widget.currentWidget()
        if current is target:
            return
        if current is self.launcher_page:
            # разворот из иконки (morph open) — как обычный запуск
            ic = self._find_icon_by_app_id(app_id)
            if ic is not None:
                root = self
                g_tl = ic.mapToGlobal(ic.rect().topLeft())
                icon_local = QRect(root.mapFromGlobal(g_tl), ic.rect().size())
                shot = target.grab()
                morph = MorphOverlay(root, icon_local, QRect(QPoint(0, 0), self.stacked_widget.size()),
                                     pixmap=ic._original_pixmap, corner_start=22, corner_end=0,
                                     snapshot=shot, rects_local=True)
                morph.run_open(duration=Duration.LAUNCH, curve=Easing.STANDARD,
                               on_finished=lambda t=target: self._finish_resume(t))
                self.stacked_widget.setCurrentWidget(target)
                target.show()
                morph.raise_()
                return
        self.stacked_widget.setCurrentWidget(target)
        target.show()
        self.setFocusProxy(target)
        self.last_unlocked_page = target
        self._set_bars_ink(target is self.browser_page)

    def _finish_resume(self, target):
        self.setFocusProxy(target)
        self.last_unlocked_page = target
        self._set_bars_ink(target is self.browser_page)

    def finalize_oobe_setup(self, language: str, navigation_mode: str, username: str):
        self.current_language = language
        self.current_navigation_mode = navigation_mode
        self.current_username = username 

        # self.user_data_manager.save_user_data(...) # Commented out to disable saving
        print(f"OOBE completed (data not saved). System language: {self.current_language}, navigation mode: {self.current_navigation_mode}, username: {self.current_username}.")
        
        self.navigation_bar.set_navigation_mode(self.current_navigation_mode)

        # OOBE завершён — выход из настройки больше не блокируется
        self.setup_page._finished = True

        # Prepare the launcher for animation
        self.launcher_page.prepare_for_animation()
        self.launcher_page.show()
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.launcher_page))
        self._set_bars_ink(False)
        self.setFocusProxy(self.launcher_page)
        self.last_unlocked_page = self.launcher_page

        # Волна появления иконок расходится ОТ кнопки «Начать работу»
        origin = None
        try:
            btn = self.setup_page.final_page.findChild(QPushButton, "primaryButton")
            if btn is not None and btn.isVisible():
                g_c = btn.mapToGlobal(btn.rect().center())
                origin = QPointF(self.central_container_widget.mapFromGlobal(g_c))
        except RuntimeError:
            origin = None
        self.launcher_page.animate_icons_in(origin=origin)
        
    def load_user_preferences(self):
        pass 

    def _handle_system_restart_for_update(self, new_version: str):
        """
        Handles the request to restart the system after an update.
        Displays a message and closes the application to simulate a restart.
        """
        print(f"Received request to restart system to apply update to version: {new_version}")
        self.system_version = new_version # Update system version in MainWindow
        QMessageBox.information(self, "HIXOS Restart", 
                                f"HIXOS updated to version {new_version}. Please restart the application manually to apply changes.")
        self.close() # Close the application

    def _set_bars_ink(self, is_light_bg: bool):
        """Единый источник истины: статус-бар и панель навигации красятся
        одинаково (iOS glass — тёмные чернила на светлом фоне, белые на тёмном)."""
        if getattr(self, "status_bar_widget", None):
            self.status_bar_widget.set_is_light_background(is_light_bg)
        if getattr(self, "navigation_bar", None):
            self.navigation_bar.set_is_light_background(is_light_bg)

    def update_status_bar_theme(self, index):
        # Карта «светлый фон страницы» для системных баров (статус + навигация)
        sw = self.stacked_widget
        light_pages = {sw.indexOf(self.setup_page), sw.indexOf(self.browser_page)}
        is_light = index in light_pages
        self._set_bars_ink(is_light)

    # --- НОВЫЕ МЕТОДЫ: Обработчики для настроек лаунчера ---
    def on_launcher_icon_size_changed(self, size: int):
        self.launcher_icon_size = size
        self.launcher_page.set_icon_size(size)
        print(f"MainWindow: Launcher icon size changed to {size}")

    def on_launcher_grid_columns_changed(self, columns: int):
        self.launcher_grid_columns = columns
        self.launcher_page.set_grid_columns(columns)
        print(f"MainWindow: Launcher grid columns changed to {columns}")

    def on_launcher_app_names_visibility_changed(self, visible: bool):
        self.launcher_show_app_names = visible
        self.launcher_page.set_app_names_visibility(visible)
        print(f"MainWindow: Launcher app names visibility changed to {visible}")

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F1:
            if self.power_state == self.POWER_OFF:
                print("F1 pressed: Powering on the system.")
                self.show_boot_page()
            elif self.power_state == self.UNLOCKED:
                print("F1 pressed: Locking screen.")
                self.show_lock_screen_page()
            elif self.power_state == self.LOCKED:
                print("F1 pressed: Attempting unlock (via F1).")
                self._on_lock_screen_unlocked()
            return 

        if self.power_state == self.BOOTING:
            if event.key() == Qt.Key_Escape:
                print("Escape pressed on main window (boot screen).")
                self.boot_page.boot_timer.stop() 
                self.on_boot_finished() 
        super().keyPressEvent(event)

    def mousePressEvent(self, event):
        if self.power_state == self.BOOTING:
            print("Mouse click on main window (boot screen).")
            self.boot_page.boot_timer.stop() 
            self.on_boot_finished() 
        super().mousePressEvent(event)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_window = MainWindow()
    sys.exit(app.exec_())
