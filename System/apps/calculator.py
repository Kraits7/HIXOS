# apps/calculator.py
import sys
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGridLayout, QApplication, QMainWindow, QSizePolicy, QSpacerItem
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt, pyqtSignal

class CalculatorContent(QWidget):
    # Сигнал для возврата в лаунчер
    go_back_to_launcher_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.current_expression = ""
        self.result = ""
        self.operand_entered = False # Флаг для отслеживания ввода операнда после операции

        self.setStyleSheet("""
            QWidget {
                background-color: #2c2c2c;
                color: white;
                font-family: "Segoe UI", "SF Pro Display", "Roboto", sans-serif;
            }
            QLabel#display_label {
                background-color: #1a1a1a;
                color: #FFFFFF;
                font-size: 48px;
                padding: 10px;
                border-radius: 10px;
                qproperty-alignment: 'AlignRight | AlignVCenter';
                min-height: 80px; /* Минимальная высота для дисплея */
            }
            QPushButton {
                background-color: #4CAF50; /* Зеленый для цифр */
                color: white;
                border-radius: 10px;
                padding: 15px;
                font-size: 24px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3e8e41;
            }
            QPushButton[cssClass="operator"] {
                background-color: #FF9800; /* Оранжевый для операторов */
            }
            QPushButton[cssClass="operator"]:hover {
                background-color: #fb8c00;
            }
            QPushButton[cssClass="operator"]:pressed {
                background-color: #f57c00;
            }
            QPushButton[cssClass="clear"] {
                background-color: #f44336; /* Красный для C */
            }
            QPushButton[cssClass="clear"]:hover {
                background-color: #e53935;
            }
            QPushButton[cssClass="clear"]:pressed {
                background-color: #d32f2f;
            }
            QPushButton[cssClass="equals"] {
                background-color: #007AFF; /* Синий для = */
            }
            QPushButton[cssClass="equals"]:hover {
                background-color: #0056b3;
            }
            QPushButton[cssClass="equals"]:pressed {
                background-color: #004d9c;
            }
            QPushButton#back_button {
                background-color: #333; /* Темно-серый для кнопки "Назад" */
                color: white;
                border-radius: 10px;
                padding: 10px 20px;
                font-size: 16px;
                font-weight: bold;
                margin-top: 20px;
            }
            QPushButton#back_button:hover {
                background-color: #555;
            }
        """)
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- Дисплей калькулятора ---
        self.display_label = QLabel(self)
        self.display_label.setObjectName("display_label") # Для QSS
        self.display_label.setText("0")
        self.display_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        main_layout.addWidget(self.display_label)

        # --- Сетка кнопок ---
        grid_layout = QGridLayout()
        grid_layout.setSpacing(10)

        buttons = [
            ('C', 'clear'), ('/', 'operator'), ('*', 'operator'),
            ('7', ''), ('8', ''), ('9', ''), ('-', 'operator'),
            ('4', ''), ('5', ''), ('6', ''), ('+', 'operator'),
            ('1', ''), ('2', ''), ('3', ''),
            ('0', ''), ('.', ''), ('=', 'equals')
        ]

        row = 0
        col = 0
        for btn_text, css_class in buttons:
            button = QPushButton(btn_text)
            if css_class:
                button.setProperty("cssClass", css_class)
            
            button.clicked.connect(lambda _, text=btn_text: self.button_clicked(text))
            
            # Особый случай для кнопки '=' (занимает 2 колонки)
            if btn_text == '=':
                grid_layout.addWidget(button, row, col, 1, 2) # 1 строка, 2 колонки
                col += 2
            else:
                grid_layout.addWidget(button, row, col)
                col += 1

            if col > 3: # Переход на следующую строку после 4 кнопок (или 3, если была =)
                col = 0
                row += 1
            elif btn_text == '+' : # Если был оператор +, переходим на новую строку
                col = 0
                row += 1

        main_layout.addLayout(grid_layout)

        main_layout.addStretch(1) # Растяжка внизу

        # --- Кнопка "Назад в Лаунчер" ---
        self.back_button = QPushButton("Назад в Лаунчер")
        self.back_button.setObjectName("back_button") # Для QSS
        self.back_button.clicked.connect(self.go_back_to_launcher_requested.emit)
        main_layout.addWidget(self.back_button, alignment=Qt.AlignCenter)

    def button_clicked(self, char):
        if char == 'C':
            self.current_expression = ""
            self.result = ""
            self.operand_entered = False
            self.display_label.setText("0")
        elif char == '=':
            try:
                # Очищаем выражение от некорректных символов, если они случайно попали
                self.current_expression = self.current_expression.replace('×', '*').replace('÷', '/')
                self.result = str(eval(self.current_expression))
                self.display_label.setText(self.result)
                self.current_expression = self.result # Результат становится началом нового выражения
                self.operand_entered = True # Результат воспринимается как введенный операнд
            except (SyntaxError, ZeroDivisionError, TypeError) as e:
                self.display_label.setText("Ошибка")
                self.current_expression = ""
                self.result = ""
                self.operand_entered = False
                print(f"Ошибка калькулятора: {e}")
        elif char in ['/', '*', '+', '-']:
            # Если предыдущий символ тоже оператор, заменяем его
            if self.current_expression and self.current_expression[-1] in ['/', '*', '+', '-']:
                self.current_expression = self.current_expression[:-1] + char
            else:
                self.current_expression += char
            self.operand_entered = False # Сбрасываем флаг после оператора
            self.display_label.setText(self.current_expression)
        elif char == '.':
            # Добавляем десятичную точку, если ее еще нет в текущем числе
            # Проверяем, есть ли уже точка в последнем числе или после последнего оператора
            if not self.current_expression or self.current_expression[-1] in ['/', '*', '+', '-']:
                self.current_expression += "0." # Начинаем с 0. если точка первая
            elif '.' not in self.current_expression.split(self._get_last_operator())[-1]:
                self.current_expression += char
            self.display_label.setText(self.current_expression)
        else: # Цифры
            if self.result and self.operand_entered: # Если это новое число после получения результата
                self.current_expression = char
                self.result = ""
                self.operand_entered = False
            else:
                self.current_expression += char
            self.display_label.setText(self.current_expression)

    def _get_last_operator(self):
        """Вспомогательная функция для получения последнего оператора в выражении."""
        operators = ['+', '-', '*', '/']
        last_op_index = -1
        for op in operators:
            idx = self.current_expression.rfind(op)
            if idx > last_op_index:
                last_op_index = idx
        if last_op_index != -1:
            return self.current_expression[last_op_index]
        return ''

# Для тестирования CalculatorContent отдельно
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setFixedSize(519, 950) # Имитируем размер основного окна

    calculator = CalculatorContent(window)
    
    def on_back_to_launcher():
        print("Запрос на возврат в лаунчер из калькулятора.")
        window.close() # Закрыть тестовое окно

    calculator.go_back_to_launcher_requested.connect(on_back_to_launcher)

    window.setCentralWidget(calculator)
    window.show()
    sys.exit(app.exec_())
