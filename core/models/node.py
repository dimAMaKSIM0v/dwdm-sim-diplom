"""
Модель узла сети (Node)
Представляет точку присутствия оборудования в сети
"""
from enum import Enum
from typing import Optional, List
from dataclasses import dataclass, field


class NodeType(Enum):
    """Типы узлов сети"""
    TERMINAL = "terminal"  # Терминальный узел (начало/конец линии)
    OADM = "oadm"  # Оптический мультиплексор ввода/вывода
    EDFA = "edfa"  # Оптический усилитель
    REGEN = "regen"  # Регенератор (OEO)
    TRANSIT = "transit"  # Транзитный узел


@dataclass
class Node:
    """
    Узел сети DWDM
    
    Attributes:
        node_id: Уникальный идентификатор узла
        node_type: Тип узла
        name: Название узла
        latitude: Широта (для геопривязки)
        longitude: Долгота (для геопривязки)
        territory: Территориальная принадлежность узла (область/регион/зона)
        organization: Организационная принадлежность (подразделение)
        equipment: Список оборудования в узле (MUX, транспондеры и т.д.)
        parameters: Дополнительные параметры узла
    """
    node_id: str
    node_type: NodeType
    name: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    territory: str = ""
    organization: str = ""
    equipment: List[str] = field(default_factory=list)
    parameters: dict = field(default_factory=dict)
    
    def __str__(self) -> str:
        return f"{self.name} ({self.node_type.value})"
    
    def distance_to(self, other: 'Node') -> float:
        """
        Вычисляет расстояние до другого узла (в км)
        Использует формулу гаверсинуса
        """
        if self.latitude is None or self.longitude is None:
            return 0.0
        if other.latitude is None or other.longitude is None:
            return 0.0
            
        from math import radians, sin, cos, sqrt, atan2
        
        R = 6371.0  # Радиус Земли в км
        
        lat1 = radians(self.latitude)
        lat2 = radians(other.latitude)
        dlat = radians(other.latitude - self.latitude)
        dlon = radians(other.longitude - self.longitude)
        
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
        return R * c

