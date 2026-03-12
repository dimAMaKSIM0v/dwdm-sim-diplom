"""
Расчет затухания в оптических волокнах
"""
from typing import List
from core.models.network import Network
from core.models.fiber import Fiber
from core.models.channel import Channel


def calculate_path_attenuation(network: Network, path: List[str]) -> float:
    """
    Рассчитывает суммарное затухание для заданного пути
    
    Args:
        network: Модель сети
        path: Список node_id, образующих путь
        
    Returns:
        Суммарное затухание в дБ
    """
    total_loss = 0.0
    fibers = network.get_path_fibers(path)
    
    for fiber in fibers:
        total_loss += fiber.calculate_fiber_loss()
    
    return total_loss


def calculate_channel_attenuation(network: Network, channel: Channel) -> float:
    """
    Рассчитывает затухание для канала (с учетом пути канала)
    
    Args:
        network: Модель сети
        channel: Канал для расчета
        
    Returns:
        Суммарное затухание в дБ
    """
    if not channel.path:
        return 0.0
    
    return calculate_path_attenuation(network, channel.path)


def calculate_power_profile(network: Network, channel: Channel) -> List[tuple]:
    """
    Рассчитывает профиль мощности сигнала вдоль пути
    
    Args:
        network: Модель сети
        channel: Канал для расчета
        
    Returns:
        Список кортежей (позиция_в_км, мощность_дБм)
    """
    profile = []
    if not channel.path:
        return profile
    
    current_power = channel.tx_power_dbm
    current_distance = 0.0
    
    profile.append((current_distance, current_power))
    
    fibers = network.get_path_fibers(channel.path)
    
    for fiber in fibers:
        fiber_loss = fiber.calculate_fiber_loss()
        current_distance += fiber.length_km
        current_power -= fiber_loss
        profile.append((current_distance, current_power))
        
        # Проверяем, есть ли усилитель в целевом узле
        target_node = network.get_node(fiber.target_node_id)
        if target_node:
            # Ищем EDFA в узле
            for eq_id in target_node.equipment:
                equipment = network.equipment.get(eq_id)
                if equipment and equipment.equipment_type.value == "edfa":
                    gain = equipment.get_gain()
                    insertion_loss = equipment.get_insertion_loss()
                    # Усилитель увеличивает мощность на (gain - insertion_loss)
                    current_power += (gain - insertion_loss)
                    profile.append((current_distance, current_power))
                    break
    
    return profile

