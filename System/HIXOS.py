# Starter.py
import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QDesktopWidget,
    QMainWindow, QPushButton, QLineEdit, QHBoxLayout,
    QComboBox, QStackedWidget, QFrame, QSizePolicy, QSpacerItem,
    QGraphicsOpacityEffect, QRadioButton, QMessageBox
)
from PyQt5.QtGui import QPixmap, QTransform, QColor
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal, QTime, QPropertyAnimation, QEasingCurve, QRect, QParallelAnimationGroup, QEvent, QDate

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
    def __init__(self, parent=None, image_path='Boot.png'): 
        super().__init__(parent)
        self.main_window = parent
        self.image_path = image_path
        self.boot_timer = QTimer(self) 
        self.init_ui()

    def init_ui(self):
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.image_label = QLabel(self)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.layout.addWidget(self.image_label)

        if os.path.exists(self.image_path):
            pixmap = QPixmap(self.image_path)
            if not pixmap.isNull():
                self.image_label.setPixmap(pixmap)
                self.image_label.setScaledContents(True) 
                self.image_label.setStyleSheet("background-color: black;") 
            else:
                self.image_label.setText(f"Error: Image '{self.image_path}' not found.")
                self.image_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold; background-color: black;")
        else:
            self.image_label.setText(f"Error: Image file '{self.image_path}' not found.")
            self.image_label.setStyleSheet("color: white; font-size: 16px; font-weight: bold; background-color: black;")
        
        self.boot_timer.singleShot(5000, self.start_initial_setup) 

    def start_initial_setup(self):
        print("Boot screen finished. Transitioning to initial setup...")
        if self.main_window:
            self.main_window.on_boot_finished() 

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
            self.setup_page.current_language = self.current_language
            self.setup_page.initial_navigation_mode = self.current_navigation_mode
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
        self.status_bar_widget.set_is_light_background(False) 
        self.setFocusProxy(self.lock_screen_page)


    def _on_lock_screen_unlocked(self):
        """
        Called when the lock screen is unlocked.
        Starts the animation to fade out the lock screen and reveal the launcher.
        """
        self.power_state = self.UNLOCKED
        print(f"Screen unlocked. Starting animation and transitioning to launcher for user: {self.current_username}.")

        opacity_effect = QGraphicsOpacityEffect(self.lock_screen_page)
        self.lock_screen_page.setGraphicsEffect(opacity_effect)

        lock_screen_fade_out_animation = QPropertyAnimation(opacity_effect, b"opacity")
        lock_screen_fade_out_animation.setDuration(300) 
        lock_screen_fade_out_animation.setStartValue(1.0)
        lock_screen_fade_out_animation.setEndValue(0.0)
        lock_screen_fade_out_animation.setEasingCurve(QEasingCurve.OutQuad)

        lock_screen_fade_out_animation.finished.connect(self._start_launcher_animation)
        
        lock_screen_fade_out_animation.start()

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
        self.status_bar_widget.set_is_light_background(True)
        self.setFocusProxy(self.setup_page)
        self.setWindowFlags(self.windowFlags() & ~Qt.FramelessWindowHint & ~Qt.WindowStaysOnTopHint)
        self.show()
        self.last_unlocked_page = self.setup_page 


    def show_launcher_page(self, selected_language: str): # Добавлен тип для selected_language
        self.power_state = self.UNLOCKED
        self.launcher_page.show() 
        self.current_language = selected_language
        self.launcher_page.set_language(selected_language) 
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.launcher_page))
        self.status_bar_widget.set_is_light_background(False)
        self.setFocusProxy(self.launcher_page)
        self.last_unlocked_page = self.launcher_page 
        

    def show_launcher_page_without_animation_prep(self):
        self.power_state = self.UNLOCKED
        self.launcher_page.show() 
        self.stacked_widget.setCurrentIndex(self.stacked_widget.indexOf(self.launcher_page))
        self.status_bar_widget.set_is_light_background(False)
        self.setFocusProxy(self.launcher_page)
        self.last_unlocked_page = self.launcher_page 


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
            print(f"Error: Unknown application '{app_id}'. Creating temporary placeholder.")
            temp_app_page = QWidget()
            temp_app_page.setStyleSheet("background-color: #333; color: white;")
            temp_layout = QVBoxLayout(temp_app_page)
            temp_layout.setAlignment(Qt.AlignCenter)
            temp_layout.addWidget(QLabel(f"Application '{app_id}' not implemented."))
            
            close_button = QPushButton("Close Application")
            close_button.setStyleSheet("background-color: #007AFF; color: white; border-radius: 8px; padding: 10px 20px;")
            close_button.clicked.connect(lambda: self.show_launcher_page(self.current_language))
            temp_layout.addWidget(close_button)

            self.stacked_widget.addWidget(temp_app_page)
            target_page = temp_app_page
            is_light_bg = False

        if target_page:
            if self.stacked_widget.indexOf(target_page) == -1:
                self.stacked_widget.addWidget(target_page)

            self.stacked_widget.setCurrentWidget(target_page)
            
            target_page.show() 

            target_page.setGraphicsEffect(None) 

            self.status_bar_widget.set_is_light_background(is_light_bg)
            self.setFocusProxy(target_page) 
            self.last_unlocked_page = target_page 
        else:
            print(f"Critical error: could not display page for '{app_id}'.")

    def set_system_language_only(self, language: str):
        self.current_language = language
        # self.user_data_manager.save_user_data(...) # Commented out to disable saving
        print(f"System language set to: {self.current_language} (not saved).")
        self.show_launcher_page(language)

    def finalize_oobe_setup(self, language: str, navigation_mode: str, username: str):
        self.current_language = language
        self.current_navigation_mode = navigation_mode
        self.current_username = username 

        # self.user_data_manager.save_user_data(...) # Commented out to disable saving
        print(f"OOBE completed (data not saved). System language: {self.current_language}, navigation mode: {self.current_navigation_mode}, username: {self.current_username}.")
        
        self.navigation_bar.set_navigation_mode(self.current_navigation_mode)
        
        # Prepare the launcher for animation
        self.launcher_page.prepare_for_animation()

        self.show_launcher_page(language)
        
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

    def update_status_bar_theme(self, index):
        if self.status_bar_widget: 
            if index == self.stacked_widget.indexOf(self.boot_page):
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.lock_screen_page): 
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.setup_page):
                self.status_bar_widget.set_is_light_background(True)
            elif index == self.stacked_widget.indexOf(self.launcher_page):
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.settings_page):
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.app1_page):
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.app2_page):
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.camera_page):
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.calculator_page):
                self.status_bar_widget.set_is_light_background(False)
            elif index == self.stacked_widget.indexOf(self.browser_page): 
                self.status_bar_widget.set_is_light_background(True) # Browser will have a light background
            else:
                self.status_bar_widget.set_is_light_background(False)

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
