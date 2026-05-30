"""
Расчет BER (Bit Error Rate) для DWDM каналов.

BER - это вероятность ошибки при приеме бита. В оптических системах BER зависит от:
1. OSNR (Optical Signal-to-Noise Ratio)
2. Битрейта и типа модуляции
3. Дисперсии (уширение импульсов)
4. ПМД (поляризационной модовой дисперсии)

Формулы:
    Для NRZ модуляции:
        BER ≈ 0.5 * erfc(Q / √2)
        где Q = √(2 * OSNR_eff * T_bit / T_symbol)

    Для RZ модуляции:
        BER ≈ 0.25 * erfc(Q / √2) * (1 + 1/√(2*OSNR_eff))

    Эффективный OSNR:
        OSNR_eff = OSNR * (B_signal / B_ref)
        где B_signal - полоса сигнала, B_ref = 0.1 нм (12.5 ГГц)

Источники:
    - Agrawal G.P. "Fiber-Optic Communication Systems", 4th ed., Chapter 7
    - ITU-T G.959.1: Optical interface parameters for SDH systems
    - Proakis J.G. "Digital Communications", 5th ed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from scipy.special import erfc

from core.models.channel import Channel, ModulationType
from core.models.network import Network
from core.calculators.osnr_calculator import OSNRCalculator, OSNRResult
from core.calculators.dispersion import DispersionCalculator, DispersionResult


@dataclass(frozen=True)
class BERResult:
    """Результат расчета BER."""

    channel_id: str
    ber: float
    q_factor: float
    osnr_eff_db: float
    osnr_db: float
    dispersion_penalty_db: float
    pmd_penalty_db: float
    modulation_type: str
    is_valid: bool

    @property
    def ber_valid(self) -> bool:
        """BER должен быть < 1e-12 для стандартных систем."""
        return self.ber < 1e-12


class BERCalculator:
    """
    Калькулятор BER для DWDM каналов.

    Модель учитывает:
    - OSNR от EDFA усилителей
    - Уширение импульса от дисперсии
    - ПМД
    - Тип модуляции (NRZ, RZ)
    """

    # Константы
    REFERENCE_BANDWIDTH_HZ = 12.5e9  # 12.5 ГГц (0.1 нм при 1550 нм)
    Q_THRESHOLD_FOR_BER_1E_12 = 7.0  # Q-factor для BER = 1e-12

    def __init__(self, network: Network):
        self.network = network
        self.osnr_calculator = OSNRCalculator(network)
        self.dispersion_calculator = DispersionCalculator()

    def calculate_q_factor(self, osnr_linear: float, bitrate_gbps: float, modulation: ModulationType) -> float:
        """
        Рассчитывает Q-фактор по OSNR и битрейту.

        Для NRZ:
            Q = √(2 * OSNR_eff * T_bit / T_symbol)

        Для RZ:
            Q = √(OSNR_eff * T_bit / T_symbol)

        Args:
            osnr_linear: OSNR в линейных единицах
            bitrate_gbps: Битрейт в Гбит/с
            modulation: Тип модуляции

        Returns:
            Q-фактор
        """
        # Битовый интервал в секундах
        t_bit_s = 1e-9 / bitrate_gbps  # 1 Гбит/с = 1e-9 с

        # Для NRZ: T_symbol = T_bit
        # Для RZ 50%: T_symbol = T_bit / 2
        if modulation == ModulationType.RZ:
            symbol_ratio = 2.0  # T_bit / T_symbol = 2
        else:  # NRZ
            symbol_ratio = 1.0

        # Эффективный OSNR (учитываем полосу сигнала)
        # B_signal ≈ 0.85 * B_bit для NRZ, ≈ B_bit для RZ
        if modulation == ModulationType.RZ:
            bandwidth_factor = 1.0
        else:
            bandwidth_factor = 0.85

        osnr_eff = osnr_linear * bandwidth_factor

        # Q-фактор
        q_factor = math.sqrt(symbol_ratio * osnr_eff)

        return q_factor

    def calculate_dispersion_penalty(self, tau_chr_ps: float, t_bit_ps: float) -> float:
        """
        Рассчитывает штраф по мощности от дисперсии.

        Для гауссовых импульсов:
            Penalty (dB) = 10 * log10(1 + (τ_CHR / (0.5 * T_bit))²)

        Args:
            tau_chr_ps: Уширение импульса от ХД в пс
            t_bit_ps: Битовый интервал в пс

        Returns:
            Штраф по мощности в дБ
        """
        if tau_chr_ps <= 0 or t_bit_ps <= 0:
            return 0.0

        # Отношение уширения к битовому интервалу
        ratio = tau_chr_ps / (0.5 * t_bit_ps)

        # Штраф по мощности (дБ)
        penalty_db = 10 * math.log10(1 + ratio ** 2)

        return penalty_db

    def calculate_pmd_penalty(self, pmd_ps: float, t_bit_ps: float) -> float:
        """
        Рассчитывает штраф по мощности от ПМД.

        Для NRZ модуляции:
            Penalty (dB) ≈ 0.5 * (PMD / T_bit)² для PMD < 0.1*T_bit
            Penalty (dB) ≈ 15 * (PMD / T_bit) для PMD > 0.1*T_bit

        Args:
            pmd_ps: ПМД в пс
            t_bit_ps: Битовый интервал в пс

        Returns:
            Штраф по мощности в дБ
        """
        if pmd_ps <= 0 or t_bit_ps <= 0:
            return 0.0

        ratio = pmd_ps / t_bit_ps

        # Эмпирическая формула для штрафа от ПМД
        if ratio < 0.1:
            # Линейная область
            penalty_db = 0.5 * (ratio ** 2)
        else:
            # Нелинейная область
            penalty_db = 15 * ratio

        return penalty_db

    def calculate_ber(
        self,
        channel: Channel,
        osnr_result: Optional[OSNRResult] = None,
        dispersion_result: Optional[DispersionResult] = None,
    ) -> BERResult:
        """
        Рассчитывает BER для канала.

        Args:
            channel: DWDM канал
            osnr_result: Результат расчета OSNR (если None, будет рассчитан)
            dispersion_result: Результат расчета дисперсии (если None, будет рассчитан)

        Returns:
            BERResult с рассчитанным BER
        """
        # Рассчитываем OSNR если не передан
        if osnr_result is None:
            osnr_result = self.osnr_calculator.calculate_osnr(channel)

        # Рассчитываем дисперсию если не передана
        if dispersion_result is None:
            dispersion_result = self.dispersion_calculator.channel_dispersion(self.network, channel)

        # Битовый интервал в пс
        t_bit_ps = 1000.0 / channel.bitrate_gbps  # 1 Гбит/с = 1000 пс

        # OSNR в линейных единицах
        osnr_linear = osnr_result.osnr_linear

        # Q-фактор
        q_factor = self.calculate_q_factor(osnr_linear, channel.bitrate_gbps, channel.modulation_type)

        # Штраф от дисперсии
        tau_chr_ps = abs(dispersion_result.total_cd_ps_nm)  # τ_CHR = D·L
        dispersion_penalty_db = self.calculate_dispersion_penalty(tau_chr_ps, t_bit_ps)

        # Штраф от ПМД
        pmd_penalty_db = self.calculate_pmd_penalty(dispersion_result.total_pmd_ps, t_bit_ps)

        # Эффективный OSNR с учетом штрафов
        # OSNR_eff = OSNR - penalty
        osnr_eff_linear = osnr_linear / (10 ** (dispersion_penalty_db / 10))
        osnr_eff_db = osnr_result.osnr_db - dispersion_penalty_db - pmd_penalty_db

        # BER для NRZ модуляции
        # BER = 0.5 * erfc(Q / √2)
        if channel.modulation_type == ModulationType.RZ:
            # Для RZ: BER ≈ 0.25 * erfc(Q / √2) * (1 + 1/√(2*OSNR_eff))
            ber = 0.25 * erfc(q_factor / math.sqrt(2)) * (1 + 1 / math.sqrt(2 * osnr_eff_linear)) if osnr_eff_linear > 0 else 1.0
        else:  # NRZ
            ber = 0.5 * erfc(q_factor / math.sqrt(2))

        # Валидация
        is_valid = ber < 1e-12

        return BERResult(
            channel_id=channel.channel_id,
            ber=ber,
            q_factor=q_factor,
            osnr_eff_db=osnr_eff_db,
            osnr_db=osnr_result.osnr_db,
            dispersion_penalty_db=dispersion_penalty_db,
            pmd_penalty_db=pmd_penalty_db,
            modulation_type=channel.modulation_type.value,
            is_valid=is_valid,
        )

    def calculate_all(self) -> dict[str, BERResult]:
        """
        Рассчитывает BER для всех каналов в сети.

        Returns:
            Словарь {channel_id: BERResult}
        """
        results = {}
        for channel in self.network.channels.values():
            results[channel.channel_id] = self.calculate_ber(channel)
        return results


def calculate_channel_ber(network: Network, channel: Channel) -> tuple:
    """
    Обратная совместимость: вернуть (BER, Q_factor, dispersion_penalty_db, pmd_penalty_db).
    """
    calc = BERCalculator(network)
    result = calc.calculate_ber(channel)
    return (result.ber, result.q_factor, result.dispersion_penalty_db, result.pmd_penalty_db)
