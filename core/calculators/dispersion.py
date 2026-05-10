"""
Расчёт хроматической дисперсии (ХД) и поляризационной модовой дисперсии (ПМД)
для DWDM-каналов.

Методика основана на стандартах ITU-T G.652-G.657 и рекомендациях ITU-T G.691.

Хроматическая дисперсия (ХД):
  D(λ) = D₀ + S₀ · (λ - λ₀)  [пс/(нм·км)]
  где D₀ - коэффициент дисперсии на опорной длине волны λ₀ = 1550 нм,
      S₀ - наклон дисперсии [пс/(нм²·км)]

  Накопленная ХД вдоль линии:
  D_total = Σ D(λ, тип_i) · L_i  [пс/нм]

Поляризационная модовая дисперсия (ПМД):
  Используется RSS-метод (Root Sum Square) согласно ITU-T G.691:
  Δτ_PMD = √(Σ (D_pmd_i · √L_i)²)  [пс]
  где D_pmd_i - коэффициент ПМД для i-го участка [пс/√км]

Источники:
  - ITU-T G.652: Characteristics of a single-mode optical fibre and cable
  - ITU-T G.691: Optical interfaces for single channel STM-64 and other SDH systems
  - Agrawal G.P. "Fiber-Optic Communication Systems", 4th ed., Chapter 2
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core.models.channel import Channel
from core.models.fiber import Fiber, FiberType
from core.models.network import Network


# Коэффициенты хроматической дисперсии D₀ на λ₀ = 1550 нм [пс/(нм·км)]
# Источник: ITU-T G.652-G.657, таблицы характеристик волокон
_CD_COEFF: Dict[FiberType, float] = {
    FiberType.G652: 17.0,   # SMF (Standard Single Mode Fiber): 16-19 пс/(нм·км) @ 1550 nm
    FiberType.G653: 0.0,    # DSF (Dispersion Shifted Fiber): λ₀ ≈ 1550 nm, D ≈ 0
    FiberType.G654: 18.0,   # Cut-off Shifted Fiber: аналогично G.652
    FiberType.G655: 4.0,    # NZ-DSF (Non-Zero Dispersion Shifted): 2-6 пс/(нм·км)
    FiberType.G656: 7.0,    # Wideband NZ-DSF: 2-14 пс/(нм·км), типовое ~7
    FiberType.G657: 17.0,   # Bend-Insensitive SMF: характеристики как G.652
}

# Наклон дисперсии S₀ на λ₀ = 1550 нм [пс/(нм²·км)]
# Источник: ITU-T G.652-G.657, Corning/Fujikura datasheets
_CD_SLOPE: Dict[FiberType, float] = {
    FiberType.G652: 0.067,  # SMF: типовое значение 0.055-0.070 пс/(нм²·км)
    FiberType.G653: 0.075,  # DSF: наклон выше из-за смещения λ₀
    FiberType.G654: 0.020,  # Cut-off Shifted: меньший наклон
    FiberType.G655: 0.045,  # NZ-DSF: 0.04-0.05 пс/(нм²·км)
    FiberType.G656: 0.045,  # Wideband NZ-DSF: аналогично G.655
    FiberType.G657: 0.067,  # Bend-Insensitive: как G.652
}

# Коэффициенты ПМД [пс/√км]
# Источник: ITU-T G.691, производители волокон (Corning, OFS, Fujikura)
# Современные волокна: < 0.1 пс/√км, старые кабели: 0.5-2.0 пс/√км
_PMD_COEFF: Dict[FiberType, float] = {
    FiberType.G652: 0.10,   # Современный SMF: 0.04-0.10 пс/√км (типовое 0.1)
    FiberType.G653: 0.50,   # DSF: старые кабели могут иметь высокую ПМД
    FiberType.G654: 0.20,   # Cut-off Shifted: 0.1-0.2 пс/√км
    FiberType.G655: 0.10,   # NZ-DSF: современные < 0.1 пс/√км
    FiberType.G656: 0.10,   # Wideband NZ-DSF: < 0.1 пс/√км
    FiberType.G657: 0.10,   # Bend-Insensitive: < 0.1 пс/√км
}

REF_WAVELENGTH_NM: float = 1550.0

# Лимиты накопленной хроматической дисперсии [пс/нм]
# Источники: ITU-T G.957, G.691, G.695, IEEE 802.3ba
# Примечание: для 100G/400G значения зависят от типа приемника (прямое детектирование vs когерентный)
_CD_LIMIT: Dict[float, float] = {
    2.5: 18000.0,   # 2.5G: NRZ, прямое детектирование, без DCM
    10.0: 800.0,    # 10G: NRZ, прямое детектирование (ITU-T G.691)
    40.0: 60.0,     # 40G: NRZ, прямое детектирование, требует DCM на длинных линиях
    100.0: 1000.0,  # 100G: когерентный приемник с DSP (Digital Signal Processing)
                    # Без DSP: ~50-100 пс/нм, с DSP: до 10000 пс/нм
    400.0: 2000.0,  # 400G: когерентный DP-16QAM с DSP, толерантность выше
                    # Типовое значение: 1000-3000 пс/нм
}


@dataclass
class FiberDispersionResult:
    fiber_id: str
    length_km: float
    dispersion_coeff_ps_nm_km: float
    accumulated_cd_ps_nm: float
    pmd_ps: float


@dataclass
class DispersionResult:
    channel_id: str
    wavelength_nm: float
    bitrate_gbps: float

    total_cd_ps_nm: float = 0.0
    total_pmd_ps: float = 0.0
    cd_limit_ps_nm: float = 0.0
    pmd_limit_ps: float = 0.0

    cd_is_valid: bool = False
    pmd_is_valid: bool = False
    fiber_results: List[FiberDispersionResult] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.cd_is_valid and self.pmd_is_valid


class DispersionCalculator:
    """
    Калькулятор дисперсионных эффектов в оптических волокнах.

    Реализует расчеты согласно ITU-T рекомендациям и стандартной теории
    распространения света в одномодовых волокнах.
    """

    @staticmethod
    def cd_coefficient(fiber_type: FiberType, wavelength_nm: float) -> float:
        """
        Вычисляет коэффициент хроматической дисперсии D(λ) для заданного типа волокна.

        Формула: D(λ) = D₀ + S₀ · (λ - λ₀)
        где D₀ - дисперсия на опорной длине волны λ₀ = 1550 нм,
            S₀ - наклон дисперсии.

        Args:
            fiber_type: Тип волокна (G.652, G.655 и т.д.)
            wavelength_nm: Длина волны [нм]

        Returns:
            Коэффициент дисперсии D(λ) [пс/(нм·км)]

        Источник: ITU-T G.652, раздел 3.3
        """
        d_ref = _CD_COEFF.get(fiber_type, 17.0)
        slope = _CD_SLOPE.get(fiber_type, 0.067)
        return d_ref + slope * (wavelength_nm - REF_WAVELENGTH_NM)

    @staticmethod
    def pmd_coefficient(fiber_type: FiberType) -> float:
        """
        Возвращает коэффициент ПМД для заданного типа волокна.

        ПМД (Polarization Mode Dispersion) - случайная величина, зависящая от
        двулучепреломления волокна. Коэффициент D_PMD характеризует среднее значение.

        Args:
            fiber_type: Тип волокна

        Returns:
            Коэффициент ПМД D_PMD [пс/√км]

        Источник: ITU-T G.691, Приложение A
        """
        return _PMD_COEFF.get(fiber_type, 0.10)

    @staticmethod
    def cd_limit(bitrate_gbps: float) -> float:
        """
        Возвращает допустимый лимит накопленной ХД для заданной скорости передачи.

        Лимит зависит от типа модуляции, приемника и наличия компенсации дисперсии.
        Значения приведены для типовых систем без электронной компенсации (EDC).

        Args:
            bitrate_gbps: Скорость передачи [Гбит/с]

        Returns:
            Максимально допустимая накопленная ХД [пс/нм]

        Источник: ITU-T G.957 (10G), G.695 (40G), IEEE 802.3ba (100G)
        """
        keys = sorted(_CD_LIMIT.keys())
        for key in keys:
            if bitrate_gbps <= key * 1.01:
                return _CD_LIMIT[key]
        return _CD_LIMIT[keys[-1]]

    @staticmethod
    def pmd_limit(bitrate_gbps: float) -> float:
        """
        Возвращает допустимый лимит ПМД для заданной скорости передачи.

        Эмпирическое правило: PMD_limit ≈ 0.1 · T_bit = 100 / bitrate [пс]
        Это соответствует штрафу по мощности ~1 дБ для NRZ модуляции.

        Для более точного расчета нужно учитывать:
        - Тип модуляции (NRZ, RZ, когерентная)
        - Допустимый BER (Bit Error Rate)
        - Наличие PMD компенсации

        Args:
            bitrate_gbps: Скорость передачи [Гбит/с]

        Returns:
            Максимально допустимая ПМД [пс]

        Источник: ITU-T G.691, раздел 6.2; Agrawal, Chapter 2.3
        """
        return 100.0 / bitrate_gbps if bitrate_gbps > 0 else float("inf")

    def fiber_dispersion(self, fiber: Fiber, wavelength_nm: float) -> FiberDispersionResult:
        """
        Рассчитывает дисперсию для одного участка волокна.

        Хроматическая дисперсия накапливается линейно:
            D_accumulated = D(λ) · L  [пс/нм]

        ПМД накапливается статистически (RSS-метод):
            PMD = D_PMD · √L  [пс]

        Args:
            fiber: Участок волокна
            wavelength_nm: Длина волны канала [нм]

        Returns:
            Результат расчета дисперсии для участка

        Источник: ITU-T G.691, раздел 6
        """
        d = self.cd_coefficient(fiber.fiber_type, wavelength_nm)
        acc_cd = d * fiber.length_km
        pmd = self.pmd_coefficient(fiber.fiber_type) * math.sqrt(max(fiber.length_km, 0.0))
        return FiberDispersionResult(
            fiber_id=fiber.fiber_id,
            length_km=fiber.length_km,
            dispersion_coeff_ps_nm_km=d,
            accumulated_cd_ps_nm=acc_cd,
            pmd_ps=pmd,
        )

    def channel_dispersion(self, network: Network, channel: Channel) -> DispersionResult:
        """
        Рассчитывает полную дисперсию для канала вдоль всего пути.

        Хроматическая дисперсия:
            D_total = Σ D(λ, тип_i) · L_i  [пс/нм]
            Накапливается алгебраически (с учетом знака).

        Поляризационная модовая дисперсия:
            PMD_total = √(Σ PMD_i²)  [пс]
            Накапливается статистически (RSS-метод согласно ITU-T G.691).

        Валидация:
            - ХД: |D_total| ≤ D_limit (зависит от битрейта)
            - ПМД: PMD_total ≤ PMD_limit ≈ 0.1 · T_bit

        Args:
            network: Модель сети
            channel: Канал для расчета

        Returns:
            Результат расчета дисперсии с валидацией

        Источник: ITU-T G.691, раздел 6; Agrawal, Chapter 2
        """
        res = DispersionResult(
            channel_id=channel.channel_id,
            wavelength_nm=channel.wavelength_nm,
            bitrate_gbps=channel.bitrate_gbps,
            cd_limit_ps_nm=self.cd_limit(channel.bitrate_gbps),
            pmd_limit_ps=self.pmd_limit(channel.bitrate_gbps),
        )

        if not channel.path or len(channel.path) < 2:
            return res

        total_cd = 0.0
        pmd_sq = 0.0
        for fiber in network.get_path_fibers(channel.path):
            fr = self.fiber_dispersion(fiber, channel.wavelength_nm)
            res.fiber_results.append(fr)
            total_cd += fr.accumulated_cd_ps_nm
            pmd_sq += fr.pmd_ps ** 2

        res.total_cd_ps_nm = total_cd
        res.total_pmd_ps = math.sqrt(pmd_sq)
        res.cd_is_valid = abs(total_cd) <= res.cd_limit_ps_nm
        res.pmd_is_valid = res.total_pmd_ps <= res.pmd_limit_ps
        return res

    def all_channels(self, network: Network) -> Dict[str, DispersionResult]:
        return {ch_id: self.channel_dispersion(network, ch) for ch_id, ch in network.channels.items()}


def calculate_channel_dispersion(network: Network, channel: Channel) -> Tuple[float, float, float]:
    """
    Обратная совместимость: вернуть (D_eff, D·L, τ_chr), где τ_chr = D·L.
    """
    fibers = network.get_path_fibers(channel.path or [])
    line_length_km = sum(max(float(fiber.length_km), 0.0) for fiber in fibers)
    calc = DispersionCalculator()
    result = calc.channel_dispersion(network, channel)
    d_eff = result.total_cd_ps_nm / line_length_km if line_length_km > 0 else 0.0
    d_l = result.total_cd_ps_nm
    tau_chr = d_l
    return d_eff, d_l, tau_chr
