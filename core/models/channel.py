"""
Модель оптического канала (Channel)
Представляет один канал (лямбду) в системе DWDM
"""
from dataclasses import dataclass, field
from typing import Optional, List

from enum import Enum


class LaserType(str, Enum):
    """Тип лазера (параметр источника)."""

    DFB = "dfb"
    EML = "eml"
    FP = "fp"


class ModulationType(str, Enum):
    """Тип модуляции (упрощённо)."""

    NRZ = "nrz"
    RZ = "rz"


@dataclass
class Channel:
    """
    Оптический канал (лямбда) в системе DWDM
    
    Attributes:
        channel_id: Уникальный идентификатор канала
        wavelength_nm: Длина волны в нанометрах
        frequency_thz: Частота в ТГц (может быть вычислена из длины волны)
        tx_power_dbm: Мощность передатчика в дБм
        rx_sensitivity_dbm: Чувствительность приемника в дБм
        bitrate_gbps: Скорость передачи (Гбит/с)
        energy_budget_db: Энергетический запас аппаратуры в дБ
        path: Путь канала (список ID узлов)
        osnr_db: Отношение сигнал/шум в дБ (вычисляется)
        current_power_dbm: Текущая мощность сигнала в дБм (вычисляется)
        laser_type: Тип лазера для расчёта дисперсии
        modulation_type: Тип модуляции для расчёта дисперсии
    """
    channel_id: str
    wavelength_nm: float
    frequency_thz: Optional[float] = None
    tx_power_dbm: float = 0.0  # Мощность на выходе передатчика
    rx_sensitivity_dbm: float = -20.0  # Чувствительность приемника
    bitrate_gbps: float = 10.0  # Скорость передачи
    energy_budget_db: Optional[float] = None
    path: List[str] = None  # Путь: список node_id
    osnr_db: Optional[float] = None
    current_power_dbm: Optional[float] = None
    laser_type: LaserType = LaserType.DFB
    modulation_type: ModulationType = ModulationType.NRZ
    
    def __post_init__(self):
        if self.path is None:
            self.path = []
        if self.frequency_thz is None:
            # Вычисление частоты из длины волны: f = c / λ
            # c = 299792.458 км/с (скорость света в вакууме)
            self.frequency_thz = 299792.458 / self.wavelength_nm
    
    def calculate_frequency_from_wavelength(self) -> float:
        """Вычисляет частоту (ТГц) из длины волны (нм)"""
        return 299792.458 / self.wavelength_nm

    def get_energy_budget_db(self) -> float:
        """Возвращает энергетический запас аппаратуры (дБ)."""
        if self.energy_budget_db is not None:
            return float(self.energy_budget_db)
        return float(self.tx_power_dbm - self.rx_sensitivity_dbm)
    
    def get_itu_channel_number(self) -> Optional[int]:
        """
        Определяет номер канала по сетке ITU-T
        Возвращает номер канала для сетки 100 GHz или 50 GHz
        """
        # Центральная частота для C-band: 193.1 THz
        # Шаг сетки: 0.1 THz (100 GHz) или 0.05 THz (50 GHz)
        ref_freq = 193.1  # THz
        channel_spacing_100ghz = 0.1  # THz
        
        freq_diff = self.frequency_thz - ref_freq
        channel_num = int(round(freq_diff / channel_spacing_100ghz))
        
        return channel_num
    
    def __str__(self) -> str:
        return f"Channel {self.channel_id}: λ={self.wavelength_nm:.2f} nm, {self.bitrate_gbps} Gbps"

