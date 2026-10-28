# ui/statusbar.py
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QLabel
from PyQt5.QtGui import QPixmap, QFont, QPainter, QColor
from PyQt5.QtCore import Qt, QTimer, QTime, QDate, pyqtSignal # Добавлен QDate

class StatusBarWidget(QWidget):
    time_updated = pyqtSignal(str) # Сигнал для обновления времени (не используется в LockScreen, но может быть полезен)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.is_light_background = False # Добавляем атрибут для отслеживания
        self.setStyleSheet(self._get_style_sheet())

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 0, 10, 0) # Отступы по бокам
        self.layout.setSpacing(10) # Расстояние между элементами

        # Иконка Wi-Fi (левая сторона)
        self.wifi_icon_label = QLabel()
        self.layout.addWidget(self.wifi_icon_label)

        # Растяжка для выравнивания времени по центру
        self.layout.addStretch()

        # Метка времени (центр)
        self.time_label = QLabel()
        self.time_label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.time_label)

        # Растяжка для выравнивания батареи по правой стороне
        self.layout.addStretch()

        # Метка батареи (правая сторона)
        self.battery_label = QLabel()
        self.battery_label.setAlignment(Qt.AlignRight)
        self.layout.addWidget(self.battery_label)

        self.setup_timers()
        self._update_time() # Инициализируем время сразу

    def setup_timers(self):
        self.time_timer = QTimer(self)
        self.time_timer.timeout.connect(self._update_time)
        self.time_timer.start(1000) # Обновлять каждую секунду

        self.battery_timer = QTimer(self)
        self.battery_timer.timeout.connect(self._update_battery_status)
        self.battery_timer.start(60000) # Обновлять статус батареи каждую минуту

    def _update_time(self):
        current_time = QTime.currentTime().toString("HH:mm")
        self.time_label.setText(current_time)
        self.time_updated.emit(current_time) # Эмитируем сигнал

    def _update_battery_status(self):
        # В реальном приложении здесь будет логика получения статуса батареи.
        # Для симуляции: случайное значение или фиксированное.
        battery_level = "100%" # Пример
        self.battery_label.setText(battery_level)
        self._update_icons() # Обновляем иконки при изменении батареи/Wi-Fi

    def _get_style_sheet(self):
        # Определяем цвет текста иконок в зависимости от фона
        text_color = "black" if self.is_light_background else "white"
        return f"""
            QWidget {{
                background-color: transparent; /* Прозрачный фон для статус-бара */
            }}
            QLabel {{
                color: {text_color};
                font-size: 13px;
                font-weight: bold;
            }}
        """

    def set_is_light_background(self, is_light: bool):
        """Устанавливает, должен ли статус-бар использовать светлую или темную тему."""
        if self.is_light_background != is_light:
            self.is_light_background = is_light
            self.setStyleSheet(self._get_style_sheet())
            self._update_icons() # Обновляем иконки в соответствии с новой темой

    def _update_icons(self):
        # В реальном приложении здесь будет логика выбора иконок Wi-Fi и батареи
        # в зависимости от состояния и выбранной темы (белая/черная).
        icon_color_suffix = "_black.png" if self.is_light_background else "_white.png"

        wifi_icon_path = f"icons/wifi_icon{icon_color_suffix}" # Пример
        battery_icon_path = f"icons/battery_icon{icon_color_suffix}" # Пример

        # Загрузка иконок Wi-Fi
        wifi_pixmap = QPixmap(wifi_icon_path)
        if not wifi_pixmap.isNull():
            self.wifi_icon_label.setPixmap(wifi_pixmap.scaled(18, 18, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            print(f"Ошибка: Иконка Wi-Fi '{wifi_icon_path}' не найдена.")
            self.wifi_icon_label.setText("W") # Заглушка
            self.wifi_icon_label.setStyleSheet(f"color: {'black' if self.is_light_background else 'white'}; font-size: 13px;")

        # Загрузка иконок Батареи
        battery_pixmap = QPixmap(battery_icon_path)
        if not battery_pixmap.isNull():
            self.battery_label.setPixmap(battery_pixmap.scaled(20, 20, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            print(f"Ошибка: Иконка батареи '{battery_icon_path}' не найдена.")
            # Текст батареи уже выводится в _update_battery_status, так что здесь можно ничего не делать или поставить заглушку.
