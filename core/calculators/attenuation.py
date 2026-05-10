"""
Расчет затухания в оптических волокнах.

Затухание сигнала в волокне складывается из:
    1. Собственное затухание волокна: α · L [дБ]
    2. Потери на сварных соединениях: n_splice · a_splice [дБ]
    3. Потери на коннекторах: n_conn · a_conn [дБ]
    4. Линейный резерв (запас на старение): L_reserve [дБ]

Общая формула:
    A_total = α · L + n_splice · a_splice + n_conn · a_conn + L_reserve [дБ]

где:
    α - коэффициент затухания волокна [дБ/км]
    L - длина участка [км]
    n_splice - количество сварных соединений
    a_splice - потери на одной сварке [дБ] (типовое: 0.02-0.05 дБ)
    n_conn - количество коннекторов
    a_conn - потери на одном коннекторе [дБ] (типовое: 0.3-0.5 дБ)
    L_reserve - линейный резерв [дБ] (типовое: 3-7 дБ)

Количество сварок определяется строительной длиной кабеля:
    n_splice = ceil(L / L_construction) - 1

где L_construction - строительная длина катушки (типовое: 2-25 км).

Источники:
    - ITU-T G.652: Характеристики одномодового волокна
    - ITU-T G.671: Transmission characteristics of optical components and subsystems
    - РД 45.190-2001: Руководство по строительству линейных сооружений ВОЛС
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
    Рассчитывает профиль мощности сигнала вдоль пути канала.

    Профиль показывает изменение мощности на каждом участке с учетом:
    - Затухания в волокне
    - Усиления в EDFA (если установлены)
    - Вносимых потерь оборудования

    Алгоритм:
        1. Начальная мощность = TX power передатчика
        2. Для каждого участка волокна:
           - Вычитаем потери в волокне
           - Проверяем наличие усилителя в конечном узле
           - Если есть EDFA: добавляем (gain - insertion_loss)
        3. Конечная мощность должна быть выше RX sensitivity

    Args:
        network: Модель сети
        channel: Канал для расчета

    Returns:
        Список кортежей (distance_km, power_dbm) - профиль мощности

    Примечание: Профиль используется для:
        - Визуализации распределения мощности
        - Проверки превышения максимальной мощности на входе усилителей
        - Оптимизации размещения усилителей

    Источник: ITU-T G.692, раздел 7 (Power budget)
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

