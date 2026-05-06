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
    dispersion_ps_per_nm_km: Optional[float] = None  # D(λ), пс/(нм·км), если задано — переопределяет тип
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

    # Коэффициент хроматической дисперсии D(λ) в пс/(нм·км) на 1550 нм
    # [ITU-T G.652, G.653, G.654, G.655, G.656, G.657; Fibotelecom.ru; Студопедия]
    DISPERSION_COEFF_MAP = {
        FiberType.G652: 17.0,   # λ₀≈1310 нм, в C-диапазоне ~17 пс/(нм·км)
        FiberType.G653: 0.0,    # Волокно со смещённой дисперсией, λ₀≈1550 нм
        FiberType.G654: 20.0,   # Аналогично G.652
        FiberType.G655: 4.5,    # Ненулевая дисперсионная смещённая, 2–6 пс/(нм·км)
        FiberType.G656: 7.0,    # Широкополосное NZ-DSF, 2–14 пс/(нм·км)
        FiberType.G657: 17.0,   # Изгибоустойчивое, характеристики как G.652
    }
    
    def get_attenuation_per_km(self) -> float:
        """Возвращает затухание в дБ/км для данного типа волокна"""
        if self.attenuation_db_per_km is not None:
            return self.attenuation_db_per_km
        return self.ATTENUATION_MAP.get(self.fiber_type, 0.22)

    def get_dispersion_coefficient_ps_per_nm_km(self) -> float:
        """
        Возвращает коэффициент хроматической дисперсии D(λ) в пс/(нм·км)
        на длине волны ~1550 нм (C-диапазон).
        """
        if self.dispersion_ps_per_nm_km is not None:
            return self.dispersion_ps_per_nm_km
        return self.DISPERSION_COEFF_MAP.get(self.fiber_type, 17.0)

    def calculate_chromatic_dispersion_ps(
        self, spectral_width_nm: float = 0.1, wavelength_nm: Optional[float] = None
    ) -> float:
        """
        Рассчитывает уширение импульса за счёт хроматической дисперсии (пс).

        τ_chr = |D(λ)| · Δλ · L

        где D(λ) — коэффициент хроматической дисперсии (пс/(нм·км)),
        Δλ — спектральная ширина источника (нм), L — длина (км).

        Args:
            spectral_width_nm: спектральная ширина источника, нм (по умолчанию 0.1 для 10G)
            wavelength_nm: длина волны для расчёта (не используется при D из справочника)

        Returns:
            Уширение импульса в пс
        """
        d = self.get_dispersion_coefficient_ps_per_nm_km()
        return abs(d) * max(0.0, spectral_width_nm) * max(0.0, self.length_km)

    def calculate_dispersion_parameter_ps_per_nm(self) -> float:
        """
        Рассчитывает дисперсионный параметр участка D·L (пс/нм).
        Используется для оценки необходимости компенсации дисперсии.
        """
        return self.get_dispersion_coefficient_ps_per_nm_km() * max(0.0, self.length_km)
    
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

