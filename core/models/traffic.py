"""
Модели для информационных направлений, маршрутов и загрузки элементов сети.
"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class InformationDirection:
    """
    Информационное направление (ИН) между двумя узлами.

    Attributes:
        direction_id: Уникальный идентификатор ИН.
        source_node_id: Узел-источник.
        target_node_id: Узел-назначение.
        capacity_gbps: Требуемая пропускная способность ИН в Гбит/с.
        capacity_unit: Единица, в которой пользователь задавал нагрузку.
        capacity_value: Значение, введенное пользователем в capacity_unit.
        routes: Набор маршрутов (каждый маршрут - список node_id).
        route_shares: Доли нагрузки по маршрутам (сумма = 1.0 для split-режимов).
        is_connected: Флаг, что для ИН найден хотя бы один маршрут.
    """
    direction_id: str
    source_node_id: str
    target_node_id: str
    capacity_gbps: float = 10.0
    capacity_unit: str = "Gbps"
    capacity_value: float = 10.0
    routes: List[List[str]] = field(default_factory=list)
    route_shares: List[float] = field(default_factory=list)
    is_connected: bool = True


@dataclass
class FiberLoad:
    """
    Загрузка линии связи (волокна) трафиком ИН.
    """
    fiber_id: str
    total_load_gbps: float = 0.0
    directions: List[str] = field(default_factory=list)
    is_critical: bool = False
    load_ratio: float = 0.0


@dataclass
class NodeLoad:
    """
    Нагрузка узла сети трафиком ИН.
    """
    node_id: str
    transit_directions: List[str] = field(default_factory=list)
    transit_count: int = 0
    is_critical: bool = False
    load_ratio: float = 0.0
