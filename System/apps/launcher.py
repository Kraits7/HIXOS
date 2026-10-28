# apps/launcher.py
import sys
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout,
    QFrame, QSizePolicy, QApplication, QMainWindow, QSpacerItem,
    QGraphicsOpacityEffect
)
from PyQt5.QtGui import (
    QPixmap, QFont, QColor, QBrush, QPainter, QLinearGradient, QPainterPath,
    QRadialGradient, QFontMetrics
)
from PyQt5.QtCore import Qt, pyqtSignal, QObject, QSize, QPoint, QPropertyAnimation, QEasingCurve, QRect, pyqtProperty, QParallelAnimationGroup, QSequentialAnimationGroup, QTimer, QPauseAnimation

# --- Системный движок анимаций (OxygenOS / iOS style) ---
try:
    from ui.animation_engine import (
        Easing, Duration, animate, _FrameDriver, MorphOverlay, StaggerReveal,
        fly_in_transform, spring_progress,
    )
except ImportError:  # запуск лаунчера standalone из папки apps
    from animation_engine import (
        Easing, Duration, animate, _FrameDriver, MorphOverlay, StaggerReveal,
        fly_in_transform, spring_progress,
    )


class SpringScaleAnimator(QObject):
    """Spring-анимация масштаба иконки в стиле iOS/OxygenOS.

    Кастомные cubic-bezier кривые нельзя передавать в QPropertyAnimation
    (PyQt копирует их на C++ сторону с потерей типа), поэтому анимация
    progress идёт покадрово через _FrameDriver со скоростью ~60 FPS.
    """

    def __init__(self, icon):
        super().__init__(icon)
        self._icon = icon
        self._driver = None

    def to(self, target: float, duration: int, curve):
        start = self._icon.scale_value  # текущее значение — плавный перехват
        if self._driver:
            self._driver.stop()

        def on_frame(p):
            self._icon.set_scale(start + (target - start) * p)

        self._driver = _FrameDriver(duration, curve, on_frame, parent=self)
        self._driver.start()

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

        # Spring-аниматор масштаба (OxygenOS/iOS style, покадровый, 60 FPS)
        self._spring = SpringScaleAnimator(self)
        
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
            # iOS 16 home screen: плотный средний шрифт, лёгкая тень под текстом
            self.name_label.setStyleSheet(
                "color: rgba(255,255,255,0.95); font-size: 12px; font-weight: 500;"
                "font-family: 'SF Pro Text', 'Segoe UI', 'Roboto', sans-serif;")
            self.name_label.setWordWrap(False) # iOS обрезает имя многоточием
            self.name_label.setTextFormat(Qt.PlainText)
            self.name_label.setFixedSize(self.width(), 18) # Ширина виджета, высота 18px
            self._elide_name(app_name)
            self.layout.addWidget(self.name_label)
            self.name_label.setVisible(self._show_name) # Изначальная видимость текста
        else:
            self.name_label = None # Иконки дока не имеют текстовых меток

    def _elide_name(self, name: str):
        """Обрезка длинных имён многоточием — как в iOS."""
        fm = QFontMetrics(self.name_label.font())
        elided = fm.elidedText(name, Qt.ElideRight, max(10, self.width() - 2))
        self.name_label.setText(elided)
        self.name_label.setToolTip(name)

    # Определение пользовательского свойства 'scale' для анимации
    @pyqtProperty(float)
    def scale(self):
        return self._scale_factor

    @scale.setter
    def scale(self, value):
        if self._scale_factor != value:
            self._scale_factor = value
            self.update() # Запрос на перерисовку при изменении масштаба

    # Алиасы для spring-аниматора (покадрового, вне QPropertyAnimation)
    @property
    def scale_value(self):
        return self._scale_factor

    def set_scale(self, value: float):
        self.scale = value

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

        # iOS 16-style: иконки с фирменным squircle-скруглением (~22.5% стороны)
        side = scaled_pixmap.width()
        if side >= 24:
            path = QPainterPath()
            path.addRoundedRect(x_pos, y_pos, side, side,
                                side * 0.225, side * 0.225)
            painter.setClipPath(path)
        painter.drawPixmap(x_pos, y_pos, scaled_pixmap)
        
        super().paintEvent(event) # Важно вызвать базовый метод для отрисовки дочерних виджетов (name_label)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # iOS-style press feedback: быстрое мягкое сжатие до 0.85
            self._spring.to(0.85, Duration.MICRO, Easing.STANDARD)

            # Эмитируем сигнал, который будет перехвачен LauncherContent,
            # передавая глобальную геометрию иконки.
            global_top_left = self.mapToGlobal(self.rect().topLeft())
            global_rect = QRect(global_top_left, self.rect().size())
            self.app_icon_pressed.emit(self.app_id, global_rect) 
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Возврат с spring-overshoot (cubic-bezier(0.34,1.56,0.64,1)) — как в iOS
            self._spring.to(1.0, Duration.SHORT, Easing.SPRING)
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
                "Greeting": "Добро пожаловать",
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
                "Greeting": "Welcome",
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
        # iOS 16 home screen: симметричные боковые поля, воздух сверху
        main_vlayout.setContentsMargins(24, 30, 24, 12)
        main_vlayout.setSpacing(0)

        # --- Верхняя часть с приветствием (iOS-заголовок крупным шрифтом) ---
        self.greeting_label = QLabel("") 
        self.greeting_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.greeting_label.setStyleSheet(
            "color: white; font-size: 26px; font-weight: 700;"
            "font-family: 'SF Pro Display', 'Segoe UI', 'Roboto', sans-serif;")
        main_vlayout.addWidget(self.greeting_label)
        
        main_vlayout.addSpacing(34)
        main_vlayout.addStretch(1) 

        # --- Сетка иконок приложений ---
        self.app_grid_layout = QGridLayout()
        self.app_grid_layout.setHorizontalSpacing(20) # iOS-подобные равномерные зазоры
        self.app_grid_layout.setVerticalSpacing(26)
        self.app_grid_layout.setAlignment(Qt.AlignTop | Qt.AlignHCenter) 

        self._populate_grid_apps() # Вызываем метод для заполнения сетки

        for i in range(self._current_grid_columns):
            self.app_grid_layout.setColumnStretch(i, 1)

        main_vlayout.addLayout(self.app_grid_layout)
        
        main_vlayout.addStretch(2) 

        # --- Док-панель: стеклянная капсула в стиле iOS 16 ---
        self.dock_frame = QFrame(self)
        self.dock_frame.setStyleSheet("""
            QFrame {
                background-color: rgba(255, 255, 255, 0.10);
                border-radius: 34px;
                border: 1px solid rgba(255, 255, 255, 0.14);
            }
        """)
        self.dock_frame.setFixedHeight(92) 
        self.dock_frame.setMaximumWidth(480) 

        self.dock_layout = QHBoxLayout(self.dock_frame) 
        self.dock_layout.setContentsMargins(22, 10, 22, 10) 
        self.dock_layout.setSpacing(22) 
        self.dock_layout.setAlignment(Qt.AlignCenter)

        self._populate_dock_apps() # Вызываем метод для заполнения дока


        main_vlayout.addWidget(self.dock_frame, alignment=Qt.AlignCenter)
        main_vlayout.addSpacing(14) 
        
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

        # iOS 16: на рабочем столе крупное «Добро пожаловать, {имя}»
        username = getattr(self.main_window, "current_username", None) or "Пользователь"
        if username in ("None", ""):
            username = "Пользователь"
        base_greeting = current_locale.get("Greeting", "Добро пожаловать")
        self.greeting_label.setText(f"{base_greeting}, {username}")

        # Обновляем тексты для иконок в сетке
        for app_icon in self.grid_app_icons:
            new_name = current_locale.get(app_icon.app_id, app_icon.app_name)
            if app_icon.name_label:
                app_icon._elide_name(new_name)
        
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
        iOS/OxygenOS-style: параллельно запускаем morph-разворот иконки в экран
        и мягкое затухание сетки дока/лаунчера; по окончании морфа эмитируем
        сигнал запуска приложения (окно появляется уже «под» анимацией).
        """
        self.current_app_id_to_launch = app_id
        self.current_icon_rect_for_animation = icon_rect

        # 1) Морф-оверлей рисуем на корне окна (над статусбаром/доком), чтобы
        #    разворачивающаяся иконка перекрывала весь рабочий стол — как zoom
        #    transition в iOS.
        root = self.window()
        target_rect = QRect(root.rect().topLeft(), root.size()) if root else QRect(icon_rect)
        src_icon = None
        for ic in self.grid_app_icons + self.dock_app_icons:
            if ic.app_id == app_id:
                src_icon = ic
                break
        pixmap = src_icon._original_pixmap if src_icon else None

        self._morph_pending = False
        self._morph = MorphOverlay(root, icon_rect, target_rect, pixmap=pixmap,
                                   corner_start=22, corner_end=0)

        # 2) Параллельно: лаунчер слегка уменьшается и уходит в fade
        #    (precise deceleration), как домашний экран при zoom-переходе iOS.
        #    QGraphicsOpacityEffect наследуется дочерними виджетами, поэтому
        #    scale+fade вешаются на сам лаунчер ОДНИМ драйвером — без конфликта
        #    с per-icon opacity во время волны появления.
        if hasattr(self, "_stagger"):
            self._stagger.stop_all()
        if getattr(self, "_flyin_driver", None) is not None:
            self._flyin_driver.stop()
            self._flyin_driver = None
        for icon in self.grid_app_icons + self.dock_app_icons:
            icon._opacity = 1.0
            icon._scale_factor = 1.0
            base = getattr(icon, "_flyin_base_y", None)
            if base is not None:
                icon.move(icon.x(), base)
            icon.update()
        eff = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(eff)
        base_size = self.size()
        base_pos = self.pos()

        def launch_out_frame(p):
            eff.setOpacity(1.0 - p)
            s = 1.0 - 0.06 * p
            w = max(1, int(base_size.width() * s))
            h = max(1, int(base_size.height() * s))
            self.setGeometry(base_pos.x() + (base_size.width() - w) // 2,
                             base_pos.y() + (base_size.height() - h) // 2,
                             w, h)

        self._launch_out_driver = _FrameDriver(
            Duration.LAUNCH, Easing.ACCELERATE, launch_out_frame,
            on_finished=self._on_outgoing_animation_finished, parent=self)
        self._launch_out_driver.start()

        # 3) Пружинный отклик самой иконки при нажатии уже обработан в AppIcon.
        #    Морф перекрывает экран до самого открытия приложения: сигнал
        #    запуска эмитим на последнем кадре — переход выглядит непрерывным.
        def _emit_launch():
            self._morph_pending = True
            self._on_outgoing_animation_finished()

        self._morph.run_open(duration=Duration.LAUNCH, curve=Easing.STANDARD,
                             on_finished=_emit_launch)

    def _on_outgoing_animation_finished(self):
        """
        Вызывается после завершения анимации скрытия лаунчера.
        Эмитирует сигнал для MainWindow для запуска приложения.
        """
        self.setGraphicsEffect(None)
        if getattr(self, "_hide_fade", None) is not None:
            try:
                self._hide_fade.stop()
            except Exception:
                pass
            self._hide_fade = None
        if getattr(self, "_launch_out_driver", None) is not None:
            self._launch_out_driver.stop()
            self._launch_out_driver = None
        self.setGeometry(self.parent().geometry()) if self.parent() else None

        self.hide()

        # Эмитируем запуск только когда морф дошёл до конца (или fade завершился
        # раньше — тогда морф дорабатываем сами и скрываем под открытым экраном).
        if getattr(self, "_morph_pending", False):
            self._morph_pending = False
            self.launch_app_requested.emit(self.current_app_id_to_launch,
                                           self.current_icon_rect_for_animation)
        elif getattr(self, "_morph", None) is not None:
            pass  # ждём on_finished морфа — там произойдёт emit

    def animate_icons_in(self, origin=None):
        """
        Появление иконок в стиле iOS/MIUI: они НЕ «волной» — каждая иконка
        ПРИЛЕТАЕТ снизу вверх с spring-оседанием (overshoot) и лёгким
        масштабным pop'ом. Единый frame-драйвер на всю сетку (60 FPS),
        stagger — маленькая диагональная задержка, чтобы выглядело как
        «россыпь прилетевших плиток», а не как последовательная волна.

        origin (QPointF|None): если задан — задержка каждой иконки считается
        по расстоянию от этой точки (волна расходится ОТ неё), например от
        кнопки «Начать работу» в конце OOBE.
        """
        all_icons = self.grid_app_icons + self.dock_app_icons

        # Дожидаемся реальной раскладки (grid может быть ещё не отложен)
        if not all_icons or all(i.height() <= 0 for i in all_icons):
            QTimer.singleShot(0, lambda: self.animate_icons_in(origin))
            return

        # Сброс: спрятанные, но НЕ уменьшенные в 0 (прилёт делает свой scale)
        for icon in all_icons:
            icon._scale_factor = 1.0
            icon.opacity = 0.0
            icon.show()

        if not hasattr(self, "_flyin_driver"):
            self._flyin_driver = None
        if self._flyin_driver is not None:
            self._flyin_driver.stop()
            self._flyin_driver = None

        # Сохраняем целевые позиции (после layout'а) — относительные, т.к.
        # absolute pos меняется при resize; offset применяем к текущему x/y
        entries = []
        columns = max(1, self._current_grid_columns)
        for i, icon in enumerate(self.grid_app_icons):
            row, col = divmod(i, columns)
            entries.append((icon, (row + col) * 0.045))
        for j, icon in enumerate(self.dock_app_icons):
            entries.append((icon, 0.02 + j * 0.05))  # док — чуть раньше всех

        total_ms = Duration.STANDARD + 260  # ~580 мс на весь прилёт
        stagger = self._stagger if hasattr(self, "_stagger") else None
        if stagger is not None:
            stagger.stop_all()  # убить остаточные драйверы старых волн

        greeting = getattr(self, "greeting_label", None)
        greet_base_y = greeting.y() if greeting is not None else 0

        def on_frame(p):
            for icon, off in entries:
                lp = max(0.0, min(1.0, (p - off) / max(1e-6, 1.0 - off)))
                dy, scale, opacity = fly_in_transform(lp)
                icon.set_scale(scale)
                icon.opacity = opacity
                # вертикальный полёт относительно базовой позиции
                base = getattr(icon, "_flyin_base_y", None)
                if base is None:
                    base = icon.y()
                    icon._flyin_base_y = base
                icon.move(icon.x(), int(base + dy))
            if greeting is not None:
                gp = max(0.0, min(1.0, p / 0.55))
                s = spring_progress(gp)
                greeting.move(greeting.x(), int(greet_base_y + 18.0 * (1.0 - s)))
                try:
                    greeting.windowOpacity  # noqa — эффект ниже через effect
                except Exception:
                    pass

        def finish():
            self._flyin_driver = None
            for icon, _ in entries:
                icon.set_scale(1.0)
                icon.opacity = 1.0
                base = getattr(icon, "_flyin_base_y", None)
                if base is not None:
                    icon.move(icon.x(), base)
            if greeting is not None:
                greeting.move(greeting.x(), greet_base_y)
                greeting.setGraphicsEffect(None)

        # Приветствие — затухание через opacity effect параллельно прилёту
        if greeting is not None:
            from PyQt5.QtWidgets import QGraphicsOpacityEffect as _GOE
            eff = _GOE(greeting)
            eff.setOpacity(0.0)
            greeting.setGraphicsEffect(eff)
            _orig_on_frame = on_frame

            def on_frame(p, _eff=eff, _of=_orig_on_frame):
                _of(p)
                _eff.setOpacity(min(1.0, p * 2.2))

        self._flyin_driver = _FrameDriver(total_ms, QEasingCurve.Linear,
                                          on_frame, finish, self)
        self._flyin_driver.start()

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

        w, h = self.width(), self.height()

        # iOS 16 wallpaper: глубокий тёмный «graphite» с мягкими цветными
        # радиальными пятнами (как обои Default / Carbon Star).
        base = QLinearGradient(0, 0, 0, h)
        base.setColorAt(0.0, QColor("#0b0d14"))
        base.setColorAt(0.5, QColor("#131722"))
        base.setColorAt(1.0, QColor("#0a0c12"))
        painter.fillRect(self.rect(), QBrush(base))

        glows = [
            (0.22 * w, 0.16 * h, 0.95 * w, QColor(58, 78, 140, 90)),   # синий сверху слева
            (0.85 * w, 0.42 * h, 0.85 * w, QColor(120, 60, 150, 60)),  # фиолетовый справа
            (0.45 * w, 1.02 * h, 0.9 * w, QColor(30, 90, 130, 70)),    # teal снизу
        ]
        for gx, gy, gr, gc in glows:
            rg = QRadialGradient(gx, gy, gr)
            rg.setColorAt(0.0, gc)
            outer = QColor(gc)
            outer.setAlpha(0)
            rg.setColorAt(1.0, outer)
            painter.setBrush(QBrush(rg))
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
