"""
Модель оборудования DWDM
MUX/DEMUX, транспондеры, усилители и т.д.
"""
from enum import Enum
from dataclasses import dataclass
from typing import Optional, List


class EquipmentType(Enum):
    """Типы оборудования"""
    MUX = "mux"  # Мультиплексор
    DEMUX = "demux"  # Демультиплексор
    OADM = "oadm"  # Оптический мультиплексор ввода/вывода
    TRANSPONDER = "transponder"  # Транспондер (передатчик/приемник)
    EDFA = "edfa"  # Оптический усилитель
    REGEN = "regen"  # Регенератор


@dataclass
class Equipment:
    """
    Единица оборудования в узле
    
    Attributes:
        equipment_id: Уникальный идентификатор оборудования
        equipment_type: Тип оборудования
        node_id: ID узла, в котором установлено оборудование
        parameters: Параметры оборудования (специфичные для типа)
    """
    equipment_id: str
    equipment_type: EquipmentType
    node_id: str
    parameters: dict = None
    
    def __post_init__(self):
        if self.parameters is None:
            self.parameters = {}
    
    def get_insertion_loss(self) -> float:
        """Возвращает вносимые потери оборудования (дБ)"""
        # Стандартные значения для разных типов
        default_losses = {
            EquipmentType.MUX: 3.0,
            EquipmentType.DEMUX: 3.0,
            EquipmentType.OADM: 4.0,
            EquipmentType.TRANSPONDER: 0.5,
            EquipmentType.EDFA: 0.5,  # Входные потери
            EquipmentType.REGEN: 1.0,
        }
        return self.parameters.get('insertion_loss', 
                                 default_losses.get(self.equipment_type, 0.0))
    
    def get_gain(self) -> float:
        """Возвращает коэффициент усиления (для EDFA, дБ)"""
        if self.equipment_type == EquipmentType.EDFA:
            return self.parameters.get('gain', 22.0)  # Стандартное усиление
        return 0.0
    
    def get_noise_figure(self) -> float:
        """Возвращает шумовую фигуру (для EDFA, дБ)"""
        if self.equipment_type == EquipmentType.EDFA:
            return self.parameters.get('noise_figure', 5.0)  # Стандартная шумовая фигура
        return 0.0
    
    def __str__(self) -> str:
        return f"{self.equipment_type.value} ({self.equipment_id})"

