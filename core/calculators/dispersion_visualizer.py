"""
Визуализация влияния дисперсии на сигнал (оценочная физическая модель).

Цель модуля — дать согласованную с учебной физикой оценку:
- уширения импульса от ХД и ПМД,
- падения пиковой мощности из-за уширения (энергия ~ const),
- отдельного ослабления/усиления по мощности (loss/gain),
- задержки распространения.

Это не полноценная оптическая симуляция (без фильтров, шума, нелинейностей и пр.),
но модель параметризована (лазер, модуляция) и прозрачна для защиты.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Optional

from core.calculators.attenuation import calculate_channel_attenuation
from core.calculators.dispersion import DispersionResult
from core.calculators.power_budget import PowerBudgetResult
from core.models.channel import Channel
from core.models.fiber import FiberType
from core.models.network import Network

LaserType = Literal["dfb", "eml", "fp"]
ModulationType = Literal["nrz", "rz"]


@dataclass(frozen=True)
class PulseMetrics:
    bitrate_gbps: float
    t_bit_ps: float
    delta_lambda_nm: float
    sigma_in_ps: float

    tau_cd_ps: float
    tau_pmd_ps: float
    sigma_out_ps: float

    net_loss_db: float
    power_ratio: float
    broadening_factor: float
    peak_ratio: float

    total_length_km: float
    group_delay_s: float

    # SNR параметры для eye diagram
    osnr_db: Optional[float] = None
    snr_linear: Optional[float] = None


class DispersionVisualizer:
    # Типовые спектральные ширины (порядки) — параметр источника, а не скорости.
    LASER_TYPES_NM = {
        "dfb": {"min": 0.0001, "typical": 0.0005, "max": 0.001},
        "eml": {"min": 0.001, "typical": 0.002, "max": 0.005},
        "fp": {"min": 1.0, "typical": 2.0, "max": 5.0},
    }

    # Групповой показатель преломления (типовые значения) — влияет на задержку.
    FIBER_NG = {
        FiberType.G652: 1.4675,
        FiberType.G653: 1.4675,
        FiberType.G654: 1.4677,
        FiberType.G655: 1.4677,
        FiberType.G656: 1.4676,
        FiberType.G657: 1.4675,
    }

    def estimate_input_sigma_ps(self, bitrate_gbps: float, modulation: ModulationType) -> float:
        """
        Оценка RMS-ширины входного импульса.

        Берём типовые приближения через FWHM относительно битового интервала.
        RMS: sigma = FWHM / 2.355 для гауссовой огибающей.
        """
        t_bit_ps = 1000.0 / bitrate_gbps if bitrate_gbps > 0 else 100.0

        if modulation == "nrz":
            fwhm_ps = 0.44 * t_bit_ps
        else:  # "rz"
            fwhm_ps = 0.25 * t_bit_ps
        return max(fwhm_ps / 2.355, 1e-6)

    def spectral_width_nm(
        self,
        bitrate_gbps: float,
        *,
        laser_type: LaserType,
        laser_width_nm_override: Optional[float] = None,
    ) -> float:
        if laser_width_nm_override is not None:
            return max(float(laser_width_nm_override), 0.0)
        meta = self.LASER_TYPES_NM.get(laser_type, self.LASER_TYPES_NM["dfb"])
        return float(meta["typical"])

    @staticmethod
    def cd_pulse_broadening_ps(total_cd_ps_nm: float, spectral_width_nm: float) -> float:
        # τ_CD = |ΣХД| · Δλ
        return abs(float(total_cd_ps_nm)) * max(float(spectral_width_nm), 0.0)

    @staticmethod
    def pmd_pulse_broadening_ps(total_pmd_ps: float) -> float:
        # τ_PMD ~ DGD (берём то, что посчитали как RMS)
        return max(float(total_pmd_ps), 0.0)

    @staticmethod
    def combine_sigma_ps(sigma_in_ps: float, tau_cd_ps: float, tau_pmd_ps: float) -> float:
        # Для гауссовой модели и независимых вкладов: sigma_out^2 = sigma_in^2 + τ_CD^2 + τ_PMD^2
        return math.sqrt(
            max(float(sigma_in_ps), 0.0) ** 2
            + max(float(tau_cd_ps), 0.0) ** 2
            + max(float(tau_pmd_ps), 0.0) ** 2
        )

    def group_delay_s(self, network: Network, channel: Channel, dispersion: DispersionResult) -> float:
        c_m_s = 299_792_458.0
        fibers = network.get_path_fibers(channel.path or [])
        length_km = sum(max(float(f.length_km), 0.0) for f in fibers)
        if length_km <= 0:
            return 0.0
        # Если по пути разные типы, берём среднее по длине.
        ng_weighted = 0.0
        for f in fibers:
            ng = float(self.FIBER_NG.get(f.fiber_type, 1.4675))
            ng_weighted += ng * max(float(f.length_km), 0.0)
        ng_eff = ng_weighted / length_km if length_km > 0 else 1.4675
        return (length_km * 1000.0) * ng_eff / c_m_s

    def net_loss_db(
        self,
        network: Network,
        channel: Channel,
        budget: Optional[PowerBudgetResult],
    ) -> float:
        if budget is not None:
            return float(getattr(budget, "net_loss_db", budget.raw_loss_db))
        return float(calculate_channel_attenuation(network, channel))

    def pulse_metrics(
        self,
        network: Network,
        channel: Channel,
        dispersion: DispersionResult,
        *,
        modulation: ModulationType = "nrz",
        laser_type: LaserType = "dfb",
        laser_width_nm_override: Optional[float] = None,
        budget: Optional[PowerBudgetResult] = None,
        osnr_result: Optional[object] = None,
    ) -> PulseMetrics:
        bitrate = float(dispersion.bitrate_gbps)
        t_bit_ps = 1000.0 / bitrate if bitrate > 0 else 100.0
        delta_lambda_nm = self.spectral_width_nm(
            bitrate,
            laser_type=laser_type,
            laser_width_nm_override=laser_width_nm_override,
        )
        sigma_in_ps = self.estimate_input_sigma_ps(bitrate, modulation)

        tau_cd_ps = self.cd_pulse_broadening_ps(dispersion.total_cd_ps_nm, delta_lambda_nm)
        tau_pmd_ps = self.pmd_pulse_broadening_ps(dispersion.total_pmd_ps)
        sigma_out_ps = self.combine_sigma_ps(sigma_in_ps, tau_cd_ps, tau_pmd_ps)

        # DEBUG: дисперсия
        print(f"DEBUG dispersion:")
        print(f"  total_cd_ps_nm = {dispersion.total_cd_ps_nm:.2f} пс/нм")
        print(f"  delta_lambda_nm = {delta_lambda_nm:.6f} нм")
        print(f"  tau_cd_ps = {dispersion.total_cd_ps_nm:.2f} * {delta_lambda_nm:.6f} = {tau_cd_ps:.2f} пс")
        print(f"  sigma_in = {sigma_in_ps:.2f} пс, sigma_out = {sigma_out_ps:.2f} пс")

        broadening_factor = sigma_out_ps / sigma_in_ps if sigma_in_ps > 0 else 1.0
        loss_db = self.net_loss_db(network, channel, budget)

        # Амплитуда сигнала после потерь и уширения
        # Для гауссовых импульсов: E = A · σ · √(2π)
        # Если энергия уменьшается (потери) и σ увеличивается (дисперсия),
        # то амплитуда: A_out = A_in · √(E_out/E_in) · (σ_in/σ_out)
        amplitude_ratio = 10 ** (-loss_db / 20.0)  # √(power_ratio)
        power_ratio = amplitude_ratio ** 2

        # Пиковая амплитуда с учетом уширения (для гауссовой модели)
        # Примечание: для идеальных прямоугольных NRZ импульсов уширение
        # влияет только на фронты, но мы используем гауссову аппроксимацию
        peak_ratio = (amplitude_ratio / broadening_factor) if broadening_factor > 0 else 0.0

        # DEBUG: выводим все значения
        print(f"DEBUG pulse_metrics:")
        print(f"  loss_db = {loss_db:.2f} дБ")
        print(f"  amplitude_ratio = 10^(-{loss_db:.2f}/20) = {amplitude_ratio:.6f}")
        print(f"  broadening_factor = {broadening_factor:.6f}")
        print(f"  peak_ratio = {amplitude_ratio:.6f} / {broadening_factor:.6f} = {peak_ratio:.6f}")

        total_length_km = sum(max(float(fr.length_km), 0.0) for fr in dispersion.fiber_results)
        group_delay_s = self.group_delay_s(network, channel, dispersion)

        # Вычисляем SNR из OSNR
        # Приоритет: 1) переданный osnr_result, 2) channel.osnr_db, 3) None
        osnr_db = None
        if osnr_result is not None and hasattr(osnr_result, 'osnr_db'):
            osnr_db = osnr_result.osnr_db
        elif channel.osnr_db is not None:
            osnr_db = channel.osnr_db

        snr_linear = None
        if osnr_db is not None and osnr_db > 0:
            # Преобразуем OSNR (дБ) в линейный SNR
            # SNR = OSNR для идеального случая (без учета полосы приемника)
            # Для более точного расчета можно учесть отношение полос:
            # SNR = OSNR * (B_ref / B_electrical), где B_ref = 12.5 ГГц (стандарт)
            # B_electrical ≈ 0.7 * bitrate для NRZ
            snr_linear = 10 ** (osnr_db / 10.0)
            print(f"DEBUG SNR: OSNR = {osnr_db:.2f} дБ, SNR_linear = {snr_linear:.2f}")

        return PulseMetrics(
            bitrate_gbps=bitrate,
            t_bit_ps=t_bit_ps,
            delta_lambda_nm=delta_lambda_nm,
            sigma_in_ps=sigma_in_ps,
            tau_cd_ps=tau_cd_ps,
            tau_pmd_ps=tau_pmd_ps,
            sigma_out_ps=sigma_out_ps,
            net_loss_db=loss_db,
            power_ratio=power_ratio,
            broadening_factor=broadening_factor,
            peak_ratio=peak_ratio,
            total_length_km=total_length_km,
            group_delay_s=group_delay_s,
            osnr_db=osnr_db,
            snr_linear=snr_linear,
        )