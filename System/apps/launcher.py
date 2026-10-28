# apps/launcher.py
import sys
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QFrame, QSizePolicy, QApplication, QMainWindow, QSpacerItem,
    QGraphicsOpacityEffect
)
from PyQt5.QtGui import QPixmap, QFont, QColor, QBrush, QPainter, QLinearGradient
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QPoint, QPropertyAnimation, QEasingCurve, QRect, pyqtProperty, QParallelAnimationGroup, QSequentialAnimationGroup, QTimer, QPauseAnimation

# Класс для одной иконки приложения
class AppIcon(QWidget):
    # Сигнал, который будет обрабатываться LauncherContent.
    # Теперь передает ID приложения и глобальную геометрию иконки.
    app_icon_pressed = pyqtSignal(str, QRect) 

    def __init__(self, app_id: str, app_name: str, icon_path: str, parent=None, is_dock_icon: bool = False, initial_icon_draw_size: int = 70, initial_show_name: bool = True):
        super().__init__(parent)
        self.app_id = app_id
        self.app_name = app_name
        self.is_dock_icon = is_dock_icon

        # Увеличенные размеры для лучшего использования пространства
        if self.is_dock_icon:
            self.setFixedSize(80, 80) # Размер контейнера для иконок в доке
            self._icon_draw_size = 70 # Размер иконки в доке, по умолчанию
            self._show_name = False # Иконки в доке обычно без текста
        else:
            self.setFixedSize(90, 100) # Фиксированный размер иконки (для иконки + текста)
            self._icon_draw_size = initial_icon_draw_size # Размер иконки в сетке, устанавливается извне
            self._show_name = initial_show_name # Видимость имени для иконок сетки

        self._scale_factor = 1.0 # Текущий коэффициент масштабирования для анимации
        self._opacity = 1.0 # Текущая прозрачность для анимации (добавлено)
        self._original_pixmap = None # Для хранения оригинального немасштабированного QPixmap
        
        # Загрузка оригинального pixmap один раз
        pixmap_loaded = QPixmap(icon_path)
        if pixmap_loaded.isNull():
            print(f"Ошибка: Иконка '{icon_path}' не найдена для '{app_name}'.")
            # Попытка загрузить заглушку
            if os.path.exists("icons/default_app_icon.png"):
                pixmap_loaded = QPixmap("icons/default_app_icon.png")
            else:
                # Если и заглушка не найдена, рисуем простой квадрат с текстом
                default_icon_pixmap = QPixmap(self._icon_draw_size, self._icon_draw_size)
                default_icon_pixmap.fill(QColor("#555555")) # Серый фон
                painter = QPainter(default_icon_pixmap)
                painter.setPen(QColor("white"))
                painter.setFont(QFont("Arial", 20, QFont.Bold))
                painter.drawText(default_icon_pixmap.rect(), Qt.AlignCenter, app_name[0].upper()) # Первая буква названия
                painter.end()
                pixmap_loaded = default_icon_pixmap
        self._original_pixmap = pixmap_loaded

        # Макет для метки названия (если это не иконка дока)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(5) 
        self.layout.setAlignment(Qt.AlignCenter)

        # Добавляем верхний отступ для иконки, которая будет отрисована в paintEvent
        # Отступ зависит от размера иконки, чтобы текст был внизу
        self.layout.addSpacing(self._icon_draw_size + (5 if not self.is_dock_icon else 0)) 

        if not self.is_dock_icon:
            self.name_label = QLabel(app_name, self)
            self.name_label.setAlignment(Qt.AlignCenter)
            self.name_label.setStyleSheet("color: white; font-size: 11px;")
            self.name_label.setWordWrap(True) # Включаем перенос слов
            self.name_label.setFixedSize(self.width(), 20) # Ширина виджета, высота 20px
            self.layout.addWidget(self.name_label)
            self.name_label.setVisible(self._show_name) # Изначальная видимость текста
        else:
            self.name_label = None # Иконки дока не имеют текстовых меток

    # Определение пользовательского свойства 'scale' для анимации
    @pyqtProperty(float)
    def scale(self):
        return self._scale_factor

    @scale.setter
    def scale(self, value):
        if self._scale_factor != value:
            self._scale_factor = value
            self.update() # Запрос на перерисовку при изменении масштаба

    # Определение пользовательского свойства 'opacity' для анимации (добавлено)
    @pyqtProperty(float)
    def opacity(self):
        return self._opacity

    @opacity.setter
    def opacity(self, value):
        if self._opacity != value:
            self._opacity = value
            self.update() # Запрос на перерисовку при изменении прозрачности

    def set_icon_draw_size(self, size: int):
        """Устанавливает новый размер для отрисовки иконки."""
        if self._icon_draw_size != size:
            self._icon_draw_size = size
            if not self.is_dock_icon: # Только для иконок в сетке, док имеет фиксированный размер контейнера
                self.setFixedSize(size + 20, size + 30) # Подстраиваем размер виджета под иконку + текст
                if self.name_label: # Обновляем ширину метки, если она есть
                    self.name_label.setFixedSize(self.width(), 20) 
                # Обновляем верхний отступ для текста, если он есть
                if self.layout and self.layout.count() > 0:
                    item = self.layout.itemAt(0) # Первый элемент - это спейсер
                    if isinstance(item, QSpacerItem):
                        self.layout.removeItem(item)
                    self.layout.insertSpacing(0, self._icon_draw_size + 5)

            self.update() # Перерисовываем виджет

    def set_app_name_visibility(self, visible: bool):
        """Устанавливает видимость названия приложения под иконкой."""
        if self._show_name != visible:
            self._show_name = visible
            if self.name_label:
                self.name_label.setVisible(visible)
            # Возможно, нужно будет скорректировать высоту виджета, если текст скрывается/показывается
            if not self.is_dock_icon:
                current_width = self.width()
                if visible:
                    self.setFixedSize(current_width, self._icon_draw_size + 30) # Иконка + текст
                else:
                    self.setFixedSize(current_width, self._icon_draw_size + 10) # Только иконка (меньше отступа)
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.SmoothPixmapTransform)
        painter.setOpacity(self._opacity) # Применяем прозрачность

        # Вычисление масштабированного размера иконки
        scaled_icon_size = int(self._icon_draw_size * self._scale_factor)
        if scaled_icon_size <= 0: # Избегаем нулевого размера
            scaled_icon_size = 1 
        
        scaled_pixmap = self._original_pixmap.scaled(scaled_icon_size, scaled_icon_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        # Вычисление позиции для центрирования иконки вверху виджета
        x_pos = (self.width() - scaled_pixmap.width()) // 2
        y_pos = (self._icon_draw_size + (5 if not self.is_dock_icon else 0) - scaled_pixmap.height()) // 2

        painter.drawPixmap(x_pos, y_pos, scaled_pixmap)
        
        super().paintEvent(event) # Важно вызвать базовый метод для отрисовки дочерних виджетов (name_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Анимация сжатия при нажатии
            self.animation = QPropertyAnimation(self, b"scale")
            self.animation.setDuration(100) # Быстрое сжатие (100 мс)
            self.animation.setStartValue(self._scale_factor)
            self.animation.setEndValue(0.85) # Сжимаем до 85% от оригинального размера
            self.animation.setEasingCurve(QEasingCurve.OutQuad) # Быстрое начало, замедление к концу
            self.animation.start()
            
            # Эмитируем сигнал, который будет перехвачен LauncherContent,
            # передавая глобальную геометрию иконки.
            global_top_left = self.mapToGlobal(self.rect().topLeft())
            global_rect = QRect(global_top_left, self.rect().size())
            self.app_icon_pressed.emit(self.app_id, global_rect) 
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Анимация возвращения с "отскоком"
            self.animation = QPropertyAnimation(self, b"scale")
            self.animation.setDuration(300) # Медленнее возвращение (300 мс)
            self.animation.setStartValue(self._scale_factor)
            self.animation.setEndValue(1.0) # Возвращаемся к нормальному размеру
            self.animation.setEasingCurve(QEasingCurve.OutElastic) # Эластичный эффект "отскока"
            self.animation.start()
        super().mouseReleaseEvent(event)

    def reset_animation_state(self):
        """Сбрасывает состояние иконки для анимации появления (невидимая и маленькая)."""
        self._scale_factor = 0.0 # Изначально невидимая
        self._opacity = 0.0 # Изначально полностью прозрачная
        self.update() # Запрос на перерисовку

# Главный виджет лаунчера
class LauncherContent(QFrame):
    # Этот сигнал будет эмитироваться ПОСЛЕ анимации лаунчера
    launch_app_requested = pyqtSignal(str, QRect) 

    def __init__(self, parent=None, language="Русский", initial_icon_size: int = 70, initial_grid_columns: int = 4, initial_show_app_names: bool = True):
        super().__init__(parent)
        self.main_window = parent
        self._language = language # Используем _language для приватности
        self._current_icon_size = initial_icon_size
        self._current_grid_columns = initial_grid_columns
        self._show_app_names = initial_show_app_names

        self.setStyleSheet("background-color: transparent;") # Прозрачный, чтобы видеть фон Main Window
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Локализация имен приложений
        self.localized_app_names = {
            "Русский": {
                "Greeting": "Привет, Пользователь!",
                "Phone": "Телефон", "Messages": "Сообщения", "Camera": "Камера",
                "Photos": "Фото", "Store": "Магазин", "Browser": "Браузер", 
                "Music": "Музыка", "Maps": "Карты", "Settings": "Настройки",
                "Calendar": "Календарь", "Clock": "Часы", "Contacts": "Контакты",
                "Notes": "Заметки", "Files": "Файлы", "Weather": "Погода",
                "Calculator": "Калькулятор", 
                "Video": "Видео", "Books": "Книги",
                "Podcasts": "Подкасты",
            },
            "English": {
                "Greeting": "Hello, User!",
                "Phone": "Phone", "Messages": "Messages", "Camera": "Camera",
                "Photos": "Photos", "Store": "Store", "Browser": "Browser", 
                "Music": "Music", "Maps": "Maps", "Settings": "Settings",
                "Calendar": "Calendar", "Clock": "Clock", "Contacts": "Contacts",
                "Notes": "Notes", "Files": "Files", "Weather": "Weather",
                "Calculator": "Calculator", 
                "Video": "Video", "Books": "Books",
                "Podcasts": "Podcasts",
            }
        }

        self.grid_app_icons = [] # Список для хранения ссылок на объекты AppIcon в сетке
        self.dock_app_icons = [] # Список для хранения ссылок на объекты AppIcon в доке
        
        # Данные приложений, которые будут использоваться для создания иконок
        self.apps_data = [
            ("Phone", "Телефон", "icons/phone.png"),
            ("Messages", "Сообщения", "icons/messages.png"),
            ("Camera", "Камера", "icons/camera.png"), 
            ("Photos", "Фото", "icons/photos.png"),
            ("Store", "Магазин", "icons/store.png"),
            ("Browser", "Браузер", "icons/browser.png"), 
            ("Music", "Музыка", "icons/music.png"),
            ("Maps", "Карты", "icons/maps.png"),
            ("Settings", "Настройки", "icons/settings.png"), 
            ("Calendar", "Календарь", "icons/calendar.png"),
            ("Clock", "Часы", "icons/clock.png"),
            ("Contacts", "Контакты", "icons/contacts.png"),
            ("Notes", "Заметки", "icons/notes.png"),
            ("Files", "Файлы", "icons/files.png"),
            ("Weather", "Погода", "icons/weather.png"),
            ("Calculator", "Калькулятор", "icons/calculator.png"), 
            ("Video", "Видео", "icons/video.png"),
            ("Books", "Книги", "icons/books.png"),
            ("Podcasts", "Подкасты", "icons/podcasts.png"),
        ]

        self.dock_apps_data = [ 
            ("Phone", "Телефон", "icons/phone.png"),
            ("Messages", "Сообщения", "icons/messages.png"),
            ("Browser", "Браузер", "icons/browser.png"), 
            ("Store", "Магазин", "icons/store.png"),
        ]


        self.init_ui() # Вызываем инициализацию UI
        
        self.current_app_id_to_launch = None 
        self.current_icon_rect_for_animation = QRect() 

        # Флаг для контроля анимации при первом показе
        self._should_animate_on_show = True 

    def init_ui(self):
        main_vlayout = QVBoxLayout(self)
        main_vlayout.setContentsMargins(15, 15, 15, 15) # Уменьшены отступы
        main_vlayout.setSpacing(15) 

        # --- Верхняя часть с приветствием ---
        self.greeting_label = QLabel("") 
        self.greeting_label.setAlignment(Qt.AlignTop | Qt.AlignCenter)
        self.greeting_label.setStyleSheet("color: white; font-size: 20px; margin-bottom: 25px;") 
        main_vlayout.addWidget(self.greeting_label)
        
        main_vlayout.addStretch(1) 

        # --- Сетка иконок приложений ---
        self.app_grid_layout = QGridLayout()
        self.app_grid_layout.setSpacing(15) # Уменьшен отступ между иконками
        self.app_grid_layout.setAlignment(Qt.AlignTop | Qt.AlignCenter) 

        self._populate_grid_apps() # Вызываем метод для заполнения сетки

        for i in range(self._current_grid_columns):
            self.app_grid_layout.setColumnStretch(i, 1)

        main_vlayout.addLayout(self.app_grid_layout)
        
        main_vlayout.addStretch(2) 

        # --- Док-панель ---
        self.dock_frame = QFrame(self)
        self.dock_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(0, 0, 0, 0.4); 
                border-radius: 35px; 
                border: 1px solid rgba(255, 255, 255, 0.15); 
            }
        """)
        self.dock_frame.setFixedHeight(90) 
        self.dock_frame.setMaximumWidth(480) 

        self.dock_layout = QHBoxLayout(self.dock_frame) 
        self.dock_layout.setContentsMargins(20, 10, 20, 10) 
        self.dock_layout.setSpacing(25) 
        self.dock_layout.setAlignment(Qt.AlignCenter)

        self._populate_dock_apps() # Вызываем метод для заполнения дока


        main_vlayout.addWidget(self.dock_frame, alignment=Qt.AlignCenter)
        main_vlayout.addSpacing(25) 
        
        self._update_localization() 

    def _populate_grid_apps(self):
        """Очищает и заново заполняет сетку приложений."""
        # Удаляем существующие иконки из макета
        while self.app_grid_layout.count():
            item = self.app_grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None) # Важно отвязать виджет от родителя
                widget.deleteLater()
        self.grid_app_icons = [] # Очищаем список ссылок

        row, col = 0, 0
        for app_id, default_name, icon_path in self.apps_data:
            display_name = self.localized_app_names.get(self._language, self.localized_app_names["Русский"]).get(app_id, default_name)
            icon = AppIcon(app_id, display_name, icon_path, self, is_dock_icon=False, initial_icon_draw_size=self._current_icon_size, initial_show_name=self._show_app_names) 
            icon.app_icon_pressed.connect(self._handle_app_icon_pressed) 
            self.app_grid_layout.addWidget(icon, row, col)
            self.grid_app_icons.append(icon) 
            col += 1
            if col >= self._current_grid_columns:
                col = 0
                row += 1
        
        # Обновляем растяжки столбцов
        for i in range(self.app_grid_layout.columnCount()):
            self.app_grid_layout.setColumnStretch(i, 0) # Сначала сбрасываем
        for i in range(self._current_grid_columns):
            self.app_grid_layout.setColumnStretch(i, 1)

    def _populate_dock_apps(self):
        """Очищает и заново заполняет док приложений."""
        while self.dock_layout.count():
            item = self.dock_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.dock_app_icons = []

        for app_id, default_name, icon_path in self.dock_apps_data:
            display_name = self.localized_app_names.get(self._language, self.localized_app_names["Русский"]).get(app_id, default_name)
            icon = AppIcon(app_id, display_name, icon_path, self.dock_frame, is_dock_icon=True) 
            icon.app_icon_pressed.connect(self._handle_app_icon_pressed) 
            self.dock_layout.addWidget(icon)
            self.dock_app_icons.append(icon) 


    def set_language(self, language: str):
        """Устанавливает язык для лаунчера и обновляет тексты."""
        if self._language != language:
            self._language = language
            self._update_localization()

    def _update_localization(self):
        """Обновляет все локализуемые тексты в лаунчере."""
        current_locale = self.localized_app_names.get(self._language, self.localized_app_names["Русский"])
        
        self.greeting_label.setText(current_locale.get("Greeting", "Привет, Пользователь!"))

        # Обновляем тексты для иконок в сетке
        for app_icon in self.grid_app_icons:
            new_name = current_locale.get(app_icon.app_id, app_icon.app_name)
            if app_icon.name_label:
                app_icon.name_label.setText(new_name)
        
        # Обновляем тексты для иконок в доке (используем сохраненные ссылки)
        for app_icon in self.dock_app_icons:
            new_name = current_locale.get(app_icon.app_id, app_icon.app_name)
            if app_icon.name_label: 
                app_icon.name_label.setText(new_name)


    # --- НОВЫЕ МЕТОДЫ ДЛЯ НАСТРОЙКИ ЛАУНЧЕРА ---
    def set_icon_size(self, size: int):
        """Устанавливает новый размер для иконок в лаунчере."""
        if self._current_icon_size != size:
            self._current_icon_size = size
            for icon in self.grid_app_icons: # Обновляем только иконки в сетке
                icon.set_icon_draw_size(size)
            # Док-иконки не изменяются по размеру через эту настройку

    def set_grid_columns(self, columns: int):
        """Устанавливает новое количество столбцов в сетке лаунчера."""
        if self._current_grid_columns != columns:
            self._current_grid_columns = columns
            self._populate_grid_apps() # Перестраиваем всю сетку

    def set_app_names_visibility(self, visible: bool):
        """Устанавливает видимость названий приложений под иконками."""
        if self._show_app_names != visible:
            self._show_app_names = visible
            for icon in self.grid_app_icons: # Обновляем только иконки в сетке
                icon.set_app_name_visibility(visible)
            # Док-иконки не имеют названий, поэтому их не затрагиваем


    def _handle_app_icon_pressed(self, app_id: str, icon_rect: QRect):
        """
        Обрабатывает нажатие на иконку приложения.
        Запускает анимацию скрытия лаунчера и затем инициирует запуск приложения.
        """
        self.current_app_id_to_launch = app_id
        self.current_icon_rect_for_animation = icon_rect

        # Создаем новый QGraphicsOpacityEffect каждый раз.
        opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(opacity_effect) 

        self.hide_animation = QPropertyAnimation(opacity_effect, b"opacity") 
        self.hide_animation.setDuration(250) 
        self.hide_animation.setStartValue(1.0)
        self.hide_animation.setEndValue(0.0)
        self.hide_animation.setEasingCurve(QEasingCurve.OutQuad)
        
        self.hide_animation.finished.connect(self._on_outgoing_animation_finished)
        
        self.hide_animation.start()

    def _on_outgoing_animation_finished(self):
        """
        Вызывается после завершения анимации скрытия лаунчера.
        Эмитирует сигнал для MainWindow для запуска приложения.
        """
        self.setGraphicsEffect(None) 

        self.hide() 
        
        self.launch_app_requested.emit(self.current_app_id_to_launch, self.current_icon_rect_for_animation)

    def animate_icons_in(self):
        """
        Запускает анимацию появления иконок (масштабирование и прозрачность)
        после разблокировки.
        """
        all_icons = self.grid_app_icons + self.dock_app_icons
        
        # Сначала убедимся, что все иконки полностью скрыты для начала анимации
        for icon in all_icons:
            icon.reset_animation_state()
        
        animation_group = QParallelAnimationGroup(self)
        
        base_delay = 50 # Базовая задержка для каждой иконки
        
        for i, icon in enumerate(all_icons):
            # Создаем последовательную группу для каждой иконки, чтобы сначала была задержка, затем анимация
            sequential_icon_animation = QSequentialAnimationGroup(self)

            # Добавляем паузу
            pause_animation = QPauseAnimation(i * base_delay, self) # Задержка для каждой иконки
            sequential_icon_animation.addAnimation(pause_animation)

            # Анимация масштаба
            scale_animation = QPropertyAnimation(icon, b"scale")
            scale_animation.setDuration(400) # Длительность анимации масштаба
            scale_animation.setStartValue(0.0) # Начинаем с невидимого размера
            scale_animation.setEndValue(1.0) # Заканчиваем нормальным размером
            scale_animation.setEasingCurve(QEasingCurve.OutBack) # Эффект "выпрыгивания"
            sequential_icon_animation.addAnimation(scale_animation) # Добавляем к последовательной группе

            # Анимация прозрачности
            opacity_animation = QPropertyAnimation(icon, b"opacity")
            opacity_animation.setDuration(300) # Длительность анимации прозрачности
            opacity_animation.setStartValue(0.0) # Начинаем с прозрачного
            opacity_animation.setEndValue(1.0) # Заканчиваем полностью видимым
            opacity_animation.setEasingCurve(QEasingCurve.OutQuad)
            sequential_icon_animation.addAnimation(opacity_animation) # Добавляем к последовательной группе
            
            # Добавляем последовательную анимацию иконки в параллельную группу
            animation_group.addAnimation(sequential_icon_animation)
            
        animation_group.start()

    def showEvent(self, event):
        """
        Переопределение showEvent для запуска анимации иконок
        при первом появлении лаунчера или после разблокировки.
        """
        super().showEvent(event)
        if self._should_animate_on_show:
            self.animate_icons_in()
            self._should_animate_on_show = False
        
    def prepare_for_animation(self):
        """
        Подготавливает лаунчер к анимации при следующем показе (например, после разблокировки).
        Вызывается извне (например, из MainWindow).
        """
        self._should_animate_on_show = True
        # Убедимся, что иконки сброшены к начальному состоянию для анимации
        for icon in self.grid_app_icons + self.dock_app_icons:
            icon.reset_animation_state()

    # Переопределяем paintEvent для рисования фона
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Рисуем градиентный фон
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor("#1f2430")) # Темно-синий/почти черный
        gradient.setColorAt(0.5, QColor("#303a4c")) # Средний синий
        gradient.setColorAt(1, QColor("#1f2430")) # Снова темно-синий
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())

        super().paintEvent(event) # Важно вызвать базовый метод, чтобы отрисовались дочерние виджеты

# Пример использования (для тестирования только лаунчера)
if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_test_window = QMainWindow() 
    main_test_window.setGeometry(100, 100, 519, 950) 
    main_test_window.setStyleSheet("background-color: black;") 

    launcher = LauncherContent(main_test_window, language="Русский")
    launcher.launch_app_requested.connect(lambda app_id, icon_rect: print(f"Launcher requested launch of: {app_id} from {icon_rect}"))

    test_layout = QVBoxLayout()
    test_layout.setContentsMargins(0,0,0,0)
    test_layout.addWidget(launcher)

    central_widget = QWidget()
    central_widget.setLayout(test_layout)
    main_test_window.setCentralWidget(central_widget)
    main_test_window.show()

    # Запустим анимацию через небольшой промежуток времени для демонстрации
    QTimer.singleShot(1000, launcher.animate_icons_in)

    # Тестирование новых настроек лаунчера
    QTimer.singleShot(3000, lambda: launcher.set_icon_size(50))
    QTimer.singleShot(4000, lambda: launcher.set_grid_columns(5))
    QTimer.singleShot(5000, lambda: launcher.set_app_names_visibility(False))
    QTimer.singleShot(6000, lambda: launcher.set_icon_size(90))
    QTimer.singleShot(7000, lambda: launcher.set_app_names_visibility(True))
    QTimer.singleShot(8000, lambda: launcher.set_grid_columns(3))


    sys.exit(app.exec_())
