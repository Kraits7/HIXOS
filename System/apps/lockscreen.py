# apps/lockscreen.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QGraphicsOpacityEffect, QHBoxLayout, QSpacerItem
from PyQt5.QtGui import QFont, QColor, QPixmap, QBrush, QPainter, QLinearGradient, QIcon
from PyQt5.QtCore import Qt, QTimer, QTime, pyqtSignal, QPropertyAnimation, QEasingCurve, QRect, QPoint, QSize, QDate

import os

class LockScreenContent(QWidget):
    unlocked_requested = pyqtSignal() # Сигнал, эмитируемый при разблокировке
    flashlight_toggled = pyqtSignal() # Сигнал-заглушка для фонарика
    camera_opened = pyqtSignal() # Сигнал-заглушка для камеры

    def __init__(self, parent=None, initial_username="Пользователь"):
        super().__init__(parent)
        self.initial_username = initial_username
        self.current_username = initial_username

        # Фон экрана блокировки (можно добавить изображение или градиент, если нужно)
        self.setStyleSheet("background-color: black;") 

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)
        self.layout.setAlignment(Qt.AlignCenter) # Выравниваем основной контент по центру

        # Верхний отступ, чтобы сместить контент немного вниз от самого верха (область статус-бара)
        self.layout.addSpacing(50) 

        # Метка для времени
        self.time_label = QLabel("00:00")
        self.time_label.setStyleSheet("color: white; font-size: 88px; font-weight: bold;") # Увеличенный размер шрифта времени
        self.time_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.time_label)

        # Метка для даты
        self.date_label = QLabel("Суббота, 29 июня")
        self.date_label.setStyleSheet("color: #CCCCCC; font-size: 22px; margin-bottom: 80px;") # Увеличенный размер шрифта даты, больший отступ снизу
        self.date_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.date_label)

        self.layout.addStretch(1) # Растяжка, чтобы прижать нижние элементы вниз

        # Макет для кнопок фонарика и камеры внизу
        self.bottom_buttons_layout = QHBoxLayout()
        self.bottom_buttons_layout.setContentsMargins(50, 0, 50, 0) # Отступы по бокам
        self.bottom_buttons_layout.setSpacing(100) # Расстояние между кнопками
        self.bottom_buttons_layout.addStretch() # Растяжка слева

        self.flashlight_button = self._create_circular_button("icons/flashlight_icon_white.png", self.flashlight_toggled.emit)
        self.camera_button = self._create_circular_button("icons/camera_icon_white.png", self.camera_opened.emit)

        self.bottom_buttons_layout.addWidget(self.flashlight_button)
        self.bottom_buttons_layout.addWidget(self.camera_button)

        self.bottom_buttons_layout.addStretch() # Растяжка справа
        
        self.layout.addLayout(self.bottom_buttons_layout)
        self.layout.addSpacing(60) # Отступ от нижнего края

        self.setup_time_update()

    def _create_circular_button(self, icon_path, slot):
        button = QPushButton(self)
        button.setFixedSize(50, 50) # Фиксированный размер для круглой кнопки
        
        icon_pixmap = QPixmap(icon_path)
        if not icon_pixmap.isNull():
            # Масштабируем иконку для кнопки
            button.setIcon(QIcon(icon_pixmap.scaled(28, 28, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            button.setIconSize(QSize(28, 28))
        else:
            print(f"Ошибка: Иконка '{icon_path}' не найдена для кнопки.")
            button.setText("?")
            button.setStyleSheet("color: white; font-size: 24px; text-align: center;")
            
        button.setStyleSheet("""
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1); /* Полупрозрачный фон */
                border: 1px solid rgba(255, 255, 255, 0.2); /* Едва заметная рамка */
                border-radius: 25px; /* Делает кнопку круглой */
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 0.2);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.3);
            }
        """)
        button.clicked.connect(slot)
        return button

    def mousePressEvent(self, event):
        # Имитирует "проведите вверх для разблокировки" по клику в любом месте экрана
        self.unlocked_requested.emit()
        super().mousePressEvent(event)

    def setup_time_update(self):
        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self._update_display_time)
        self.time_timer.start(1000) # Обновлять каждую секунду
        self._update_display_time() # Изначальное обновление

    def _update_display_time(self):
        current_time = QTime.currentTime().toString("HH:mm")
        
        # Локализация даты на русском языке
        months_ru = ["января", "февраля", "марта", "апреля", "мая", "июня",
                     "июля", "августа", "сентября", "октября", "ноября", "декабря"]
        days_ru = ["Воскресенье", "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота"]
        
        day_of_week_index = QDate.currentDate().dayOfWeek() % 7 # 0=Вс, 1=Пн ... 6=Сб
        day_of_week_ru = days_ru[day_of_week_index]
        
        month_index = QDate.currentDate().month() - 1
        month_ru = months_ru[month_index]

        day_of_month = QDate.currentDate().day()
        current_date_str_ru = f"{day_of_week_ru}, {day_of_month} {month_ru}"

        self.time_label.setText(current_time)
        self.date_label.setText(current_date_str_ru)

    def set_username(self, username: str):
        """
        Обновляет имя пользователя. На iOS-подобном локскрине прямое приветствие
        по имени обычно не отображается, но метод сохранен для совместимости.
        """
        self.current_username = username
        # self.greeting_label.setText(f"Привет, {self.current_username}!") # Эта метка удалена

    def showEvent(self, event):
        """Переопределение showEvent для обновления времени при показе."""
        self._update_display_time()
        super().showEvent(event)

# Для тестирования LockScreenContent отдельно
if __name__ == "__main__":
    from PyQt5.QtCore import QDate 
    import sys
    from PyQt5.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)
    lock_screen = LockScreenContent(initial_username="Тест")
    
    main_window = QMainWindow() 
    main_window.setFixedSize(519, 950)
    main_window.setCentralWidget(lock_screen)
    main_window.show()
    
    sys.exit(app.exec_())
