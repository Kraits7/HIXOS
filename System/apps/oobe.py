# apps/oobe.py
import sys
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox,
    QStackedWidget, QLineEdit, QScrollArea, QApplication, QMessageBox,
    QTextBrowser, QRadioButton, QButtonGroup, QSpacerItem, QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtGui import QFont, QColor, QBrush, QPainter, QLinearGradient

# Импортируем константы навигации из navigation_bar
from ui.navigation_bar import NAVIGATION_MODE_THREE_BUTTON, NAVIGATION_MODE_GESTURES


# Базовый класс для страниц OOBE, содержит общие стили и навигационные кнопки
class BaseOOBEPage(QWidget):
    # Сигналы для навигации между страницами OOBE
    next_page_requested = pyqtSignal()
    prev_page_requested = pyqtSignal()
    # Сигнал для завершения OOBE, передает выбранный язык, режим навигации и имя пользователя
    finish_oobe_requested = pyqtSignal(str, str, str) 

    def __init__(self, parent=None, oobe_content_instance=None): # Добавлен oobe_content_instance
        super().__init__(parent)
        self.oobe_content_instance = oobe_content_instance # Сохраняем ссылку на OOBEContent

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(30, 30, 30, 30)
        self.main_layout.setSpacing(15) # Увеличен отступ между элементами
        self.main_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        
        # Общие стили для всех страниц OOBE в стиле OxygenOS
        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a; /* Очень темный фон */
                color: white;
                font-family: "Inter", "Segoe UI", "SF Pro Display", "Roboto", sans-serif;
            }
            QLabel {
                font-size: 16px;
                margin-bottom: 5px; /* Уменьшен отступ */
            }
            QLabel#pageTitle { /* Стиль для заголовков страниц */
                font-size: 28px;
                font-weight: bold;
                color: #007AFF; /* Основной акцентный цвет */
                margin-bottom: 25px;
            }
            QLabel#instructionText { /* Стиль для инструкций */
                font-size: 15px;
                color: #BBBBBB;
                margin-bottom: 20px;
            }
            QPushButton {
                background-color: #007AFF; /* Синий цвет кнопки */
                color: white;
                border-radius: 12px; /* Более скругленные углы */
                padding: 15px 30px; /* Увеличенный паддинг */
                font-size: 18px; /* Увеличенный шрифт */
                font-weight: bold;
                min-height: 45px; /* Минимальная высота кнопки */
            }
            QPushButton:hover {
                background-color: #0056b3; /* Цвет при наведении */
            }
            QPushButton:pressed {
                background-color: #004d9c; /* Цвет при нажатии */
            }
            QPushButton:disabled {
                background-color: #333333; /* Неактивная кнопка */
                color: #888888;
            }
            QLineEdit {
                border: 1px solid #444; /* Более темная рамка */
                border-radius: 10px; /* Скругленные углы */
                padding: 12px; /* Увеличенный паддинг */
                background-color: #2c2c2c; /* Темный фон поля ввода */
                color: white;
                font-size: 16px;
            }
            QComboBox {
                border: 1px solid #444;
                border-radius: 10px;
                padding: 12px;
                background-color: #2c2c2c;
                color: white;
                font-size: 16px;
            }
            QComboBox::drop-down {
                border: 0px;
            }
            QComboBox QAbstractItemView {
                border: 1px solid #444;
                background-color: #2c2c2c;
                selection-background-color: #007AFF;
                color: white;
            }
            QTextBrowser {
                background-color: #2c2c2c;
                border: 1px solid #444;
                border-radius: 10px;
                padding: 15px;
                color: #DDDDDD; /* Более светлый текст */
                font-size: 14px;
            }
            QRadioButton {
                color: white;
                font-size: 16px; /* Увеличенный шрифт */
                margin-bottom: 10px; /* Увеличенный отступ */
            }
            QRadioButton::indicator {
                width: 18px; /* Увеличенный индикатор */
                height: 18px;
                border-radius: 9px; /* Круглый индикатор */
                border: 2px solid #555; /* Более толстая рамка */
                background-color: #333;
            }
            QRadioButton::indicator:hover {
                border: 2px solid #007AFF;
            }
            QRadioButton::indicator:checked {
                background-color: #007AFF;
                border: 2px solid #007AFF;
            }
            /* Стиль для кнопки "Назад" */
            QPushButton#backButton {
                background-color: transparent;
                border: 1px solid #444; /* Тонкая рамка */
                color: #007AFF;
                border-radius: 12px;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
            }
            QPushButton#backButton:hover {
                background-color: rgba(0, 122, 255, 0.1); /* Легкий синий фон при наведении */
            }
        """)

    def add_navigation_buttons(self, show_back=True, show_next=True, next_text="Далее", finish_text="Завершить"):
        nav_layout = QHBoxLayout()
        nav_layout.addStretch(1) # Растяжка для выравнивания кнопок справа

        if show_back:
            back_button = QPushButton("Назад")
            back_button.setObjectName("backButton") # Устанавливаем objectName для специфичного QSS
            back_button.clicked.connect(self.prev_page_requested.emit)
            nav_layout.addWidget(back_button)
            nav_layout.addSpacing(15) # Отступ между кнопками
        
        if show_next:
            if next_text == "Завершить" or next_text == "Начать работу":
                self.next_button = QPushButton(finish_text)
                self.next_button.clicked.connect(
                    lambda: self.finish_oobe_requested.emit(
                        self.oobe_content_instance._current_language, 
                        self.oobe_content_instance._current_navigation_mode,
                        self.oobe_content_instance._username 
                    )
                )
            else:
                self.next_button = QPushButton(next_text)
                self.next_button.clicked.connect(self.next_page_requested.emit)
            nav_layout.addWidget(self.next_button)
        
        self.main_layout.addLayout(nav_layout)
    
    def get_selected_language(self):
        return "Русский" 

    def get_selected_navigation_mode(self):
        return NAVIGATION_MODE_THREE_BUTTON

    def get_username(self):
        return ""


# OOBE Страница 1: Приветствие и Выбор языка
class WelcomeLanguagePage(BaseOOBEPage):
    def __init__(self, parent=None, oobe_content_instance=None, current_language="Русский"): 
        super().__init__(parent, oobe_content_instance) 
        
        self._selected_language = current_language 

        title_label = QLabel("Добро пожаловать в HIXOS!")
        title_label.setObjectName("pageTitle")
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)

        instruction_label = QLabel("Пожалуйста, выберите язык системы:")
        instruction_label.setObjectName("instructionText")
        instruction_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(instruction_label)

        language_layout = QHBoxLayout()
        language_layout.addStretch(1)
        language_label = QLabel("Язык:")
        language_label.setStyleSheet("font-size: 16px;") # Увеличиваем шрифт для метки
        language_layout.addWidget(language_label)
        
        self.language_combo = QComboBox()
        self.language_combo.addItems(["Русский", "English", "Deutsch", "Français"])
        self.language_combo.setCurrentText(self._selected_language) 
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        language_layout.addWidget(self.language_combo)
        language_layout.addStretch(1)
        self.main_layout.addLayout(language_layout)

        self.main_layout.addStretch(1) 
        self.add_navigation_buttons(show_back=False, next_text="Далее")

    def _on_language_changed(self, index):
        self._selected_language = self.language_combo.currentText()

    def get_selected_language(self):
        return self._selected_language


# OOBE Страница 2: Лицензионное Соглашение с Конечным Пользователем (EULA)
class EULAPage(BaseOOBEPage):
    def __init__(self, parent=None, oobe_content_instance=None): 
        super().__init__(parent, oobe_content_instance) 

        title_label = QLabel("Лицензионное Соглашение")
        title_label.setObjectName("pageTitle")
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)

        instruction_label = QLabel("Пожалуйста, ознакомьтесь с условиями использования HIXOS.")
        instruction_label.setObjectName("instructionText")
        instruction_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(instruction_label)

        eula_text = """
        ДОБРО ПОЖАЛОВАТЬ В HIXOS!

        ВНИМАТЕЛЬНО ПРОЧТИТЕ ДАННОЕ ЛИЦЕНЗИОННОЕ СОГЛАШЕНИЕ ПОЛЬЗОВАТЕЛЯ (далее – «Соглашение»).
        ИСПОЛЬЗУЯ СИСТЕМУ HIXOS, ВЫ ПОДТВЕРЖДАЕТЕ СВОЕ СОГЛАСИЕ СО ВСЕМИ УСЛОВИЯМИ ДАННОГО СОГЛАШЕНИЯ.

        1. Лицензия. Вам предоставляется неисключительная, непередаваемая лицензия на использование HIXOS.
        2. Ограничения. Вы не можете декомпилировать, изменять, распространять или продавать HIXOS.
        3. Отказ от гарантий. HIXOS предоставляется «как есть», без каких-либо гарантий.
        4. Ограничение ответственности. Мы не несем ответственности за любые убытки, возникшие в результате использования HIXOS.
        5. Изменения. Мы оставляем за собой право изменять это Соглашение в любое время.

        Нажимая "Принять и Продолжить", вы соглашаетесь с этими условиями.
        """
        
        self.eula_viewer = QTextBrowser()
        self.eula_viewer.setPlainText(eula_text)
        self.eula_viewer.setReadOnly(True) 
        self.main_layout.addWidget(self.eula_viewer)

        self.accept_checkbox = QPushButton("Я принимаю условия соглашения")
        self.accept_checkbox.setCheckable(True) 
        self.accept_checkbox.setChecked(False)
        self.accept_checkbox.setStyleSheet("""
            QPushButton {
                background-color: #333; /* Темнее, чем основные кнопки */
                color: white;
                border-radius: 12px;
                padding: 12px 25px;
                font-size: 16px;
                font-weight: bold;
                margin-top: 15px;
            }
            QPushButton:checked {
                background-color: #34C759; /* Зеленый при принятии */
            }
            QPushButton:hover {
                background-color: #555;
            }
        """)
        self.main_layout.addWidget(self.accept_checkbox, alignment=Qt.AlignCenter)

        self.main_layout.addStretch(1)
        self.add_navigation_buttons(show_back=True, next_text="Принять и Продолжить")
        
        self.next_button.setEnabled(False) 
        self.accept_checkbox.toggled.connect(self.next_button.setEnabled) 


# OOBE Страница 3: Настройка учетной записи пользователя
class UserSetupPage(BaseOOBEPage):
    def __init__(self, parent=None, oobe_content_instance=None): 
        super().__init__(parent, oobe_content_instance) 
        self._username = "" 

        title_label = QLabel("Создайте учетную запись")
        title_label.setObjectName("pageTitle")
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)

        instruction_label = QLabel("Введите имя пользователя для вашей системы HIXOS.")
        instruction_label.setObjectName("instructionText")
        instruction_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(instruction_label)

        username_layout = QHBoxLayout()
        username_layout.addStretch(1)
        username_label = QLabel("Имя пользователя:")
        username_label.setStyleSheet("font-size: 16px;")
        username_layout.addWidget(username_label)
        
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("Ваше имя")
        self.username_input.textChanged.connect(self._on_username_changed) 
        username_layout.addWidget(self.username_input)
        username_layout.addStretch(1)
        self.main_layout.addLayout(username_layout)

        self.main_layout.addSpacing(15) 

        self.main_layout.addStretch(1)
        self.add_navigation_buttons(show_back=True, next_text="Создать учетную запись")
        
        self.next_button.setEnabled(False)
        self.username_input.textChanged.connect(self._check_input)

    def _check_input(self, text):
        self.next_button.setEnabled(bool(text.strip())) 

    def _on_username_changed(self, text):
        self._username = text 

    def get_username(self):
        return self._username 


# OOBE Страница 4: Выбор типа навигации
class NavigationChoicePage(BaseOOBEPage):
    def __init__(self, parent=None, oobe_content_instance=None, initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON): 
        super().__init__(parent, oobe_content_instance) 
        self._selected_navigation_mode = initial_navigation_mode

        title_label = QLabel("Выберите тип навигации")
        title_label.setObjectName("pageTitle")
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)

        instruction_label = QLabel("Как вы предпочитаете управлять системой?")
        instruction_label.setObjectName("instructionText")
        instruction_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(instruction_label)

        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)

        self.three_button_radio = QRadioButton("Три кнопки (Назад, Домой, Недавние)")
        self.three_button_radio.setStyleSheet("QRadioButton { font-size: 16px; margin-bottom: 10px; } QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #555; background-color: #333; } QRadioButton::indicator:checked { background-color: #007AFF; border: 2px solid #007AFF; }")
        self.three_button_radio.setChecked(self._selected_navigation_mode == NAVIGATION_MODE_THREE_BUTTON)
        self.three_button_radio.toggled.connect(lambda checked: self._on_mode_selected(NAVIGATION_MODE_THREE_BUTTON, checked))
        self.navigation_group.addButton(self.three_button_radio)
        self.main_layout.addWidget(self.three_button_radio)

        self.gestures_radio = QRadioButton("Жесты (свайпы для навигации)")
        self.gestures_radio.setStyleSheet("QRadioButton { font-size: 16px; margin-bottom: 10px; } QRadioButton::indicator { width: 18px; height: 18px; border-radius: 9px; border: 2px solid #555; background-color: #333; } QRadioButton::indicator:checked { background-color: #007AFF; border: 2px solid #007AFF; }")
        self.gestures_radio.setChecked(self._selected_navigation_mode == NAVIGATION_MODE_GESTURES)
        self.gestures_radio.toggled.connect(lambda checked: self._on_mode_selected(NAVIGATION_MODE_GESTURES, checked))
        self.navigation_group.addButton(self.gestures_radio)
        self.main_layout.addWidget(self.gestures_radio)
        
        self.main_layout.addStretch(1)
        
        self.add_navigation_buttons(show_back=True, next_text="Далее")
        
    def _on_mode_selected(self, mode: str, checked: bool):
        if checked:
            self._selected_navigation_mode = mode
            print(f"NavigationChoicePage: Выбран режим навигации: {self._selected_navigation_mode}")

    def get_selected_navigation_mode(self):
        return self._selected_navigation_mode


# OOBE Страница 5: Завершение настройки
class FinalOOBEPage(BaseOOBEPage):
    def __init__(self, parent=None, oobe_content_instance=None): 
        super().__init__(parent, oobe_content_instance) 

        title_label = QLabel("Настройка завершена!")
        title_label.setObjectName("pageTitle")
        title_label.setStyleSheet("font-size: 32px; font-weight: bold; margin-bottom: 20px; color: #34C759;") # Более крупный шрифт, зеленый цвет
        title_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(title_label)

        info_label = QLabel("Поздравляем! Ваша система HIXOS готова к использованию.")
        info_label.setObjectName("instructionText")
        info_label.setStyleSheet("font-size: 18px;") # Увеличенный шрифт
        info_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(info_label)

        enjoy_label = QLabel("Наслаждайтесь!")
        enjoy_label.setStyleSheet("font-size: 24px; font-style: italic; margin-top: 30px; color: #BBBBBB;") # Более крупный, серый
        enjoy_label.setAlignment(Qt.AlignCenter)
        self.main_layout.addWidget(enjoy_label)

        self.main_layout.addStretch(1)
        self.add_navigation_buttons(show_back=False, show_next=True, next_text="Завершить", finish_text="Начать работу")


# Главный виджет OOBE (управляет страницами)
class OOBEContent(QWidget):
    # Сигнал, который отправляется, когда OOBE полностью завершено
    oobe_finished = pyqtSignal(str, str, str) 

    def __init__(self, parent=None, current_language="Русский", initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON, user_data_manager=None):
        super().__init__(parent)
        self.main_window = parent
        self._current_language = current_language 
        self._current_navigation_mode = initial_navigation_mode 
        self.user_data_manager = user_data_manager 
        self._username = "" 

        self.setStyleSheet("background-color: #1a1a1a;") # Основной фон для OOBEContent

        main_vlayout = QVBoxLayout(self)
        main_vlayout.setContentsMargins(0,0,0,0)
        main_vlayout.setSpacing(0)

        # --- Индикатор прогресса ---
        self.progress_indicator_layout = QHBoxLayout()
        self.progress_indicator_layout.setContentsMargins(0, 15, 0, 15) # Отступы сверху/снизу
        self.progress_indicator_layout.setSpacing(10)
        self.progress_indicator_layout.setAlignment(Qt.AlignCenter)
        main_vlayout.addLayout(self.progress_indicator_layout)

        self.progress_dots = []
        num_pages = 5 # Количество страниц OOBE
        for i in range(num_pages):
            dot = QFrame(self)
            dot.setFixedSize(10, 10) # Размер точки
            dot.setStyleSheet("background-color: #444; border-radius: 5px;") # Неактивная точка
            self.progress_dots.append(dot)
            self.progress_indicator_layout.addWidget(dot)
        
        main_vlayout.addSpacing(10) # Отступ между индикатором и страницами

        self.stacked_pages = QStackedWidget(self) 
        main_vlayout.addWidget(self.stacked_pages, 1) # Растягиваем stacked_pages

        self._create_pages()
        self._connect_signals()
        
        self.stacked_pages.setCurrentIndex(0) 
        self._update_progress_indicator(0) # Обновляем индикатор при старте

        # Подключаем сигнал изменения текущей страницы для обновления индикатора
        self.stacked_pages.currentChanged.connect(self._update_progress_indicator)

    def _create_pages(self):
        self.welcome_page = WelcomeLanguagePage(self, oobe_content_instance=self, current_language=self._current_language) 
        self.eula_page = EULAPage(self, oobe_content_instance=self)
        self.user_setup_page = UserSetupPage(self, oobe_content_instance=self)
        self.navigation_choice_page = NavigationChoicePage(self, oobe_content_instance=self, initial_navigation_mode=self._current_navigation_mode)
        self.final_page = FinalOOBEPage(self, oobe_content_instance=self)

        self.stacked_pages.addWidget(self.welcome_page)
        self.stacked_pages.addWidget(self.eula_page)
        self.stacked_pages.addWidget(self.user_setup_page)
        self.stacked_pages.addWidget(self.navigation_choice_page)
        self.stacked_pages.addWidget(self.final_page)

    def _connect_signals(self):
        self.welcome_page.next_page_requested.connect(self._next_page)

        self.eula_page.next_page_requested.connect(self._next_page)
        self.eula_page.prev_page_requested.connect(self._prev_page)

        self.user_setup_page.next_page_requested.connect(self._next_page)
        self.user_setup_page.prev_page_requested.connect(self._prev_page)
        
        self.navigation_choice_page.next_page_requested.connect(self._next_page)
        self.navigation_choice_page.prev_page_requested.connect(self._prev_page)

        self.final_page.finish_oobe_requested.connect(self._handle_oobe_finish)

    def _next_page(self):
        current_index = self.stacked_pages.currentIndex()
        if current_index < self.stacked_pages.count() - 1:
            if isinstance(self.stacked_pages.widget(current_index), WelcomeLanguagePage):
                self._current_language = self.welcome_page.get_selected_language()
            elif isinstance(self.stacked_pages.widget(current_index), NavigationChoicePage):
                self._current_navigation_mode = self.navigation_choice_page.get_selected_navigation_mode()
            elif isinstance(self.stacked_pages.widget(current_index), UserSetupPage):
                self._username = self.user_setup_page.username_input.text().strip()

            self.stacked_pages.setCurrentIndex(current_index + 1)

    def _prev_page(self):
        current_index = self.stacked_pages.currentIndex()
        if current_index > 0:
            self.stacked_pages.setCurrentIndex(current_index - 1)

    def _update_progress_indicator(self, index: int):
        """Обновляет внешний вид точек индикатора прогресса."""
        for i, dot in enumerate(self.progress_dots):
            if i == index:
                dot.setStyleSheet("background-color: #007AFF; border-radius: 5px;") # Активная точка синяя
            else:
                dot.setStyleSheet("background-color: #444; border-radius: 5px;") # Неактивная точка серая

    def _handle_oobe_finish(self, selected_language, selected_navigation_mode, username):
        self.oobe_finished.emit(selected_language, selected_navigation_mode, username)


# Это блок для тестирования OOBEContent отдельно (можно удалить после интеграции в Starter.py)
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Создаем заглушки для отсутствующих иконок, если их нет
    if not os.path.exists("icons/arrow_down_white.png"):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("white"))
        painter.drawLine(5, 8, 10, 13)
        painter.drawLine(15, 8, 10, 13)
        painter.end()
        pixmap.save("icons/arrow_down_white.png")
        print("Создана заглушка для icons/arrow_down_white.png")

    if not os.path.exists("icons/arrow_up_white.png"):
        pixmap = QPixmap(20, 20)
        pixmap.fill(QColor("transparent"))
        painter = QPainter(pixmap)
        painter.setPen(QColor("white"))
        painter.drawLine(5, 13, 10, 8)
        painter.drawLine(15, 13, 10, 8)
        painter.end()
        pixmap.save("icons/arrow_up_white.png")
        print("Создана заглушка для icons/arrow_up_white.png")

    # Имитация отсутствия hixos_logo.png
    if not os.path.exists("hixos_logo.png"):
        print("ПРЕДУПРЕЖДЕНИЕ: hixos_logo.png не найдена. Убедитесь, что она есть в корневой папке.")


    window = QWidget()
    window.setWindowTitle("HIXOS OOBE Test")
    window.setGeometry(100, 100, 519, 950) 
    window.setStyleSheet("background-color: #1a1a1a;")

    class DummyUserDataManager:
        def load_user_data(self): 
            print("DummyDataManager: Loading dummy data (no save).")
            return {"username": "ТестовыйПользователь", "language": "Русский", "navigation_mode": NAVIGATION_MODE_THREE_BUTTON, "system_version": "1.0.0"}
        def save_user_data(self, data): 
            print(f"DummyDataManager: Saving dummy data (no actual save): {data}")
        @property
        def user_id(self): return "test_user"
        @user_id.setter
        def user_id(self, new_id): 
            print(f"DummyDataManager: User ID set to {new_id} (no actual save).")

    oobe_widget = OOBEContent(window, current_language="Русский", initial_navigation_mode=NAVIGATION_MODE_THREE_BUTTON, user_data_manager=DummyUserDataManager())
    
    def handle_oobe_complete(lang, nav_mode, username): 
        QMessageBox.information(window, "OOBE Завершено", f"OOBE успешно завершено!\nВыбран язык: {lang}\nРежим навигации: {nav_mode}\nИмя пользователя: {username}\nТеперь можно было бы перейти к лаунчеру.")
        window.close() 

    oobe_widget.oobe_finished.connect(handle_oobe_complete)

    layout = QVBoxLayout(window)
    layout.addWidget(oobe_widget)
    window.show()
    sys.exit(app.exec_())
