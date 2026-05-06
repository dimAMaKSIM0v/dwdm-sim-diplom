"""
Расчёт хроматической дисперсии (ХД) и поляризационной модовой дисперсии (ПМД)
для DWDM-каналов.

Методика:
  Накопленная ХД:  D_total = Σ D(λ,тип) · L_i   [пс/нм]
  ПМД (RSS-метод): Δτ_PMD  = √(Σ (D_pmd_i · √L_i)²)  [пс]
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from core.models.channel import Channel
from core.models.fiber import Fiber, FiberType
from core.models.network import Network


_CD_COEFF: Dict[FiberType, float] = {
    FiberType.G652: 17.0,
    FiberType.G653: 0.0,
    FiberType.G654: 18.0,
    FiberType.G655: 4.0,
    FiberType.G656: 7.0,
    FiberType.G657: 17.0,
}

_CD_SLOPE: Dict[FiberType, float] = {
    FiberType.G652: 0.067,
    FiberType.G653: 0.075,
    FiberType.G654: 0.020,
    FiberType.G655: 0.045,
    FiberType.G656: 0.045,
    FiberType.G657: 0.067,
}

_PMD_COEFF: Dict[FiberType, float] = {
    FiberType.G652: 0.10,
    FiberType.G653: 0.50,
    FiberType.G654: 0.20,
    FiberType.G655: 0.10,
    FiberType.G656: 0.10,
    FiberType.G657: 0.10,
}

REF_WAVELENGTH_NM: float = 1550.0

_CD_LIMIT: Dict[float, float] = {
    2.5: 18000.0,
    10.0: 800.0,
    40.0: 60.0,
    100.0: 50000.0,
    400.0: 20000.0,
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
    @staticmethod
    def cd_coefficient(fiber_type: FiberType, wavelength_nm: float) -> float:
        d_ref = _CD_COEFF.get(fiber_type, 17.0)
        slope = _CD_SLOPE.get(fiber_type, 0.067)
        return d_ref + slope * (wavelength_nm - REF_WAVELENGTH_NM)

    @staticmethod
    def pmd_coefficient(fiber_type: FiberType) -> float:
        return _PMD_COEFF.get(fiber_type, 0.10)

    @staticmethod
    def cd_limit(bitrate_gbps: float) -> float:
        keys = sorted(_CD_LIMIT.keys())
        for key in keys:
            if bitrate_gbps <= key * 1.01:
                return _CD_LIMIT[key]
        return _CD_LIMIT[keys[-1]]

    @staticmethod
    def pmd_limit(bitrate_gbps: float) -> float:
        return 100.0 / bitrate_gbps if bitrate_gbps > 0 else float("inf")

    def fiber_dispersion(self, fiber: Fiber, wavelength_nm: float) -> FiberDispersionResult:
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
