# apps/camera.py
import sys
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QApplication, QMainWindow, QMessageBox
)
from PyQt5.QtMultimedia import QCamera, QCameraImageCapture, QCameraInfo
from PyQt5.QtMultimediaWidgets import QCameraViewfinder
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, pyqtSignal, QSize, QBuffer, QIODevice

class CameraContent(QWidget):
    # Сигнал для возврата в лаунчер
    go_back_to_launcher_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.main_window = parent
        self.camera = None
        self.image_capture = None
        self.viewfinder = None
        self.captured_image_label = None

        self.setStyleSheet("""
            QWidget {
                background-color: #1a1a1a; /* Темный фон для камеры */
                color: white;
                font-family: "Segoe UI", "SF Pro Display", "Roboto", sans-serif;
            }
            QPushButton {
                background-color: #007AFF;
                color: white;
                border-radius: 8px;
                padding: 10px 20px;
                font-size: 15px;
                font-weight: bold;
                margin: 5px;
            }
            QPushButton:hover {
                background-color: #0056b3;
            }
            QPushButton:pressed {
                background-color: #004d9c;
            }
            QPushButton#back_to_launcher_button {
                background-color: #333;
                color: white;
                border-radius: 10px;
                padding: 12px 25px;
                font-size: 16px;
                font-weight: bold;
                margin-top: 20px;
            }
            QPushButton#back_to_launcher_button:hover {
                background-color: #555;
            }
            QLabel#status_message {
                font-size: 14px;
                color: #ccc;
                text-align: center;
                margin-top: 10px;
            }
        """)
        self.init_ui()
        self.initialize_camera()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # Сообщение о статусе камеры
        self.status_message_label = QLabel("Инициализация камеры...")
        self.status_message_label.setObjectName("status_message")
        self.status_message_label.setAlignment(Qt.AlignCenter)
        main_layout.addWidget(self.status_message_label)
        
        # Видоискатель камеры
        self.viewfinder = QCameraViewfinder(self)
        self.viewfinder.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.viewfinder.setStyleSheet("border: 1px solid #444; background-color: black;")
        main_layout.addWidget(self.viewfinder)

        # Метка для отображения захваченного изображения
        self.captured_image_label = QLabel("Изображение не захвачено")
        self.captured_image_label.setAlignment(Qt.AlignCenter)
        self.captured_image_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.captured_image_label.setStyleSheet("background-color: #333; border: 1px dashed #555;")
        self.captured_image_label.hide() # Изначально скрыто
        main_layout.addWidget(self.captured_image_label)

        # Кнопки управления камерой
        control_layout = QHBoxLayout()
        control_layout.addStretch(1)

        self.capture_button = QPushButton("Сделать фото")
        self.capture_button.clicked.connect(self.take_photo)
        self.capture_button.setEnabled(False) # Изначально неактивна
        control_layout.addWidget(self.capture_button)

        self.retake_button = QPushButton("Переснять")
        self.retake_button.clicked.connect(self.retake_photo)
        self.retake_button.setEnabled(False) # Изначально неактивна
        control_layout.addWidget(self.retake_button)

        control_layout.addStretch(1)
        main_layout.addLayout(control_layout)

        # Кнопка "Назад в Лаунчер"
        self.back_to_launcher_button = QPushButton("Назад в Лаунчер")
        self.back_to_launcher_button.setObjectName("back_to_launcher_button")
        self.back_to_launcher_button.clicked.connect(self.go_back_to_launcher_requested.emit)
        main_layout.addWidget(self.back_to_launcher_button, alignment=Qt.AlignCenter)

    def initialize_camera(self):
        available_cameras = QCameraInfo.availableCameras()
        if not available_cameras:
            self.status_message_label.setText("Ошибка: Камера не найдена.")
            self.capture_button.setEnabled(False)
            self.viewfinder.hide()
            self.captured_image_label.setText("Камера не доступна")
            self.captured_image_label.show()
            QMessageBox.warning(self, "Ошибка Камеры", "Камера не найдена на вашем устройстве.")
            return

        self.camera = QCamera(available_cameras[0]) # Используем первую доступную камеру
        self.camera.setViewfinder(self.viewfinder)

        self.image_capture = QCameraImageCapture(self.camera)
        self.image_capture.readyForCaptureChanged.connect(self._on_ready_for_capture_changed)
        self.image_capture.imageCaptured.connect(self._on_image_captured)
        self.image_capture.imageSaved.connect(self._on_image_saved)
        self.image_capture.error.connect(self._on_capture_error)

        self.camera.statusChanged.connect(self._on_camera_status_changed)
        self.camera.error.connect(self._on_camera_error)
        
        self.camera.start()
        self.status_message_label.setText("Запуск камеры...")

    def _on_ready_for_capture_changed(self, ready):
        self.capture_button.setEnabled(ready)
        if ready:
            self.status_message_label.setText("Камера готова.")

    def take_photo(self):
        if self.image_capture and self.image_capture.isReadyForCapture():
            self.status_message_label.setText("Делаем фото...")
            self.viewfinder.hide() # Скрываем видоискатель при захвате
            self.captured_image_label.show() # Показываем метку для изображения
            # Захватываем изображение
            self.image_capture.capture()
            self.capture_button.setEnabled(False) # Отключаем кнопку пока идет захват
            self.retake_button.setEnabled(False)
        else:
            self.status_message_label.setText("Камера не готова для захвата.")

    def _on_image_captured(self, requestId, img):
        # Отображаем захваченное изображение
        pixmap = QPixmap.fromImage(img)
        # Масштабируем изображение, чтобы оно помещалось в QLabel
        scaled_pixmap = pixmap.scaled(
            self.captured_image_label.size(), 
            Qt.KeepAspectRatio, 
            Qt.SmoothTransformation
        )
        self.captured_image_label.setPixmap(scaled_pixmap)
        self.captured_image_label.setText("") # Очищаем текст, если изображение отображается

        self.status_message_label.setText("Фото сделано.")
        self.retake_button.setEnabled(True) # Включаем кнопку "Переснять"

    def _on_image_saved(self, requestId, filename):
        # Этот сигнал может быть использован для подтверждения сохранения на диск, если это реализовано.
        print(f"Изображение сохранено в: {filename}")
        self.status_message_label.setText(f"Фото сохранено: {os.path.basename(filename)}")


    def _on_capture_error(self, id, error, errorString):
        self.status_message_label.setText(f"Ошибка захвата: {errorString}")
        self.capture_button.setEnabled(True)
        self.retake_button.setEnabled(False)
        self.viewfinder.show() # Возвращаем видоискатель
        self.captured_image_label.hide() # Скрываем метку
        QMessageBox.critical(self, "Ошибка Захвата", f"Произошла ошибка при захвате изображения: {errorString}")

    def _on_camera_status_changed(self, status):
        # Можно использовать для более детального отслеживания статуса камеры
        # print(f"Статус камеры: {status}")
        pass

    def _on_camera_error(self, error):
        self.status_message_label.setText(f"Ошибка камеры: {error}")
        self.capture_button.setEnabled(False)
        self.retake_button.setEnabled(False)
        self.viewfinder.hide()
        self.captured_image_label.setText(f"Ошибка камеры: {error}")
        self.captured_image_label.show()
        QMessageBox.critical(self, "Ошибка Камеры", f"Произошла ошибка с камерой: {error}")


    def retake_photo(self):
        self.captured_image_label.hide()
        self.captured_image_label.setPixmap(QPixmap()) # Очищаем предыдущее изображение
        self.captured_image_label.setText("Изображение не захвачено")
        self.viewfinder.show()
        self.status_message_label.setText("Камера готова.")
        self.capture_button.setEnabled(True)
        self.retake_button.setEnabled(False) # Отключаем до следующего захвата

    def showEvent(self, event):
        """Переопределяем showEvent для запуска камеры при появлении виджета."""
        super().showEvent(event)
        if self.camera and self.camera.status() == QCamera.CameraStatus.UnloadedStatus:
            self.camera.start()
            self.status_message_label.setText("Запуск камеры...")
            self.captured_image_label.hide() # Убедимся, что метка скрыта при запуске камеры
            self.viewfinder.show()

    def hideEvent(self, event):
        """Переопределяем hideEvent для остановки камеры при скрытии виджета."""
        if self.camera and self.camera.status() != QCamera.CameraStatus.UnloadedStatus:
            self.camera.stop()
            self.status_message_label.setText("Камера остановлена.")
        super().hideEvent(event)

    def closeEvent(self, event):
        """Останавливаем камеру при закрытии приложения."""
        if self.camera:
            self.camera.stop()
        super().closeEvent(event)


# Пример использования (для тестирования только CameraContent)
if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setFixedSize(519, 950) # Имитируем размер основного окна

    camera_widget = CameraContent(window)
    
    def on_back_to_launcher():
        print("Запрос на возврат в лаунчер из камеры.")
        window.close() # Закрыть тестовое окно

    camera_widget.go_back_to_launcher_requested.connect(on_back_to_launcher)

    window.setCentralWidget(camera_widget)
    window.show()
    sys.exit(app.exec_())
