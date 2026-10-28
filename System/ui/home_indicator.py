# ui/home_indicator.py
from PyQt5.QtWidgets import QFrame, QHBoxLayout
from PyQt5.QtCore import Qt, QSize

class HomeIndicatorWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(150, 5) # Ширина и высота индикатора
        self.setStyleSheet("""
            HomeIndicatorWidget {
                background-color: white; /* Белый цвет индикатора */
                border-radius: 2.5px; /* Скругленные углы */
            }
        """)
        self.setContentsMargins(0,0,0,0) # Уберем отступы

        # Центрируем индикатор внутри родительского макета, если он будет в QHBoxLayout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setAlignment(Qt.AlignCenter)
        # Этот виджет сам по себе и есть индикатор, поэтому не нужно добавлять QLabel в него.
        # Просто его фон и размер создают полоску.