# ui/navigation_bar.py
from PyQt5.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QApplication, QMainWindow, QFrame, QSizePolicy
from PyQt5.QtGui import QColor, QFont, QIcon, QTransform
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QRect, QPointF, QTimer # Добавлен QPointF для работы с координатами касания, QTimer для таймаута нажатия

# --- Константы режима навигации ---
NAVIGATION_MODE_THREE_BUTTON = "three_button"
NAVIGATION_MODE_GESTURES = "gestures" # Убедитесь, что эта строка присутствует и не закомментирована!

class NavigationBarWidget(QFrame):
    # Сигналы для навигационных действий
    home_button_pressed = pyqtSignal()
    back_button_pressed = pyqtSignal()
    recent_button_pressed = pyqtSignal()

    def __init__(self, parent=None, initial_mode=NAVIGATION_MODE_THREE_BUTTON):
        super().__init__(parent)
        self.setFixedHeight(40) # Фиксированная высота навигационной панели
        self.setContentsMargins(0, 0, 0, 0)
        
        # Основной горизонтальный макет для кнопок
        self.main_layout = QHBoxLayout(self) 
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.current_mode = initial_mode

        # Переменные для отслеживания жестов
        self._touch_start_pos = QPointF()
        self._touch_last_pos = QPointF() # Добавлено для отслеживания движения
        self._is_touch_active = False
        self._gesture_threshold = 30 # Минимальное расстояние для распознавания свайпа
        self._long_press_timer = QTimer(self) # Таймер для обнаружения долгого нажатия
        self._long_press_timer.setSingleShot(True)
        self._long_press_timer_threshold = 500 # 500 мс для долгого нажатия

        # Включаем обработку сенсорных событий
        self.setAttribute(Qt.WA_AcceptTouchEvents)

        self.init_ui() # Инициализация всех элементов UI
        self.set_navigation_mode(self.current_mode) # Установка начального режима

        # Включены стили для навигационной панели
        self.setStyleSheet("""
            NavigationBarWidget {
                background-color: rgba(30, 30, 30, 0.7); /* Полупрозрачный темно-серый фон */
                border-top: 1px solid rgba(255, 255, 255, 0.1); /* Тонкая белая линия сверху */
                border-bottom-left-radius: 15px; /* Скругление углов */
                border-bottom-right-radius: 15px;
            }
            QPushButton {
                background-color: transparent;
                border: none;
                color: white;
                font-size: 16px;
                padding: 5px;
                min-width: 50px;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 0.1);
                border-radius: 5px;
            }
            /* Стиль для кнопки Home */
            QPushButton#HomeButton {
                font-size: 24px; /* Увеличиваем размер точки */
            }
            QPushButton#HomeButton:pressed {
                border-radius: 20px; /* Круглое выделение при нажатии */
            }
        """)
        # Убедимся, что виджет растягивается по горизонтали
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def init_ui(self):
        # Кнопка "Назад"
        self.back_button = QPushButton("˂", self) 
        self.back_button.clicked.connect(self.back_button_pressed)
        
        # Кнопка "Домой"
        self.home_button = QPushButton("⌂", self) 
        self.home_button.setObjectName("HomeButton") # Устанавливаем objectName для специфичного QSS
        self.home_button.clicked.connect(self.home_button_pressed)

        # Кнопка "Недавние приложения"
        self.recent_button = QPushButton("■", self) 
        self.recent_button.clicked.connect(self.recent_button_pressed)
        
        # Добавляем все кнопки в основной макет с растяжителями
        self.main_layout.addStretch(1) # Растяжитель слева
        self.main_layout.addWidget(self.back_button, alignment=Qt.AlignCenter)
        self.main_layout.addStretch(1) # Растяжитель между кнопками

        self.main_layout.addWidget(self.home_button, alignment=Qt.AlignCenter)
        self.main_layout.addStretch(1) # Растяжитель между кнопками

        self.main_layout.addWidget(self.recent_button, alignment=Qt.AlignCenter)
        self.main_layout.addStretch(1) # Растяжитель справа

    def set_navigation_mode(self, mode: str):
        """
        Устанавливает режим навигации.
        В режиме жестов кнопки скрываются и активируется обработка касаний.
        """
        self.current_mode = mode
        if mode == NAVIGATION_MODE_THREE_BUTTON:
            print("Navigation mode: Three Buttons activated in NavigationBarWidget.")
            self.back_button.show()
            self.home_button.show()
            self.recent_button.show()
            # Отключаем фильтр событий для жестов
            self.removeEventFilter(self) 
        elif mode == NAVIGATION_MODE_GESTURES:
            print("Navigation mode: Gestures activated in NavigationBarWidget.")
            self.back_button.hide()
            self.home_button.hide()
            self.recent_button.hide()
            # Включаем фильтр событий для жестов (если еще не включен)
            self.installEventFilter(self) 
        else:
            print(f"Unknown navigation mode: {mode}. Defaulting to Three Buttons.")
            self.back_button.show()
            self.home_button.show()
            self.recent_button.show()
            self.removeEventFilter(self)

        self.update() # Принудительное обновление отрисовки

    def update_language(self, language: str):
        """
        Обновляет текст кнопок навигации в зависимости от языка.
        (Символы фиксированы, но метод оставлен для совместимости).
        """
        self.back_button.setText("˂")
        self.home_button.setText("⌂")
        self.recent_button.setText("■")
        self.update()

    def eventFilter(self, obj, event):
        """
        Фильтр событий для перехвата сенсорных событий,
        когда NavigationBarWidget находится в режиме жестов.
        """
        if obj == self and self.current_mode == NAVIGATION_MODE_GESTURES:
            if event.type() == QEvent.TouchBegin:
                return self.touchEvent(event)
            elif event.type() == QEvent.TouchUpdate:
                return self.touchEvent(event)
            elif event.type() == QEvent.TouchEnd:
                return self.touchEvent(event)
            elif event.type() == QEvent.TouchCancel:
                return self.touchEvent(event)
        return super().eventFilter(obj, event)

    def touchEvent(self, event):
        """
        Обрабатывает сенсорные события для распознавания жестов.
        """
        touch_points = event.touchPoints()

        if not touch_points:
            return False

        # Мы обрабатываем только первый палец для простых жестов
        primary_touch_point = touch_points[0]

        if event.type() == QEvent.TouchBegin:
            self._touch_start_pos = primary_touch_point.pos()
            self._touch_last_pos = primary_touch_point.pos()
            self._is_touch_active = True
            # Запускаем таймер для долгого нажатия, если палец остается на месте
            self._long_press_timer.singleShot(self._long_press_timer_threshold, self._on_long_press_timeout)
            return True # Событие обработано

        elif event.type() == QEvent.TouchUpdate:
            if self._is_touch_active:
                current_pos = primary_touch_point.pos()
                delta_x = current_pos.x() - self._touch_start_pos.x()
                delta_y = current_pos.y() - self._touch_start_pos.y()

                # Отменяем таймер долгого нажатия, если палец начал двигаться
                if abs(delta_x) > self._gesture_threshold / 2 or abs(delta_y) > self._gesture_threshold / 2:
                    self._long_press_timer.stop()

                self._touch_last_pos = current_pos # Обновляем последнюю позицию
                return True # Событие обработано

        elif event.type() == QEvent.TouchEnd or event.type() == QEvent.TouchCancel:
            if self._is_touch_active:
                self._is_touch_active = False
                self._long_press_timer.stop() # Остановка таймера при отпускании
                
                # Расчет общего смещения от начальной точки
                delta_x = primary_touch_point.pos().x() - self._touch_start_pos.x()
                delta_y = primary_touch_point.pos().y() - self._touch_start_pos.y()

                # Проверка на свайп (главное смещение должно быть больше порога)
                if abs(delta_x) > self._gesture_threshold or abs(delta_y) > self._gesture_threshold:
                    if abs(delta_x) > abs(delta_y): # Горизонтальный свайп
                        if delta_x > self._gesture_threshold: # Свайп вправо (недавние)
                            print("Gesture: Swipe Right (Recent)")
                            self.recent_button_pressed.emit()
                        elif delta_x < -self._gesture_threshold: # Свайп влево (назад)
                            print("Gesture: Swipe Left (Back)")
                            self.back_button_pressed.emit()
                    else: # Вертикальный свайп
                        if delta_y < -self._gesture_threshold: # Свайп вверх (домой)
                            print("Gesture: Swipe Up (Home)")
                            self.home_button_pressed.emit()
                # Если это не свайп, возможно, это было короткое нажатие (если таймер не сработал)
                elif primary_touch_point.pressState() == Qt.TouchPointReleased:
                    print("Gesture: Short Tap/Click (No specific action for this widget usually)")
                    # Для NavigationBar, короткое нажатие без движения обычно ничего не делает
            return True # Событие обработано
        
        return super().touchEvent(event) # Передаем событие дальше, если не обработано

    def _on_long_press_timeout(self):
        """
        Вызывается, если палец удерживается дольше порога без значительного движения.
        В этом контексте, долгое нажатие может быть обработано как "Домой" или "Недавние"
        если палец находился в определенной зоне, но для простоты пока нет действий.
        """
        if self._is_touch_active:
            print("Gesture: Long Press (No action currently defined for NavigationBar)")
            # Можно добавить логику для долгого нажатия, например, открыть меню недавних
            # self.recent_button_pressed.emit() 


# Example Usage (for testing purposes, if you run this file directly)
if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    main_window = QMainWindow()
    main_window.setGeometry(100, 100, 400, 800)
    
    central_container = QWidget()
    main_window.setCentralWidget(central_container)
    main_layout = QVBoxLayout(central_container)
    main_layout.setContentsMargins(0,0,0,0)
    main_layout.setSpacing(0)

    top_content = QLabel("Приложение или контент")
    top_content.setAlignment(Qt.AlignCenter)
    top_content.setStyleSheet("background-color: #555; color: white; font-size: 20px;")
    main_layout.addWidget(top_content, 1)

    nav_bar = NavigationBarWidget(main_window, initial_mode=NAVIGATION_MODE_THREE_BUTTON)
    nav_bar.home_button_pressed.connect(lambda: print("Home button (or gesture) pressed!"))
    nav_bar.back_button_pressed.connect(lambda: print("Back button (or gesture) pressed!"))
    nav_bar.recent_button_pressed.connect(lambda: print("Recent button (or gesture) pressed!"))
    main_layout.addWidget(nav_bar, alignment=Qt.AlignBottom)

    mode_toggle_button = QPushButton("Переключить режим навигации")
    mode_toggle_button.clicked.connect(lambda: nav_bar.set_navigation_mode(NAVIGATION_MODE_GESTURES if nav_bar.current_mode == NAVIGATION_MODE_THREE_BUTTON else NAVIGATION_MODE_THREE_BUTTON))
    main_layout.addWidget(mode_toggle_button, alignment=Qt.AlignCenter)

    main_window.show()
    sys.exit(app.exec_())
