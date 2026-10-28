# minimal_hixos_test.py - Новый файл для диагностики

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget, QDesktopWidget
from PyQt5.QtCore import Qt, QSize

APP_WIDTH = 519
APP_HEIGHT = 950

class MinimalMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('HIXOS - Минимальный Тест')
        self.setGeometry(0, 0, APP_WIDTH, APP_HEIGHT)
        self.setFixedSize(QSize(APP_WIDTH, APP_HEIGHT)) # Используем QSize для setFixedSize

        # Простой черный фон
        self.setStyleSheet("background-color: black;") 

        # Центральный виджет
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # Вертикальный макет для центрального виджета
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Единственный QLabel в центре
        self.test_label = QLabel("Hello from the ABSOLUTE MINIMAL HIXOS Test!\n(If you see this, we are very close to a solution.)", self.central_widget)
        self.test_label.setAlignment(Qt.AlignCenter)
        self.test_label.setStyleSheet("color: white; font-size: 20px; background-color: darkred;")
        self.main_layout.addWidget(self.test_label)

        # Центрирование окна
        self.center_window()
        self.show()

    def center_window(self):
        qr = self.frameGeometry()
        cp = QDesktopWidget().availableGeometry().center()
        qr.moveCenter(cp)
        self.move(qr.topLeft())

if __name__ == '__main__':
    # ЭТОТ КОД ДОЛЖЕН БЫТЬ ТОЛЬКО ЗДЕСЬ
    # Никаких других импортов или инициализаций!

    app = QApplication(sys.argv)
    main_window = MinimalMainWindow()
    sys.exit(app.exec_())