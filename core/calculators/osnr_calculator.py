"""
Расчет OSNR (Optical Signal-to-Noise Ratio) для DWDM каналов.

OSNR - отношение мощности оптического сигнала к мощности шума в эталонной полосе 0.1 нм (12.5 ГГц).

Основные источники шума:
1. ASE (Amplified Spontaneous Emission) от EDFA усилителей
2. Тепловой шум приемника (обычно пренебрегается в оптике)

Формула OSNR:
    OSNR = P_signal / P_ASE_in_0.1nm

где P_ASE зависит от:
- Коэффициента шума усилителя (NF)
- Количества усилителей
- Коэффициента усиления каждого усилителя
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from core.models.channel import Channel
from core.models.equipment import Equipment, EquipmentType
from core.models.network import Network


@dataclass(frozen=True)
class OSNRResult:
    """Результат расчета OSNR."""

    channel_id: str
    osnr_db: float
    signal_power_dbm: float
    ase_noise_power_dbm: float
    num_amplifiers: int
    total_span_loss_db: float

    @property
    def osnr_linear(self) -> float:
        """OSNR в линейных единицах."""
        return 10 ** (self.osnr_db / 10.0)


class OSNRCalculator:
    """
    Калькулятор OSNR для DWDM каналов.

    Модель учитывает:
    - Мощность передатчика
    - Затухание в волокнах
    - Усиление и шум EDFA
    - Накопление ASE шума
    """

    # Константы
    H_PLANCK = 6.62607015e-34  # Дж·с
    C_LIGHT = 299792458.0  # м/с
    REFERENCE_BANDWIDTH_NM = 0.1  # Эталонная полоса для OSNR (нм)

    def __init__(self, network: Network):
        self.network = network

    def calculate_osnr(
        self,
        channel: Channel,
        *,
        default_nf_db: float = 5.0,
        default_gain_db: Optional[float] = None,
    ) -> OSNRResult:
        """
        Рассчитывает OSNR для канала.

        Args:
            channel: DWDM канал
            default_nf_db: Коэффициент шума усилителя по умолчанию (дБ)
            default_gain_db: Усиление по умолчанию (если None, компенсирует потери пролета)

        Returns:
            OSNRResult с рассчитанным OSNR
        """
        if not channel.path or len(channel.path) < 2:
            # Нет маршрута - возвращаем высокий OSNR (back-to-back)
            return OSNRResult(
                channel_id=channel.channel_id,
                osnr_db=40.0,
                signal_power_dbm=channel.tx_power_dbm,
                ase_noise_power_dbm=-60.0,
                num_amplifiers=0,
                total_span_loss_db=0.0,
            )

        # Получаем волокна на маршруте
        fibers = self.network.get_path_fibers(channel.path)
        if not fibers:
            return OSNRResult(
                channel_id=channel.channel_id,
                osnr_db=40.0,
                signal_power_dbm=channel.tx_power_dbm,
                ase_noise_power_dbm=-60.0,
                num_amplifiers=0,
                total_span_loss_db=0.0,
            )

        # Начальная мощность сигнала
        signal_power_dbm = channel.tx_power_dbm

        # Накопленная мощность ASE шума (в линейных единицах, мВт)
        ase_power_mw = 0.0

        # Подсчет усилителей и пролетов
        num_amplifiers = 0
        total_span_loss_db = 0.0

        # Проходим по каждому волокну (пролету)
        for fiber in fibers:
            # Потери в пролете
            span_loss_db = fiber.calculate_fiber_loss()
            total_span_loss_db += span_loss_db

            # Мощность сигнала после пролета
            signal_power_dbm -= span_loss_db

            # Находим усилитель в конце пролета (если есть)
            target_node_id = fiber.target_node_id
            amplifiers = [
                eq for eq in self.network.equipment.values()
                if eq.node_id == target_node_id and eq.equipment_type == EquipmentType.EDFA
            ]

            if amplifiers:
                # Есть усилитель - используем его параметры
                amp = amplifiers[0]
                gain_db = amp.parameters.get("gain_db", default_gain_db or span_loss_db)
                nf_db = amp.parameters.get("nf_db", default_nf_db)
            else:
                # Нет усилителя - используем параметры по умолчанию
                gain_db = default_gain_db if default_gain_db is not None else span_loss_db
                nf_db = default_nf_db

            # Добавляем ASE шум от усилителя
            ase_power_mw += self._calculate_ase_power(
                gain_db=gain_db,
                nf_db=nf_db,
                wavelength_nm=channel.wavelength_nm,
            )

            # Усиливаем сигнал
            signal_power_dbm += gain_db
            num_amplifiers += 1

        # Преобразуем мощность сигнала в мВт
        signal_power_mw = 10 ** (signal_power_dbm / 10.0)

        # OSNR в линейных единицах
        if ase_power_mw > 0:
            osnr_linear = signal_power_mw / ase_power_mw
            osnr_db = 10 * math.log10(osnr_linear)
        else:
            # Нет шума - идеальный случай
            osnr_db = 40.0

        # Мощность ASE в дБм
        ase_noise_power_dbm = 10 * math.log10(ase_power_mw) if ase_power_mw > 0 else -60.0

        return OSNRResult(
            channel_id=channel.channel_id,
            osnr_db=osnr_db,
            signal_power_dbm=signal_power_dbm,
            ase_noise_power_dbm=ase_noise_power_dbm,
            num_amplifiers=num_amplifiers,
            total_span_loss_db=total_span_loss_db,
        )

    def _calculate_ase_power(
        self,
        gain_db: float,
        nf_db: float,
        wavelength_nm: float,
    ) -> float:
        """
        Рассчитывает мощность ASE шума от одного усилителя в эталонной полосе 0.1 нм.

        Формула:
            P_ASE = 2 * n_sp * h * ν * (G - 1) * Δν

        где:
            n_sp = (NF * G - 1) / (2 * (G - 1)) - коэффициент инверсии населенности
            h - постоянная Планка
            ν - частота света
            G - коэффициент усиления (линейный)
            Δν - полоса шума (Гц)

        Args:
            gain_db: Усиление усилителя (дБ)
            nf_db: Коэффициент шума (дБ)
            wavelength_nm: Длина волны (нм)

        Returns:
            Мощность ASE в мВт
        """
        # Преобразуем в линейные единицы
        gain_linear = 10 ** (gain_db / 10.0)
        nf_linear = 10 ** (nf_db / 10.0)

        # Частота света
        frequency_hz = self.C_LIGHT / (wavelength_nm * 1e-9)

        # Полоса шума в Гц (0.1 нм при 1550 нм ≈ 12.5 ГГц)
        # Δν = c * Δλ / λ²
        bandwidth_hz = (self.C_LIGHT * self.REFERENCE_BANDWIDTH_NM * 1e-9) / (wavelength_nm * 1e-9) ** 2

        # Коэффициент инверсии населенности
        if gain_linear > 1.0:
            n_sp = (nf_linear * gain_linear - 1) / (2 * (gain_linear - 1))
        else:
            n_sp = 1.0  # Минимальное значение

        # Мощность ASE (в Вт)
        p_ase_w = 2 * n_sp * self.H_PLANCK * frequency_hz * (gain_linear - 1) * bandwidth_hz

        # Преобразуем в мВт
        p_ase_mw = p_ase_w * 1000.0

        return p_ase_mw

    def calculate_all(
        self,
        *,
        default_nf_db: float = 5.0,
        default_gain_db: Optional[float] = None,
    ) -> dict[str, OSNRResult]:
        """
        Рассчитывает OSNR для всех каналов в сети.

        Args:
            default_nf_db: Коэффициент шума по умолчанию (дБ)
            default_gain_db: Усиление по умолчанию (дБ)

        Returns:
            Словарь {channel_id: OSNRResult}
        """
        results = {}
        for channel in self.network.channels.values():
            results[channel.channel_id] = self.calculate_osnr(
                channel,
                default_nf_db=default_nf_db,
                default_gain_db=default_gain_db,
            )
        return results
