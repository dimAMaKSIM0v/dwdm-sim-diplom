"""Виджет карты для работы с топологией и потоковой структурой сети."""
from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Set, Tuple

import networkx as nx
from PyQt5.QtCore import QObject, Qt, pyqtSignal, pyqtSlot
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QFileDialog,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.managers.topology_analyzer import TopologyAnalyzer
from core.managers.topology_manager import TopologyManager
from core.managers.traffic_manager import TrafficManager
from core.calculators.amplifier_placer import AmplifierPlacer
from core.calculators.attenuation import calculate_channel_attenuation
from core.calculators.dispersion import DispersionCalculator, DispersionResult
from core.calculators.dispersion_visualizer import DispersionVisualizer
from core.calculators.frequency_plan import FrequencyPlan
from core.calculators.power_budget import PowerBudgetResult
from core.managers.simulation_manager import SimulationManager
from core.models.channel import Channel
from core.models.equipment import EquipmentType
from core.models.fiber import Fiber, FiberType
from core.models.network import Network
from core.models.node import Node, NodeType
from utils.project_io import ProjectLoadError, load_network_from_json, save_network_to_json

try:
    from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
    from matplotlib.figure import Figure
except Exception:  # pragma: no cover - runtime fallback if matplotlib is missing
    FigureCanvas = None
    Figure = None

try:
    from openpyxl import Workbook
except Exception:  # pragma: no cover - optional Excel export dependency
    Workbook = None


@dataclass
class MapClickContext:
    device_type: Optional[str] = None
    handler: Optional[Callable[[float, float, Optional[str]], None]] = None


class EyeDiagramDialog(QDialog):
    """Диалоговое окно для отображения глазковой диаграммы в большом размере."""

    def __init__(self, parent, metrics, channel_id: str, modulation: str, laser_type: str):
        super().__init__(parent)
        self.metrics = metrics
        self.channel_id = channel_id
        self.modulation = modulation
        self.laser_type = laser_type

        self.setWindowTitle(f"Глазковая диаграмма — Канал {channel_id}")
        self.resize(1200, 800)

        layout = QVBoxLayout()

        # Заголовок с параметрами
        info_label = QLabel(
            f"<b>Канал:</b> {channel_id} | "
            f"<b>Модуляция:</b> {modulation.upper()} | "
            f"<b>Лазер:</b> {laser_type.upper()} | "
            f"<b>Δλ:</b> {metrics.delta_lambda_nm:.6f} нм | "
            f"<b>Битрейт:</b> {metrics.bitrate_gbps:.1f} Гбит/с"
        )
        info_label.setStyleSheet("font-size: 12pt; padding: 10px; background-color: #f0f0f0; border-radius: 5px;")
        layout.addWidget(info_label)

        # График
        if FigureCanvas is not None and Figure is not None:
            self.figure = Figure(figsize=(12, 8))
            self.canvas = FigureCanvas(self.figure)
            layout.addWidget(self.canvas)

            # Рисуем Eye Diagram
            self._plot_eye_diagram()
        else:
            layout.addWidget(QLabel("Matplotlib недоступен."))

        # Кнопки
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def _plot_eye_diagram(self):
        """Рисует глазковую диаграмму."""
        import numpy as np
        from scipy.special import erf

        axis = self.figure.add_subplot(111)

        # Параметры
        t_bit = self.metrics.t_bit_ps
        sigma_in = self.metrics.sigma_in_ps
        sigma_out = self.metrics.sigma_out_ps
        peak_in = 1.0
        peak_out = self.metrics.peak_ratio

        # SNR параметры
        snr_linear = self.metrics.snr_linear
        osnr_db = self.metrics.osnr_db

        # Эффективные sigma для видимости
        rise_time_in = 2.2 * sigma_in
        rise_time_out = 2.2 * sigma_out

        # Временная ось: расширяем до ±2.5*t_bit для полного покрытия
        n_samples = 5000
        t_axis = np.linspace(-2.5 * t_bit, 2.5 * t_bit, n_samples)

        # Генерируем все 5-битовые последовательности для центрального бита
        # [a, b, CENTER, d, e] - центральный бит в позиции [0, t_bit]
        traces_high_in = []
        traces_low_in = []
        traces_high_out = []
        traces_low_out = []

        for a in [0, 1]:
            for b in [0, 1]:
                for c in [0, 1]:  # центральный бит
                    for d in [0, 1]:
                        for e in [0, 1]:
                            y_in = np.zeros_like(t_axis)
                            y_out = np.zeros_like(t_axis)

                            # 5 битов: позиции [-2, -1, 0, 1, 2] * t_bit
                            bit_sequence = [a, b, c, d, e]
                            for bit_idx, bit_val in enumerate(bit_sequence):
                                t_start = (bit_idx - 2) * t_bit
                                t_end = (bit_idx - 1) * t_bit

                                if bit_val == 1:
                                    # Входной сигнал
                                    sigma_eff_in = max(sigma_in, t_bit * 0.005)
                                    y_in += 0.5 * peak_in * (1 + erf((t_axis - t_start) / (sigma_eff_in * np.sqrt(2))))
                                    y_in -= 0.5 * peak_in * (1 + erf((t_axis - t_end) / (sigma_eff_in * np.sqrt(2))))

                                    # Выходной сигнал
                                    sigma_eff_out = max(sigma_out, t_bit * 0.02)
                                    y_out += 0.5 * peak_out * (1 + erf((t_axis - t_start) / (sigma_eff_out * np.sqrt(2))))
                                    y_out -= 0.5 * peak_out * (1 + erf((t_axis - t_end) / (sigma_eff_out * np.sqrt(2))))

                            # Классифицируем по центральному биту (c)
                            if c == 1:
                                traces_high_in.append(y_in)
                                traces_high_out.append(y_out)
                            else:
                                traces_low_in.append(y_in)
                                traces_low_out.append(y_out)

        # Вычисляем уровень шума на основе SNR
        noise_std = 0.0
        if snr_linear is not None and snr_linear > 0:
            # Стандартное отклонение шума: σ_noise = A_signal / √SNR
            # Используем пиковую амплитуду выходного сигнала
            noise_std = peak_out / np.sqrt(snr_linear)
            print(f"DEBUG Eye Diagram: SNR_linear = {snr_linear:.2f}, noise_std = {noise_std:.6f}")

        # Рисуем только выходной сигнал (без входного) с добавлением шума
        for y_out in traces_high_out:
            # Добавляем гауссов шум к каждой трассе
            if noise_std > 0:
                noise = np.random.normal(0, noise_std, len(y_out))
                y_out_noisy = y_out + noise
            else:
                y_out_noisy = y_out
            axis.plot(t_axis, y_out_noisy, color="#E53935", linewidth=2.5, alpha=0.7)

        for y_out in traces_low_out:
            if noise_std > 0:
                noise = np.random.normal(0, noise_std, len(y_out))
                y_out_noisy = y_out + noise
            else:
                y_out_noisy = y_out
            axis.plot(t_axis, y_out_noisy, color="#FF9800", linewidth=2.5, alpha=0.7)

        # Оформление
        axis.set_title("Eye Diagram (глазковая диаграмма): влияние дисперсии на качество сигнала",
                      fontsize=14, fontweight="bold", pad=20)
        axis.set_xlabel("Время в битовом интервале (пс)", fontsize=12)
        axis.set_ylabel("Нормализованная мощность", fontsize=12)
        axis.grid(True, linestyle="--", alpha=0.3)
        axis.set_xlim(-t_bit * 1.5, t_bit * 1.5)

        # Автоматический масштаб по Y: показываем только область "глаза"
        # с небольшими отступами сверху и снизу
        y_margin = peak_out * 0.15  # 15% отступ от пика
        axis.set_ylim(-y_margin, peak_out + y_margin)

        # Пороговая линия
        threshold = 0.5 * peak_out
        axis.axhline(threshold, color="green", linestyle="--", alpha=0.8, linewidth=2.5,
                    label=f"Порог решения ({threshold:.2f})")

        # Центр бита
        axis.axvline(0, color="gray", linestyle=":", alpha=0.6, linewidth=1.5)
        axis.text(0, peak_out + y_margin * 0.85, "Центр бита (оптимальная точка семплирования)",
                 ha="center", fontsize=10, color="gray", fontweight="bold")

        # Легенда
        from matplotlib.patches import Patch
        legend_elements = [
            Patch(facecolor="#E53935", alpha=0.7, label="Выходной: бит=1"),
            Patch(facecolor="#FF9800", alpha=0.7, label="Выходной: бит=0"),
        ]
        axis.legend(handles=legend_elements, loc="upper right", fontsize=11)

        # Информационная панель
        snr_info = ""
        if osnr_db is not None:
            snr_info = f"OSNR = {osnr_db:.2f} дБ"
            if snr_linear is not None:
                snr_db = 10 * np.log10(snr_linear) if snr_linear > 0 else 0
                snr_info += f", SNR ≈ {snr_db:.2f} дБ (linear: {snr_linear:.1f})"
            snr_info += "\n"

        eye_info = (
            f"{snr_info}"
            f"σ_in = {sigma_in:.3f} пс (время нарастания ≈ {rise_time_in:.2f} пс)\n"
            f"σ_out = {sigma_out:.3f} пс (время нарастания ≈ {rise_time_out:.2f} пс)\n"
            f"Битовый интервал = {t_bit:.1f} пс\n"
            f"τ_CD = {self.metrics.tau_cd_ps:.1f} пс, τ_PMD = {self.metrics.tau_pmd_ps:.2f} пс\n"
            f"Потери = {self.metrics.net_loss_db:.2f} дБ, пик = {peak_out:.3f}\n"
            f"Задержка = {self.metrics.group_delay_s*1e3:.3f} мс"
        )
        axis.text(0.02, 0.02, eye_info, transform=axis.transAxes,
                 fontsize=10, verticalalignment='bottom',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7, pad=0.8))

        self.figure.tight_layout()
        self.canvas.draw()


class NodeEditDialog(QDialog):
    """Диалог редактирования узла."""

    def __init__(self, parent=None, node_data=None):
        super().__init__(parent)
        self.node_data = node_data or {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Редактирование узла" if self.node_data else "Новый узел")
        self.setGeometry(120, 120, 420, 360)

        layout = QFormLayout()
        self.node_id_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.type_combo = QComboBox()
        self.type_combo.addItems([nt.value for nt in NodeType])
        self.territory_edit = QLineEdit()
        self.organization_edit = QLineEdit()
        self.lat_spin = QDoubleSpinBox()
        self.lat_spin.setRange(-90.0, 90.0)
        self.lat_spin.setDecimals(6)
        self.lon_spin = QDoubleSpinBox()
        self.lon_spin.setRange(-180.0, 180.0)
        self.lon_spin.setDecimals(6)

        layout.addRow("ID узла:", self.node_id_edit)
        layout.addRow("Название:", self.name_edit)
        layout.addRow("Тип узла:", self.type_combo)
        layout.addRow("Территория:", self.territory_edit)
        layout.addRow("Организация:", self.organization_edit)
        layout.addRow("Широта:", self.lat_spin)
        layout.addRow("Долгота:", self.lon_spin)

        if self.node_data:
            self.node_id_edit.setText(self.node_data.get("node_id", ""))
            self.node_id_edit.setReadOnly(True)
            self.name_edit.setText(self.node_data.get("name", ""))
            self.type_combo.setCurrentText(self.node_data.get("node_type", NodeType.TERMINAL.value))
            self.territory_edit.setText(self.node_data.get("territory", ""))
            self.organization_edit.setText(self.node_data.get("organization", ""))
            self.lat_spin.setValue(float(self.node_data.get("latitude", 0.0)))
            self.lon_spin.setValue(float(self.node_data.get("longitude", 0.0)))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.setLayout(layout)

    def get_data(self) -> dict:
        return {
            "node_id": self.node_id_edit.text().strip(),
            "name": self.name_edit.text().strip(),
            "node_type": self.type_combo.currentText(),
            "territory": self.territory_edit.text().strip(),
            "organization": self.organization_edit.text().strip(),
            "latitude": self.lat_spin.value(),
            "longitude": self.lon_spin.value(),
        }


class FiberEditDialog(QDialog):
    """Диалог редактирования волокна."""

    def __init__(self, parent=None, fiber_data=None, network: Optional[Network] = None):
        super().__init__(parent)
        self.fiber_data = fiber_data or {}
        self.network = network
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Редактирование волокна" if self.fiber_data else "Новое волокно")
        self.setGeometry(120, 120, 460, 360)

        layout = QFormLayout()
        self.fiber_id_edit = QLineEdit()
        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        self.type_combo = QComboBox()
        self.type_combo.addItems([ft.value for ft in FiberType])
        self.length_spin = QDoubleSpinBox()
        self.length_spin.setRange(0.0, 100000.0)
        self.length_spin.setDecimals(2)
        self.coil_length_spin = QDoubleSpinBox()
        self.coil_length_spin.setRange(0.01, 100000.0)
        self.coil_length_spin.setDecimals(2)
        self.coil_length_spin.setValue(25.0)
        self.splice_loss_spin = QDoubleSpinBox()
        self.splice_loss_spin.setRange(0.0, 10.0)
        self.splice_loss_spin.setDecimals(3)
        self.splice_loss_spin.setValue(0.02)
        self.connector_loss_spin = QDoubleSpinBox()
        self.connector_loss_spin.setRange(0.0, 10.0)
        self.connector_loss_spin.setDecimals(3)
        self.connector_loss_spin.setValue(0.3)
        self.line_reserve_spin = QDoubleSpinBox()
        self.line_reserve_spin.setRange(0.0, 100.0)
        self.line_reserve_spin.setDecimals(3)
        self.line_reserve_spin.setValue(0.0)

        if self.network:
            node_ids = list(self.network.nodes.keys())
            self.source_combo.addItems(node_ids)
            self.target_combo.addItems(node_ids)
            if len(node_ids) > 1:
                self.target_combo.setCurrentIndex(1)

        layout.addRow("ID волокна:", self.fiber_id_edit)
        layout.addRow("Узел 1:", self.source_combo)
        layout.addRow("Узел 2:", self.target_combo)
        layout.addRow("Тип волокна:", self.type_combo)
        layout.addRow("Длина (км):", self.length_spin)
        layout.addRow("Длина катушки (км):", self.coil_length_spin)
        layout.addRow("Потери на 1 сварке (дБ):", self.splice_loss_spin)
        layout.addRow("Потери на 1 коннекторе (дБ):", self.connector_loss_spin)
        layout.addRow("Резерв линии (дБ):", self.line_reserve_spin)

        if self.fiber_data:
            self.fiber_id_edit.setText(self.fiber_data.get("fiber_id", ""))
            self.fiber_id_edit.setReadOnly(True)
            self.source_combo.setCurrentText(self.fiber_data.get("source_node_id", ""))
            self.target_combo.setCurrentText(self.fiber_data.get("target_node_id", ""))
            self.type_combo.setCurrentText(self.fiber_data.get("fiber_type", FiberType.G652.value))
            self.length_spin.setValue(float(self.fiber_data.get("length_km", 0.0)))
            self.coil_length_spin.setValue(float(self.fiber_data.get("coil_length_km", 25.0)))
            self.splice_loss_spin.setValue(float(self.fiber_data.get("splice_losses_db", 0.02)))
            self.connector_loss_spin.setValue(float(self.fiber_data.get("connector_losses_db", 0.3)))
            self.line_reserve_spin.setValue(float(self.fiber_data.get("line_reserve_db", 0.0)))

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.setLayout(layout)

    def get_data(self) -> dict:
        return {
            "fiber_id": self.fiber_id_edit.text().strip(),
            "source_node_id": self.source_combo.currentText(),
            "target_node_id": self.target_combo.currentText(),
            "fiber_type": self.type_combo.currentText(),
            "length_km": self.length_spin.value(),
            "coil_length_km": self.coil_length_spin.value(),
            "splice_losses_db": self.splice_loss_spin.value(),
            "connector_losses_db": self.connector_loss_spin.value(),
            "line_reserve_db": self.line_reserve_spin.value(),
        }


class FiberConnectionDialog(QDialog):
    """Диалог создания волокна между двумя узлами."""

    def __init__(self, parent=None, network: Optional[Network] = None):
        super().__init__(parent)
        self.network = network
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Создание волокна")
        self.setGeometry(120, 120, 460, 330)
        layout = QFormLayout()

        self.source_combo = QComboBox()
        self.target_combo = QComboBox()
        self.fiber_type_combo = QComboBox()
        self.fiber_type_combo.addItems([ft.value for ft in FiberType])
        self.coil_length_spin = QDoubleSpinBox()
        self.coil_length_spin.setRange(0.01, 100000.0)
        self.coil_length_spin.setDecimals(2)    
        self.coil_length_spin.setValue(25.0)
        self.splice_loss_spin = QDoubleSpinBox()
        self.splice_loss_spin.setRange(0.0, 10.0)
        self.splice_loss_spin.setDecimals(3)
        self.splice_loss_spin.setValue(0.02)
        self.connector_loss_spin = QDoubleSpinBox()
        self.connector_loss_spin.setRange(0.0, 10.0)
        self.connector_loss_spin.setDecimals(3)
        self.connector_loss_spin.setValue(0.3)
        self.line_reserve_spin = QDoubleSpinBox()
        self.line_reserve_spin.setRange(0.0, 100.0)
        self.line_reserve_spin.setDecimals(3)
        self.line_reserve_spin.setValue(0.0)

        if self.network:
            node_ids = list(self.network.nodes.keys())
            self.source_combo.addItems(node_ids)
            self.target_combo.addItems(node_ids)
            if len(node_ids) > 1:
                self.target_combo.setCurrentIndex(1)

        layout.addRow("Узел 1 (источник):", self.source_combo)
        layout.addRow("Узел 2 (назначение):", self.target_combo)
        layout.addRow("Тип волокна:", self.fiber_type_combo)
        layout.addRow("Длина катушки (км):", self.coil_length_spin)
        layout.addRow("Потери на 1 сварке (дБ):", self.splice_loss_spin)
        layout.addRow("Потери на 1 коннекторе (дБ):", self.connector_loss_spin)
        layout.addRow("Резерв линии (дБ):", self.line_reserve_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)
        self.setLayout(layout)

    def get_data(self) -> dict:
        return {
            "source_node_id": self.source_combo.currentText(),
            "target_node_id": self.target_combo.currentText(),
            "fiber_type": self.fiber_type_combo.currentText(),
            "coil_length_km": self.coil_length_spin.value(),
            "splice_losses_db": self.splice_loss_spin.value(),
            "connector_losses_db": self.connector_loss_spin.value(),
            "line_reserve_db": self.line_reserve_spin.value(),
        }


class MapBridge(QObject):
    """Мост JS <-> Python."""

    mapClicked = pyqtSignal(float, float)
    markerClicked = pyqtSignal(str)

    @pyqtSlot(float, float)
    def click_on_map(self, lat: float, lon: float):
        self.mapClicked.emit(lat, lon)

    @pyqtSlot(str)
    def click_on_marker(self, node_id: str):
        self.markerClicked.emit(node_id)


class MapWidget(QWidget):
    """Основной виджет карты и управления сетью."""

    BITRATE_OPTIONS_GBPS: Tuple[float, ...] = (2.5, 10.0, 40.0, 100.0, 400.0)

    def __init__(self, network: Network, parent=None):
        super().__init__(parent)
        self.network = network
        self.topology_manager = TopologyManager(self.network)
        self.topology_analyzer = TopologyAnalyzer(self.network)
        self.traffic_manager = TrafficManager(self.network)
        self.simulation_manager = SimulationManager(self.network)
        self.dispersion_visualizer = DispersionVisualizer()

        self.power_budget_results: Dict[str, PowerBudgetResult] = {}
        self.dispersion_results: Dict[str, DispersionResult] = {}
        self.selected_channel_id: Optional[str] = None
        self.selected_channel_edges: Set[Tuple[str, str]] = set()
        self._syncing_channel_selection = False

        self.click_context = MapClickContext()
        self.bridge = MapBridge()
        self.bridge.mapClicked.connect(self._handle_map_click)
        self.bridge.markerClicked.connect(self._handle_marker_click)

        self.highlight_trunk_fibers: Set[str] = set()
        self.highlight_critical_fibers: Set[str] = set()
        self.highlight_heavy_fibers: Set[str] = set()
        self.highlight_critical_nodes: Set[str] = set()
        self.highlight_heavy_nodes: Set[str] = set()
        self.trunk_scores: Dict[str, float] = {}
        self._fiber_events_filled: bool = False
        self._fiber_events_signature: Tuple[Tuple[str, float, float, float, float, float], ...] | None = None

        self.assets_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "assets",
            "icons",
        )

        self.init_ui()

    def init_ui(self):
        main_layout = QHBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.setContentsMargins(8, 8, 8, 8)
        left_layout.setSpacing(6)
        title = QLabel("Панель управления")
        title.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 4px;")
        left_layout.addWidget(title)
        left_layout.addWidget(self._build_workspace_tabs(), stretch=1)
        left_panel.setLayout(left_layout)

        map_container = QWidget()
        map_layout = QVBoxLayout()
        map_layout.setContentsMargins(0, 0, 0, 0)
        map_layout.setSpacing(0)
        title_map = QLabel("Карта топологии сети")
        title_map.setStyleSheet("font-weight: bold; font-size: 11pt; padding: 4px;")
        map_layout.addWidget(title_map)
        self.web_view = QWebEngineView()
        self.web_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        map_layout.addWidget(self.web_view, stretch=1)
        map_container.setLayout(map_layout)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(map_container)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([560, 860])
        main_layout.addWidget(splitter, stretch=1)

        self.channel = QWebChannel(self.web_view.page())
        self.channel.registerObject("pyBridge", self.bridge)
        self.web_view.page().setWebChannel(self.channel)

        self.setLayout(main_layout)
        self.refresh_all()

    @classmethod
    def _configure_bitrate_combo(cls, combo: QComboBox, default_value: float = 100.0):
        combo.clear()
        for bitrate in cls.BITRATE_OPTIONS_GBPS:
            combo.addItem(str(int(bitrate)) if float(bitrate).is_integer() else str(bitrate), float(bitrate))
        cls._set_bitrate_widget_value(combo, default_value)

    @staticmethod
    def _set_bitrate_widget_value(widget, value: float):
        bitrate = float(value)
        if isinstance(widget, QDoubleSpinBox):
            widget.setValue(bitrate)
            return
        if isinstance(widget, QComboBox):
            for idx in range(widget.count()):
                item_value = widget.itemData(idx)
                if item_value is not None and math.isclose(float(item_value), bitrate, rel_tol=0.0, abs_tol=1e-6):
                    widget.setCurrentIndex(idx)
                    return
            widget.setCurrentText(str(int(bitrate)) if bitrate.is_integer() else str(bitrate))

    @staticmethod
    def _get_bitrate_widget_value(widget) -> float:
        if isinstance(widget, QDoubleSpinBox):
            return float(widget.value())
        if isinstance(widget, QComboBox):
            data = widget.currentData()
            if data is not None:
                return float(data)
            text = widget.currentText().strip().replace(",", ".")
            return float(text) if text else 0.0
        return 0.0

    # ---------- UI builders ----------

    def _build_workspace_tabs(self) -> QWidget:
        self.workspace_tabs = QTabWidget()
        self.workspace_tabs.addTab(self._build_management_tab(), "Топология")
        self.workspace_tabs.addTab(self._build_automation_tab(), "Трассировка")
        self.workspace_tabs.addTab(self._build_dwdm_tab(), "Каналы")
        self.workspace_tabs.addTab(self._build_graphs_tab(), "Графики")
        self.workspace_tabs.addTab(self._build_excel_line_calc_tab(), "Таблица")
        self.workspace_tabs.addTab(self._build_project_files_tab(), "Файлы")
        return self.workspace_tabs

    def _build_management_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()
        control_tabs = QTabWidget()
        control_tabs.addTab(self._build_nodes_tab(), "Узлы")
        control_tabs.addTab(self._build_fibers_tab(), "Волокна")
        layout.addWidget(control_tabs, stretch=1)

        stats_group = QGroupBox("Статистика")
        stats_layout = QVBoxLayout()
        self.stats_label = QLabel("Узлов: 0\nВолокон: 0\nСвязность: 0")
        self.stats_label.setStyleSheet("font-size: 9pt; color: #333;")
        stats_layout.addWidget(self.stats_label)
        stats_group.setLayout(stats_layout)
        layout.addWidget(stats_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _build_automation_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        trace_group = QGroupBox("Трассировка линий")
        trace_layout = QFormLayout()
        self.trace_mode_combo = QComboBox()
        self.trace_mode_combo.addItem("По дорогам (авто, OSRM)", "roads")
        self.trace_mode_combo.addItem("Прямая линия", "straight")
        self.trace_selected_btn = QPushButton("Трассировать выбранную линию")
        self.trace_selected_btn.clicked.connect(self.trace_selected_fiber)
        self.trace_all_btn = QPushButton("Трассировать все линии")
        self.trace_all_btn.clicked.connect(self.trace_all_fibers)
        self.trace_reset_btn = QPushButton("Сбросить трассировку (прямые)")
        self.trace_reset_btn.clicked.connect(self.reset_all_traces)
        trace_layout.addRow("Режим:", self.trace_mode_combo)
        trace_layout.addRow(self.trace_selected_btn)
        trace_layout.addRow(self.trace_all_btn)
        trace_layout.addRow(self.trace_reset_btn)
        trace_group.setLayout(trace_layout)
        layout.addWidget(trace_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _build_project_files_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        project_group = QGroupBox("Загрузка и сохранение")
        project_layout = QVBoxLayout()
        self.load_project_btn = QPushButton("Загрузить проект JSON")
        self.load_project_btn.clicked.connect(self.load_project_from_file)
        self.save_project_btn = QPushButton("Сохранить проект JSON")
        self.save_project_btn.clicked.connect(self.save_project_to_file)
        self.clear_project_btn = QPushButton("Очистить проект")
        self.clear_project_btn.clicked.connect(self.clear_project_data)
        project_layout.addWidget(self.load_project_btn)
        project_layout.addWidget(self.save_project_btn)
        project_layout.addWidget(self.clear_project_btn)
        project_group.setLayout(project_layout)
        layout.addWidget(project_group)

        export_group = QGroupBox("Экспорт")
        export_layout = QVBoxLayout()
        self.export_tables_btn = QPushButton("Экспорт таблиц в Excel")
        self.export_tables_btn.clicked.connect(self.open_export_tables_dialog)
        export_layout.addWidget(self.export_tables_btn)
        export_group.setLayout(export_layout)
        layout.addWidget(export_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    def _build_nodes_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        nodes_group = QGroupBox("Добавление узла")
        nodes_layout = QFormLayout()
        self.node_id_edit = QLineEdit()
        self.node_id_edit.setPlaceholderText("узел_1")
        self.node_name_edit = QLineEdit()
        self.node_name_edit.setPlaceholderText("Название узла")
        self.node_type_combo = QComboBox()
        self.node_type_combo.addItems([nt.value for nt in NodeType])
        self.node_territory_edit = QLineEdit()
        self.node_territory_edit.setPlaceholderText("Регион/зона")
        self.node_org_edit = QLineEdit()
        self.node_org_edit.setPlaceholderText("Подразделение/организация")
        self.place_node_btn = QPushButton("Разместить узел на карте")
        self.place_node_btn.clicked.connect(self.on_place_node)
        nodes_layout.addRow("ID узла:", self.node_id_edit)
        nodes_layout.addRow("Название:", self.node_name_edit)
        nodes_layout.addRow("Тип узла:", self.node_type_combo)
        nodes_layout.addRow("Территория:", self.node_territory_edit)
        nodes_layout.addRow("Организация:", self.node_org_edit)
        nodes_layout.addRow(self.place_node_btn)
        nodes_group.setLayout(nodes_layout)
        layout.addWidget(nodes_group)

        btn_layout = QHBoxLayout()
        self.edit_node_btn = QPushButton("Редактировать")
        self.edit_node_btn.clicked.connect(self.edit_selected_node)
        self.delete_node_btn = QPushButton("Удалить")
        self.delete_node_btn.clicked.connect(self.delete_selected_node)
        btn_layout.addWidget(self.edit_node_btn)
        btn_layout.addWidget(self.delete_node_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.nodes_table = QTableWidget()
        self.nodes_table.setColumnCount(7)
        self.nodes_table.setHorizontalHeaderLabels(
            ["ID", "Название", "Тип", "Территория", "Орг.", "Широта", "Долгота"]
        )
        self.nodes_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.nodes_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.nodes_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.nodes_table.itemSelectionChanged.connect(self.on_node_selection_changed)
        layout.addWidget(self.nodes_table)
        widget.setLayout(layout)
        return widget

    def _build_fibers_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        fibers_group = QGroupBox("Добавление волокна")
        fibers_layout = QFormLayout()
        self.fiber_id_edit = QLineEdit()
        self.fiber_id_edit.setPlaceholderText("волокно_1")
        self.fiber_type_combo = QComboBox()
        self.fiber_type_combo.addItems([ft.value for ft in FiberType])
        self.fiber_source_combo = QComboBox()
        self.fiber_target_combo = QComboBox()
        self.fiber_coil_length_spin = QDoubleSpinBox()
        self.fiber_coil_length_spin.setRange(0.01, 100000.0)
        self.fiber_coil_length_spin.setDecimals(2)
        self.fiber_coil_length_spin.setValue(25.0)
        self.fiber_splice_loss_spin = QDoubleSpinBox()
        self.fiber_splice_loss_spin.setRange(0.0, 10.0)
        self.fiber_splice_loss_spin.setDecimals(3)
        self.fiber_splice_loss_spin.setValue(0.02)
        self.fiber_connector_loss_spin = QDoubleSpinBox()
        self.fiber_connector_loss_spin.setRange(0.0, 10.0)
        self.fiber_connector_loss_spin.setDecimals(3)
        self.fiber_connector_loss_spin.setValue(0.3)
        self.fiber_line_reserve_spin = QDoubleSpinBox()
        self.fiber_line_reserve_spin.setRange(0.0, 100.0)
        self.fiber_line_reserve_spin.setDecimals(3)
        self.fiber_line_reserve_spin.setValue(0.0)
        self.connect_nodes_btn = QPushButton("Соединить узлы волокном")
        self.connect_nodes_btn.clicked.connect(self.on_connect_nodes)
        fibers_layout.addRow("ID волокна:", self.fiber_id_edit)
        fibers_layout.addRow("Тип волокна:", self.fiber_type_combo)
        fibers_layout.addRow("Узел 1:", self.fiber_source_combo)
        fibers_layout.addRow("Узел 2:", self.fiber_target_combo)
        fibers_layout.addRow("Длина катушки (км):", self.fiber_coil_length_spin)
        fibers_layout.addRow("Потери на 1 сварке (дБ):", self.fiber_splice_loss_spin)
        fibers_layout.addRow("Потери на 1 коннекторе (дБ):", self.fiber_connector_loss_spin)
        fibers_layout.addRow("Резерв линии (дБ):", self.fiber_line_reserve_spin)
        fibers_layout.addRow(self.connect_nodes_btn)
        fibers_group.setLayout(fibers_layout)
        layout.addWidget(fibers_group)

        btn_layout = QHBoxLayout()
        self.edit_fiber_btn = QPushButton("Редактировать")
        self.edit_fiber_btn.clicked.connect(self.edit_selected_fiber)
        self.delete_fiber_btn = QPushButton("Удалить")
        self.delete_fiber_btn.clicked.connect(self.delete_selected_fiber)
        btn_layout.addWidget(self.edit_fiber_btn)
        btn_layout.addWidget(self.delete_fiber_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        self.fibers_table = QTableWidget()
        self.fibers_table.setColumnCount(8)
        self.fibers_table.setHorizontalHeaderLabels(
            [
                "ID",
                "От",
                "До",
                "L, км",
                "Тип",
                "α, дБ/км",
                "Lстр, км",
                "Трасса",
            ]
        )
        self.fibers_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.fibers_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.fibers_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.fibers_table.itemSelectionChanged.connect(self.on_fiber_selection_changed)
        layout.addWidget(self.fibers_table)

        events_group = QGroupBox("Сварки и коннекторы")
        events_layout = QVBoxLayout()
        self.fiber_events_table = QTableWidget()
        self.fiber_events_table.setColumnCount(5)
        self.fiber_events_table.setHorizontalHeaderLabels(
            ["Волокно", "Тип", "Позиция, км", "Потери, дБ", "Комментарий"]
        )
        self.fiber_events_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.fiber_events_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.fiber_events_table.setSelectionBehavior(QTableWidget.SelectRows)
        events_layout.addWidget(self.fiber_events_table)
        events_group.setLayout(events_layout)
        layout.addWidget(events_group, stretch=1)
        self._fiber_events_filled = False
        self._fiber_events_signature = None
        widget.setLayout(layout)
        return widget

    def _build_flows_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        gen_group = QGroupBox("3.2.1 Генерация информационных направлений")
        gen_form = QFormLayout()
        self.direction_mode_combo = QComboBox()
        self.direction_mode_combo.addItem("Полносвязная структура", "full_mesh")
        self.direction_mode_combo.addItem("По территориальной принадлежности", "by_territory")
        self.direction_mode_combo.addItem("По организационной принадлежности", "by_organization")
        self.capacity_unit_combo = QComboBox()
        self.capacity_unit_combo.addItems(["Gbps", "ETH-Mbps", "STM-1", "E1", "WDM-CH"])
        self.capacity_value_spin = QDoubleSpinBox()
        self.capacity_value_spin.setRange(0.001, 100000.0)
        self.capacity_value_spin.setDecimals(3)
        self.capacity_value_spin.setValue(10.0)
        self.bidirectional_check = QCheckBox("Двусторонние ИН")
        self.bidirectional_check.setChecked(True)
        self.generate_dirs_btn = QPushButton("Сгенерировать ИН")
        self.generate_dirs_btn.clicked.connect(self.generate_directions)
        gen_form.addRow("Режим:", self.direction_mode_combo)
        gen_form.addRow("Единица:", self.capacity_unit_combo)
        gen_form.addRow("Значение:", self.capacity_value_spin)
        gen_form.addRow(self.bidirectional_check)
        gen_form.addRow(self.generate_dirs_btn)
        gen_group.setLayout(gen_form)
        layout.addWidget(gen_group)

        flow_group = QGroupBox("3.2.2 Потоковая структура")
        flow_form = QFormLayout()
        self.routes_per_direction_spin = QSpinBox()
        self.routes_per_direction_spin.setRange(1, 5)
        self.routes_per_direction_spin.setValue(2)
        self.route_criterion_combo = QComboBox()
        self.route_criterion_combo.addItem("Минимальная длина маршрута", "length")
        self.route_criterion_combo.addItem("Минимум максимальной нагрузки", "min_max_load")
        self.route_criterion_combo.addItem("Минимум переприемов (хопов)", "min_hops")
        self.load_distribution_combo = QComboBox()
        self.load_distribution_combo.addItem("Обратно пропорц. длине", "inverse_length")
        self.load_distribution_combo.addItem("Обратно пропорц. числу хопов", "inverse_hops")
        self.load_distribution_combo.addItem("100% на каждый маршрут", "duplicate_100")
        self.compute_flows_btn = QPushButton("Найти потоковую структуру")
        self.compute_flows_btn.clicked.connect(self.compute_flow_structure)
        self.find_vulnerable_btn = QPushButton("Найти уязвимые элементы")
        self.find_vulnerable_btn.clicked.connect(self.find_vulnerable_elements)
        flow_form.addRow("Маршрутов на ИН:", self.routes_per_direction_spin)
        flow_form.addRow("Критерий маршрута:", self.route_criterion_combo)
        flow_form.addRow("Распределение нагрузки:", self.load_distribution_combo)
        flow_form.addRow(self.compute_flows_btn)
        flow_form.addRow(self.find_vulnerable_btn)
        flow_group.setLayout(flow_form)
        layout.addWidget(flow_group)

        dirs_group = QGroupBox("Информационные направления")
        dirs_layout = QVBoxLayout()
        self.directions_table = QTableWidget()
        self.directions_table.setColumnCount(6)
        self.directions_table.setHorizontalHeaderLabels(
            ["ID", "От", "До", "Емкость (Гбит/с)", "Маршруты", "Статус"]
        )
        self.directions_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.directions_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        dirs_layout.addWidget(self.directions_table)
        dirs_group.setLayout(dirs_layout)
        layout.addWidget(dirs_group, stretch=1)

        fiber_loads_group = QGroupBox("Загрузка линий и уязвимость")
        fiber_loads_layout = QVBoxLayout()
        self.flow_loads_table = QTableWidget()
        self.flow_loads_table.setColumnCount(5)
        self.flow_loads_table.setHorizontalHeaderLabels(
            ["Линия", "Нагрузка (Гбит/с)", "Число ИН", "Отн. нагрузка", "Критичность"]
        )
        self.flow_loads_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.flow_loads_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        fiber_loads_layout.addWidget(self.flow_loads_table)
        fiber_loads_group.setLayout(fiber_loads_layout)
        layout.addWidget(fiber_loads_group, stretch=1)

        node_loads_group = QGroupBox("Уязвимые узлы")
        node_loads_layout = QVBoxLayout()
        self.node_loads_table = QTableWidget()
        self.node_loads_table.setColumnCount(4)
        self.node_loads_table.setHorizontalHeaderLabels(
            ["Узел", "Транзит ИН", "Отн. нагрузка", "Критичность"]
        )
        self.node_loads_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.node_loads_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        node_loads_layout.addWidget(self.node_loads_table)
        node_loads_group.setLayout(node_loads_layout)
        layout.addWidget(node_loads_group, stretch=1)

        widget.setLayout(layout)
        return widget

    def _build_dwdm_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        channels_group = QGroupBox("Параметры канала")
        channels_form = QFormLayout()
        self.channel_src_combo = QComboBox()
        self.channel_dst_combo = QComboBox()
        self.channel_wavelength_spin = QDoubleSpinBox()
        self.channel_wavelength_spin.setRange(1200.0, 1700.0)
        self.channel_wavelength_spin.setDecimals(3)
        self.channel_wavelength_spin.setSingleStep(0.001)
        self.channel_wavelength_spin.setValue(1550.120)
        self.channel_bitrate_spin = QComboBox()
        self._configure_bitrate_combo(self.channel_bitrate_spin, 100.0)
        self.channel_tx_power_spin = QDoubleSpinBox()
        self.channel_tx_power_spin.setRange(-20.0, 20.0)
        self.channel_tx_power_spin.setDecimals(1)
        self.channel_tx_power_spin.setValue(0.0)
        self.channel_rx_sens_spin = QDoubleSpinBox()
        self.channel_rx_sens_spin.setRange(-50.0, 0.0)
        self.channel_rx_sens_spin.setDecimals(1)
        self.channel_rx_sens_spin.setValue(-20.0)
        self.channel_energy_budget_spin = QDoubleSpinBox()
        self.channel_energy_budget_spin.setRange(0.0, 200.0)
        self.channel_energy_budget_spin.setDecimals(1)
        self.channel_energy_budget_spin.setValue(40.0)
        self.channel_spacing_combo = QComboBox()
        self.channel_spacing_combo.addItem("100 GHz", 0.1)
        self.channel_spacing_combo.addItem("50 GHz", 0.05)

        channels_buttons = QHBoxLayout()
        self.create_channel_btn = QPushButton("Создать канал")
        self.create_channel_btn.clicked.connect(self.create_channel_between_nodes)
        self.delete_channel_btn = QPushButton("Удалить выбранный")
        self.delete_channel_btn.clicked.connect(self.delete_selected_channel)
        self.clear_channels_btn = QPushButton("Очистить каналы")
        self.clear_channels_btn.clicked.connect(self.clear_all_channels)
        self.assign_wavelengths_btn = QPushButton("Назначить длины волн ITU")
        self.assign_wavelengths_btn.clicked.connect(self.assign_wavelengths_to_channels)
        channels_buttons.addWidget(self.create_channel_btn)
        channels_buttons.addWidget(self.delete_channel_btn)
        channels_buttons.addWidget(self.clear_channels_btn)

        channels_form.addRow("Узел-источник:", self.channel_src_combo)
        channels_form.addRow("Узел-назначение:", self.channel_dst_combo)
        channels_form.addRow("Длина волны, нм:", self.channel_wavelength_spin)
        channels_form.addRow("Скорость, Гбит/с:", self.channel_bitrate_spin)
        channels_form.addRow("Энерг. запас аппаратуры, дБ:", self.channel_energy_budget_spin)
        channels_form.addRow(channels_buttons)
        channels_group.setLayout(channels_form)
        layout.addWidget(channels_group)

        calc_group = QGroupBox("Физические расчеты")
        calc_form = QFormLayout()
        calc_buttons = QHBoxLayout()
        self.place_amplifiers_btn = QPushButton("Авторасстановка EDFA")
        self.place_amplifiers_btn.clicked.connect(self.auto_place_amplifiers)
        self.run_budget_btn = QPushButton("Рассчитать бюджет мощности")
        self.run_budget_btn.clicked.connect(self.run_power_budget)
        calc_buttons.addWidget(self.place_amplifiers_btn)
        calc_buttons.addWidget(self.run_budget_btn)
        calc_form.addRow(calc_buttons)
        disp_buttons = QHBoxLayout()
        self.run_dispersion_btn = QPushButton("Рассчитать дисперсию")
        self.run_dispersion_btn.clicked.connect(self.run_dispersion_calc)
        disp_buttons.addWidget(self.run_dispersion_btn)
        calc_form.addRow(disp_buttons)
        calc_group.setLayout(calc_form)
        layout.addWidget(calc_group)

        self.dwdm_summary_label = QLabel("Каналов: 0 | EDFA: 0 | Расчет: не запускался")
        layout.addWidget(self.dwdm_summary_label)

        self.channels_table = QTableWidget()
        self.channels_table.setColumnCount(9)
        self.channels_table.setHorizontalHeaderLabels(
            [
                "ID",
                "Источник",
                "Назначение",
                "Путь",
                "Длина волны, нм",
                "Частота, ТГц",
                "Потери, дБ",
                "Запас, дБ",
                "Статус",
            ]
        )
        self.channels_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.channels_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.channels_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.channels_table.itemSelectionChanged.connect(self.on_channel_selection_changed)
        layout.addWidget(self.channels_table, stretch=1)

        widget.setLayout(layout)
        return widget

    def _build_graphs_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        profile_group = QGroupBox("Профиль мощности выбранного канала")
        profile_layout = QVBoxLayout()
        self.profile_table = QTableWidget()
        self.profile_table.setColumnCount(2)
        self.profile_table.setHorizontalHeaderLabels(["Расстояние, км", "Мощность, дБм"])
        self.profile_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.profile_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        profile_layout.addWidget(self.profile_table)
        if FigureCanvas is not None and Figure is not None:
            self.profile_figure = Figure(figsize=(4, 2))
            self.profile_canvas = FigureCanvas(self.profile_figure)
            profile_layout.addWidget(self.profile_canvas)
        else:
            self.profile_figure = None
            self.profile_canvas = None
            profile_layout.addWidget(QLabel("Matplotlib недоступен."))
        profile_group.setLayout(profile_layout)
        layout.addWidget(profile_group, stretch=2)

        dispersion_group = QGroupBox("Профиль дисперсии выбранного канала")
        dispersion_layout = QVBoxLayout()
        self.dispersion_profile_label = QLabel("Выберите канал для отображения профиля дисперсии.")
        dispersion_layout.addWidget(self.dispersion_profile_label)
        disp_controls = QHBoxLayout()
        self.disp_modulation_combo = QComboBox()
        self.disp_modulation_combo.addItem("NRZ", "nrz")
        self.disp_modulation_combo.addItem("RZ", "rz")
        self.disp_laser_combo = QComboBox()
        self.disp_laser_combo.addItem("DFB (узкий)", "dfb")
        self.disp_laser_combo.addItem("EML (средний)", "eml")
        self.disp_laser_combo.addItem("FP (широкий)", "fp")
        self.disp_laser_width_override = QDoubleSpinBox()
        self.disp_laser_width_override.setRange(0.0, 10.0)
        self.disp_laser_width_override.setDecimals(6)
        self.disp_laser_width_override.setSingleStep(0.0001)
        self.disp_laser_width_override.setValue(0.0)
        self.disp_laser_width_override.setToolTip("Δλ, нм. 0 = взять типовое по выбранному типу лазера.")
        disp_controls.addWidget(QLabel("Модуляция:"))
        disp_controls.addWidget(self.disp_modulation_combo)
        disp_controls.addSpacing(8)
        disp_controls.addWidget(QLabel("Лазер:"))
        disp_controls.addWidget(self.disp_laser_combo)
        disp_controls.addSpacing(8)
        disp_controls.addWidget(QLabel("Δλ, нм (0=авто):"))
        disp_controls.addWidget(self.disp_laser_width_override)
        disp_controls.addStretch()

        # Кнопка для открытия графика в отдельном окне
        self.open_eye_diagram_btn = QPushButton("📊 Открыть глазковую диаграмму в отдельном окне")
        self.open_eye_diagram_btn.clicked.connect(self._open_eye_diagram_window)
        self.open_eye_diagram_btn.setStyleSheet("QPushButton { font-weight: bold; padding: 8px; }")
        disp_controls.addWidget(self.open_eye_diagram_btn)

        dispersion_layout.addLayout(disp_controls)
        if FigureCanvas is not None and Figure is not None:
            self.dispersion_figure = Figure(figsize=(4, 2))
            self.dispersion_canvas = FigureCanvas(self.dispersion_figure)
            dispersion_layout.addWidget(self.dispersion_canvas)
            self.dispersion_pulse_figure = Figure(figsize=(4, 1.8))
            self.dispersion_pulse_canvas = FigureCanvas(self.dispersion_pulse_figure)
            dispersion_layout.addWidget(self.dispersion_pulse_canvas)
        else:
            self.dispersion_figure = None
            self.dispersion_canvas = None
            self.dispersion_pulse_figure = None
            self.dispersion_pulse_canvas = None
            dispersion_layout.addWidget(QLabel("Matplotlib недоступен."))
        dispersion_group.setLayout(dispersion_layout)
        layout.addWidget(dispersion_group, stretch=2)

        widget.setLayout(layout)
        return widget

    def _build_excel_line_calc_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        self.excel_line_calc_table = QTableWidget()
        self.excel_line_calc_table.setColumnCount(37)
        self.excel_line_calc_table.setHorizontalHeaderLabels(
            [
                "№ п/п",
                "ID",
                "Источник",
                "Назначение",
                "Путь",
                "Энерг. запас, дБ",
                "Длина линии, км",
                "Lстр, км",
                "Резерв, дБ",
                "α, дБ/км",
                "Разъем, дБ",
                "Сварка, дБ",
                "Кол-во участков",
                "Кол-во соединений",
                "Σзатух в линии, дБ",
                "Σзатух в соед., дБ",
                "Σзатух в разъем., дБ",
                "Σзатух усил. уч., дБ",
                "Сравнение с B",
                "Длина усил. участка, км",
                "Кол-во усил. участков",
                "Стр. длин на усил. участке",
                "Среднее усил. уч., км",
                "Тип ОВ",
                "Длина волны λ, нм",
                "Скорость, Гбит/с",
                "D, пс/(нм·км)",
                "ΣХД, пс/нм",
                "Лим. ХД, пс/нм",
                "ХД",
                "ПМД, пс",
                "Лим. ПМД, пс",
                "ПМД",
                "BER",
                "Q-фактор",
                "OSNR_eff, дБ",
                "Штраф ХД, дБ",
                "Штраф ПМД, дБ",
            ]
        )
        self.excel_line_calc_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.excel_line_calc_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.excel_line_calc_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.excel_line_calc_table.itemSelectionChanged.connect(self.on_excel_channel_selection_changed)
        layout.addWidget(self.excel_line_calc_table, stretch=1)

        widget.setLayout(layout)
        return widget

    def _build_two_point_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout()

        points_group = QGroupBox("Терминальные точки")
        points_form = QFormLayout()
        self.quick_node_a_id_edit = QLineEdit("NODE_A")
        self.quick_node_a_name_edit = QLineEdit("Node A")
        self.quick_node_b_id_edit = QLineEdit("NODE_B")
        self.quick_node_b_name_edit = QLineEdit("Node B")
        self.quick_place_node_a_btn = QPushButton("Поставить точку A")
        self.quick_place_node_b_btn = QPushButton("Поставить точку B")
        self.quick_place_node_a_btn.clicked.connect(self.place_quick_node_a)
        self.quick_place_node_b_btn.clicked.connect(self.place_quick_node_b)
        point_btns = QHBoxLayout()
        point_btns.addWidget(self.quick_place_node_a_btn)
        point_btns.addWidget(self.quick_place_node_b_btn)
        points_form.addRow("ID точки A:", self.quick_node_a_id_edit)
        points_form.addRow("Название A:", self.quick_node_a_name_edit)
        points_form.addRow("ID точки B:", self.quick_node_b_id_edit)
        points_form.addRow("Название B:", self.quick_node_b_name_edit)
        points_form.addRow(point_btns)
        points_group.setLayout(points_form)
        layout.addWidget(points_group)

        line_group = QGroupBox("Параметры линии")
        line_form = QFormLayout()
        self.quick_fiber_type_combo = QComboBox()
        self.quick_fiber_type_combo.addItems([ft.value for ft in FiberType])
        self.quick_fiber_type_combo.setCurrentText(FiberType.G652.value)
        self.quick_alpha_spin = QDoubleSpinBox()
        self.quick_alpha_spin.setRange(0.0, 2.0)
        self.quick_alpha_spin.setDecimals(3)
        self.quick_alpha_spin.setValue(0.22)
        self.quick_coil_length_spin = QDoubleSpinBox()
        self.quick_coil_length_spin.setRange(0.001, 1000.0)
        self.quick_coil_length_spin.setDecimals(2)
        self.quick_coil_length_spin.setValue(25.0)
        self.quick_splice_loss_spin = QDoubleSpinBox()
        self.quick_splice_loss_spin.setRange(0.0, 10.0)
        self.quick_splice_loss_spin.setDecimals(3)
        self.quick_splice_loss_spin.setValue(0.02)
        self.quick_connector_loss_spin = QDoubleSpinBox()
        self.quick_connector_loss_spin.setRange(0.0, 10.0)
        self.quick_connector_loss_spin.setDecimals(3)
        self.quick_connector_loss_spin.setValue(0.35)
        self.quick_line_reserve_spin = QDoubleSpinBox()
        self.quick_line_reserve_spin.setRange(0.0, 100.0)
        self.quick_line_reserve_spin.setDecimals(2)
        self.quick_line_reserve_spin.setValue(7.0)
        self.quick_trace_mode_combo = QComboBox()
        self.quick_trace_mode_combo.addItem("По дорогам (OSRM)", "roads")
        self.quick_trace_mode_combo.addItem("Прямая линия", "straight")
        self.quick_trace_mode_combo.setCurrentIndex(0)
        self.quick_wavelength_spin = QDoubleSpinBox()
        self.quick_wavelength_spin.setRange(1200.0, 1700.0)
        self.quick_wavelength_spin.setDecimals(3)
        self.quick_wavelength_spin.setSingleStep(0.001)
        self.quick_wavelength_spin.setValue(1550.120)
        self.quick_bitrate_spin = QComboBox()
        self._configure_bitrate_combo(self.quick_bitrate_spin, 100.0)
        self.quick_energy_budget_spin = QDoubleSpinBox()
        self.quick_energy_budget_spin.setRange(0.0, 200.0)
        self.quick_energy_budget_spin.setDecimals(1)
        self.quick_energy_budget_spin.setValue(40.0)

        line_form.addRow("Тип ОВ:", self.quick_fiber_type_combo)
        line_form.addRow("α, дБ/км:", self.quick_alpha_spin)
        line_form.addRow("Lстр, км:", self.quick_coil_length_spin)
        line_form.addRow("Потери сварки, дБ:", self.quick_splice_loss_spin)
        line_form.addRow("Потери разъема, дБ:", self.quick_connector_loss_spin)
        line_form.addRow("Резерв линии, дБ:", self.quick_line_reserve_spin)
        line_form.addRow("Трассировка:", self.quick_trace_mode_combo)
        line_form.addRow("Длина волны, нм:", self.quick_wavelength_spin)
        line_form.addRow("Скорость, Гбит/с:", self.quick_bitrate_spin)
        line_form.addRow("Энерг. запас, дБ:", self.quick_energy_budget_spin)
        line_group.setLayout(line_form)
        layout.addWidget(line_group)

        actions_group = QGroupBox("Действия")
        actions_layout = QVBoxLayout()
        actions_btns = QHBoxLayout()
        self.quick_build_fiber_btn = QPushButton("Соединить точки")
        self.quick_build_fiber_btn.clicked.connect(self.quick_build_fiber_between_points)
        self.quick_trace_fiber_btn = QPushButton("Трассировать линию")
        self.quick_trace_fiber_btn.clicked.connect(self.quick_trace_pair_fiber)
        self.quick_run_pipeline_btn = QPushButton("EDFA + Проверка")
        self.quick_run_pipeline_btn.clicked.connect(self.run_quick_two_point_pipeline)
        self.quick_clear_pipeline_btn = QPushButton("Очистить сценарий")
        self.quick_clear_pipeline_btn.clicked.connect(self.clear_quick_two_point_artifacts)
        actions_btns.addWidget(self.quick_build_fiber_btn)
        actions_btns.addWidget(self.quick_trace_fiber_btn)
        actions_layout.addLayout(actions_btns)
        actions_layout.addWidget(self.quick_run_pipeline_btn)
        actions_layout.addWidget(self.quick_clear_pipeline_btn)
        self.quick_status_label = QLabel(
            "Готово. Поставьте 2 точки, соедините их, затем выполните трассировку и расчет."
        )
        actions_layout.addWidget(self.quick_status_label)
        actions_group.setLayout(actions_layout)
        layout.addWidget(actions_group)

        layout.addStretch()
        widget.setLayout(layout)
        return widget

    # ---------- Common helpers ----------

    def activate_place_mode(self, device_type: str, handler: Callable[[float, float, str], None]):
        self.click_context = MapClickContext(device_type=device_type, handler=handler)
        self.web_view.page().runJavaScript("window.placeMode = true;")

    def _handle_map_click(self, lat: float, lon: float):
        if self.click_context.handler:
            handler = self.click_context.handler
            device_type = self.click_context.device_type
            self.web_view.page().runJavaScript("window.placeMode = false;")
            self.click_context = MapClickContext()
            handler(lat, lon, device_type)

    def _handle_marker_click(self, node_id: str):
        if not hasattr(self, "nodes_table"):
            return
        for row in range(self.nodes_table.rowCount()):
            item = self.nodes_table.item(row, 0)
            if item and item.text() == node_id:
                self.nodes_table.selectRow(row)
                break
        self.edit_selected_node()

    def refresh_all(self):
        if hasattr(self, "fiber_source_combo") and hasattr(self, "fiber_target_combo"):
            self._refresh_fiber_connection_selectors()
        if hasattr(self, "nodes_table") and hasattr(self, "fibers_table"):
            self.refresh_tables()
        if (
            hasattr(self, "directions_table")
            and hasattr(self, "flow_loads_table")
            and hasattr(self, "node_loads_table")
        ):
            self.refresh_traffic_tables()
        if hasattr(self, "channels_table"):
            self.refresh_dwdm_tables()
        if hasattr(self, "stats_label"):
            self.update_stats()
        self.update_map()

    def _clear_flow_state(self):
        self.traffic_manager.directions.clear()
        self.traffic_manager.fiber_loads.clear()
        self.traffic_manager.node_loads.clear()
        self.highlight_critical_fibers.clear()
        self.highlight_heavy_fibers.clear()
        self.highlight_critical_nodes.clear()
        self.highlight_heavy_nodes.clear()

    def _clear_topology_marks(self):
        self.highlight_trunk_fibers.clear()
        self.trunk_scores.clear()
        for fiber in self.network.fibers.values():
            fiber.is_trunk = False

    def _selected_fiber_id(self) -> Optional[str]:
        if not hasattr(self, "fibers_table"):
            return None
        selected = self.fibers_table.selectedItems()
        if not selected:
            return None
        row = self.fibers_table.row(selected[0])
        item = self.fibers_table.item(row, 0)
        return item.text() if item else None

    def _edge_key(self, source_id: str, target_id: str) -> Tuple[str, str]:
        return (source_id, target_id) if source_id < target_id else (target_id, source_id)

    def _build_network_graph(self) -> nx.Graph:
        graph = nx.Graph()
        graph.add_nodes_from(self.network.nodes.keys())
        for fiber in self.network.fibers.values():
            src = fiber.source_node_id
            dst = fiber.target_node_id
            weight = float(fiber.length_km)
            if graph.has_edge(src, dst):
                if weight < float(graph[src][dst].get("weight", weight)):
                    graph[src][dst]["weight"] = weight
                continue
            graph.add_edge(src, dst, weight=weight)
        return graph

    def _path_has_all_fibers(self, path: List[str]) -> bool:
        if len(path) < 2:
            return False
        for source_id, target_id in zip(path[:-1], path[1:]):
            if not self.network.get_fibers_between(source_id, target_id):
                return False
        return True

    def _find_shortest_path(self, source_id: str, target_id: str) -> List[str]:
        graph = self._build_network_graph()
        try:
            return nx.shortest_path(graph, source_id, target_id, weight="weight")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def _edfa_count(self) -> int:
        return sum(
            1
            for eq in self.network.equipment.values()
            if eq.equipment_type == EquipmentType.EDFA
        )

    def _refresh_channel_selectors(self):
        node_ids = sorted(self.network.nodes.keys())
        current_src = self.channel_src_combo.currentText()
        current_dst = self.channel_dst_combo.currentText()
        self.channel_src_combo.blockSignals(True)
        self.channel_dst_combo.blockSignals(True)
        self.channel_src_combo.clear()
        self.channel_dst_combo.clear()
        self.channel_src_combo.addItems(node_ids)
        self.channel_dst_combo.addItems(node_ids)
        if current_src in node_ids:
            self.channel_src_combo.setCurrentText(current_src)
        if current_dst in node_ids:
            self.channel_dst_combo.setCurrentText(current_dst)
        if self.channel_dst_combo.count() > 1 and self.channel_src_combo.currentText() == self.channel_dst_combo.currentText():
            self.channel_dst_combo.setCurrentIndex(1)
        self.channel_src_combo.blockSignals(False)
        self.channel_dst_combo.blockSignals(False)

    def _refresh_fiber_connection_selectors(
        self,
        preferred_src: Optional[str] = None,
        preferred_dst: Optional[str] = None,
    ):
        node_ids = sorted(self.network.nodes.keys())
        current_src = preferred_src or self.fiber_source_combo.currentText()
        current_dst = preferred_dst or self.fiber_target_combo.currentText()

        self.fiber_source_combo.blockSignals(True)
        self.fiber_target_combo.blockSignals(True)
        self.fiber_source_combo.clear()
        self.fiber_target_combo.clear()
        self.fiber_source_combo.addItems(node_ids)
        self.fiber_target_combo.addItems(node_ids)

        if current_src in node_ids:
            self.fiber_source_combo.setCurrentText(current_src)
        elif node_ids:
            self.fiber_source_combo.setCurrentIndex(0)

        if current_dst in node_ids:
            self.fiber_target_combo.setCurrentText(current_dst)
        elif len(node_ids) > 1:
            self.fiber_target_combo.setCurrentIndex(1)
        elif node_ids:
            self.fiber_target_combo.setCurrentIndex(0)

        if self.fiber_target_combo.count() > 1 and self.fiber_source_combo.currentText() == self.fiber_target_combo.currentText():
            for idx, node_id in enumerate(node_ids):
                if node_id != self.fiber_source_combo.currentText():
                    self.fiber_target_combo.setCurrentIndex(idx)
                    break

        self.fiber_source_combo.blockSignals(False)
        self.fiber_target_combo.blockSignals(False)

    def _replace_network_data(self, loaded_network: Network):
        self.network.clear()
        self.network.name = loaded_network.name
        self.network.nodes = loaded_network.nodes
        self.network.fibers = loaded_network.fibers
        self.network.channels = loaded_network.channels
        self.network.equipment = loaded_network.equipment
        self.power_budget_results.clear()
        self.dispersion_results.clear()
        self.selected_channel_id = None
        self.selected_channel_edges.clear()
        self._clear_flow_state()
        self._clear_topology_marks()

    def _read_two_point_settings_from_file(self, path: str) -> Dict[str, float | str]:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception:
            return {}
        if not isinstance(payload, dict):
            return {}

        settings: Dict[str, float | str] = {}
        block = payload.get("line_channel")
        if isinstance(block, dict):
            settings.update(block)

        nodes = payload.get("nodes", [])
        if isinstance(nodes, list) and len(nodes) >= 2:
            if isinstance(nodes[0], dict):
                settings.setdefault("source_node_id", nodes[0].get("node_id"))
            if isinstance(nodes[1], dict):
                settings.setdefault("target_node_id", nodes[1].get("node_id"))

        fibers = payload.get("fibers", [])
        if isinstance(fibers, list) and fibers and isinstance(fibers[0], dict):
            fiber = fibers[0]
            settings.setdefault("source_node_id", fiber.get("source_node_id"))
            settings.setdefault("target_node_id", fiber.get("target_node_id"))
            settings.setdefault("fiber_type", fiber.get("fiber_type"))
            settings.setdefault("attenuation_db_per_km", fiber.get("attenuation_db_per_km"))
            settings.setdefault("splice_interval_km", fiber.get("splice_interval_km", fiber.get("coil_length_km")))
            settings.setdefault("splice_losses_db", fiber.get("splice_losses_db"))
            settings.setdefault("connector_losses_db", fiber.get("connector_losses_db"))
            settings.setdefault("line_reserve_db", fiber.get("line_reserve_db"))

        channels = payload.get("channels", [])
        if isinstance(channels, list) and channels and isinstance(channels[0], dict):
            channel = channels[0]
            settings.setdefault("wavelength_nm", channel.get("wavelength_nm"))
            settings.setdefault("bitrate_gbps", channel.get("bitrate_gbps"))
            settings.setdefault("tx_power_dbm", channel.get("tx_power_dbm"))
            settings.setdefault("rx_sensitivity_dbm", channel.get("rx_sensitivity_dbm"))
            settings.setdefault("energy_budget_db", channel.get("energy_budget_db"))

        return settings

    def _sync_quick_node_fields_from_network(self):
        if not all(
            hasattr(self, attr)
            for attr in (
                "quick_node_a_id_edit",
                "quick_node_a_name_edit",
                "quick_node_b_id_edit",
                "quick_node_b_name_edit",
            )
        ):
            return
        node_a = self.network.get_node("NODE_A")
        node_b = self.network.get_node("NODE_B")
        if node_a:
            self.quick_node_a_id_edit.setText(node_a.node_id)
            self.quick_node_a_name_edit.setText(node_a.name or node_a.node_id)
        if node_b:
            self.quick_node_b_id_edit.setText(node_b.node_id)
            self.quick_node_b_name_edit.setText(node_b.name or node_b.node_id)
        if hasattr(self, "fiber_source_combo") and hasattr(self, "fiber_target_combo"):
            self._refresh_fiber_connection_selectors()
        if hasattr(self, "channel_src_combo") and hasattr(self, "channel_dst_combo"):
            self._refresh_channel_selectors()

    def _apply_two_point_settings(self, settings: Dict[str, float | str]):
        if not settings:
            return

        raw_fiber_type = str(settings.get("fiber_type", "") or "").strip()
        def set_fiber_type(combo_name: str):
            if not raw_fiber_type or not hasattr(self, combo_name):
                return
            combo = getattr(self, combo_name)
            if not isinstance(combo, QComboBox):
                return

            matched_index: Optional[int] = None
            raw_digits = "".join(ch for ch in raw_fiber_type if ch.isdigit())
            for idx in range(combo.count()):
                text = combo.itemText(idx).strip()
                if text == raw_fiber_type:
                    matched_index = idx
                    break
                text_digits = "".join(ch for ch in text if ch.isdigit())
                if raw_digits and raw_digits == text_digits:
                    matched_index = idx
                    break
            if matched_index is not None:
                combo.setCurrentIndex(matched_index)

        set_fiber_type("quick_fiber_type_combo")
        set_fiber_type("fiber_type_combo")

        def set_spin(key: str, spin_name: str):
            if not hasattr(self, spin_name):
                return
            value = settings.get(key)
            if value is None or value == "":
                return
            try:
                spin = getattr(self, spin_name)
                if isinstance(spin, QDoubleSpinBox):
                    spin.setValue(float(value))
                elif isinstance(spin, QComboBox) and key == "bitrate_gbps":
                    self._set_bitrate_widget_value(spin, float(value))
            except (TypeError, ValueError):
                return

        set_spin("attenuation_db_per_km", "quick_alpha_spin")
        set_spin("splice_interval_km", "quick_coil_length_spin")
        set_spin("splice_losses_db", "quick_splice_loss_spin")
        set_spin("connector_losses_db", "quick_connector_loss_spin")
        set_spin("line_reserve_db", "quick_line_reserve_spin")
        set_spin("splice_interval_km", "fiber_coil_length_spin")
        set_spin("splice_losses_db", "fiber_splice_loss_spin")
        set_spin("connector_losses_db", "fiber_connector_loss_spin")
        set_spin("line_reserve_db", "fiber_line_reserve_spin")
        set_spin("wavelength_nm", "quick_wavelength_spin")
        set_spin("bitrate_gbps", "quick_bitrate_spin")
        set_spin("energy_budget_db", "quick_energy_budget_spin")
        set_spin("wavelength_nm", "channel_wavelength_spin")
        set_spin("bitrate_gbps", "channel_bitrate_spin")
        set_spin("tx_power_dbm", "channel_tx_power_spin")
        set_spin("rx_sensitivity_dbm", "channel_rx_sens_spin")
        set_spin("energy_budget_db", "channel_energy_budget_spin")

        def set_combo_value(key: str, combo_name: str):
            if not hasattr(self, combo_name):
                return
            value = str(settings.get(key, "") or "").strip()
            if not value:
                return
            combo = getattr(self, combo_name)
            if isinstance(combo, QComboBox):
                combo.setCurrentText(value)

        set_combo_value("source_node_id", "fiber_source_combo")
        set_combo_value("target_node_id", "fiber_target_combo")
        set_combo_value("source_node_id", "channel_src_combo")
        set_combo_value("target_node_id", "channel_dst_combo")

        trace_mode = str(settings.get("trace_mode", "") or "").strip().lower()
        if trace_mode in {"roads", "straight"}:
            for combo_name in ("quick_trace_mode_combo", "trace_mode_combo"):
                if not hasattr(self, combo_name):
                    continue
                combo = getattr(self, combo_name)
                if not isinstance(combo, QComboBox):
                    continue
                for idx in range(combo.count()):
                    if combo.itemData(idx) == trace_mode:
                        combo.setCurrentIndex(idx)
                        break

    def _collect_two_point_settings(self) -> Dict[str, float | str]:
        settings: Dict[str, float | str] = {}

        if all(
            hasattr(self, attr)
            for attr in (
                "fiber_type_combo",
                "fiber_source_combo",
                "fiber_target_combo",
                "fiber_coil_length_spin",
                "fiber_splice_loss_spin",
                "fiber_connector_loss_spin",
                "fiber_line_reserve_spin",
            )
        ):
            settings.update(
                {
                    "fiber_type": self.fiber_type_combo.currentText(),
                    "source_node_id": self.fiber_source_combo.currentText(),
                    "target_node_id": self.fiber_target_combo.currentText(),
                    "splice_interval_km": float(self.fiber_coil_length_spin.value()),
                    "splice_losses_db": float(self.fiber_splice_loss_spin.value()),
                    "connector_losses_db": float(self.fiber_connector_loss_spin.value()),
                    "line_reserve_db": float(self.fiber_line_reserve_spin.value()),
                }
            )

        if all(
            hasattr(self, attr)
            for attr in (
                "quick_fiber_type_combo",
                "quick_alpha_spin",
                "quick_coil_length_spin",
                "quick_splice_loss_spin",
                "quick_connector_loss_spin",
                "quick_line_reserve_spin",
                "quick_trace_mode_combo",
                "quick_wavelength_spin",
                "quick_bitrate_spin",
                "quick_energy_budget_spin",
            )
        ):
            settings.update(
                {
                    "attenuation_db_per_km": float(self.quick_alpha_spin.value()),
                    "trace_mode": str(self.quick_trace_mode_combo.currentData() or "roads"),
                    "wavelength_nm": float(self.quick_wavelength_spin.value()),
                    "bitrate_gbps": self._get_bitrate_widget_value(self.quick_bitrate_spin),
                    "energy_budget_db": float(self.quick_energy_budget_spin.value()),
                }
            )

        if self.network.fibers:
            fiber = sorted(self.network.fibers.values(), key=lambda item: item.fiber_id)[0]
            settings.update(
                {
                    "source_node_id": fiber.source_node_id,
                    "target_node_id": fiber.target_node_id,
                    "fiber_type": fiber.fiber_type.value,
                    "attenuation_db_per_km": float(fiber.get_attenuation_per_km()),
                    "splice_interval_km": float(fiber.splice_interval_km),
                    "splice_losses_db": float(fiber.splice_losses_db),
                    "connector_losses_db": float(fiber.connector_losses_db),
                    "line_reserve_db": float(fiber.line_reserve_db),
                }
            )

        if self.network.channels:
            channel = sorted(self.network.channels.values(), key=lambda item: item.channel_id)[0]
            settings["wavelength_nm"] = float(channel.wavelength_nm)

        if hasattr(self, "trace_mode_combo"):
            settings["trace_mode"] = str(self.trace_mode_combo.currentData() or "roads")
        if hasattr(self, "channel_wavelength_spin"):
            settings["wavelength_nm"] = float(self.channel_wavelength_spin.value())
        if hasattr(self, "channel_bitrate_spin"):
            settings["bitrate_gbps"] = self._get_bitrate_widget_value(self.channel_bitrate_spin)
        if hasattr(self, "channel_tx_power_spin"):
            settings["tx_power_dbm"] = float(self.channel_tx_power_spin.value())
        if hasattr(self, "channel_rx_sens_spin"):
            settings["rx_sensitivity_dbm"] = float(self.channel_rx_sens_spin.value())
        if hasattr(self, "channel_energy_budget_spin"):
            settings["energy_budget_db"] = float(self.channel_energy_budget_spin.value())

        return settings

    def _rebuild_channels_after_topology_change(self):
        self.power_budget_results.clear()
        to_remove: List[str] = []
        for channel in self.network.channels.values():
            if not channel.path or len(channel.path) < 2:
                to_remove.append(channel.channel_id)
                continue
            source_id = channel.path[0]
            target_id = channel.path[-1]
            if source_id not in self.network.nodes or target_id not in self.network.nodes:
                to_remove.append(channel.channel_id)
                continue
            if self._path_has_all_fibers(channel.path):
                continue
            new_path = self._find_shortest_path(source_id, target_id)
            if not new_path:
                to_remove.append(channel.channel_id)
                continue
            channel.path = new_path
        for channel_id in to_remove:
            self.network.channels.pop(channel_id, None)
            self.power_budget_results.pop(channel_id, None)
            self.dispersion_results.pop(channel_id, None)
            if self.selected_channel_id == channel_id:
                self.selected_channel_id = None
                self.selected_channel_edges.clear()

    # ---------- File actions ----------

    def load_project_from_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузка проекта",
            "",
            "JSON файлы (*.json);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            loaded_network = load_network_from_json(path)
        except ProjectLoadError as exc:
            QMessageBox.critical(self, "Ошибка загрузки", str(exc))
            return
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка загрузки", f"Непредвиденная ошибка: {exc}")
            return

        settings = self._read_two_point_settings_from_file(path)
        self._replace_network_data(loaded_network)
        self.refresh_all()
        self._sync_quick_node_fields_from_network()
        self._apply_two_point_settings(settings)
        QMessageBox.information(
            self,
            "Загружено",
            (
                f"Проект загружен из:\n{path}\n\n"
                f"Узлов: {len(self.network.nodes)}\n"
                f"Волокон: {len(self.network.fibers)}\n"
                f"Каналов: {len(self.network.channels)}\n"
                f"Оборудования: {len(self.network.equipment)}"
            ),
        )

    def save_project_to_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранение проекта",
            "проект_сети.json",
            "JSON файлы (*.json);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            save_network_to_json(self.network, path)
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, dict):
                payload["line_channel"] = self._collect_two_point_settings()
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, ensure_ascii=False, indent=2)
                    fh.write("\n")
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка сохранения", f"Не удалось сохранить: {exc}")
            return
        QMessageBox.information(self, "Сохранено", f"Проект сохранен:\n{path}")

    def load_test_scheme(self):
        root_dir = os.path.dirname(os.path.dirname(__file__))
        schemes_dir = os.path.join(root_dir, "examples")
        default_path = os.path.join(schemes_dir, "test_scheme_variant_01.json")
        if not os.path.exists(schemes_dir):
            QMessageBox.warning(
                self,
                "Файл не найден",
                f"Каталог тестовых схем не найден:\n{schemes_dir}",
            )
            return
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите тестовый вариант",
            default_path,
            "JSON файлы (*.json);;Все файлы (*.*)",
        )
        if not path:
            return
        try:
            loaded_network = load_network_from_json(path)
        except ProjectLoadError as exc:
            QMessageBox.critical(self, "Ошибка загрузки", str(exc))
            return
        settings = self._read_two_point_settings_from_file(path)
        self._replace_network_data(loaded_network)
        self.refresh_all()
        self._sync_quick_node_fields_from_network()
        self._apply_two_point_settings(settings)
        QMessageBox.information(self, "Загружено", f"Загружена тестовая схема:\n{path}")

    def clear_project_data(self):
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Очистить весь проект (узлы, волокна, каналы, оборудование)?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.network.clear()
        self.power_budget_results.clear()
        self.selected_channel_id = None
        self.selected_channel_edges.clear()
        self._clear_flow_state()
        self._clear_topology_marks()
        self.refresh_all()

    # ---------- DWDM actions ----------

    def create_channel_between_nodes(self):
        source_id = self.channel_src_combo.currentText().strip()
        target_id = self.channel_dst_combo.currentText().strip()
        if not source_id or not target_id:
            QMessageBox.warning(self, "Ошибка ввода", "Выберите узел-источник и узел-назначение.")
            return
        if source_id == target_id:
            QMessageBox.warning(self, "Ошибка ввода", "Источник и назначение должны различаться.")
            return

        path = self._find_shortest_path(source_id, target_id)
        if not path:
            QMessageBox.warning(self, "Нет маршрута", "Между выбранными узлами нет пути.")
            return

        wavelength = float(self.channel_wavelength_spin.value())
        energy_budget_db = float(self.channel_energy_budget_spin.value())
        tx_power_dbm = 0.0
        rx_sensitivity_dbm = -energy_budget_db

        idx = 1
        while f"CH{idx}" in self.network.channels:
            idx += 1
        channel_id = f"CH{idx}"
        channel = Channel(
            channel_id=channel_id,
            wavelength_nm=wavelength,
            tx_power_dbm=tx_power_dbm,
            rx_sensitivity_dbm=rx_sensitivity_dbm,
            bitrate_gbps=self._get_bitrate_widget_value(self.channel_bitrate_spin),
            energy_budget_db=energy_budget_db,
            path=path,
        )
        channel.frequency_thz = FrequencyPlan.wavelength_to_frequency(channel.wavelength_nm)
        self.network.add_channel(channel)

        self.selected_channel_id = channel_id
        self.selected_channel_edges = {
            self._edge_key(a, b) for a, b in zip(path[:-1], path[1:])
        }
        self.refresh_dwdm_tables()
        self.update_map()
        QMessageBox.information(
            self,
            "Канал создан",
            (
                f"Канал: {channel_id}\n"
                f"Путь: {' -> '.join(path)}\n"
                f"Длина волны: {wavelength:.3f} нм"
            ),
        )

    def delete_selected_channel(self):
        selected = self.channels_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Выбор", "Сначала выберите канал.")
            return
        row = self.channels_table.row(selected[0])
        channel_item = self.channels_table.item(row, 0)
        if not channel_item:
            return
        channel_id = channel_item.text().strip()
        if not channel_id:
            return

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить канал '{channel_id}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.network.channels.pop(channel_id, None)
        self.power_budget_results.pop(channel_id, None)
        self.dispersion_results.pop(channel_id, None)
        if self.selected_channel_id == channel_id:
            self.selected_channel_id = None
            self.selected_channel_edges.clear()
        self.refresh_dwdm_tables()
        self.update_map()

    def clear_all_channels(self):
        if not self.network.channels:
            return
        reply = QMessageBox.question(
            self,
            "Подтверждение",
            "Удалить все оптические каналы?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.network.channels.clear()
        self.power_budget_results.clear()
        self.dispersion_results.clear()
        self.selected_channel_id = None
        self.selected_channel_edges.clear()
        self.refresh_dwdm_tables()
        self.update_map()

    def assign_wavelengths_to_channels(self):
        if not self.network.channels:
            QMessageBox.warning(self, "Нет каналов", "Сначала создайте каналы.")
            return
        spacing = float(self.channel_spacing_combo.currentData() or 0.1)
        groups: Dict[Tuple[str, ...], List[Channel]] = {}
        for channel in self.network.channels.values():
            groups.setdefault(tuple(channel.path or []), []).append(channel)

        unassigned: List[str] = []
        assigned_total = 0
        for path_key, channels in groups.items():
            if len(path_key) < 2:
                unassigned.extend(ch.channel_id for ch in channels)
                continue
            ordered = sorted(channels, key=lambda ch: ch.channel_id)
            assigned = FrequencyPlan.assign_wavelengths_to_channels(
                ordered,
                spacing_thz=spacing,
                start_channel=-40,
            )
            assigned_total += len(assigned)
            if len(assigned) < len(ordered):
                for channel in ordered:
                    if channel.channel_id not in assigned:
                        unassigned.append(channel.channel_id)

        self.refresh_dwdm_tables()
        if unassigned:
            QMessageBox.warning(
                self,
                "Назначение с предупреждениями",
                (
                    f"Назначено каналов: {assigned_total}\n"
                    f"Не назначены (вне C-band): {', '.join(unassigned)}"
                ),
            )
            return
        QMessageBox.information(self, "Назначено", f"Назначено длин волн: {assigned_total}")

    def auto_place_amplifiers(self):
        if not self.network.channels:
            QMessageBox.warning(self, "Нет каналов", "Сначала создайте каналы.")
            return

        placer = AmplifierPlacer(self.network)
        inline_added = 0
        for channel_id in list(self.network.channels.keys()):
            inline_added += placer.split_fibers_and_update_channel_path(channel_id)
        node_added = placer.place_amplifiers_for_all_channels()

        self._clear_flow_state()
        self._clear_topology_marks()
        self.power_budget_results.clear()
        self.refresh_all()
        QMessageBox.information(
            self,
            "Расстановка EDFA",
            (
                f"Добавлено линейных EDFA-узлов: {inline_added}\n"
                f"Добавлено EDFA в существующих узлах: {node_added}\n"
                f"Всего EDFA: {self._edfa_count()}"
            ),
        )

    def run_power_budget(self):
        if not self.network.channels:
            QMessageBox.warning(self, "Нет каналов", "Сначала создайте каналы.")
            return
        self.simulation_manager.power_budget_results = {}
        simulation_result = self.simulation_manager.run_simulation(auto_place_amplifiers=False)
        self.power_budget_results = dict(self.simulation_manager.power_budget_results)
        self.refresh_dwdm_tables()

        total = len(self.power_budget_results)
        valid = sum(1 for result in self.power_budget_results.values() if result.is_valid)
        invalid = total - valid
        message = (
            f"Оценено каналов: {total}\n"
            f"Валидных: {valid}\n"
            f"Невалидных: {invalid}"
        )
        warnings = simulation_result.get("warnings", [])
        if warnings:
            message += "\n\nПредупреждения:\n" + "\n".join(warnings[:10])
        QMessageBox.information(self, "Бюджет мощности", message)

    def run_dispersion_calc(self):
        if not self.network.channels:
            QMessageBox.warning(self, "Нет каналов", "Сначала создайте каналы.")
            return

        calc = DispersionCalculator()
        self.dispersion_results = calc.all_channels(self.network)

        total = len(self.dispersion_results)
        cd_ok = sum(1 for r in self.dispersion_results.values() if r.cd_is_valid)
        pmd_ok = sum(1 for r in self.dispersion_results.values() if r.pmd_is_valid)

        self.refresh_dwdm_tables()

        lines = [
            f"Каналов проверено: {total}",
            "",
            "Хроматическая дисперсия (ХД):",
            f"  OK:   {cd_ok}",
            f"  FAIL: {total - cd_ok}",
            "",
            "Поляризационная модовая дисперсия (ПМД):",
            f"  OK:   {pmd_ok}",
            f"  FAIL: {total - pmd_ok}",
        ]

        fail_details = []
        for r in self.dispersion_results.values():
            if not r.is_valid:
                cd_flag = "" if r.cd_is_valid else f"ХД={r.total_cd_ps_nm:.0f}>{r.cd_limit_ps_nm:.0f}"
                pmd_flag = "" if r.pmd_is_valid else f"ПМД={r.total_pmd_ps:.2f}>{r.pmd_limit_ps:.2f}"
                detail = f"  {r.channel_id}: " + ", ".join(filter(None, [cd_flag, pmd_flag]))
                fail_details.append(detail)

        if fail_details:
            lines.append("")
            lines.append("Проблемные каналы:")
            lines.extend(fail_details[:15])
            if len(fail_details) > 15:
                lines.append(f"  ... и ещё {len(fail_details) - 15}")

        QMessageBox.information(self, "Результат расчёта дисперсии", "\n".join(lines))

    def _apply_channel_selection(self, channel_id: Optional[str]):
        if not channel_id or channel_id not in self.network.channels:
            self.selected_channel_id = None
            self.selected_channel_edges.clear()
            self.profile_table.setRowCount(0)
            self._plot_profile([])
            self._plot_dispersion_profile(None)
            self.update_map()
            return

        self.selected_channel_id = channel_id
        channel = self.network.channels.get(channel_id)
        if channel and channel.path and len(channel.path) >= 2:
            self.selected_channel_edges = {
                self._edge_key(a, b) for a, b in zip(channel.path[:-1], channel.path[1:])
            }
        else:
            self.selected_channel_edges.clear()

        profile = self.power_budget_results.get(channel_id).profile if channel_id in self.power_budget_results else []
        self.profile_table.setRowCount(len(profile))
        for row_idx, (distance_km, power_dbm) in enumerate(profile):
            self.profile_table.setItem(row_idx, 0, QTableWidgetItem(f"{distance_km:.2f}"))
            self.profile_table.setItem(row_idx, 1, QTableWidgetItem(f"{power_dbm:.2f}"))
        self._plot_profile(profile)
        self._plot_dispersion_profile(channel)
        self.update_map()

    @staticmethod
    def _select_channel_row(table: QTableWidget, channel_id: Optional[str], id_col: int):
        table.blockSignals(True)
        try:
            if not channel_id:
                table.clearSelection()
                return
            for row in range(table.rowCount()):
                item = table.item(row, id_col)
                if item and item.text().strip() == channel_id:
                    table.selectRow(row)
                    return
            table.clearSelection()
        finally:
            table.blockSignals(False)

    def _sync_channel_selection(self, channel_id: Optional[str], source: str):
        if self._syncing_channel_selection:
            return
        self._syncing_channel_selection = True
        try:
            if source != "channels" and hasattr(self, "channels_table"):
                self._select_channel_row(self.channels_table, channel_id, 0)
            if source != "excel" and hasattr(self, "excel_line_calc_table"):
                self._select_channel_row(self.excel_line_calc_table, channel_id, 1)
            self._apply_channel_selection(channel_id)
        finally:
            self._syncing_channel_selection = False

    def on_channel_selection_changed(self):
        if self._syncing_channel_selection:
            return
        selected = self.channels_table.selectedItems()
        if not selected:
            self._sync_channel_selection(None, source="channels")
            return
        row = self.channels_table.row(selected[0])
        item = self.channels_table.item(row, 0)
        channel_id = item.text().strip() if item else ""
        self._sync_channel_selection(channel_id or None, source="channels")

    def on_excel_channel_selection_changed(self):
        if self._syncing_channel_selection:
            return
        selected = self.excel_line_calc_table.selectedItems()
        if not selected:
            self._sync_channel_selection(None, source="excel")
            return
        row = self.excel_line_calc_table.row(selected[0])
        item = self.excel_line_calc_table.item(row, 1)
        channel_id = item.text().strip() if item else ""
        self._sync_channel_selection(channel_id or None, source="excel")

    def _plot_profile(self, profile: List[Tuple[float, float]]):
        if self.profile_figure is None or self.profile_canvas is None:
            return
        self.profile_figure.clear()
        axis = self.profile_figure.add_subplot(111)
        if profile:
            distances = [point[0] for point in profile]
            powers = [point[1] for point in profile]
            axis.plot(distances, powers, marker="o", linewidth=1.5, markersize=3)
            axis.set_xlabel("Расстояние, км")
            axis.set_ylabel("Мощность, дБм")
            axis.grid(True, linestyle="--", alpha=0.4)
        else:
            axis.text(0.5, 0.5, "Нет профиля", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
        self.profile_figure.tight_layout()
        self.profile_canvas.draw()

    def _plot_dispersion_profile(self, channel: Optional[Channel]):
        if not hasattr(self, "dispersion_profile_label"):
            return
        if channel is None:
            self.dispersion_profile_label.setText("Выберите канал для отображения профиля дисперсии.")
            if self.dispersion_figure is not None and self.dispersion_canvas is not None:
                self.dispersion_figure.clear()
                axis = self.dispersion_figure.add_subplot(111)
                axis.text(0.5, 0.5, "Нет профиля", ha="center", va="center", transform=axis.transAxes)
                axis.set_axis_off()
                self.dispersion_figure.tight_layout()
                self.dispersion_canvas.draw()
            self._plot_pulse_broadening(None, None)
            return

        result = self.dispersion_results.get(channel.channel_id)
        if result is None:
            self.dispersion_profile_label.setText(
                "Сначала нажмите 'Рассчитать дисперсию' на вкладке 'Каналы'."
            )
            if self.dispersion_figure is not None and self.dispersion_canvas is not None:
                self.dispersion_figure.clear()
                axis = self.dispersion_figure.add_subplot(111)
                axis.text(0.5, 0.5, "Нет профиля", ha="center", va="center", transform=axis.transAxes)
                axis.set_axis_off()
                self.dispersion_figure.tight_layout()
                self.dispersion_canvas.draw()
            self._plot_pulse_broadening(None, None)
            return

        if not result.fiber_results:
            self.dispersion_profile_label.setText("Нет данных по трассе канала для расчета дисперсии.")
            if self.dispersion_figure is not None and self.dispersion_canvas is not None:
                self.dispersion_figure.clear()
                axis = self.dispersion_figure.add_subplot(111)
                axis.text(0.5, 0.5, "Нет профиля", ha="center", va="center", transform=axis.transAxes)
                axis.set_axis_off()
                self.dispersion_figure.tight_layout()
                self.dispersion_canvas.draw()
            self._plot_pulse_broadening(None, None)
            return

        distances = [0.0]
        cd_values = [0.0]
        pmd_values = [0.0]
        cumulative_length = 0.0
        cumulative_cd = 0.0
        cumulative_pmd_sq = 0.0
        for fiber_res in result.fiber_results:
            cumulative_length += max(float(fiber_res.length_km), 0.0)
            cumulative_cd += float(fiber_res.accumulated_cd_ps_nm)
            cumulative_pmd_sq += float(fiber_res.pmd_ps) ** 2
            distances.append(cumulative_length)
            cd_values.append(cumulative_cd)
            pmd_values.append(math.sqrt(cumulative_pmd_sq))

        self.dispersion_profile_label.setText(
            (
                f"ХД: {result.total_cd_ps_nm:.1f}/{result.cd_limit_ps_nm:.0f} пс/нм "
                f"({'OK' if result.cd_is_valid else 'FAIL'}) | "
                f"ПМД: {result.total_pmd_ps:.2f}/{result.pmd_limit_ps:.2f} пс "
                f"({'OK' if result.pmd_is_valid else 'FAIL'})"
            )
        )

        if self.dispersion_figure is None or self.dispersion_canvas is None:
            return
        self.dispersion_figure.clear()
        axis = self.dispersion_figure.add_subplot(111)
        axis.plot(distances, cd_values, marker="o", linewidth=1.5, markersize=3, label="ΣХД, пс/нм")
        axis.plot(distances, pmd_values, marker="s", linewidth=1.5, markersize=3, label="ПМД, пс")
        axis.set_xlabel("Расстояние, км")
        axis.set_ylabel("Накопленное значение")
        axis.grid(True, linestyle="--", alpha=0.4)
        axis.legend(loc="best", fontsize=8)
        self.dispersion_figure.tight_layout()
        self.dispersion_canvas.draw()
        self._plot_pulse_broadening(result, channel)

    def _plot_pulse_broadening(self, result: Optional[DispersionResult], channel: Optional[Channel]):
        if self.dispersion_pulse_figure is None or self.dispersion_pulse_canvas is None:
            return

        self.dispersion_pulse_figure.clear()
        axis = self.dispersion_pulse_figure.add_subplot(111)

        if result is None or channel is None:
            axis.text(0.5, 0.5, "Нет данных", ha="center", va="center", transform=axis.transAxes)
            axis.set_axis_off()
            self.dispersion_pulse_figure.tight_layout()
            self.dispersion_pulse_canvas.draw()
            return

        # --- Получить параметры модуляции и лазера из UI ---
        modulation = "nrz"
        if hasattr(self, "disp_modulation_combo"):
            modulation = str(self.disp_modulation_combo.currentData() or "nrz")

        laser_type = "dfb"
        if hasattr(self, "disp_laser_combo"):
            laser_type = str(self.disp_laser_combo.currentData() or "dfb")

        laser_width_override = None
        if hasattr(self, "disp_laser_width_override"):
            raw = float(self.disp_laser_width_override.value())
            laser_width_override = raw if raw > 0 else None

        # --- Рассчитать метрики пульса используя физический визуализатор ---
        budget = self.power_budget_results.get(channel.channel_id)
        metrics = self.dispersion_visualizer.pulse_metrics(
            self.network,
            channel,
            result,
            modulation=modulation,  # type: ignore[arg-type]
            laser_type=laser_type,  # type: ignore[arg-type]
            laser_width_nm_override=laser_width_override,
            budget=budget,
        )

        # --- Выбрать тип графика ---
        # Вариант 1: Temporal (временная диаграмма импульсов)
        # self._plot_nrz_sequence(axis, metrics)

        # График OSNR vs расстояние
        self._plot_osnr_vs_distance(axis, metrics, channel.channel_id)

        # --- Добавить информацию ---
        axis.text(
            0.01,
            0.98,
            (
                f"Лазер={laser_type.upper()}, модуляция={modulation.upper()}, Δλ≈{metrics.delta_lambda_nm:.6f} нм\n"
                f"τ_CD≈{metrics.tau_cd_ps:.1f} пс, τ_PMD≈{metrics.tau_pmd_ps:.2f} пс\n"
                f"σ_in≈{metrics.sigma_in_ps:.2f} пс, σ_out≈{metrics.sigma_out_ps:.2f} пс\n"
                f"Потери≈{metrics.net_loss_db:.2f} дБ, пик≈{metrics.peak_ratio:.3g}\n"
                f"Задержка≈{metrics.group_delay_s*1e3:.3f} мс"
            ),
            transform=axis.transAxes,
            ha="left",
            va="top",
            fontsize=8,
            color="#333",
            bbox=dict(boxstyle="round,pad=0.5", facecolor="yellow", alpha=0.2),
        )

        self.dispersion_pulse_figure.tight_layout()
        self.dispersion_pulse_canvas.draw()

    def _plot_nrz_sequence(self, axis, metrics):
        """
        Рисует последовательность NRZ импульсов с уширением от дисперсии.

        Показывает:
        - Входной импульс (прямоугольный NRZ с резкими фронтами)
        - Выходной импульс (с размытыми фронтами от дисперсии)
        - Несколько повторений для видимости ISI (межсимвольной интерференции)
        """
        import numpy as np
        from scipy.special import erf

        # Параметры
        t_bit = metrics.t_bit_ps
        sigma_in = metrics.sigma_in_ps
        sigma_out = metrics.sigma_out_ps
        peak_in = 1.0
        peak_out = metrics.peak_ratio

        # Показываем 6 битов для наглядности
        n_bits = 6
        bit_sequence = [1, 0, 1, 1, 0, 1]

        # Временная ось
        n_samples = 2000
        t_min = -0.5 * t_bit
        t_max = (n_bits + 0.5) * t_bit
        t_axis = np.linspace(t_min, t_max, n_samples)

        # Построить идеальный NRZ сигнал (прямоугольные импульсы)
        y_ideal = np.zeros_like(t_axis)
        for i, bit in enumerate(bit_sequence):
            mask = (t_axis >= i * t_bit) & (t_axis < (i + 1) * t_bit)
            y_ideal[mask] = peak_in if bit == 1 else 0.0

        # Входной сигнал с небольшим размытием (свёртка с узким гауссом)
        # Используем функцию ошибок для моделирования фронтов
        y_in = np.zeros_like(t_axis)
        for i, bit in enumerate(bit_sequence):
            t_start = i * t_bit
            t_end = (i + 1) * t_bit

            # Передний фронт (0→1 или остаёмся на уровне)
            if bit == 1:
                y_in += 0.5 * peak_in * (1 + erf((t_axis - t_start) / (sigma_in * np.sqrt(2))))

            # Задний фронт (1→0)
            if bit == 1:
                y_in -= 0.5 * peak_in * (1 + erf((t_axis - t_end) / (sigma_in * np.sqrt(2))))

        # Выходной сигнал с сильным размытием (дисперсия)
        y_out = np.zeros_like(t_axis)
        for i, bit in enumerate(bit_sequence):
            t_start = i * t_bit
            t_end = (i + 1) * t_bit

            if bit == 1:
                y_out += 0.5 * peak_out * (1 + erf((t_axis - t_start) / (sigma_out * np.sqrt(2))))
                y_out -= 0.5 * peak_out * (1 + erf((t_axis - t_end) / (sigma_out * np.sqrt(2))))

        # Рисовать
        # Идеальный сигнал (пунктир)
        axis.plot(t_axis, y_ideal, color="#BDBDBD", linewidth=1, linestyle="--",
                 label="Идеальный NRZ", alpha=0.5)

        # Входной сигнал
        axis.fill_between(t_axis, y_in, color="#64B5F6", alpha=0.25)
        axis.plot(t_axis, y_in, color="#1E88E5", linewidth=2, label=f"Входной (σ={sigma_in:.2f} пс)")

        # Выходной сигнал
        axis.fill_between(t_axis, y_out, color="#FFB74D", alpha=0.25)
        axis.plot(t_axis, y_out, color="#E53935", linewidth=2,
                 label=f"Выходной (σ={sigma_out:.2f} пс, потери={metrics.net_loss_db:.1f} дБ)")

        # Оформление
        axis.set_title("NRZ импульсы: влияние ХД + ПМД на уширение", fontsize=10, fontweight="bold")
        axis.set_xlabel("Время (пс)")
        axis.set_ylabel("Нормализованная мощность")
        axis.grid(True, linestyle="--", alpha=0.3)
        axis.legend(loc="upper right", fontsize=8)
        axis.set_xlim(t_min, t_max)

        # Автоматический масштаб по Y
        y_margin = peak_out * 0.15
        axis.set_ylim(-y_margin, peak_in + y_margin)

        # Добавить разметку битовых интервалов
        for i in range(n_bits + 1):
            t = i * t_bit
            axis.axvline(t, color="gray", linestyle=":", alpha=0.3, linewidth=0.5)
            if i < n_bits:
                # Подписать биты
                axis.text(t + t_bit/2, peak_in + y_margin * 0.85, str(bit_sequence[i]),
                         ha="center", va="bottom", fontsize=9, color="#666")

    def _plot_osnr_vs_distance(self, axis, metrics, channel_id):
        """
        Рисует график зависимости OSNR от расстояния.

        Показывает деградацию OSNR по мере распространения сигнала через сеть.
        """
        import numpy as np

        print(f"\n{'='*60}")
        print(f"DEBUG: График OSNR для канала {channel_id}")
        print(f"{'='*60}")

        # Получаем канал и его маршрут
        channel = self.network.channels.get(channel_id)
        if not channel or not channel.path:
            axis.text(0.5, 0.5, "Нет данных о маршруте канала",
                     ha='center', va='center', transform=axis.transAxes)
            return

        print(f"Маршрут: {' -> '.join(channel.path)}")
        print(f"Начальный OSNR из JSON: {channel.osnr_db} дБ")
        print(f"Начальная мощность Tx: {channel.tx_power_dbm} дБм")

        # Получаем волокна на маршруте
        fibers = self.network.get_path_fibers(channel.path)
        if not fibers:
            axis.text(0.5, 0.5, "Нет волокон на маршруте",
                     ha='center', va='center', transform=axis.transAxes)
            return

        print(f"Количество пролетов: {len(fibers)}")

        # Рассчитываем OSNR в каждой точке маршрута
        distances = [0.0]  # Начальная точка
        osnr_values = [40.0]  # Начальный OSNR (передатчик)
        node_names = [channel.path[0]]

        cumulative_distance = 0.0

        # Начальная мощность сигнала (дБм)
        signal_power_dbm = channel.tx_power_dbm

        # Накопленная мощность ASE шума (в линейных единицах, мВт)
        # Начальный шум от передатчика (очень мал)
        initial_osnr_linear = 10 ** (40.0 / 10.0)  # OSNR = 40 дБ
        signal_power_mw = 10 ** (signal_power_dbm / 10.0)
        ase_noise_mw = signal_power_mw / initial_osnr_linear

        # Параметры по умолчанию
        nf_db = 5.0  # Коэффициент шума EDFA
        nf_linear = 10 ** (nf_db / 10.0)

        print(f"\nНачальный OSNR: 40.0 дБ (передатчик)")
        print(f"Начальная мощность сигнала: {signal_power_dbm:.2f} дБм ({signal_power_mw:.6f} мВт)")
        print(f"Начальный шум ASE: {10*np.log10(ase_noise_mw):.2f} дБм ({ase_noise_mw:.9f} мВт)")

        for i, fiber in enumerate(fibers):
            print(f"\n--- Пролет {i+1}: {fiber.source_node_id} -> {fiber.target_node_id} ---")

            # Добавляем расстояние
            cumulative_distance += fiber.length_km
            print(f"Длина пролета: {fiber.length_km:.2f} км")
            print(f"Накопленное расстояние: {cumulative_distance:.2f} км")

            # Потери в пролете
            span_loss_db = fiber.calculate_fiber_loss()
            span_loss_linear = 10 ** (span_loss_db / 10.0)
            print(f"Потери в пролете: {span_loss_db:.2f} дБ")

            # После пролета: и сигнал, и шум ослабляются одинаково
            signal_power_dbm -= span_loss_db
            signal_power_mw /= span_loss_linear
            ase_noise_mw /= span_loss_linear

            osnr_after_span = signal_power_mw / ase_noise_mw if ase_noise_mw > 0 else 1e6
            print(f"После пролета: сигнал = {signal_power_dbm:.2f} дБм, шум = {10*np.log10(ase_noise_mw):.2f} дБм")
            print(f"OSNR после пролета: {10*np.log10(osnr_after_span):.2f} дБ")

            # Усилитель компенсирует потери и добавляет ASE шум
            gain_db = span_loss_db  # Компенсируем потери
            gain_linear = 10 ** (gain_db / 10.0)

            print(f"Усиление EDFA: {gain_db:.2f} дБ")
            print(f"Коэффициент шума NF: {nf_db:.2f} дБ")

            # Усиливаем сигнал
            signal_power_dbm += gain_db
            signal_power_mw *= gain_linear

            # Добавляем ASE шум от усилителя
            # P_ASE = n_sp * h * nu * (G - 1) * B_ref
            # Упрощенно: P_ASE ≈ (NF - 1) * G * h * nu * B_ref
            # Еще проще: P_ASE_mW ≈ (NF_linear - 1) * signal_power_before_amp_mW

            # ASE шум пропорционален (NF-1) и мощности сигнала до усилителя
            signal_before_amp_mw = signal_power_mw / gain_linear
            ase_from_amp_mw = (nf_linear - 1) * signal_before_amp_mw
            ase_noise_mw += ase_from_amp_mw

            print(f"ASE от усилителя: {10*np.log10(ase_from_amp_mw):.2f} дБм ({ase_from_amp_mw:.9f} мВт)")
            print(f"Суммарный шум: {10*np.log10(ase_noise_mw):.2f} дБм ({ase_noise_mw:.9f} мВт)")

            # Записываем значение
            distances.append(cumulative_distance)
            osnr_linear = signal_power_mw / ase_noise_mw if ase_noise_mw > 0 else 1e6
            osnr_db = 10 * np.log10(osnr_linear)
            osnr_values.append(osnr_db)
            node_names.append(fiber.target_node_id)

            print(f"После усилителя: сигнал = {signal_power_dbm:.2f} дБм, OSNR = {osnr_db:.2f} дБ")

        print(f"\n{'='*60}")
        print(f"ИТОГО:")
        print(f"  Финальный OSNR: {osnr_values[-1]:.2f} дБ")
        print(f"  Общая длина: {cumulative_distance:.2f} км")
        print(f"  Усилителей: {len(fibers)}")
        print(f"  OSNR из JSON: {channel.osnr_db} дБ")
        print(f"{'='*60}\n")

        # Рисуем график
        axis.plot(distances, osnr_values, 'b-o', linewidth=2, markersize=6, label='OSNR (расчетный)')

        # Если есть OSNR из JSON, показываем его как горизонтальную линию
        if channel.osnr_db is not None:
            axis.axhline(y=channel.osnr_db, color='purple', linestyle='-.', linewidth=2,
                        alpha=0.7, label=f'OSNR из JSON ({channel.osnr_db:.1f} дБ)')

        # Добавляем пороговые линии
        axis.axhline(y=15, color='red', linestyle='--', linewidth=1.5, alpha=0.7, label='Минимум (15 дБ)')
        axis.axhline(y=20, color='orange', linestyle='--', linewidth=1.5, alpha=0.7, label='Приемлемо (20 дБ)')
        axis.axhline(y=25, color='green', linestyle='--', linewidth=1.5, alpha=0.7, label='Хорошо (25 дБ)')

        # Подписываем узлы
        for i, (dist, osnr, node) in enumerate(zip(distances, osnr_values, node_names)):
            if i % 2 == 0:  # Подписываем каждый второй узел для читаемости
                axis.annotate(node, (dist, osnr),
                            textcoords="offset points", xytext=(0, 10),
                            ha='center', fontsize=8, color='blue')

        # Оформление
        axis.set_title(f"Деградация OSNR вдоль маршрута канала {channel_id}",
                      fontsize=10, fontweight="bold")
        axis.set_xlabel("Расстояние (км)", fontsize=9)
        axis.set_ylabel("OSNR (дБ)", fontsize=9)
        axis.grid(True, linestyle="--", alpha=0.3)
        axis.legend(loc='best', fontsize=8)

        # Устанавливаем пределы по Y
        axis.set_ylim(10, 45)

        # Добавляем информацию
        info_text = f"Итоговый OSNR (расчет): {osnr_values[-1]:.1f} дБ\n"
        if channel.osnr_db is not None:
            info_text += f"OSNR из JSON: {channel.osnr_db:.1f} дБ\n"
        info_text += f"Общая длина: {cumulative_distance:.1f} км\n"
        info_text += f"Усилителей: {len(fibers)}"

        axis.text(0.98, 0.02, info_text, transform=axis.transAxes,
                 fontsize=8, verticalalignment='bottom', horizontalalignment='right',
                 bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    def _open_eye_diagram_window(self):
        """Открывает глазковую диаграмму в отдельном большом окне."""
        # Получить текущий выбранный канал
        channel_id = self.selected_channel_id
        if not channel_id:
            QMessageBox.warning(self, "Нет канала", "Выберите канал в таблице для отображения глазковой диаграммы.")
            return

        channel = self.network.channels.get(channel_id)
        result = self.dispersion_results.get(channel_id)

        if not channel or not result:
            QMessageBox.warning(self, "Нет данных", "Сначала рассчитайте дисперсию для выбранного канала.")
            return

        # Получить параметры из UI
        modulation = str(self.disp_modulation_combo.currentData() or "nrz")
        laser_type = str(self.disp_laser_combo.currentData() or "dfb")
        laser_width_override = None
        if hasattr(self, "disp_laser_width_override"):
            raw = float(self.disp_laser_width_override.value())
            laser_width_override = raw if raw > 0 else None

        # Рассчитать OSNR для канала
        from core.calculators.osnr_calculator import OSNRCalculator
        osnr_calc = OSNRCalculator(self.network)
        osnr_result = osnr_calc.calculate_osnr(channel)

        print(f"\n{'='*60}")
        print(f"DEBUG: Eye Diagram для канала {channel_id}")
        print(f"Рассчитанный OSNR: {osnr_result.osnr_db:.2f} дБ")
        print(f"{'='*60}\n")

        # Рассчитать метрики с учетом OSNR
        budget = self.power_budget_results.get(channel.channel_id)
        metrics = self.dispersion_visualizer.pulse_metrics(
            self.network,
            channel,
            result,
            modulation=modulation,  # type: ignore[arg-type]
            laser_type=laser_type,  # type: ignore[arg-type]
            laser_width_nm_override=laser_width_override,
            budget=budget,
            osnr_result=osnr_result,  # Передаем рассчитанный OSNR
        )

        # Создать и показать окно
        dialog = EyeDiagramDialog(self, metrics, channel_id, modulation, laser_type)
        dialog.exec_()

    def refresh_dwdm_tables(self):
        self._refresh_channel_selectors()

        channels = sorted(self.network.channels.values(), key=lambda channel: channel.channel_id)
        self.channels_table.setRowCount(len(channels))
        valid_count = 0

        for row, channel in enumerate(channels):
            source_id = channel.path[0] if channel.path else "-"
            target_id = channel.path[-1] if channel.path else "-"
            path_text = " -> ".join(channel.path or [])
            result = self.power_budget_results.get(channel.channel_id)
            raw_loss = result.raw_loss_db if result else None
            margin = result.power_margin_db if result else None
            status_text = "-"
            if result:
                status_text = "OK" if result.is_valid else "FAIL"
                if result.is_valid:
                    valid_count += 1

            values = [
                channel.channel_id,
                source_id,
                target_id,
                path_text,
                f"{channel.wavelength_nm:.3f}",
                f"{channel.frequency_thz:.3f}" if channel.frequency_thz is not None else "-",
                f"{raw_loss:.2f}" if raw_loss is not None else "-",
                f"{margin:.2f}" if margin is not None else "-",
                status_text,
            ]
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col == 8 and status_text == "FAIL":
                    item.setForeground(Qt.red)
                if col == 8 and status_text == "OK":
                    item.setForeground(Qt.darkGreen)
                self.channels_table.setItem(row, col, item)

        total_channels = len(channels)
        edfa_count = self._edfa_count()
        if self.power_budget_results:
            self.dwdm_summary_label.setText(
                f"Каналов: {total_channels} | EDFA: {edfa_count} | Валидных: {valid_count}/{total_channels}"
            )
        else:
            self.dwdm_summary_label.setText(
                f"Каналов: {total_channels} | EDFA: {edfa_count} | Расчет: не запускался"
            )

        self.refresh_excel_line_calc_table()

        if self.selected_channel_id and self.selected_channel_id in self.network.channels:
            for row in range(self.channels_table.rowCount()):
                item = self.channels_table.item(row, 0)
                if item and item.text() == self.selected_channel_id:
                    self.channels_table.selectRow(row)
                    break
            if hasattr(self, "excel_line_calc_table"):
                self._select_channel_row(self.excel_line_calc_table, self.selected_channel_id, 1)
            self._apply_channel_selection(self.selected_channel_id)
        elif channels:
            first_channel_id = channels[0].channel_id
            self.selected_channel_id = first_channel_id
            self._select_channel_row(self.channels_table, first_channel_id, 0)
            if hasattr(self, "excel_line_calc_table"):
                self._select_channel_row(self.excel_line_calc_table, first_channel_id, 1)
            self._apply_channel_selection(first_channel_id)
        else:
            self.selected_channel_id = None
            self.selected_channel_edges.clear()
            self.profile_table.setRowCount(0)
            self._plot_profile([])
            self._plot_dispersion_profile(None)

    @staticmethod
    def _fmt_calc_value(value: float, decimals: int) -> str:
        text = f"{value:.{decimals}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    def open_export_tables_dialog(self):
        if Workbook is None:
            QMessageBox.warning(
                self,
                "Экспорт недоступен",
                "Для экспорта в Excel нужен пакет openpyxl.\n"
                "Установите его и перезапустите приложение.",
            )
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("Экспорт таблиц")
        dialog.setMinimumWidth(420)

        layout = QVBoxLayout()
        layout.addWidget(QLabel("Выберите таблицы для экспорта:"))

        table_defs = self._get_export_table_defs()
        checkboxes: List[Tuple[QCheckBox, str, str]] = []
        for label, attr in table_defs:
            if not hasattr(self, attr):
                continue
            checkbox = QCheckBox(label)
            checkbox.setChecked(True)
            layout.addWidget(checkbox)
            checkboxes.append((checkbox, attr, label))

        if not checkboxes:
            QMessageBox.warning(self, "Экспорт", "Нет таблиц для экспорта.")
            return

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setLayout(layout)

        if dialog.exec_() != QDialog.Accepted:
            return

        selected_tables: List[Tuple[str, QTableWidget]] = []
        for checkbox, attr, label in checkboxes:
            if checkbox.isChecked():
                table = getattr(self, attr, None)
                if isinstance(table, QTableWidget):
                    selected_tables.append((label, table))

        if not selected_tables:
            QMessageBox.warning(self, "Экспорт", "Не выбрано ни одной таблицы.")
            return

        default_name = "export_tables.xlsx"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить Excel",
            default_name,
            "Excel (*.xlsx);;Все файлы (*.*)",
        )
        if not path:
            return
        if not path.lower().endswith(".xlsx"):
            path += ".xlsx"

        try:
            self._export_tables_to_excel(path, selected_tables)
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка экспорта", f"Не удалось экспортировать:\n{exc}")
            return

        QMessageBox.information(self, "Экспорт завершен", f"Файл сохранен:\n{path}")

    @staticmethod
    def _get_export_table_defs() -> List[Tuple[str, str]]:
        return [
            ("Узлы", "nodes_table"),
            ("Волокна", "fibers_table"),
            ("Сварки и коннекторы", "fiber_events_table"),
            ("Каналы", "channels_table"),
            ("Таблица расчета линии", "excel_line_calc_table"),
            ("Направления", "directions_table"),
            ("Нагрузки волокон", "flow_loads_table"),
            ("Нагрузки узлов", "node_loads_table"),
        ]

    @staticmethod
    def _sanitize_sheet_title(title: str, existing: Set[str]) -> str:
        invalid = set(":\\/?*[]")
        cleaned = "".join(ch if ch not in invalid else "_" for ch in (title or "Sheet"))
        cleaned = cleaned.strip() or "Sheet"
        cleaned = cleaned[:31]
        if cleaned not in existing:
            existing.add(cleaned)
            return cleaned
        idx = 2
        while True:
            suffix = f"_{idx}"
            base = cleaned[: 31 - len(suffix)]
            candidate = f"{base}{suffix}"
            if candidate not in existing:
                existing.add(candidate)
                return candidate
            idx += 1

    @staticmethod
    def _table_to_rows(table: QTableWidget) -> Tuple[List[str], List[List[str]]]:
        headers: List[str] = []
        for col in range(table.columnCount()):
            header_item = table.horizontalHeaderItem(col)
            headers.append(header_item.text() if header_item else f"Col {col + 1}")
        rows: List[List[str]] = []
        for row in range(table.rowCount()):
            row_values: List[str] = []
            for col in range(table.columnCount()):
                item = table.item(row, col)
                row_values.append(item.text() if item else "")
            rows.append(row_values)
        return headers, rows

    def _export_tables_to_excel(self, path: str, tables: List[Tuple[str, QTableWidget]]):
        self.refresh_all()
        workbook = Workbook()
        existing_titles: Set[str] = set()
        first_sheet = True

        for label, table in tables:
            sheet_title = self._sanitize_sheet_title(label, existing_titles)
            if first_sheet:
                sheet = workbook.active
                sheet.title = sheet_title
                first_sheet = False
            else:
                sheet = workbook.create_sheet(title=sheet_title)

            headers, rows = self._table_to_rows(table)
            sheet.append(headers)
            for row in rows:
                sheet.append(row)

        workbook.save(path)

    def refresh_excel_line_calc_table(self):
        if not hasattr(self, "excel_line_calc_table"):
            return

        channels = sorted(self.network.channels.values(), key=lambda channel: channel.channel_id)
        self.excel_line_calc_table.setRowCount(len(channels))

        for row_idx, channel in enumerate(channels):
            fibers = self.network.get_path_fibers(channel.path or [])
            row_number = row_idx + 1
            source_id = channel.path[0] if channel.path else "-"
            target_id = channel.path[-1] if channel.path else "-"
            path_text = " -> ".join(channel.path or [])
            prefix_values = [str(row_number), channel.channel_id, source_id, target_id, path_text]

            if not fibers:
                values = prefix_values + ["-"] * 28
                for col_idx, value in enumerate(values):
                    self.excel_line_calc_table.setItem(row_idx, col_idx, QTableWidgetItem(value))
                continue

            line_length_km = sum(max(float(fiber.length_km), 0.0) for fiber in fibers)
            if line_length_km <= 0.0:
                values = prefix_values + ["-"] * 28
                for col_idx, value in enumerate(values):
                    self.excel_line_calc_table.setItem(row_idx, col_idx, QTableWidgetItem(value))
                continue

            energy_budget_db = float(channel.get_energy_budget_db())
            construction_length_km = max(
                max(float(getattr(fiber, "splice_interval_km", 25.0)), 0.001) for fiber in fibers
            )
            splice_loss_db = max(float(getattr(fiber, "splice_losses_db", 0.02)) for fiber in fibers)
            connector_loss_db = max(float(getattr(fiber, "connector_losses_db", 0.3)) for fiber in fibers)
            line_reserve_db = max(float(getattr(fiber, "line_reserve_db", 0.0)) for fiber in fibers)

            weighted_alpha = sum(
                max(float(fiber.length_km), 0.0) * max(float(fiber.get_attenuation_per_km()), 0.0)
                for fiber in fibers
            )
            alpha_db_per_km = weighted_alpha / line_length_km if line_length_km > 0 else 0.0

            sections_count = max(1, Fiber._excel_round(line_length_km / construction_length_km))
            splices_count = max(0, sections_count - 1)

            connector_total_db = 2.0 * connector_loss_db
            splice_total_db = splices_count * splice_loss_db
            line_total_db = (
                line_length_km * alpha_db_per_km
                + splice_total_db
                + connector_total_db
                + line_reserve_db
            )

            amplifier_span_km = 0
            if alpha_db_per_km > 0:
                amplifier_span_km = Fiber._excel_round(
                    ((energy_budget_db - line_reserve_db - connector_total_db) / alpha_db_per_km)
                    + (splice_loss_db / construction_length_km)
                )

            amplifier_sections_count = 0
            avg_amplifier_section_km = 0
            construction_per_amp_section = 0
            amplifier_section_loss_db = 0.0
            compare_state = "-"

            if amplifier_span_km > 0:
                amplifier_sections_count = max(1, int(math.ceil(line_length_km / float(amplifier_span_km))))
                avg_amplifier_section_km = max(
                    1, Fiber._excel_round(line_length_km / float(amplifier_sections_count))
                )
                construction_per_amp_section = max(
                    0,
                    Fiber._excel_round(avg_amplifier_section_km / construction_length_km),
                )
                amplifier_section_loss_db = (
                    avg_amplifier_section_km * alpha_db_per_km
                    + construction_per_amp_section * splice_loss_db
                    + connector_total_db
                    + line_reserve_db
                )
                compare_state = "ok" if amplifier_section_loss_db <= energy_budget_db else "no"

            fiber_types = sorted({str(fiber.fiber_type.value).replace(".", " ") for fiber in fibers})
            fiber_type_text = fiber_types[0] if len(fiber_types) == 1 else "/".join(fiber_types)

            disp = self.dispersion_results.get(channel.channel_id)
            if disp is not None:
                d_avg = disp.total_cd_ps_nm / line_length_km if line_length_km > 0 else 0.0
                disp_values = [
                    self._fmt_calc_value(d_avg, 2),
                    self._fmt_calc_value(disp.total_cd_ps_nm, 1),
                    self._fmt_calc_value(disp.cd_limit_ps_nm, 0),
                    "OK" if disp.cd_is_valid else "FAIL",
                    self._fmt_calc_value(disp.total_pmd_ps, 2),
                    self._fmt_calc_value(disp.pmd_limit_ps, 2),
                    "OK" if disp.pmd_is_valid else "FAIL",
                ]
            else:
                disp_values = ["-"] * 7

            # Расчет BER
            ber_values = ["-"] * 5
            if channel.channel_id in self.simulation_manager.ber_results:
                ber_result = self.simulation_manager.ber_results[channel.channel_id]
                ber_values = [
                    f"{ber_result.ber:.2e}",
                    self._fmt_calc_value(ber_result.q_factor, 3),
                    self._fmt_calc_value(ber_result.osnr_eff_db, 2),
                    self._fmt_calc_value(ber_result.dispersion_penalty_db, 3),
                    self._fmt_calc_value(ber_result.pmd_penalty_db, 3),
                ]

            values = prefix_values + [
                self._fmt_calc_value(energy_budget_db, 1),
                self._fmt_calc_value(line_length_km, 1),
                self._fmt_calc_value(construction_length_km, 1),
                self._fmt_calc_value(line_reserve_db, 1),
                self._fmt_calc_value(alpha_db_per_km, 3),
                self._fmt_calc_value(connector_loss_db, 3),
                self._fmt_calc_value(splice_loss_db, 3),
                str(sections_count),
                str(splices_count),
                self._fmt_calc_value(line_total_db, 1),
                self._fmt_calc_value(splice_total_db, 3),
                self._fmt_calc_value(connector_total_db, 3),
                self._fmt_calc_value(amplifier_section_loss_db, 1) if amplifier_sections_count else "-",
                compare_state,
                str(amplifier_span_km) if amplifier_span_km > 0 else "-",
                str(amplifier_sections_count) if amplifier_sections_count else "-",
                str(construction_per_amp_section) if amplifier_sections_count else "-",
                str(avg_amplifier_section_km) if amplifier_sections_count else "-",
                fiber_type_text,
                self._fmt_calc_value(float(channel.wavelength_nm), 3),
                self._fmt_calc_value(float(channel.bitrate_gbps), 1),
            ] + disp_values + ber_values

            compare_col_idx = 18
            cd_status_col = 29
            pmd_status_col = 32
            ber_col = 33
            for col_idx, value in enumerate(values):
                item = QTableWidgetItem(value)
                if col_idx == compare_col_idx and compare_state == "no":
                    item.setForeground(Qt.red)
                if col_idx == compare_col_idx and compare_state == "ok":
                    item.setForeground(Qt.darkGreen)
                if col_idx == cd_status_col and value == "FAIL":
                    item.setForeground(Qt.red)
                if col_idx == cd_status_col and value == "OK":
                    item.setForeground(Qt.darkGreen)
                if col_idx == pmd_status_col and value == "FAIL":
                    item.setForeground(Qt.red)
                if col_idx == pmd_status_col and value == "OK":
                    item.setForeground(Qt.darkGreen)
                if col_idx == ber_col and value != "-":
                    ber_val = float(value)
                    if ber_val < 1e-12:
                        item.setForeground(Qt.darkGreen)
                    elif ber_val < 1e-9:
                        item.setForeground(Qt.darkYellow)
                    else:
                        item.setForeground(Qt.red)
                self.excel_line_calc_table.setItem(row_idx, col_idx, item)

    @staticmethod
    def _safe_id_token(raw_id: str) -> str:
        token = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in (raw_id or "").strip())
        return token or "ID"

    def _quick_pair_ids(self) -> Tuple[str, str]:
        source_id = self.quick_node_a_id_edit.text().strip()
        target_id = self.quick_node_b_id_edit.text().strip()
        return source_id, target_id

    def _quick_pair_fiber_id(self, source_id: str, target_id: str) -> str:
        a_token, b_token = sorted([self._safe_id_token(source_id), self._safe_id_token(target_id)])
        return f"F_{a_token}_{b_token}"

    def _quick_pair_channel_id(self, source_id: str, target_id: str) -> str:
        a_token, b_token = sorted([self._safe_id_token(source_id), self._safe_id_token(target_id)])
        return f"CH_{a_token}_{b_token}"

    def place_quick_node_a(self):
        self._place_quick_terminal_node("A")

    def place_quick_node_b(self):
        self._place_quick_terminal_node("B")

    def _place_quick_terminal_node(self, side: str):
        is_a = side.upper() == "A"
        id_edit = self.quick_node_a_id_edit if is_a else self.quick_node_b_id_edit
        name_edit = self.quick_node_a_name_edit if is_a else self.quick_node_b_name_edit
        button = self.quick_place_node_a_btn if is_a else self.quick_place_node_b_btn
        other_id = self.quick_node_b_id_edit.text().strip() if is_a else self.quick_node_a_id_edit.text().strip()

        node_id = id_edit.text().strip()
        node_name = name_edit.text().strip() or node_id
        if not node_id:
            QMessageBox.warning(self, "Ошибка", f"Укажите ID точки {side}.")
            return
        if other_id and node_id == other_id:
            QMessageBox.warning(self, "Ошибка", "ID точек A и B должны различаться.")
            return

        button.setText("Кликните на карте...")
        button.setEnabled(False)

        def node_handler(lat: float, lon: float, _device_type: Optional[str]):
            existing = self.network.get_node(node_id)
            if existing:
                existing.name = node_name
                existing.node_type = NodeType.TERMINAL
                existing.latitude = float(lat)
                existing.longitude = float(lon)
            else:
                self.network.add_node(
                    Node(
                        node_id=node_id,
                        name=node_name,
                        node_type=NodeType.TERMINAL,
                        latitude=float(lat),
                        longitude=float(lon),
                    )
                )

            button.setText(f"Поставить точку {side}")
            button.setEnabled(True)
            self.quick_status_label.setText(
                f"Точка {side} сохранена: {node_id} ({lat:.5f}, {lon:.5f})"
            )
            self._clear_flow_state()
            self._clear_topology_marks()
            self.refresh_all()
            QMessageBox.information(self, "Готово", f"Точка {side} ({node_id}) размещена.")

        self.activate_place_mode("node", node_handler)

    def _validate_quick_pair_nodes(self) -> Optional[Tuple[Node, Node]]:
        source_id, target_id = self._quick_pair_ids()
        if not source_id or not target_id:
            QMessageBox.warning(self, "Ошибка", "Укажите ID точек A и B.")
            return None
        if source_id == target_id:
            QMessageBox.warning(self, "Ошибка", "Точки A и B должны различаться.")
            return None

        source = self.network.get_node(source_id)
        target = self.network.get_node(target_id)
        if not source or not target:
            QMessageBox.warning(
                self,
                "Ошибка",
                "Сначала поставьте обе точки на карте (кнопки 'Поставить точку A/B').",
            )
            return None
        if (
            source.latitude is None
            or source.longitude is None
            or target.latitude is None
            or target.longitude is None
        ):
            QMessageBox.warning(self, "Ошибка", "У точек A/B отсутствуют координаты.")
            return None
        return source, target

    def _cleanup_quick_pair_artifacts(
        self,
        source_id: str,
        target_id: str,
        *,
        remove_channel: bool,
    ):
        fiber_id = self._quick_pair_fiber_id(source_id, target_id)
        channel_id = self._quick_pair_channel_id(source_id, target_id)
        inline_prefix = f"EDFA_{fiber_id}_"
        segment_prefix = f"{fiber_id}_S"

        if remove_channel:
            channels_to_remove: List[str] = []
            for channel in self.network.channels.values():
                if channel.channel_id == channel_id:
                    channels_to_remove.append(channel.channel_id)
                    continue
                if channel.path and len(channel.path) >= 2:
                    src, dst = channel.path[0], channel.path[-1]
                    if {src, dst} == {source_id, target_id}:
                        channels_to_remove.append(channel.channel_id)
            for cid in channels_to_remove:
                self.network.channels.pop(cid, None)
                self.power_budget_results.pop(cid, None)
                if self.selected_channel_id == cid:
                    self.selected_channel_id = None
                    self.selected_channel_edges.clear()

        inline_node_ids = {
            node_id for node_id in self.network.nodes.keys() if node_id.startswith(inline_prefix)
        }

        fibers_to_remove: List[str] = []
        for fid, fiber in self.network.fibers.items():
            is_pair_fiber = {fiber.source_node_id, fiber.target_node_id} == {source_id, target_id}
            if (
                fid == fiber_id
                or fid.startswith(segment_prefix)
                or is_pair_fiber
                or fiber.source_node_id in inline_node_ids
                or fiber.target_node_id in inline_node_ids
            ):
                fibers_to_remove.append(fid)
        for fid in fibers_to_remove:
            self.network.fibers.pop(fid, None)

        equipment_to_remove: List[str] = []
        for eq_id, eq in self.network.equipment.items():
            if (
                eq.node_id in inline_node_ids
                or eq_id.startswith(f"EQ_{inline_prefix}")
                or f"_{channel_id}_" in eq_id
            ):
                equipment_to_remove.append(eq_id)
        for eq_id in equipment_to_remove:
            self.network.equipment.pop(eq_id, None)

        for node_id in inline_node_ids:
            self.network.nodes.pop(node_id, None)

        for node in self.network.nodes.values():
            node.equipment = [eq_id for eq_id in node.equipment if eq_id in self.network.equipment]

    def _quick_build_pair_fiber(self, *, cleanup: bool, silent: bool) -> Optional[Fiber]:
        nodes = self._validate_quick_pair_nodes()
        if not nodes:
            return None
        source, target = nodes
        source_id, target_id = source.node_id, target.node_id
        fiber_id = self._quick_pair_fiber_id(source_id, target_id)

        if cleanup:
            self._cleanup_quick_pair_artifacts(source_id, target_id, remove_channel=False)

        length = TopologyManager.calculate_great_circle_distance(
            float(source.latitude),
            float(source.longitude),
            float(target.latitude),
            float(target.longitude),
        )
        alpha_db_per_km = float(self.quick_alpha_spin.value())
        attenuation_override = alpha_db_per_km if alpha_db_per_km > 0 else None

        fiber = Fiber(
            fiber_id=fiber_id,
            source_node_id=source_id,
            target_node_id=target_id,
            length_km=length,
            fiber_type=FiberType(self.quick_fiber_type_combo.currentText()),
            attenuation_db_per_km=attenuation_override,
            splice_interval_km=float(self.quick_coil_length_spin.value()),
            splice_losses_db=float(self.quick_splice_loss_spin.value()),
            connector_losses_db=float(self.quick_connector_loss_spin.value()),
            line_reserve_db=float(self.quick_line_reserve_spin.value()),
        )
        self.network.add_fiber(fiber)
        self._rebuild_channels_after_topology_change()
        self.power_budget_results.clear()
        self._clear_flow_state()
        self.refresh_all()

        self.quick_status_label.setText(f"Линия {fiber_id} создана. Длина: {length:.2f} км.")
        if not silent:
            QMessageBox.information(
                self,
                "Линия создана",
                f"ID: {fiber_id}\nОт: {source_id}\nДо: {target_id}\nДлина: {length:.2f} км",
            )
        return fiber

    def quick_build_fiber_between_points(self):
        self._quick_build_pair_fiber(cleanup=True, silent=False)

    def _quick_trace_pair_fiber(self, *, silent: bool) -> Tuple[bool, str]:
        source_id, target_id = self._quick_pair_ids()
        fiber_id = self._quick_pair_fiber_id(source_id, target_id)
        if fiber_id not in self.network.fibers:
            fiber = self._quick_build_pair_fiber(cleanup=True, silent=True)
            if fiber is None:
                return False, "нет линии"
            fiber_id = fiber.fiber_id

        use_roads = self.quick_trace_mode_combo.currentData() == "roads"
        traced = self.topology_manager.trace_fiber(fiber_id, use_roads=use_roads)
        mode_text = "по дорогам (OSRM)" if use_roads else "прямая линия"
        if not traced and use_roads:
            traced = self.topology_manager.trace_fiber(fiber_id, use_roads=False)
            if traced:
                mode_text = "прямая линия (fallback)"

        if traced:
            self.power_budget_results.clear()
            self._clear_flow_state()
            self.refresh_all()
            self.quick_status_label.setText(f"Линия {fiber_id} трассирована: {mode_text}.")
            if not silent:
                QMessageBox.information(self, "Трассировка", f"Линия {fiber_id} трассирована ({mode_text}).")
            return True, mode_text

        self.quick_status_label.setText(f"Трассировка линии {fiber_id} не выполнена.")
        if not silent:
            QMessageBox.warning(self, "Ошибка", f"Не удалось трассировать линию {fiber_id}.")
        return False, mode_text

    def quick_trace_pair_fiber(self):
        self._quick_trace_pair_fiber(silent=False)

    def _quick_create_or_update_pair_channel(self, *, silent: bool) -> Optional[Channel]:
        nodes = self._validate_quick_pair_nodes()
        if not nodes:
            return None
        source, target = nodes
        path = self._find_shortest_path(source.node_id, target.node_id)
        if not path:
            if not silent:
                QMessageBox.warning(self, "Нет маршрута", "Между точками A и B нет оптического пути.")
            self.quick_status_label.setText("Нет маршрута между точками A и B.")
            return None

        channel_id = self._quick_pair_channel_id(source.node_id, target.node_id)
        wavelength_nm = float(self.quick_wavelength_spin.value())
        bitrate_gbps = self._get_bitrate_widget_value(self.quick_bitrate_spin)
        energy_budget_db = float(self.quick_energy_budget_spin.value())
        tx_power_dbm = 0.0
        rx_sensitivity_dbm = -energy_budget_db
        frequency_thz = FrequencyPlan.wavelength_to_frequency(wavelength_nm)

        channel = self.network.channels.get(channel_id)
        if channel is None:
            channel = Channel(
                channel_id=channel_id,
                wavelength_nm=wavelength_nm,
                frequency_thz=frequency_thz,
                tx_power_dbm=tx_power_dbm,
                rx_sensitivity_dbm=rx_sensitivity_dbm,
                bitrate_gbps=bitrate_gbps,
                energy_budget_db=energy_budget_db,
                path=path,
            )
            self.network.add_channel(channel)
        else:
            channel.wavelength_nm = wavelength_nm
            channel.frequency_thz = frequency_thz
            channel.tx_power_dbm = tx_power_dbm
            channel.rx_sensitivity_dbm = rx_sensitivity_dbm
            channel.bitrate_gbps = bitrate_gbps
            channel.energy_budget_db = energy_budget_db
            channel.path = path

        self.selected_channel_id = channel.channel_id
        if channel.path and len(channel.path) >= 2:
            self.selected_channel_edges = {
                self._edge_key(a, b) for a, b in zip(channel.path[:-1], channel.path[1:])
            }
        if hasattr(self, "channels_table"):
            self.refresh_dwdm_tables()
        return channel

    def run_quick_two_point_pipeline(self):
        nodes = self._validate_quick_pair_nodes()
        if not nodes:
            return
        source, target = nodes
        source_id, target_id = source.node_id, target.node_id
        channel_id = self._quick_pair_channel_id(source_id, target_id)

        self._cleanup_quick_pair_artifacts(source_id, target_id, remove_channel=True)

        fiber = self._quick_build_pair_fiber(cleanup=False, silent=True)
        if fiber is None:
            return
        traced, trace_mode = self._quick_trace_pair_fiber(silent=True)
        if not traced:
            QMessageBox.warning(self, "Ошибка", "Не удалось выполнить трассировку линии.")
            return

        channel = self._quick_create_or_update_pair_channel(silent=True)
        if channel is None:
            return

        placer = AmplifierPlacer(self.network)
        inline_added = placer.split_fibers_and_update_channel_path(channel.channel_id)
        node_added = placer.place_amplifiers_for_channel(channel.channel_id)

        fibers = self.network.get_path_fibers(channel.path or [])
        calc_status = "FAIL"
        calc_text = "-"
        if fibers:
            line_length_km = sum(max(float(f.length_km), 0.0) for f in fibers)
            construction_length_km = max(
                max(float(getattr(f, "splice_interval_km", 25.0)), 0.001) for f in fibers
            )
            splice_loss_db = max(float(getattr(f, "splice_losses_db", 0.02)) for f in fibers)
            connector_loss_db = max(float(getattr(f, "connector_losses_db", 0.3)) for f in fibers)
            line_reserve_db = max(float(getattr(f, "line_reserve_db", 0.0)) for f in fibers)
            weighted_alpha = sum(
                max(float(f.length_km), 0.0) * max(float(f.get_attenuation_per_km()), 0.0)
                for f in fibers
            )
            alpha_db_per_km = weighted_alpha / line_length_km if line_length_km > 0 else 0.0
            energy_budget_db = float(channel.get_energy_budget_db())
            connector_total_db = 2.0 * connector_loss_db

            amplifier_span_km = 0
            if alpha_db_per_km > 0:
                amplifier_span_km = Fiber._excel_round(
                    ((energy_budget_db - line_reserve_db - connector_total_db) / alpha_db_per_km)
                    + (splice_loss_db / construction_length_km)
                )

            if amplifier_span_km > 0 and line_length_km > 0:
                amplifier_sections_count = max(1, int(math.ceil(line_length_km / float(amplifier_span_km))))
                avg_amplifier_section_km = max(
                    1, Fiber._excel_round(line_length_km / float(amplifier_sections_count))
                )
                construction_per_amp_section = max(
                    0, Fiber._excel_round(avg_amplifier_section_km / construction_length_km)
                )
                amplifier_section_loss_db = (
                    avg_amplifier_section_km * alpha_db_per_km
                    + construction_per_amp_section * splice_loss_db
                    + connector_total_db
                    + line_reserve_db
                )
                calc_status = "OK" if amplifier_section_loss_db <= energy_budget_db else "FAIL"
                calc_text = (
                    f"N={amplifier_section_loss_db:.2f} дБ, "
                    f"B={energy_budget_db:.2f} дБ"
                )

        self.power_budget_results.clear()

        self._clear_flow_state()
        self.refresh_all()

        self.quick_status_label.setText(
            f"Сценарий выполнен: {source_id} -> {target_id} | трасса: {trace_mode} | статус методики: {calc_status}"
        )
        QMessageBox.information(
            self,
            "Сценарий 2 точки",
            (
                f"Линия: {fiber.fiber_id}\n"
                f"Канал: {channel.channel_id}\n"
                f"Режим трассировки: {trace_mode}\n"
                f"Добавлено линейных EDFA-узлов: {inline_added}\n"
                f"Добавлено EDFA в узлах: {node_added}\n"
                f"Проверка по методике (N<=B): {calc_status}\n"
                f"{calc_text}"
            ),
        )

    def clear_quick_two_point_artifacts(self):
        source_id, target_id = self._quick_pair_ids()
        if not source_id or not target_id or source_id == target_id:
            QMessageBox.warning(self, "Ошибка", "Проверьте ID точек A/B.")
            return
        self._cleanup_quick_pair_artifacts(source_id, target_id, remove_channel=True)
        self._rebuild_channels_after_topology_change()
        self.power_budget_results.clear()
        self._clear_flow_state()
        self.refresh_all()
        self.quick_status_label.setText("Сценарные линия/канал/EDFA очищены.")
        QMessageBox.information(self, "Очищено", "Сценарий для пары точек очищен.")

    # ---------- Topology actions ----------

    def on_place_node(self):
        node_id = self.node_id_edit.text().strip()
        node_name = self.node_name_edit.text().strip()
        territory = self.node_territory_edit.text().strip()
        organization = self.node_org_edit.text().strip()

        if not node_id or not node_name:
            QMessageBox.warning(self, "Ошибка", "Укажите ID и название узла.")
            return
        if node_id in self.network.nodes:
            QMessageBox.warning(self, "Ошибка", f"Узел с ID '{node_id}' уже существует.")
            return

        self.place_node_btn.setText("Кликните на карте...")
        self.place_node_btn.setEnabled(False)

        def node_handler(lat: float, lon: float, _device_type: Optional[str]):
            node = Node(
                node_id=node_id,
                name=node_name,
                node_type=NodeType(self.node_type_combo.currentText()),
                latitude=lat,
                longitude=lon,
                territory=territory,
                organization=organization,
            )
            self.network.add_node(node)

            self.node_id_edit.clear()
            self.node_name_edit.clear()
            self.node_territory_edit.clear()
            self.node_org_edit.clear()
            self.place_node_btn.setText("Разместить узел на карте")
            self.place_node_btn.setEnabled(True)

            self._clear_flow_state()
            self.refresh_all()
            QMessageBox.information(self, "Успех", f"Узел '{node_name}' добавлен.")

        self.activate_place_mode("node", node_handler)

    def on_connect_nodes(self):
        if len(self.network.nodes) < 2:
            QMessageBox.warning(self, "Ошибка", "Нужно минимум 2 узла.")
            return

        fiber_id = self.fiber_id_edit.text().strip()
        if not fiber_id:
            QMessageBox.warning(self, "Ошибка", "Укажите ID волокна.")
            return
        if fiber_id in self.network.fibers:
            QMessageBox.warning(self, "Ошибка", f"Волокно с ID '{fiber_id}' уже существует.")
            return

        src_id = self.fiber_source_combo.currentText().strip()
        dst_id = self.fiber_target_combo.currentText().strip()
        if src_id == dst_id:
            QMessageBox.warning(self, "Ошибка", "Источник и назначение должны быть разными.")
            return

        src = self.network.get_node(src_id)
        dst = self.network.get_node(dst_id)
        if not src or not dst:
            QMessageBox.warning(self, "Ошибка", "Не удалось найти выбранные узлы.")
            return
        if src.latitude is None or src.longitude is None or dst.latitude is None or dst.longitude is None:
            QMessageBox.warning(self, "Ошибка", "У выбранных узлов отсутствуют координаты.")
            return

        length = TopologyManager.calculate_great_circle_distance(
            src.latitude, src.longitude, dst.latitude, dst.longitude
        )
        fiber = Fiber(
            fiber_id=fiber_id,
            source_node_id=src_id,
            target_node_id=dst_id,
            length_km=length,
            fiber_type=FiberType(self.fiber_type_combo.currentText()),
            splice_interval_km=float(self.fiber_coil_length_spin.value()),
            splice_losses_db=float(self.fiber_splice_loss_spin.value()),
            connector_losses_db=float(self.fiber_connector_loss_spin.value()),
            line_reserve_db=float(self.fiber_line_reserve_spin.value()),
        )
        self.network.add_fiber(fiber)
        self.fiber_id_edit.clear()
        self._rebuild_channels_after_topology_change()
        self._clear_flow_state()
        self.refresh_all()

        QMessageBox.information(
            self,
            "Успех",
            f"Волокно '{fiber_id}' создано\n"
            f"От: {src.name}\n"
            f"До: {dst.name}\n"
            f"Длина: {length:.2f} км",
        )

    def build_minimum_spanning_tree(self):
        if len(self.network.nodes) < 2:
            QMessageBox.warning(self, "Ошибка", "Нужно минимум 2 узла.")
            return
        fibers = self.topology_manager.build_minimum_spanning_tree()
        if not fibers:
            QMessageBox.warning(self, "Информация", "МОД не построено (проверьте координаты узлов).")
            return
        self._clear_flow_state()
        self._clear_topology_marks()
        self._rebuild_channels_after_topology_change()
        self.refresh_all()
        QMessageBox.information(self, "МОД построено", f"Добавлено волокон: {len(fibers)}")

    def calculate_reliability(self):
        if len(self.network.nodes) < 2:
            QMessageBox.warning(self, "Ошибка", "Нужно минимум 2 узла.")
            return
        reliability, edge_connectivity = self.topology_analyzer.compute_structural_reliability()
        QMessageBox.information(
            self,
            "Надежность сети",
            f"Структурная надежность R = {reliability:.4f}\n"
            f"Реберная связность = {edge_connectivity}\n\n"
            f"Узлов: {len(self.network.nodes)}\n"
            f"Волокон: {len(self.network.fibers)}",
        )

    def build_auto_line_grid(self):
        if len(self.network.nodes) < 2:
            QMessageBox.warning(self, "Ошибка", "Нужно минимум 2 узла.")
            return
        method = self.grid_method_combo.currentData()
        target_connectivity = int(self.grid_connectivity_spin.value())
        max_edges = int(self.grid_max_edges_spin.value()) or None

        try:
            fibers = self.topology_manager.build_line_grid(
                method=method,
                target_connectivity=target_connectivity,
                max_edges=max_edges,
                replace_existing=True,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Автопостроение не выполнено: {exc}")
            return

        self._clear_flow_state()
        self._clear_topology_marks()
        self._rebuild_channels_after_topology_change()
        self.refresh_all()
        QMessageBox.information(
            self,
            "Готово",
            f"Автосетка построена.\nМетод: {self.grid_method_combo.currentText()}\n"
            f"Волокон: {len(fibers)}",
        )

    def trace_selected_fiber(self):
        fiber_id = self._selected_fiber_id()
        if not fiber_id:
            QMessageBox.warning(self, "Ошибка", "Выберите волокно в таблице.")
            return
        use_roads = self.trace_mode_combo.currentData() == "roads"
        ok = self.topology_manager.trace_fiber(fiber_id, use_roads=use_roads)
        if not ok:
            QMessageBox.warning(self, "Ошибка", "Не удалось трассировать выбранное волокно.")
            return
        self.power_budget_results.clear()
        self._clear_flow_state()
        self.refresh_all()
        QMessageBox.information(self, "Готово", f"Волокно '{fiber_id}' трассировано.")

    def trace_all_fibers(self):
        if not self.network.fibers:
            QMessageBox.warning(self, "Ошибка", "Нет волокон для трассировки.")
            return
        use_roads = self.trace_mode_combo.currentData() == "roads"
        ok, total = self.topology_manager.trace_all_fibers(use_roads=use_roads)
        self.power_budget_results.clear()
        self._clear_flow_state()
        self.refresh_all()
        QMessageBox.information(
            self,
            "Готово",
            f"Трассировано линий: {ok}/{total}\n"
            f"Режим: {self.trace_mode_combo.currentText()}",
        )

    def reset_all_traces(self):
        if not self.network.fibers:
            return
        ok, total = self.topology_manager.trace_all_fibers(use_roads=False)
        self.power_budget_results.clear()
        self._clear_flow_state()
        self.refresh_all()
        QMessageBox.information(self, "Готово", f"Сброшено трасс: {ok}/{total}")

    def find_trunk_network(self):
        if len(self.network.fibers) < 1:
            QMessageBox.warning(self, "Ошибка", "Нет волокон для анализа магистрали.")
            return
        percentile = float(self.trunk_percentile_spin.value()) / 100.0
        trunk_ids, score_map = self.topology_manager.find_trunk_network(
            min_regions=2,
            percentile=percentile,
        )
        self.highlight_trunk_fibers = set(trunk_ids)
        self.trunk_scores = score_map
        self.refresh_all()

        if not trunk_ids:
            QMessageBox.information(
                self,
                "Информация",
                "Магистральные линии не выделены.\n"
                "Проверьте, что узлы имеют территориальную принадлежность минимум двух регионов.",
            )
            return

        preview = ", ".join(trunk_ids[:10])
        QMessageBox.information(
            self,
            "Магистраль найдена",
            f"Выделено магистральных линий: {len(trunk_ids)}\n"
            f"Линии: {preview}",
        )

    def clear_trunk_network(self):
        self.topology_manager.clear_trunk_marks()
        self.highlight_trunk_fibers.clear()
        self.trunk_scores.clear()
        self.refresh_all()

    # ---------- Flows actions ----------

    def generate_directions(self):
        if len(self.network.nodes) < 2:
            QMessageBox.warning(self, "Ошибка", "Нужно минимум 2 узла.")
            return
        mode = self.direction_mode_combo.currentData()
        capacity_unit = self.capacity_unit_combo.currentText()
        capacity_value = float(self.capacity_value_spin.value())
        bidirectional = bool(self.bidirectional_check.isChecked())

        try:
            count = self.traffic_manager.generate_directions(
                mode=mode,
                capacity_value=capacity_value,
                capacity_unit=capacity_unit,
                bidirectional=bidirectional,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Генерация ИН завершилась ошибкой: {exc}")
            return

        self.refresh_traffic_tables()
        QMessageBox.information(self, "Готово", f"Сгенерировано информационных направлений: {count}")

    def compute_flow_structure(self):
        if not self.traffic_manager.directions:
            QMessageBox.warning(self, "Ошибка", "Сначала сгенерируйте ИН.")
            return
        if len(self.network.fibers) < 1:
            QMessageBox.warning(self, "Ошибка", "Для расчета потоков нужна сетка линий.")
            return

        routes = int(self.routes_per_direction_spin.value())
        criterion = self.route_criterion_combo.currentData()
        distribution = self.load_distribution_combo.currentData()

        try:
            self.traffic_manager.compute_flows(
                routes_per_direction=routes,
                criterion=criterion,
                distribution=distribution,
            )
        except Exception as exc:
            QMessageBox.critical(self, "Ошибка", f"Расчет потоковой структуры не выполнен: {exc}")
            return

        self.refresh_traffic_tables()
        self.update_map()
        QMessageBox.information(
            self,
            "Готово",
            f"Потоковая структура рассчитана.\nМаршрутов на ИН: {routes}",
        )

    def find_vulnerable_elements(self):
        if not self.traffic_manager.fiber_loads and not self.traffic_manager.node_loads:
            QMessageBox.warning(
                self,
                "Нет данных",
                "Сначала выполните поиск потоковой структуры.",
            )
            return

        loads, top_fibers, node_loads, top_nodes = self.traffic_manager.find_vulnerable_elements_detailed()
        self.highlight_critical_fibers = {fl.fiber_id for fl in loads if fl.is_critical}
        self.highlight_heavy_fibers = {fl.fiber_id for fl in loads if fl.load_ratio >= 0.7}
        self.highlight_critical_nodes = {nl.node_id for nl in node_loads if nl.is_critical}
        self.highlight_heavy_nodes = {nl.node_id for nl in node_loads if nl.load_ratio >= 0.7}

        self.refresh_traffic_tables()
        self.update_map()

        msg_lines = [
            f"Критичных линий: {len(self.highlight_critical_fibers)}",
            f"Критичных узлов: {len(self.highlight_critical_nodes)}",
        ]
        if top_fibers:
            msg_lines.append("Топ линий: " + ", ".join(top_fibers[:10]))
        if top_nodes:
            msg_lines.append("Топ узлов: " + ", ".join(top_nodes[:10]))
        QMessageBox.information(self, "Уязвимые элементы", "\n".join(msg_lines))

    # ---------- Tables & stats ----------

    def refresh_tables(self):
        self.nodes_table.setRowCount(len(self.network.nodes))
        for row, (node_id, node) in enumerate(self.network.nodes.items()):
            self.nodes_table.setItem(row, 0, QTableWidgetItem(node_id))
            self.nodes_table.setItem(row, 1, QTableWidgetItem(node.name))
            self.nodes_table.setItem(row, 2, QTableWidgetItem(node.node_type.value))
            self.nodes_table.setItem(row, 3, QTableWidgetItem(node.territory or ""))
            self.nodes_table.setItem(row, 4, QTableWidgetItem(node.organization or ""))
            self.nodes_table.setItem(
                row,
                5,
                QTableWidgetItem(f"{node.latitude:.6f}" if node.latitude is not None else ""),
            )
            self.nodes_table.setItem(
                row,
                6,
                QTableWidgetItem(f"{node.longitude:.6f}" if node.longitude is not None else ""),
            )

        self.fibers_table.setRowCount(len(self.network.fibers))
        for row, (fiber_id, fiber) in enumerate(self.network.fibers.items()):
            route_state = "маршрут" if fiber.route_points else "прямая"
            attenuation = fiber.get_attenuation_per_km()
            self.fibers_table.setItem(row, 0, QTableWidgetItem(fiber_id))
            self.fibers_table.setItem(row, 1, QTableWidgetItem(fiber.source_node_id))
            self.fibers_table.setItem(row, 2, QTableWidgetItem(fiber.target_node_id))
            self.fibers_table.setItem(row, 3, QTableWidgetItem(f"{fiber.length_km:.2f}"))
            self.fibers_table.setItem(row, 4, QTableWidgetItem(fiber.fiber_type.value))
            self.fibers_table.setItem(row, 5, QTableWidgetItem(f"{attenuation:.3f}"))
            self.fibers_table.setItem(row, 6, QTableWidgetItem(f"{fiber.splice_interval_km:.2f}"))
            self.fibers_table.setItem(row, 7, QTableWidgetItem(route_state))

        if hasattr(self, "fiber_events_table"):
            # Тяжелую таблицу событий не пересчитываем на каждом refresh,
            # если сеть пустая или уже посчитана и топология не менялась.
            if not self.network.fibers:
                self.fiber_events_table.setRowCount(0)
                self._fiber_events_filled = False
                self._fiber_events_signature = None
                return
            signature = tuple(
                (
                    fiber.fiber_id,
                    float(fiber.length_km),
                    float(fiber.splice_interval_km),
                    float(fiber.splice_losses_db),
                    float(fiber.connector_losses_db),
                    float(fiber.line_reserve_db),
                )
                for fiber in self.network.fibers.values()
            )
            if (
                getattr(self, "_fiber_events_filled", False)
                and signature == getattr(self, "_fiber_events_signature", None)
            ):
                return

            rows: List[Tuple[str, str, str, str, str]] = []
            max_splice_rows_per_fiber = 2000
            for fiber_id, fiber in self.network.fibers.items():
                length_km = max(float(fiber.length_km), 0.0)
                rows.append(
                    (
                        fiber_id,
                        "Коннектор",
                        "0.00",
                        f"{fiber.connector_losses_db:.3f}",
                        f"Узел {fiber.source_node_id}",
                    )
                )
                rows.append(
                    (
                        fiber_id,
                        "Коннектор",
                        f"{length_km:.2f}",
                        f"{fiber.connector_losses_db:.3f}",
                        f"Узел {fiber.target_node_id}",
                    )
                )

                splice_count = fiber.calculate_splice_count()
                display_splices = min(splice_count, max_splice_rows_per_fiber)
                interval_km = max(float(fiber.splice_interval_km), 0.001)
                for idx in range(display_splices):
                    position_km = min((idx + 1) * interval_km, max(length_km - 1e-6, 0.0))
                    rows.append(
                        (
                            fiber_id,
                            "Сварка",
                            f"{position_km:.2f}",
                            f"{fiber.splice_losses_db:.3f}",
                            f"Стык {idx + 1}",
                        )
                    )
                if splice_count > display_splices:
                    rows.append(
                        (
                            fiber_id,
                            "Сварка",
                            "...",
                            f"{fiber.splice_losses_db:.3f}",
                            f"Показано {display_splices} из {splice_count}",
                        )
                    )

            self.fiber_events_table.setRowCount(len(rows))
            for row_idx, (fiber_id, event_type, position, loss, note) in enumerate(rows):
                self.fiber_events_table.setItem(row_idx, 0, QTableWidgetItem(fiber_id))
                self.fiber_events_table.setItem(row_idx, 1, QTableWidgetItem(event_type))
                self.fiber_events_table.setItem(row_idx, 2, QTableWidgetItem(position))
                self.fiber_events_table.setItem(row_idx, 3, QTableWidgetItem(loss))
                self.fiber_events_table.setItem(row_idx, 4, QTableWidgetItem(note))
            self._fiber_events_filled = True
            self._fiber_events_signature = signature

    def refresh_traffic_tables(self):
        if not (
            hasattr(self, "directions_table")
            and hasattr(self, "flow_loads_table")
            and hasattr(self, "node_loads_table")
        ):
            return

        directions = list(self.traffic_manager.directions.values())
        self.directions_table.setRowCount(len(directions))
        for row, d in enumerate(directions):
            routes_str = "; ".join("->".join(path) for path in d.routes) if d.routes else "-"
            status = "OK" if d.is_connected else "Нет маршрута"
            self.directions_table.setItem(row, 0, QTableWidgetItem(d.direction_id))
            self.directions_table.setItem(row, 1, QTableWidgetItem(d.source_node_id))
            self.directions_table.setItem(row, 2, QTableWidgetItem(d.target_node_id))
            self.directions_table.setItem(row, 3, QTableWidgetItem(f"{d.capacity_gbps:.4f}"))
            self.directions_table.setItem(row, 4, QTableWidgetItem(routes_str))
            self.directions_table.setItem(row, 5, QTableWidgetItem(status))

        fiber_loads = sorted(
            self.traffic_manager.fiber_loads.values(),
            key=lambda fl: fl.total_load_gbps,
            reverse=True,
        )
        self.flow_loads_table.setRowCount(len(fiber_loads))
        for row, fl in enumerate(fiber_loads):
            critical = "Критичная" if fl.is_critical else ""
            self.flow_loads_table.setItem(row, 0, QTableWidgetItem(fl.fiber_id))
            self.flow_loads_table.setItem(row, 1, QTableWidgetItem(f"{fl.total_load_gbps:.4f}"))
            self.flow_loads_table.setItem(row, 2, QTableWidgetItem(str(len(fl.directions))))
            self.flow_loads_table.setItem(row, 3, QTableWidgetItem(f"{fl.load_ratio:.2f}"))
            item = QTableWidgetItem(critical)
            if fl.is_critical:
                item.setForeground(Qt.red)
            self.flow_loads_table.setItem(row, 4, item)

        node_loads = sorted(
            self.traffic_manager.node_loads.values(),
            key=lambda nl: nl.transit_count,
            reverse=True,
        )
        self.node_loads_table.setRowCount(len(node_loads))
        for row, nl in enumerate(node_loads):
            critical = "Критичный" if nl.is_critical else ""
            self.node_loads_table.setItem(row, 0, QTableWidgetItem(nl.node_id))
            self.node_loads_table.setItem(row, 1, QTableWidgetItem(str(nl.transit_count)))
            self.node_loads_table.setItem(row, 2, QTableWidgetItem(f"{nl.load_ratio:.2f}"))
            item = QTableWidgetItem(critical)
            if nl.is_critical:
                item.setForeground(Qt.red)
            self.node_loads_table.setItem(row, 3, item)

    def update_stats(self):
        num_nodes = len(self.network.nodes)
        num_fibers = len(self.network.fibers)
        num_channels = len(self.network.channels)
        num_edfa = self._edfa_count()
        self.stats_label.setText(
            f"Узлов: {num_nodes}\n"
            f"Волокон: {num_fibers}\n"
            f"Каналов: {num_channels}\n"
            f"EDFA: {num_edfa}"
        )

    # ---------- Selection handlers ----------

    def on_node_selection_changed(self):
        _ = self.nodes_table.selectedItems()

    def on_fiber_selection_changed(self):
        _ = self.fibers_table.selectedItems()

    # ---------- CRUD ----------

    def edit_selected_node(self):
        selected = self.nodes_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите узел для редактирования.")
            return
        row = self.nodes_table.row(selected[0])
        item = self.nodes_table.item(row, 0)
        if not item:
            return
        node_id = item.text()
        node = self.network.get_node(node_id)
        if not node:
            return

        dialog = NodeEditDialog(
            self,
            {
                "node_id": node.node_id,
                "name": node.name,
                "node_type": node.node_type.value,
                "territory": node.territory,
                "organization": node.organization,
                "latitude": node.latitude or 0.0,
                "longitude": node.longitude or 0.0,
            },
        )
        if dialog.exec_() != QDialog.Accepted:
            return
        data = dialog.get_data()
        node.name = data["name"]
        node.node_type = NodeType(data["node_type"])
        node.territory = data["territory"]
        node.organization = data["organization"]
        node.latitude = data["latitude"]
        node.longitude = data["longitude"]

        self._clear_flow_state()
        self.refresh_all()
        QMessageBox.information(self, "Успех", f"Узел '{node_id}' обновлен.")

    def edit_selected_fiber(self):
        selected = self.fibers_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите волокно для редактирования.")
            return
        row = self.fibers_table.row(selected[0])
        item = self.fibers_table.item(row, 0)
        if not item:
            return
        fiber_id = item.text()
        fiber = self.network.fibers.get(fiber_id)
        if not fiber:
            return

        dialog = FiberEditDialog(
            self,
            {
                "fiber_id": fiber.fiber_id,
                "source_node_id": fiber.source_node_id,
                "target_node_id": fiber.target_node_id,
                "fiber_type": fiber.fiber_type.value,
                "length_km": fiber.length_km,
                "coil_length_km": fiber.splice_interval_km,
                "splice_losses_db": fiber.splice_losses_db,
                "connector_losses_db": fiber.connector_losses_db,
                "line_reserve_db": fiber.line_reserve_db,
            },
            self.network,
        )
        if dialog.exec_() != QDialog.Accepted:
            return

        data = dialog.get_data()
        fiber.source_node_id = data["source_node_id"]
        fiber.target_node_id = data["target_node_id"]
        fiber.fiber_type = FiberType(data["fiber_type"])
        fiber.length_km = data["length_km"]
        fiber.splice_interval_km = data["coil_length_km"]
        fiber.splice_losses_db = data["splice_losses_db"]
        fiber.connector_losses_db = data["connector_losses_db"]
        fiber.line_reserve_db = data["line_reserve_db"]

        self._rebuild_channels_after_topology_change()
        self._clear_flow_state()
        self.refresh_all()
        QMessageBox.information(self, "Успех", f"Волокно '{fiber_id}' обновлено.")

    def delete_selected_node(self):
        selected = self.nodes_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите узел для удаления.")
            return
        row = self.nodes_table.row(selected[0])
        item = self.nodes_table.item(row, 0)
        if not item:
            return
        node_id = item.text()

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить узел '{node_id}'?\nВсе связанные волокна также будут удалены.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if node_id in self.network.nodes:
            del self.network.nodes[node_id]
            to_remove = [
                fid
                for fid, f in self.network.fibers.items()
                if f.source_node_id == node_id or f.target_node_id == node_id
            ]
            for fid in to_remove:
                del self.network.fibers[fid]
            eq_remove = [
                eq_id
                for eq_id, eq in self.network.equipment.items()
                if eq.node_id == node_id
            ]
            for eq_id in eq_remove:
                del self.network.equipment[eq_id]

        self._rebuild_channels_after_topology_change()
        self._clear_flow_state()
        self._clear_topology_marks()
        self.refresh_all()
        QMessageBox.information(self, "Успех", f"Узел '{node_id}' удален.")

    def delete_selected_fiber(self):
        selected = self.fibers_table.selectedItems()
        if not selected:
            QMessageBox.warning(self, "Ошибка", "Выберите волокно для удаления.")
            return
        row = self.fibers_table.row(selected[0])
        item = self.fibers_table.item(row, 0)
        if not item:
            return
        fiber_id = item.text()

        reply = QMessageBox.question(
            self,
            "Подтверждение",
            f"Удалить волокно '{fiber_id}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if fiber_id in self.network.fibers:
            del self.network.fibers[fiber_id]
        self._rebuild_channels_after_topology_change()
        self._clear_flow_state()
        self._clear_topology_marks()
        self.refresh_all()
        QMessageBox.information(self, "Успех", f"Волокно '{fiber_id}' удалено.")

    # ---------- Map rendering ----------

    def _get_icon_urls(self) -> Dict[str, Optional[str]]:
        urls: Dict[str, Optional[str]] = {}
        for node_type in ["terminal", "oadm", "edfa", "regen", "transit"]:
            icon_path = os.path.join(self.assets_path, f"{node_type}.png")
            if os.path.exists(icon_path):
                urls[node_type] = f"file:///{icon_path.replace(chr(92), '/')}"
            else:
                urls[node_type] = None
        return urls

    def _fiber_style(self, fiber: Fiber) -> Tuple[str, int, float]:
        edge_key = self._edge_key(fiber.source_node_id, fiber.target_node_id)
        if edge_key in self.selected_channel_edges:
            return "#1b5e20", 6, 0.95
        fiber_id = fiber.fiber_id
        is_trunk = fiber.is_trunk
        if fiber_id in self.highlight_critical_fibers:
            return "#d32f2f", 5, 0.95
        if is_trunk or fiber_id in self.highlight_trunk_fibers:
            return "#ef6c00", 4, 0.90
        if fiber_id in self.highlight_heavy_fibers:
            return "#f9a825", 4, 0.85
        return "#1565c0", 3, 0.75

    def update_map(self):
        nodes: List[dict] = []
        for node in self.network.nodes.values():
            if node.latitude is None or node.longitude is None:
                continue
            nodes.append(
                {
                    "id": node.node_id,
                    "name": node.name,
                    "type": node.node_type.value,
                    "territory": node.territory or "",
                    "organization": node.organization or "",
                    "lat": node.latitude,
                    "lon": node.longitude,
                    "critical": node.node_id in self.highlight_critical_nodes,
                    "heavy": node.node_id in self.highlight_heavy_nodes,
                }
            )

        fibers: List[dict] = []
        for fiber in self.network.fibers.values():
            src = self.network.get_node(fiber.source_node_id)
            dst = self.network.get_node(fiber.target_node_id)
            if not src or not dst:
                continue
            if src.latitude is None or src.longitude is None or dst.latitude is None or dst.longitude is None:
                continue

            path_points = (
                [[lat, lon] for lat, lon in fiber.route_points]
                if fiber.route_points
                else [[src.latitude, src.longitude], [dst.latitude, dst.longitude]]
            )
            color, weight, opacity = self._fiber_style(fiber)
            load = self.traffic_manager.fiber_loads.get(fiber.fiber_id)
            load_gbps = load.total_load_gbps if load else 0.0
            load_ratio = load.load_ratio if load else 0.0

            fibers.append(
                {
                    "id": fiber.fiber_id,
                    "length": fiber.length_km,
                    "type": fiber.fiber_type.value,
                    "src": {"name": src.name, "id": src.node_id},
                    "dst": {"name": dst.name, "id": dst.node_id},
                    "path": path_points,
                    "color": color,
                    "weight": weight,
                    "opacity": opacity,
                    "is_trunk": bool(fiber.is_trunk),
                    "is_critical": fiber.fiber_id in self.highlight_critical_fibers,
                    "load_gbps": load_gbps,
                    "load_ratio": load_ratio,
                }
            )

        center_lat, center_lon = 55.7558, 37.6173
        zoom = 5
        if nodes:
            center_lat = sum(n["lat"] for n in nodes) / len(nodes)
            center_lon = sum(n["lon"] for n in nodes) / len(nodes)
            zoom = 6 if len(nodes) <= 3 else 5

        icon_urls = self._get_icon_urls()
        html = f"""
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8" />
  <title>DWDM Map</title>
  <style>
    html, body, #map {{ height: 100%; margin: 0; padding: 0; }}
    .node-label {{ font-size: 12px; }}
  </style>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script src="qrc:///qtwebchannel/qwebchannel.js"></script>
</head>
<body>
  <div id="map"></div>
  <script>
    const nodes = {json.dumps(nodes)};
    const fibers = {json.dumps(fibers)};
    const iconUrls = {json.dumps(icon_urls)};

    const map = L.map('map').setView([{center_lat}, {center_lon}], {zoom});
    L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 18,
      attribution: '&copy; OpenStreetMap contributors'
    }}).addTo(map);

    const fallbackColors = {{
      "terminal": "blue",
      "oadm": "green",
      "edfa": "orange",
      "regen": "red",
      "transit": "violet"
    }};

    const markers = [];
    nodes.forEach(n => {{
      let icon;
      if (iconUrls[n.type]) {{
        icon = L.icon({{
          iconUrl: iconUrls[n.type],
          iconSize: [32, 32],
          iconAnchor: [16, 32],
          popupAnchor: [0, -32]
        }});
      }} else {{
        const color = fallbackColors[n.type] || 'grey';
        icon = L.icon({{
          iconUrl: `https://raw.githubusercontent.com/pointhi/leaflet-color-markers/master/img/marker-icon-2x-${{color}}.png`,
          shadowUrl: 'https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png',
          iconSize: [25, 41],
          iconAnchor: [12, 41],
          popupAnchor: [1, -34],
          shadowSize: [41, 41]
        }});
      }}

      const marker = L.marker([n.lat, n.lon], {{ icon: icon, title: n.name }}).addTo(map);
      marker.on('click', function() {{
        if (window.pyBridge) {{
          window.pyBridge.click_on_marker(n.id);
        }}
      }});

      const popup = `
        <b>${{n.name}}</b><br>
        ID: ${{n.id}}<br>
        Тип: ${{      n.type}}<br>
        Территория: ${{                     n.territory || '-'}}<br>
        Организация: ${{                       n.organization || '-'}}<br>
        Координаты: ${{                      n.lat.toFixed(4)}}, ${{n.lon.toFixed(4)}}
      `;
      marker.bindPopup(popup);

      L.tooltip({{
        permanent: true,
        direction: 'right',
        offset: [15, 0],
        className: 'node-label'
      }})
      .setContent(`<b style="cursor:pointer;">${{n.id}}</b><br>${{n.name}}`)
      .setLatLng([n.lat, n.lon])
      .addTo(map);

      if (n.critical || n.heavy) {{
        const color = n.critical ? '#d32f2f' : '#f9a825';
        L.circleMarker([n.lat, n.lon], {{
          radius: n.critical ? 15 : 13,
          color: color,
          weight: 3,
          fillOpacity: 0
        }}).addTo(map);
      }}

      markers.push(marker);
    }});

    fibers.forEach(f => {{
      const line = L.polyline(f.path, {{
        color: f.color,
        weight: f.weight,
        opacity: f.opacity
      }}).addTo(map);

      const tags = [];
      if (f.is_trunk) tags.push('магистраль');
      if (f.is_critical) tags.push('критичная');
      const tagsStr = tags.length ? tags.join(', ') : '-';

      line.bindPopup(`
        <b>${{f.id}}</b><br>
        От: ${{     f.src.name}} (${{f.src.id}})<br>
        До: ${{     f.dst.name}} (${{f.dst.id}})<br>
        Длина: ${{           f.length.toFixed(2)}} км<br>
        Тип: ${{      f.type}}<br>
        Нагрузка: ${{                f.load_gbps.toFixed(4)}} Гбит/с<br>
        Отн. нагрузка: ${{                       f.load_ratio.toFixed(2)}}<br>
        Признаки: ${{                tagsStr}}
      `);
    }});

    if (markers.length > 0) {{
      const group = L.featureGroup(markers);
      map.fitBounds(group.getBounds().pad(0.2));
    }}

    window.placeMode = false;
    new QWebChannel(qt.webChannelTransport, function(channel) {{
      window.pyBridge = channel.objects.pyBridge;
    }});

    map.on('click', function(e) {{
      if (window.placeMode && window.pyBridge) {{
        window.pyBridge.click_on_map(e.latlng.lat, e.latlng.lng);
      }}
    }});
  </script>
</body>
</html>
"""
        self.web_view.setHtml(html)