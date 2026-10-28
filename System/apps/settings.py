# apps/settings.py
import sys
import os
import random # Для имитации проверки обновлений
import subprocess # Для возможной имитации выполнения команд git (не используется напрямую для безопасности)
import requests # Для HTTP-запросов к GitHub
import json # Для парсинга JSON
# import zipfile # Для распаковки ZIP (не используется напрямую для безопасности)

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QSizePolicy, QApplication, QMessageBox,
    QSpacerItem, QRadioButton, QComboBox, QStackedWidget, QButtonGroup,
    QSpinBox, QCheckBox # Добавлены для новых настроек
)
from PyQt5.QtGui import QFont, QPixmap, QMovie, QColor
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QTimer, QThread # Добавлен QThread для неблокирующих операций

# Импортируем константы навигации
from ui.navigation_bar import NAVIGATION_MODE_THREE_BUTTON

# URL для проверки обновлений на GitHub (заглушка)
# Замените на реальный репозиторий при необходимости
GITHUB_UPDATE_JSON_URL = "https://raw.githubusercontent.com/username/repo/main/update.json"
GITHUB_RELEASE_ZIP_URL = "https://github.com/username/repo/releases/download/{version}/update.zip"

# Рабочий поток для проверки обновлений
class UpdateChecker(QThread):
    update_check_finished = pyqtSignal(bool, str, str) # Есть обновление, новая версия, сообщение об ошибке
    
    def __init__(self, current_version: str):
        super().__init__()
        self.current_version = current_version

    def run(self):
        try:
            # Имитация проверки обновлений
            # В реальном приложении здесь был бы запрос к GitHub API
            # Для простоты, сгенерируем случайную "новую" версию.
            
            response = requests.get(GITHUB_UPDATE_JSON_URL)
            response.raise_for_status() # Вызывает исключение для ошибок HTTP
            update_info = response.json()

            latest_version_str = update_info.get("latest_version")
            if not latest_version_str:
                self.update_check_finished.emit(False, "", "Не удалось найти 'latest_version' в update.json.")
                return

            # Простая проверка версии (сравнение строк, можно улучшить для семантического версионирования)
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


# Рабочий поток для загрузки обновлений (имитация)
class UpdateDownloader(QThread):
    download_progress = pyqtSignal(int) # Прогресс в процентах
    download_finished = pyqtSignal(bool, str) # Успех, сообщение об ошибке

    def __init__(self, new_version: str):
        super().__init__()
        self.new_version = new_version

    def run(self):
        try:
            # Имитация загрузки
            print(f"Имитация загрузки update.zip для версии {self.new_version}...")
            for i in range(0, 101, 10):
                self.download_progress.emit(i)
                self.msleep(150) # Имитация задержки

            # Имитация успешной загрузки
            self.download_finished.emit(True, "")
            print("Имитация загрузки завершена.")

        except Exception as e:
            self.download_finished.emit(False, f"Ошибка при имитации загрузки: {e}")
            print(f"Ошибка при имитации загрузки: {e}")


# --- Базовый класс для подстраниц настроек ---
class BaseSettingsSubPage(QWidget):
    # Сигнал для возврата на главную страницу настроек
    back_to_main_settings_requested = pyqtSignal()
    # Сигналы для уведомления о сделанном выборе
    language_selected = pyqtSignal(str)
    navigation_mode_selected = pyqtSignal(str)

    def __init__(self, parent=None, settings_content_instance=None):
        super().__init__(parent)
        self.settings_content_instance = settings_content_instance # Ссылка на основной SettingsContent
        
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(20, 20, 20, 20)
        self.main_layout.setSpacing(10)
        self.main_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.setStyleSheet("""
            QWidget {
                background-color: #1c1c1c; /* Фон как у SettingsContent */
                color: white;
                font-family: "Segoe UI", "SF Pro Display", "Roboto", sans-serif;
            }
            QLabel {
                font-size: 16px;
                margin-bottom: 10px;
            }
            QPushButton {
                background-color: #007AFF; /* Синий цвет кнопки */
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 15px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3; /* Цвет при наведении */
            }
            QPushButton:disabled {
                background-color: #555; /* Неактивная кнопка */
                color: #aaa;
            }
            QComboBox {
                border: 1px solid #555;
                border-radius: 5px;
                padding: 8px;
                background-color: #333;
                color: white;
                font-size: 14px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #555;
                background-color: #333;
                selection-background-color: #007AFF;
                color: white;
            }
            QRadioButton {
                color: white;
                font-size: 14px;
                margin-bottom: 5px;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 8px;
                border: 1px solid #999;
                background-color: #444;
            }
            QRadioButton::indicator:hover {
                border: 1px solid #007AFF;
            }
            QRadioButton::indicator:checked {
                background-color: #007AFF;
                border: 1px solid #007AFF;
            }
            QSpinBox {
                border: 1px solid #555;
                border-radius: 5px;
                padding: 5px;
                background-color: #333;
                color: white;
                font-size: 14px;
            }
            QSpinBox::up-button, QSpinBox::down-button {
                width: 20px;
                height: 20px;
                background-color: #007AFF;
                border-radius: 5px;
            }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {
                background-color: #0056b3;
            }
            QSpinBox::up-arrow, QSpinBox::down-arrow {
                image: url(icons/arrow_up_white.png); /* Заглушка, если нет иконки */
                width: 12px;
                height: 12px;
            }
            QSpinBox::down-arrow {
                image: url(icons/arrow_down_white.png); /* Заглушка, если нет иконки */
            }
            QCheckBox {
                color: white;
                font-size: 14px;
                spacing: 5px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border-radius: 4px;
                border: 1px solid #999;
                background-color: #444;
            }
            QCheckBox::indicator:hover {
                border: 1px solid #007AFF;
            }
            QCheckBox::indicator:checked {
                background-color: #007AFF;
                border: 1px solid #007AFF;
            }
            QCheckBox::indicator:checked:hover {
                background-color: #0056b3;
            }

        """)

        # Кнопка "Назад" для подстраницы
        self.back_button = QPushButton("← Назад")
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #007AFF;
                font-size: 16px;
                font-weight: bold;
                padding: 5px;
                text-align: left;
            }
            QPushButton:hover {
                color: #0056b3;
            }
        """)
        self.back_button.clicked.connect(self.back_to_main_settings_requested.emit)
        
        back_button_layout = QHBoxLayout()
        back_button_layout.addWidget(self.back_button, alignment=Qt.AlignLeft)
        back_button_layout.addStretch(1) # Прижимает кнопку влево
        self.main_layout.addLayout(back_button_layout)

    def update_localization(self, language: str):
        """Обновляет тексты на этой странице в соответствии с выбранным языком."""
        localized = self.settings_content_instance.localized_texts.get(language, {})
        self.back_button.setText(f"← {localized.get('Back', 'Назад')}")


# --- Подстраница выбора языка ---
class LanguageSettingsPage(BaseSettingsSubPage):
    def __init__(self, parent=None, settings_content_instance=None, current_language="Русский"):
        super().__init__(parent, settings_content_instance)
        self._current_language = current_language

        # Метки теперь являются атрибутами экземпляра
        self.title_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Language & Region", "Язык и Регион"))
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px; color: #007AFF;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)
        
        self.main_layout.addSpacing(30) # Отступ

        self.instruction_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Choose Language", "Выберите язык:"))
        self.instruction_label.setStyleSheet("font-size: 16px; margin-bottom: 15px;")
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.instruction_label)

        language_layout = QHBoxLayout()
        language_layout.addStretch(1)
        self.language_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Language", "Язык:"))
        self.language_label.setStyleSheet("font-size: 14px;")
        language_layout.addWidget(self.language_label)
        
        self.language_combo = QComboBox()
        self.language_combo.addItems(["Русский", "English", "Deutsch", "Français"])
        self.language_combo.setCurrentText(self._current_language)
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_layout.addWidget(self.language_combo)
        language_layout.addStretch(1)
        self.main_layout.addLayout(language_layout)

        self.main_layout.addStretch(1) # Растяжка для выравнивания содержимого
    
    def _on_language_changed(self, index):
        new_language = self.language_combo.currentText()
        self._current_language = new_language
        self.language_selected.emit(new_language) # Эмитируем сигнал о выбранном языке
        # Обновим UI этой страницы на новый язык
        self.update_localization(new_language)

    def update_localization(self, language: str):
        """Обновляет тексты на этой странице в соответствии с выбранным языком."""
        super().update_localization(language) # Вызов базового метода для кнопки "Назад"
        localized = self.settings_content_instance.localized_texts.get(language, {})
        # Обновляем текст, используя прямые ссылки на атрибуты
        self.title_label.setText(localized.get("Language & Region", "Язык и Регион"))
        self.instruction_label.setText(localized.get("Choose Language", "Выберите язык:"))
        self.language_label.setText(localized.get("Language", "Язык:"))


# --- Подстраница выбора режима навигации ---
class NavigationSettingsPage(BaseSettingsSubPage):
    def __init__(self, parent=None, settings_content_instance=None, initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON):
        super().__init__(parent, settings_content_instance)
        self._selected_navigation_mode = initial_navigation_mode

        # Метки теперь являются атрибутами экземпляра
        self.title_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Navigation Mode", "Режим Навигации"))
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px; color: #007AFF;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)
        
        self.main_layout.addSpacing(30) # Отступ

        self.instruction_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Choose Navigation Mode", "Выберите режим навигации:"))
        self.instruction_label.setStyleSheet("font-size: 16px; margin-bottom: 20px;")
        self.instruction_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.instruction_label)

        self.navigation_group = QButtonGroup(self)
        
        self.three_button_radio = QRadioButton(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Three Buttons", "Три кнопки (Назад, Домой, Недавние)"))
        self.three_button_radio.setStyleSheet("QRadioButton { font-size: 16px; margin-bottom: 10px; } QRadioButton::indicator { width: 16px; height: 16px; }")
        self.three_button_radio.setChecked(True) # Всегда выбран, т.к. это единственный вариант
        self.three_button_radio.setEnabled(False) # Делаем неактивным, чтобы нельзя было снять выбор
        self.navigation_group.addButton(self.three_button_radio)
        self.main_layout.addWidget(self.three_button_radio)
        
        # Добавляем растяжку, чтобы нижние элементы не прилипали к радио-кнопке
        self.main_layout.addStretch(1)
        
        # Так как теперь только один режим, сразу устанавливаем его
        self._on_mode_selected(NAVIGATION_MODE_THREE_BUTTON, True) # Принудительный выбор
        
    def _on_mode_selected(self, mode: str, checked: bool):
        # Этот метод теперь просто подтверждает выбор режима
        if checked:
            self._selected_navigation_mode = mode
            print(f"NavigationSettingsPage: Выбран режим навигации: {self._selected_navigation_mode}")

    def update_localization(self, language: str):
        """Обновляет тексты на этой странице в соответствии с выбранным языком."""
        super().update_localization(language) # Вызов базового метода для кнопки "Назад"
        localized = self.settings_content_instance.localized_texts.get(language, {})
        # Обновляем текст, используя прямые ссылки на атрибуты
        self.title_label.setText(localized.get("Navigation Mode", "Режим Навигации"))
        self.instruction_label.setText(localized.get("Choose Navigation Mode", "Выберите режим навигации:"))
        self.three_button_radio.setText(localized.get("Three Buttons", "Три кнопки (Назад, Домой, Недавние)"))


# --- НОВАЯ ПОДСТРАНИЦА: Настройки Лаунчера ---
class LauncherSettingsPage(BaseSettingsSubPage):
    # Новые сигналы для настроек лаунчера
    icon_size_changed = pyqtSignal(int)
    grid_columns_changed = pyqtSignal(int)
    app_names_visibility_changed = pyqtSignal(bool)

    def __init__(self, parent=None, settings_content_instance=None):
        super().__init__(parent, settings_content_instance)
        # Установим начальные значения для настроек лаунчера
        self._current_icon_size = 70 # Default icon size in LauncherContent's AppIcon
        self._current_grid_columns = 4 # Default columns in LauncherContent
        self._show_app_names = True # Default for app name visibility

        self.title_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Launcher Settings", "Настройки Лаунчера"))
        self.title_label.setStyleSheet("font-size: 24px; font-weight: bold; margin-bottom: 20px; color: #007AFF;")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(self.title_label)

        instruction_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Customize your launcher experience.", "Настройте работу вашего лаунчера."))
        instruction_label.setStyleSheet("font-size: 16px; margin-bottom: 20px;")
        instruction_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(instruction_label)

        # --- Настройка размера иконок ---
        icon_size_layout = QHBoxLayout()
        icon_size_layout.addStretch(1)
        self.icon_size_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Icon Size", "Размер иконок:"))
        icon_size_layout.addWidget(self.icon_size_label)
        
        self.icon_size_spinbox = QSpinBox()
        self.icon_size_spinbox.setRange(40, 100) # Диапазон размеров иконок
        self.icon_size_spinbox.setSingleStep(5) # Шаг изменения размера
        self.icon_size_spinbox.setValue(self._current_icon_size)
        self.icon_size_spinbox.setSuffix(" px")
        self.icon_size_spinbox.valueChanged.connect(self._on_icon_size_changed)
        icon_size_layout.addWidget(self.icon_size_spinbox)
        icon_size_layout.addStretch(1)
        self.main_layout.addLayout(icon_size_layout)

        self.main_layout.addSpacing(15)

        # --- Настройка количества столбцов в сетке ---
        grid_columns_layout = QHBoxLayout()
        grid_columns_layout.addStretch(1)
        self.grid_columns_label = QLabel(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Grid Columns", "Столбцов в сетке:"))
        grid_columns_layout.addWidget(self.grid_columns_label)

        self.grid_columns_combo = QComboBox()
        self.grid_columns_combo.addItems(["3", "4", "5"]) # Возможные количества столбцов
        self.grid_columns_combo.setCurrentText(str(self._current_grid_columns))
        self.grid_columns_combo.currentIndexChanged.connect(self._on_grid_columns_changed)
        grid_columns_layout.addWidget(self.grid_columns_combo)
        grid_columns_layout.addStretch(1)
        self.main_layout.addLayout(grid_columns_layout)

        self.main_layout.addSpacing(15)

        # --- Настройка видимости текста под иконками ---
        show_app_names_layout = QHBoxLayout()
        show_app_names_layout.addStretch(1)
        self.show_app_names_checkbox = QCheckBox(self.settings_content_instance.localized_texts.get(self.settings_content_instance._language, {}).get("Show App Names", "Показывать названия приложений"))
        self.show_app_names_checkbox.setChecked(self._show_app_names)
        self.show_app_names_checkbox.toggled.connect(self._on_app_names_visibility_changed)
        show_app_names_layout.addWidget(self.show_app_names_checkbox)
        show_app_names_layout.addStretch(1)
        self.main_layout.addLayout(show_app_names_layout)

        self.main_layout.addStretch(1)

    def _on_icon_size_changed(self, value: int):
        self._current_icon_size = value
        self.icon_size_changed.emit(value) # Эмитируем сигнал

    def _on_grid_columns_changed(self, index: int):
        value = int(self.grid_columns_combo.currentText())
        self._current_grid_columns = value
        self.grid_columns_changed.emit(value) # Эмитируем сигнал

    def _on_app_names_visibility_changed(self, checked: bool):
        self._show_app_names = checked
        self.app_names_visibility_changed.emit(checked) # Эмитируем сигнал

    def update_localization(self, language: str):
        """Обновляет тексты на этой странице в соответствии с выбранным языком."""
        super().update_localization(language) # Вызов базового метода для кнопки "Назад"
        localized = self.settings_content_instance.localized_texts.get(language, {})
        self.title_label.setText(localized.get("Launcher Settings", "Настройки Лаунчера"))
        
        self.icon_size_label.setText(localized.get("Icon Size", "Размер иконок:"))
        self.grid_columns_label.setText(localized.get("Grid Columns", "Столбцов в сетке:"))
        self.show_app_names_checkbox.setText(localized.get("Show App Names", "Показывать названия приложений"))


# --- Главный виджет настроек ---
class SettingsContent(QFrame):
    # Сигналы для связи с MainWindow
    go_back_to_launcher_requested = pyqtSignal()
    language_changed = pyqtSignal(str)
    navigation_mode_changed = pyqtSignal(str) # Теперь может передавать только один режим
    system_restart_requested = pyqtSignal(str) # Передает новую версию после обновления

    # Новые сигналы для настроек лаунчера (ре-эмитируем сигналы от LauncherSettingsPage)
    launcher_icon_size_changed = pyqtSignal(int)
    launcher_grid_columns_changed = pyqtSignal(int)
    launcher_app_names_visibility_changed = pyqtSignal(bool)


    def __init__(self, parent=None, current_language="Русский", system_version="1.0.0", initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON, user_data_manager=None):
        super().__init__(parent)
        self.main_window = parent
        self._language = current_language
        self._system_version = system_version
        self._current_navigation_mode = initial_navigation_mode
        self.user_data_manager = user_data_manager # Получаем менеджер данных

        self.setStyleSheet("background-color: #1c1c1c; color: white;")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.localized_texts = {
            "Русский": {
                "Settings": "Настройки",
                "General": "Основные",
                "Display & Brightness": "Экран и Яркость",
                "Language & Region": "Язык и Регион",
                "Navigation Mode": "Режим Навигации",
                "Launcher Settings": "Настройки Лаунчера", 
                "Customize your launcher experience.": "Настройте работу вашего лаунчера.", 
                "Icon Size": "Размер иконок:", # НОВОЕ
                "Grid Columns": "Столбцов в сетке:", # НОВОЕ
                "Show App Names": "Показывать названия приложений", # НОВОЕ
                "No specific settings yet. Coming soon!": "Особых настроек пока нет. Скоро будет!", 
                "Privacy": "Приватность",
                "Security": "Безопасность",
                "About": "Об устройстве",
                "System Version": "Версия системы:",
                "Check for Updates": "Проверить обновления",
                "Back to Launcher": "Назад",
                "Choose Language": "Выберите язык:",
                "Language": "Язык:", 
                "Choose Navigation Mode": "Выберите режим навигации:",
                "Three Buttons": "Три кнопки (Назад, Домой, Недавние)",
                "Gestures": "Жесты (свайпы для навигации)",
                "UpdatingTitle": "Проверка обновлений",
                "CheckingUpdates": "Проверка наличия обновлений...",
                "NoUpdates": "Обновлений не найдено. Ваша система актуальна.",
                "UpdatesAvailable": "Доступны обновления! Версия {new_version}. Хотите обновить?",
                "UpdateFailed": "Не удалось проверить обновления. Ошибка: {error}",
                "UpdatingSystem": "Обновление системы...",
                "UpdateSuccessful": "Система успешно обновлена до версии {new_version}! Пожалуйста, перезапустите HIXOS вручную.", 
                "UpdateFailedGeneric": "Ошибка при обновлении. Попробуйте снова.",
                "ConfirmUpdate": "Подтверждение обновления",
                "UpdateWarning": "Обновление займет некоторое время. Убедитесь, что устройство заряжено. Продолжить?",
                "UpdateCancelled": "Обновление отменено.",
                "Back": "Назад" 
            },
            "English": {
                "Settings": "Settings",
                "General": "General",
                "Display & Brightness": "Display & Brightness",
                "Language & Region": "Language & & Region",
                "Navigation Mode": "Navigation Mode",
                "Launcher Settings": "Launcher Settings", 
                "Customize your launcher experience.": "Customize your launcher experience.", 
                "Icon Size": "Icon Size:", # NEW
                "Grid Columns": "Grid Columns:", # NEW
                "Show App Names": "Show App Names", # NEW
                "No specific settings yet. Coming soon!": "No specific settings yet. Coming soon!", 
                "Privacy": "Privacy",
                "Security": "Security",
                "About": "About",
                "System Version": "System Version:",
                "Check for Updates": "Check for Updates",
                "Back to Launcher": "Back to Launcher",
                "Choose Language": "Choose Language:",
                "Language": "Language:", 
                "Choose Navigation Mode": "Choose Navigation Mode:",
                "Three Buttons": "Three Buttons (Back, Home, Recents)",
                "Gestures": "Gestures (swipes for navigation)",
                "UpdatingTitle": "Checking for Updates",
                "CheckingUpdates": "Checking for updates...",
                "NoUpdates": "No updates found. Your system is up to date.",
                "UpdatesAvailable": "Updates available! Version {new_version}. Do you want to update?",
                "UpdateFailed": "Failed to check for updates. Error: {error}",
                "UpdatingSystem": "Updating system...",
                "UpdateSuccessful": "System successfully updated to version {new_version}! Please restart HIXOS manually.", 
                "UpdateFailedGeneric": "Update failed. Please try again.",
                "ConfirmUpdate": "Confirm Update",
                "UpdateWarning": "The update will take some time. Ensure your device is charged. Continue?",
                "UpdateCancelled": "Update cancelled.",
                "Back": "Back" 
            }
        }

        # Используем QStackedWidget для переключения между главной страницей настроек и подстраницами
        self.stacked_pages = QStackedWidget(self)

        # Создаем основную страницу настроек
        self.main_settings_page = QWidget()
        self.main_settings_layout = QVBoxLayout(self.main_settings_page)
        self.main_settings_layout.setContentsMargins(0, 0, 0, 0) # Уберем отступы, чтобы ScrollArea управляла ими

        self.scroll_area = QScrollArea(self.main_settings_page)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; } QWidget { background-color: #1c1c1c; }")
        
        self.scroll_content = QWidget()
        self.scroll_content_layout = QVBoxLayout(self.scroll_content)
        self.scroll_content_layout.setContentsMargins(20, 20, 20, 20)
        self.scroll_content_layout.setSpacing(10)
        self.scroll_content_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.scroll_area.setWidget(self.scroll_content)
        self.main_settings_layout.addWidget(self.scroll_area)


        # Добавляем основную страницу в stacked_pages
        self.stacked_pages.addWidget(self.main_settings_page)

        # Создаем подстраницы
        self.language_page = LanguageSettingsPage(self, settings_content_instance=self, current_language=self._language)
        self.navigation_page = NavigationSettingsPage(self, settings_content_instance=self, initial_navigation_mode=self._current_navigation_mode)
        self.launcher_settings_page = LauncherSettingsPage(self, settings_content_instance=self) 
        
        self.stacked_pages.addWidget(self.language_page)
        self.stacked_pages.addWidget(self.navigation_page)
        self.stacked_pages.addWidget(self.launcher_settings_page) 


        main_vlayout = QVBoxLayout(self)
        main_vlayout.setContentsMargins(0,0,0,0)
        main_vlayout.addWidget(self.stacked_pages) 

        # Ссылки на QLabels для версии системы и кнопку обновления
        self.system_version_label_value = QLabel(self._system_version) 
        self.check_for_updates_button = QPushButton() 

        self.init_main_settings_ui() 
        self._connect_subpage_signals() 
        self._update_localization() 
        
        self.current_new_version = None 

        # Инициализация потоков для обновлений
        self.update_checker_thread = None
        self.update_downloader_thread = None

    def init_main_settings_ui(self):
        # --- Логотип HIXOS ---
        self.logo_label = QLabel(self)
        logo_pixmap = QPixmap("hixos_logo.png") 
        if not logo_pixmap.isNull():
            scaled_logo = logo_pixmap.scaled(150, 150, Qt.KeepAspectRatio, Qt.SmoothTransformation) 
            self.logo_label.setPixmap(scaled_logo)
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.scroll_content_layout.addWidget(self.logo_label)
        else:
            self.logo_label.setText("HIXOS")
            self.logo_label.setStyleSheet("color: white; font-size: 36px; font-weight: bold;")
            self.logo_label.setAlignment(Qt.AlignCenter)
            self.scroll_content_layout.addWidget(self.logo_label)

        # Добавим немного пространства под логотипом
        self.scroll_content_layout.addSpacing(30)


        # Заголовок "Настройки"
        self.settings_title = QLabel(self.localized_texts.get(self._language, {}).get("Settings", "Настройки"))
        self.settings_title.setStyleSheet("font-size: 28px; font-weight: bold; margin-bottom: 20px; color: #007AFF;")
        self.settings_title.setAlignment(Qt.AlignCenter)
        self.scroll_content_layout.addWidget(self.settings_title)

        # Группы настроек
        self._add_settings_group("General", [ 
            self._create_setting_row("Language & Region", lambda: self.stacked_pages.setCurrentWidget(self.language_page)), 
            self._create_setting_row("Navigation Mode", lambda: self.stacked_pages.setCurrentWidget(self.navigation_page)), 
            self._create_setting_row("Launcher Settings", lambda: self.stacked_pages.setCurrentWidget(self.launcher_settings_page)), 
        ])
        
        self._add_settings_group("About", [ 
            self._create_info_row("System Version", self.system_version_label_value), 
            self._create_action_row("Check for Updates", self._check_for_updates, button_instance=self.check_for_updates_button) 
        ])
        
        self.scroll_content_layout.addStretch(1) 

        # Кнопка "Назад" внизу
        self.back_button = QPushButton(self.localized_texts.get(self._language, {}).get("Back to Launcher", "Назад"))
        self.back_button.setStyleSheet("""
            QPushButton {
                background-color: #333;
                color: white;
                border-radius: 10px;
                padding: 12px 25px;
                font-size: 16px;
                font-weight: bold;
                margin-top: 20px;
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        self.back_button.clicked.connect(self.go_back_to_launcher_requested.emit)
        self.scroll_content_layout.addWidget(self.back_button, alignment=Qt.AlignCenter)


    def _connect_subpage_signals(self):
        """Подключает сигналы от подстраниц к методам SettingsContent."""
        self.language_page.back_to_main_settings_requested.connect(self._show_main_settings_page)
        self.language_page.language_selected.connect(self._on_language_selected_from_subpage)

        self.navigation_page.back_to_main_settings_requested.connect(self._show_main_settings_page)
        self.navigation_page.navigation_mode_selected.connect(self._on_navigation_mode_selected_from_subpage)

        self.launcher_settings_page.back_to_main_settings_requested.connect(self._show_main_settings_page)
        # НОВЫЕ: Подключаем сигналы от LauncherSettingsPage к сигналам SettingsContent для ре-эмиссии
        self.launcher_settings_page.icon_size_changed.connect(self.launcher_icon_size_changed.emit)
        self.launcher_settings_page.grid_columns_changed.connect(self.launcher_grid_columns_changed.emit)
        self.launcher_settings_page.app_names_visibility_changed.connect(self.launcher_app_names_visibility_changed.emit)


    def _show_main_settings_page(self):
        """Переключает на главную страницу настроек."""
        self.stacked_pages.setCurrentWidget(self.main_settings_page)
        self._update_localization() # Обновляем тексты на главной странице после возвращения

    def _on_language_selected_from_subpage(self, new_language: str):
        """Обрабатывает выбор языка на подстранице."""
        if new_language != self._language:
            self._language = new_language
            self.language_changed.emit(new_language) # Эмитируем сигнал для MainWindow/Launcher


    def _on_navigation_mode_selected_from_subpage(self, new_mode: str):
        """Обрабатывает выбор режима навигации на подстранице."""
        if new_mode != self._current_navigation_mode:
            self._current_navigation_mode = new_mode
            self.navigation_mode_changed.emit(new_mode) # Эмитируем сигнал для MainWindow/NavigationBar


    def _add_settings_group(self, title_key: str, rows: list):
        group_label = QLabel(self.localized_texts.get(self._language, {}).get(title_key, title_key))
        group_label.setStyleSheet("font-size: 20px; font-weight: bold; color: #BBBBBB; margin-top: 20px; margin-bottom: 10px;")
        self.scroll_content_layout.addWidget(group_label)

        for row_widget in rows:
            self.scroll_content_layout.addWidget(row_widget)

    def _create_setting_row(self, text_key: str, action):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        label = QLabel(self.localized_texts.get(self._language, {}).get(text_key, text_key))
        label.setStyleSheet("font-size: 16px; color: white;")
        row_layout.addWidget(label)
        row_layout.addStretch(1)

        # Кнопка со стрелкой
        button = QPushButton("→")
        button.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                border: none;
                color: #007AFF;
                font-size: 18px;
                padding: 5px;
            }
            QPushButton:hover {
                color: #0056b3;
            }
        """)
        button.setFixedSize(30, 30)
        button.clicked.connect(action)
        row_layout.addWidget(button)
        return row_widget

    def _create_info_row(self, label_text_key: str, value_label_instance: QLabel): 
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        label = QLabel(self.localized_texts.get(self._language, {}).get(label_text_key, label_text_key))
        label.setStyleSheet("font-size: 16px; color: white;")
        row_layout.addWidget(label)
        row_layout.addStretch(1)

        value_label_instance.setStyleSheet("font-size: 16px; color: #AAAAAA;")
        row_layout.addWidget(value_label_instance)
        return row_widget

    def _create_action_row(self, button_text_key: str, action, button_instance: QPushButton = None): 
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)
        row_layout.addStretch(1) 

        button = button_instance if button_instance else QPushButton()
        button.setText(self.localized_texts.get(self._language, {}).get(button_text_key, button_text_key))
        button.setStyleSheet("""
            QPushButton {
                background-color: #333;
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 15px;
                font-weight: bold;
                border: 1px solid #555;
            }
            QPushButton:hover {
                background-color: #555;
            }
            QPushButton:pressed {
                background-color: #666;
            }
        """)
        button.clicked.connect(action)
        row_layout.addWidget(button)
        row_layout.addStretch(1) 
        return row_widget


    def _show_language_settings(self):
        self.language_page._current_language = self._language 
        self.language_page.language_combo.setCurrentText(self._language) 
        self.language_page.update_localization(self._language) 
        self.stacked_pages.setCurrentWidget(self.language_page)


    def _show_navigation_settings(self):
        self.navigation_page._selected_navigation_mode = self._current_navigation_mode 
        self.navigation_page.three_button_radio.setChecked(self._current_navigation_mode == NAVIGATION_MODE_THREE_BUTTON)
        self.navigation_page.update_localization(self._language) 
        self.stacked_pages.setCurrentWidget(self.navigation_page)

    def _show_launcher_settings(self):
        """Переключает на страницу настроек лаунчера."""
        self.launcher_settings_page.update_localization(self._language)
        self.stacked_pages.setCurrentWidget(self.launcher_settings_page)


    def _check_for_updates(self):
        """
        Инициирует проверку обновлений в отдельном потоке.
        """
        self.check_for_updates_button.setEnabled(False) 
        self._show_message_box(
            self.localized_texts.get(self._language, {}).get("UpdatingTitle", "Проверка обновлений"),
            self.localized_texts.get(self._language, {}).get("CheckingUpdates", "Проверка наличия обновлений..."),
            QMessageBox.Information,
            modal=True 
        )
        
        self.update_checker_thread = UpdateChecker(self._system_version)
        self.update_checker_thread.update_check_finished.connect(self._on_update_check_finished)
        self.update_checker_thread.start()

    def _on_update_check_finished(self, update_available: bool, new_version: str, error_message: str):
        """
        Обрабатывает результат проверки обновлений.
        """
        self.check_for_updates_button.setEnabled(True) 
        if update_available:
            self.current_new_version = new_version
            reply = self._show_message_box(
                self.localized_texts.get(self._language, {}).get("ConfirmUpdate", "Подтверждение обновления"),
                self.localized_texts.get(self._language, {}).get("UpdatesAvailable", "Доступны обновления! Версия {new_version}. Хотите обновить?").format(new_version=self.current_new_version),
                QMessageBox.Question,
                standard_buttons=QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self._initiate_update_download()
            else:
                self._show_message_box(
                    self.localized_texts.get(self._language, {}).get("UpdatingTitle", "Обновления"),
                    self.localized_texts.get(self._language, {}).get("UpdateCancelled", "Обновление отменено."),
                    QMessageBox.Information
                )
        else:
            if error_message:
                self._show_message_box(
                    self.localized_texts.get(self._language, {}).get("UpdateFailed", "Ошибка обновления"),
                    self.localized_texts.get(self._language, {}).get("UpdateFailed", "Не удалось проверить обновления. Ошибка: {error}").format(error=error_message),
                    QMessageBox.Critical
                )
            else:
                self._show_message_box(
                    self.localized_texts.get(self._language, {}).get("UpdatingTitle", "Обновления"),
                    self.localized_texts.get(self._language, {}).get("NoUpdates", "Обновлений не найдено. Ваша система актуальна."),
                    QMessageBox.Information
                )

    def _initiate_update_download(self):
        """
        Инициирует имитацию загрузки обновления в отдельном потоке.
        """
        self.check_for_updates_button.setEnabled(False) 
        self._show_message_box(
            self.localized_texts.get(self._language, {}).get("UpdatingTitle", "Обновление системы"),
            self.localized_texts.get(self._language, {}).get("UpdatingSystem", "Обновление системы..."),
            QMessageBox.Information,
            modal=True 
        )

        self.update_downloader_thread = UpdateDownloader(self.current_new_version)
        self.update_downloader_thread.download_finished.connect(self._on_update_download_finished)
        self.update_downloader_thread.start()

    def _on_update_download_finished(self, success: bool, error_message: str):
        """
        Обрабатывает результат загрузки обновления.
        """
        self.check_for_updates_button.setEnabled(True) 
        if success:
            self._system_version = self.current_new_version 
            self.system_version_label_value.setText(self._system_version) 
            
            self.system_restart_requested.emit(self._system_version) 
            
            self._show_message_box(
                self.localized_texts.get(self._language, {}).get("UpdatingTitle", "Обновление"),
                self.localized_texts.get(self._language, {}).get("UpdateSuccessful", "Система успешно обновлена до версии {new_version}! Пожалуйста, перезапустите HIXOS вручную.").format(new_version=self._system_version),
                QMessageBox.Information
            )
        else:
            self._show_message_box(
                self.localized_texts.get(self._language, {}).get("UpdatingTitle", "Обновление"),
                self.localized_texts.get(self._language, {}).get("UpdateFailedGeneric", "Ошибка при обновлении. Попробуйте снова.") + f" ({error_message})",
                QMessageBox.Critical
            )


    def _show_message_box(self, title: str, text: str, icon: QMessageBox.Icon, standard_buttons=QMessageBox.Ok, modal=False, timeout=0):
        """
        Вспомогательная функция для отображения QMessageBox.
        Добавлена поддержка таймаута для автоматического закрытия.
        """
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle(title)
        msg_box.setText(text)
        msg_box.setIcon(icon)
        msg_box.setStandardButtons(standard_buttons)

        if modal:
            msg_box.setWindowModality(Qt.ApplicationModal) 
        
        if timeout > 0:
            QTimer.singleShot(timeout, msg_box.close)

        return msg_box.exec_() 


    def set_initial_preferences(self, language: str, navigation_mode: str, system_version: str): 
        """Устанавливает начальные предпочтения, например, при загрузке из Firestore."""
        self._language = language
        self._current_navigation_mode = navigation_mode
        self._system_version = system_version 
        
        self.language_page._current_language = language 
        self.navigation_page._selected_navigation_mode = navigation_mode 
        self.system_version_label_value.setText(self._system_version) 
        self._update_localization() 

    def _update_localization(self):
        """Обновляет все локализуемые тексты в UI настроек."""
        current_locale = self.localized_texts.get(self._language, self.localized_texts["Русский"])

        self.settings_title.setText(current_locale.get("Settings", "Настройки"))
        
        for i in range(self.scroll_content_layout.count()):
            item_widget = self.scroll_content_layout.itemAt(i).widget()
            if isinstance(item_widget, QLabel):
                if item_widget.text() in [self.localized_texts["Русский"]["General"], self.localized_texts["English"]["General"]]:
                    item_widget.setText(current_locale.get("General", "Основные"))
                elif item_widget.text() in [self.localized_texts["Русский"]["About"], self.localized_texts["English"]["About"]]:
                    item_widget.setText(current_locale.get("About", "Об устройстве"))
            elif isinstance(item_widget, QWidget): 
                row_layout = item_widget.layout()
                if row_layout is None: 
                    continue 
                for j in range(row_layout.count()):
                    item = row_layout.itemAt(j)
                    if item and item.widget():
                        sub_widget = item.widget()
                        if isinstance(sub_widget, QLabel):
                            text_to_check = sub_widget.text()
                            if text_to_check in [self.localized_texts["Русский"]["Language & Region"], self.localized_texts["English"]["Language & Region"]]:
                                sub_widget.setText(current_locale.get("Language & Region", "Язык и Регион"))
                            elif text_to_check in [self.localized_texts["Русский"]["Navigation Mode"], self.localized_texts["English"]["Navigation Mode"]]:
                                sub_widget.setText(current_locale.get("Navigation Mode", "Режим Навигации"))
                            elif text_to_check in [self.localized_texts["Русский"]["Launcher Settings"], self.localized_texts["English"]["Launcher Settings"]]: 
                                sub_widget.setText(current_locale.get("Launcher Settings", "Настройки Лаунчера")) 
                            elif text_to_check in [self.localized_texts["Русский"]["System Version"], self.localized_texts["English"]["System Version"]]:
                                sub_widget.setText(current_locale.get("System Version", "Версия системы:"))
                                self.system_version_label_value.setText(self._system_version) 
                        elif isinstance(sub_widget, QPushButton):
                            if sub_widget is self.check_for_updates_button:
                                sub_widget.setText(current_locale.get("Check for Updates", "Проверить обновления"))

        self.back_button.setText(current_locale.get("Back to Launcher", "Назад"))
        
        self.language_page.update_localization(self._language)
        self.navigation_page.update_localization(self._language)
        self.launcher_settings_page.update_localization(self._language) 

        self.update() 

# Для тестирования SettingsContent отдельно
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    class DummyUserDataManager:
        def load_user_data(self): 
            print("DummyDataManager: Loading dummy data (no save).")
            return {"username": "ТестовыйПользователь", "language": "Русский", "navigation_mode": "three_button", "system_version": "1.0.0"} 
        def save_user_data(self, data): 
            print(f"DummyDataManager: Saving dummy data (no actual save): {data}")
        @property
        def user_id(self): return "test_user"
        @user_id.setter
        def user_id(self, new_id): 
            print(f"DummyDataManager: User ID set to {new_id} (no actual save).")

    settings_window = QMainWindow()
    settings_window.setFixedSize(519, 950)
    
    settings_content = SettingsContent(settings_window, current_language="Русский", system_version="1.0.0", user_data_manager=DummyUserDataManager())
    
    def on_back():
        print("Вернуться в лаунчер запрошено!")
        settings_window.close()

    def on_lang_changed(lang):
        print(f"Язык изменен на: {lang}")

    def on_nav_changed(mode):
        print(f"Режим навигации изменен на: {mode}")

    def on_launcher_icon_size_changed(size):
        print(f"Размер иконок лаунчера изменен на: {size}")

    def on_launcher_grid_columns_changed(columns):
        print(f"Количество столбцов лаунчера изменено на: {columns}")

    def on_launcher_app_names_visibility_changed(visible):
        print(f"Видимость названий приложений лаунчера: {visible}")

    def on_system_restart_requested(new_version):
        print(f"Система запросила перезапуск для применения обновления до версии {new_version}!")
        settings_window.close() 
        QMessageBox.information(None, "Перезапуск HIXOS", f"HIXOS обновился до версии {new_version}. Пожалуйста, перезапустите приложение вручную, чтобы применить изменения.")


    settings_content.go_back_to_launcher_requested.connect(on_back)
    settings_content.language_changed.connect(on_lang_changed)
    settings_content.navigation_mode_changed.connect(on_nav_changed)
    # НОВЫЕ ПОДКЛЮЧЕНИЯ для настроек лаунчера
    settings_content.launcher_icon_size_changed.connect(on_launcher_icon_size_changed)
    settings_content.launcher_grid_columns_changed.connect(on_launcher_grid_columns_changed)
    settings_content.launcher_app_names_visibility_changed.connect(on_launcher_app_names_visibility_changed)
    settings_content.system_restart_requested.connect(on_system_restart_requested) 

    settings_window.setCentralWidget(settings_content)
    settings_window.show()
    sys.exit(app.exec_())
