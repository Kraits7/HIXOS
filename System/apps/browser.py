# apps/browser.py
import sys
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSizePolicy, QApplication, QMainWindow
)
from PyQt5.QtWebEngineWidgets import QWebEngineView, QWebEnginePage # Импорт для браузера
from PyQt5.QtCore import Qt, pyqtSignal, QUrl

class BrowserContent(QWidget):
    # Сигнал для возврата в лаунчер
    go_back_to_launcher_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent

        self.setStyleSheet("""
            QWidget {
                background-color: #2c2c2c;
                color: white;
                font-family: "Segoe UI", "SF Pro Display", "Roboto", sans-serif;
            }
            QLineEdit {
                border: 1px solid #555;
                border-radius: 8px;
                padding: 8px 10px;
                background-color: #3a3a3a;
                color: white;
                font-size: 14px;
            }
            QPushButton {
                background-color: #007AFF;
                color: white;
                border-radius: 8px;
                padding: 8px 15px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004d9c;
            }
            QPushButton#nav_button { /* Стиль для навигационных кнопок браузера */
                background-color: #555;
                padding: 5px 10px;
                border-radius: 5px;
                font-size: 18px;
            }
            QPushButton#nav_button:hover {
                background-color: #777;
            }
            QPushButton#nav_button:pressed {
                background-color: #999;
            }
            QPushButton#back_to_launcher_button {
                background-color: #333;
                color: white;
                border-radius: 10px;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
                margin-top: 20px;
            }
            QPushButton#back_to_launcher_button:hover {
                background-color: #555;
            }
        """)
        self.init_ui()
        self.load_default_url()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # --- Адресная строка и навигационные кнопки ---
        url_bar_layout = QHBoxLayout()
        
        self.back_button = QPushButton("←")
        self.back_button.setObjectName("nav_button")
        self.back_button.setFixedSize(35, 35)
        self.back_button.clicked.connect(self.go_back)
        url_bar_layout.addWidget(self.back_button)

        self.forward_button = QPushButton("→")
        self.forward_button.setObjectName("nav_button")
        self.forward_button.setFixedSize(35, 35)
        self.forward_button.clicked.connect(self.go_forward)
        url_bar_layout.addWidget(self.forward_button)

        self.reload_button = QPushButton("↻")
        self.reload_button.setObjectName("nav_button")
        self.reload_button.setFixedSize(35, 35)
        self.reload_button.clicked.connect(self.reload_page)
        url_bar_layout.addWidget(self.reload_button)

        self.url_input = QLineEdit(self)
        self.url_input.setPlaceholderText("Введите URL")
        self.url_input.returnPressed.connect(self.navigate_to_url)
        url_bar_layout.addWidget(self.url_input)

        self.go_button = QPushButton("Перейти")
        self.go_button.clicked.connect(self.navigate_to_url)
        url_bar_layout.addWidget(self.go_button)

        main_layout.addLayout(url_bar_layout)

        # --- Просмотрщик веб-страниц ---
        self.browser_view = QWebEngineView(self)
        self.browser_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.browser_view.urlChanged.connect(self.update_url_input) # Обновление адресной строки
        self.browser_view.titleChanged.connect(self.update_title) # Обновление заголовка окна
        main_layout.addWidget(self.browser_view)

        # --- Кнопка "Назад в Лаунчер" ---
        self.back_to_launcher_button = QPushButton("Назад в Лаунчер")
        self.back_to_launcher_button.setObjectName("back_to_launcher_button")
        self.back_to_launcher_button.clicked.connect(self.go_back_to_launcher_requested.emit)
        main_layout.addWidget(self.back_to_launcher_button, alignment=Qt.AlignCenter)

    def load_default_url(self):
        # Начальная страница
        self.browser_view.setUrl(QUrl("https://www.google.com"))

    def navigate_to_url(self):
        url = self.url_input.text()
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url # Добавляем HTTPS по умолчанию
        self.browser_view.setUrl(QUrl(url))

    def update_url_input(self, qurl):
        self.url_input.setText(qurl.toString())

    def update_title(self, title):
        # Можно использовать заголовок для чего-то, например, для отладки
        print(f"Заголовок страницы: {title}")

    def go_back(self):
        self.browser_view.back()

    def go_forward(self):
        self.browser_view.forward()

    def reload_page(self):
        self.browser_view.reload()

# Для тестирования BrowserContent отдельно
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setFixedSize(519, 950) # Имитируем размер основного окна

    browser = BrowserContent(window)
    
    def on_back_to_launcher():
        print("Запрос на возврат в лаунчер из браузера.")
        window.close() # Закрыть тестовое окно

    browser.go_back_to_launcher_requested.connect(on_back_to_launcher)

    window.setCentralWidget(browser)
    window.show()
    sys.exit(app.exec_())
