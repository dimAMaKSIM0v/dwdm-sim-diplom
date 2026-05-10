"""
Расчет оптического бюджета мощности (Power Budget).

Оптический бюджет определяет, достаточно ли мощности передатчика для
надежного приема сигнала с учетом всех потерь в линии.

Основные компоненты:
    1. TX power - мощность передатчика [дБм]
    2. RX sensitivity - чувствительность приемника [дБм]
    3. Total loss - суммарные потери в линии [дБ]
    4. Power margin - запас по мощности [дБ]

Формулы:
    Energy_budget = TX_power - RX_sensitivity [дБ]
    Power_margin = RX_power - RX_sensitivity [дБ]
    RX_power = TX_power - Total_loss + Total_gain [дБм]

Критерии валидности:
    - Power_margin ≥ 3 дБ (минимальный запас)
    - Power_margin ≥ 5 дБ (рекомендуемый запас)
    - RX_power ≤ RX_overload (защита от перегрузки)

Типовые значения:
    TX power: 0 дБм (1 мВт) для 10G, +2 дБм для 40G/100G
    RX sensitivity: -20 дБм для 10G NRZ, -10 дБм для 100G когерентный
    Energy budget: 20-40 дБ (зависит от класса оборудования)

Источники:
    - ITU-T G.957: Optical interfaces for equipments and systems
    - ITU-T G.691: Optical interfaces for single channel STM-64
    - ITU-T G.692: Optical interfaces for multichannel systems with optical amplifiers
"""
from typing import Dict, Optional, List
from core.models.network import Network
from core.models.channel import Channel
from core.calculators.attenuation import calculate_channel_attenuation, calculate_power_profile


class PowerBudgetResult:
    """
    Результат расчета оптического бюджета мощности.

    Атрибуты:
        channel: Канал, для которого выполнен расчет
        raw_loss_db: Суммарные потери без учета усилителей [дБ]
        net_loss_db: Фактические потери с учетом усиления [дБ]
        total_loss_db: Полные потери (для совместимости = raw_loss_db) [дБ]
        rx_power_dbm: Мощность на входе приемника [дБм]
        power_margin_db: Запас по мощности [дБ]
        is_valid: Флаг валидности (margin ≥ 3 дБ)
        profile: Профиль мощности вдоль линии [(distance_km, power_dbm)]

    Интерпретация результатов:
        power_margin_db > 5 дБ: Отличный запас, линия надежна
        power_margin_db = 3-5 дБ: Приемлемый запас, линия работоспособна
        power_margin_db = 0-3 дБ: Недостаточный запас, риск ошибок
        power_margin_db < 0 дБ: Линия не работает, требуются усилители
    """

    def __init__(self, channel: Channel):
        self.channel = channel
        # Полные потери по линии БЕЗ учета усилителей (волокно + соединения)
        self.raw_loss_db: float = 0.0
        # Суммарные потери с учетом усиления (TX - RX)
        self.net_loss_db: float = 0.0
        # Для совместимости: будем хранить здесь то же, что и raw_loss_db
        self.total_loss_db: float = 0.0
        self.rx_power_dbm: float = 0.0
        self.power_margin_db: float = 0.0
        self.is_valid: bool = False
        self.profile: List[tuple] = []

    def __str__(self) -> str:
        status = "✓" if self.is_valid else "✗"
        return (f"{status} Channel {self.channel.channel_id}: "
                f"RX={self.rx_power_dbm:.2f} dBm, "
                f"Margin={self.power_margin_db:.2f} dB")


def calculate_power_budget(network: Network, channel: Channel) -> PowerBudgetResult:
    """
    Рассчитывает оптический бюджет мощности для канала
    
    Оптический бюджет = TX_power - RX_sensitivity - (потери в волокне + потери в оборудовании)
    
    Args:
        network: Модель сети
        channel: Канал для расчета
        
    Returns:
        Результат расчета бюджета
    """
    result = PowerBudgetResult(channel)
    
    # 1. Считаем профиль мощности с учетом усилителей
    result.profile = calculate_power_profile(network, channel)
    
    if not result.profile:
        return result
    
    # 2. Мощность на входе приемника - последняя точка профиля
    result.rx_power_dbm = result.profile[-1][1]
    
    # 3. \"Сырая\" сумма потерь по линии без учета усилителей
    # (соответствует формуле Total_Loss из пояснительной записки)
    result.raw_loss_db = calculate_channel_attenuation(network, channel)
    
    # 4. Фактические потери с учетом усиления (TX - RX)
    result.net_loss_db = channel.tx_power_dbm - result.rx_power_dbm
    
    # Для совместимости в остальных частях кода считаем,
    # что total_loss_db = raw_loss_db (именно это логично показывать в GUI)
    result.total_loss_db = result.raw_loss_db
    
    # 5. Запас по мощности (Power Margin)
    # Запас = Мощность на входе приемника - Чувствительность приемника
    result.power_margin_db = result.rx_power_dbm - channel.rx_sensitivity_dbm
    
    # Валидация: запас должен быть положительным (с небольшим допуском на потери)
    # Обычно требуется запас не менее 3-5 дБ
    result.is_valid = result.power_margin_db >= 3.0
    
    return result


def calculate_all_power_budgets(network: Network) -> Dict[str, PowerBudgetResult]:
    """
    Рассчитывает оптический бюджет для всех каналов в сети
    
    Args:
        network: Модель сети
        
    Returns:
        Словарь {channel_id: PowerBudgetResult}
    """
    results = {}
    
    for channel_id, channel in network.channels.items():
        results[channel_id] = calculate_power_budget(network, channel)
    
    return results


def find_min_power_along_path(network: Network, channel: Channel) -> tuple:
    """
    Находит минимальную мощность сигнала вдоль пути канала
    
    Returns:
        Кортеж (минимальная_мощность_дБм, позиция_в_км)
    """
    profile = calculate_power_profile(network, channel)
    
    if not profile:
        return (channel.tx_power_dbm, 0.0)
    
    min_power = min(point[1] for point in profile)
    min_position = next(point[0] for point in profile if point[1] == min_power)
    
    return (min_power, min_position)

