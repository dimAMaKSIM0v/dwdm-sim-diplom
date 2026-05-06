"""
Расчёт хроматической дисперсии в волоконно-оптических линиях связи.

Хроматическая дисперсия — расширение оптического импульса при распространении
из-за различной групповой скорости спектральных составляющих. Уширение импульса:

    τ_chr = |D(λ)| · Δλ · L  [пс]

где D(λ) — коэффициент хроматической дисперсии (пс/(нм·км)),
Δλ — спектральная ширина источника (нм), L — длина (км).

Литература:
[1] Fibotelecom.ru — Хроматическая дисперсия в оптическом волокне
[2] Студопедия — Измерение хроматической дисперсии
[3] ITU-T G.652, G.653, G.655 — Характеристики одномодовых волокон
[4] IEC/TR 61282-7 — Статистический расчёт хроматической дисперсии
"""
from typing import List, Optional, Tuple

from core.models.network import Network
from core.models.fiber import Fiber
from core.models.channel import Channel


def estimate_spectral_width_nm(bitrate_gbps: float) -> float:
    """
    Оценка спектральной ширины источника (нм) по скорости передачи.

    Приближённая зависимость для систем с внешней модуляцией:
    10G ~ 0.1 нм, 100G (когерентные) ~ 0.01 нм.

    Args:
        bitrate_gbps: Скорость в Гбит/с

    Returns:
        Оценка Δλ в нм
    """
    if bitrate_gbps <= 0:
        return 0.1
    if bitrate_gbps >= 100:
        return 0.01
    if bitrate_gbps >= 40:
        return 0.02
    return max(0.01, 0.5 / (bitrate_gbps ** 0.5))


def calculate_path_dispersion_coefficient_weighted(
    fibers: List[Fiber],
) -> float:
    """
    Взвешенное среднее D(λ) по участкам (пс/(нм·км)).
    """
    if not fibers:
        return 0.0
    total_km = sum(max(0.0, f.length_km) for f in fibers)
    if total_km <= 0:
        return 0.0
    weighted = sum(
        f.length_km * f.get_dispersion_coefficient_ps_per_nm_km()
        for f in fibers
    )
    return weighted / total_km


def calculate_path_dispersion_parameter_ps_per_nm(fibers: List[Fiber]) -> float:
    """
    Суммарный дисперсионный параметр D·L (пс/нм) для пути.
    """
    return sum(
        f.calculate_dispersion_parameter_ps_per_nm()
        for f in fibers
    )


def calculate_path_chromatic_dispersion_ps(
    fibers: List[Fiber],
    spectral_width_nm: Optional[float] = None,
    bitrate_gbps: Optional[float] = None,
) -> float:
    """
    Уширение импульса (пс) за счёт хроматической дисперсии на всём пути.

    Args:
        fibers: Список волокон на пути
        spectral_width_nm: Спектральная ширина (нм). Если None — из bitrate
        bitrate_gbps: Скорость (Гбит/с) для оценки Δλ при spectral_width_nm=None

    Returns:
        τ_chr в пс
    """
    if spectral_width_nm is None:
        spectral_width_nm = estimate_spectral_width_nm(bitrate_gbps or 10.0)
    return sum(
        f.calculate_chromatic_dispersion_ps(spectral_width_nm=spectral_width_nm)
        for f in fibers
    )


def calculate_channel_dispersion(
    network: Network,
    channel: Channel,
) -> Tuple[float, float, float]:
    """
    Расчёт дисперсии для канала.

    Args:
        network: Модель сети
        channel: Канал

    Returns:
        (D_eff пс/(нм·км), D·L пс/нм, τ_chr пс)
    """
    fibers = network.get_path_fibers(channel.path or [])
    if not fibers:
        return 0.0, 0.0, 0.0

    delta_lambda = estimate_spectral_width_nm(channel.bitrate_gbps)
    d_eff = calculate_path_dispersion_coefficient_weighted(fibers)
    d_l = calculate_path_dispersion_parameter_ps_per_nm(fibers)
    tau_chr = calculate_path_chromatic_dispersion_ps(
        fibers, spectral_width_nm=delta_lambda
    )
    return d_eff, d_l, tau_chr
