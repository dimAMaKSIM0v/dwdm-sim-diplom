"""
Модель оптического волокна (Fiber)
Представляет отрезок волоконно-оптической линии связи между узлами
"""
import math
from enum import Enum
from typing import Optional, List, Tuple
from dataclasses import dataclass, field


class FiberType(Enum):
    """Типы оптического волокна"""
    G652 = "G.652"  # Стандартное одномодовое волокно
    G652D = "G.652"  # Алиас для обратной совместимости
    G653 = "G.653"  # Волокно со смещенной дисперсией
    G654 = "G.654"  # Волокно со сдвинутой отсечкой
    G655 = "G.655"  # Ненулевая дисперсионная смещенная
    G656 = "G.656"  # Широкополосное ненулевой дисперсионной смещенное
    G657 = "G.657"  # Изгибоустойчивое одномодовое


@dataclass
class Fiber:
    """
    Оптическое волокно между двумя узлами
    
    Attributes:
        fiber_id: Уникальный идентификатор волокна
        source_node_id: ID узла источника
        target_node_id: ID узла назначения
        length_km: Длина волокна в километрах
        fiber_type: Тип волокна (G.652 и т.д.)
        attenuation_db_per_km: Затухание в дБ/км (если None - берется из типа)
        splice_losses_db: Потери на сварках (дБ)
        connector_losses_db: Потери на коннекторах (дБ)
        route_points: Точки трассы в формате [(lat, lon), ...], если трасса не прямая
        is_trunk: Признак магистральной линии
    """
    fiber_id: str
    source_node_id: str
    target_node_id: str
    length_km: float
    fiber_type: FiberType = FiberType.G652
    attenuation_db_per_km: Optional[float] = None
    # По методичке: A = L*alpha + n_splice*a_splice + n_conn*a_conn
    # a_splice = 0.02 дБ, a_conn = 0.3 дБ, n_splice зависит от строительной длины.
    splice_losses_db: float = 0.02  # Потери на одном сварном соединении
    splice_interval_km: float = 25.0  # Строительная длина катушки/кабеля (км)
    connector_losses_db: float = 0.3  # Потери на одном коннекторе
    line_reserve_db: float = 0.0
    splice_count_override: Optional[int] = None
    route_points: List[Tuple[float, float]] = field(default_factory=list)
    is_trunk: bool = False
    
    # Стандартные значения затухания по типам волокон (дБ/км на 1550 нм)
    ATTENUATION_MAP = {
        FiberType.G652: 0.22,
        FiberType.G653: 0.25,
        FiberType.G654: 0.19,
        FiberType.G655: 0.21,
        FiberType.G656: 0.22,
        FiberType.G657: 0.22,
    }
    
    def get_attenuation_per_km(self) -> float:
        """Возвращает затухание в дБ/км для данного типа волокна"""
        if self.attenuation_db_per_km is not None:
            return self.attenuation_db_per_km
        return self.ATTENUATION_MAP.get(self.fiber_type, 0.22)
    
    def calculate_fiber_loss(self) -> float:
        """
        Рассчитывает общие потери в волокне
        
        Returns:
            Общие потери в дБ
        """
        fiber_loss = self.length_km * self.get_attenuation_per_km()
        # По формуле из методички: nср = ceil(L / Lстр) - 1
        num_splices = self.calculate_splice_count()
        splice_loss = num_splices * self.splice_losses_db
        # Потери на коннекторах (2 коннектора - на входе и выходе)
        connector_loss = 2 * self.connector_losses_db
        
        return fiber_loss + splice_loss + connector_loss + self.line_reserve_db

    def calculate_splice_count(self) -> int:
        """Количество сварок по длине участка и строительной длине катушки."""
        if self.splice_count_override is not None:
            return max(0, int(self.splice_count_override))
        if self.length_km <= 0:
            return 0
        construction_length_km = max(self.splice_interval_km, 0.001)
        sections_count = max(1, self._excel_round(self.length_km / construction_length_km))
        return max(0, sections_count - 1)

    @staticmethod
    def _excel_round(value: float) -> int:
        """Округление как в Excel (0.5 вверх для положительных чисел)."""
        if value >= 0:
            return int(math.floor(value + 0.5))
        return int(math.ceil(value - 0.5))

    def loss_per_km_estimate(self) -> float:
        """
        Оценка потерь на км (дБ/км) для разбиения на пролеты.
        Коннекторы тут не учитываем, они точечные на концах.
        """
        if self.length_km <= 0:
            return self.get_attenuation_per_km()
        splice_component = (self.calculate_splice_count() * self.splice_losses_db) / self.length_km
        return self.get_attenuation_per_km() + splice_component
    
    def __str__(self) -> str:
        return f"Fiber {self.source_node_id} -> {self.target_node_id} ({self.length_km:.2f} km)"

