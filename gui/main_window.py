"""Главное окно приложения."""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel, QMainWindow, QMessageBox, QSizePolicy, QVBoxLayout, QWidget

from core.models.network import Network
from gui.map_widget import MapWidget


class MainWindow(QMainWindow):
    """Главное окно приложения моделирования DWDM-сети."""

    def __init__(self, network: Network | None = None):
        super().__init__()
        self.network = network or Network()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("DWDM: топология, трассировка и каналы")
        self.setGeometry(100, 100, 1400, 900)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(2, 2, 2, 2)
        main_layout.setSpacing(2)
        central_widget.setLayout(main_layout)

        # Компактный заголовок, чтобы не съедать высоту в полноэкранном режиме.
        title = QLabel("DWDM: топология, трассировка, каналы и расчет линии")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size: 11pt; font-weight: bold; padding: 0px;")
        title.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        title.setFixedHeight(28)
        main_layout.addWidget(title, 0)

        self.map_widget = MapWidget(self.network)
        main_layout.addWidget(self.map_widget, 1)

        self.statusBar().showMessage(
            "Готово: используйте вкладки слева для работы с топологией, трассировкой и каналами."
        )

    def show_message(self, title: str, message: str, icon=QMessageBox.Information):
        """Показывает сообщение пользователю."""
        msg = QMessageBox(self)
        msg.setIcon(icon)
        msg.setWindowTitle(title)
        msg.setText(message)
        msg.exec_()
