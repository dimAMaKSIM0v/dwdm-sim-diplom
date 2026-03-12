"""Модель сети DWDM.

Контейнер для узлов, волокон, каналов и оборудования.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .channel import Channel
from .equipment import Equipment
from .fiber import Fiber
from .node import Node


@dataclass
class Network:
    """Модель сети DWDM с базовыми операциями хранения и валидации."""

    nodes: Dict[str, Node] = field(default_factory=dict)
    fibers: Dict[str, Fiber] = field(default_factory=dict)
    channels: Dict[str, Channel] = field(default_factory=dict)
    equipment: Dict[str, Equipment] = field(default_factory=dict)
    name: str = "DWDM Network"

    def add_node(self, node: Node) -> None:
        """Добавляет узел в сеть."""
        self.nodes[node.node_id] = node

    def add_fiber(self, fiber: Fiber) -> None:
        """Добавляет волокно в сеть."""
        self.fibers[fiber.fiber_id] = fiber

    def add_channel(self, channel: Channel) -> None:
        """Добавляет канал в сеть."""
        self.channels[channel.channel_id] = channel

    def add_equipment(self, equipment: Equipment) -> None:
        """Добавляет оборудование в сеть."""
        self.equipment[equipment.equipment_id] = equipment
        # Привязываем оборудование к узлу.
        if equipment.node_id in self.nodes:
            self.nodes[equipment.node_id].equipment.append(equipment.equipment_id)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Возвращает узел по ID."""
        return self.nodes.get(node_id)

    def get_fiber(self, fiber_id: str) -> Optional[Fiber]:
        """Возвращает волокно по ID."""
        return self.fibers.get(fiber_id)

    def get_fibers_between(self, source_id: str, target_id: str) -> List[Fiber]:
        """Возвращает все волокна между двумя узлами (без учета направления)."""
        return [
            f
            for f in self.fibers.values()
            if (
                f.source_node_id == source_id
                and f.target_node_id == target_id
            ) or (
                f.source_node_id == target_id
                and f.target_node_id == source_id
            )
        ]

    def get_path_fibers(self, path: List[str]) -> List[Fiber]:
        """Возвращает список волокон для заданного пути."""
        fibers: List[Fiber] = []
        for i in range(len(path) - 1):
            source_id = path[i]
            target_id = path[i + 1]
            fiber_list = self.get_fibers_between(source_id, target_id)
            if fiber_list:
                # При параллельных волокнах берем первое найденное.
                fibers.append(fiber_list[0])
        return fibers

    def validate(self) -> List[str]:
        """Проверяет целостность ссылок в сети и возвращает список ошибок."""
        errors: List[str] = []

        # Проверка волокон: узлы должны существовать.
        for fiber in self.fibers.values():
            if fiber.source_node_id not in self.nodes:
                errors.append(f"Fiber {fiber.fiber_id}: source node {fiber.source_node_id} not found")
            if fiber.target_node_id not in self.nodes:
                errors.append(f"Fiber {fiber.fiber_id}: target node {fiber.target_node_id} not found")

        # Проверка каналов: узлы в пути должны существовать.
        for channel in self.channels.values():
            for node_id in channel.path:
                if node_id not in self.nodes:
                    errors.append(f"Channel {channel.channel_id}: node {node_id} in path not found")

        # Проверка оборудования: узлы должны существовать.
        for equipment in self.equipment.values():
            if equipment.node_id not in self.nodes:
                errors.append(f"Equipment {equipment.equipment_id}: node {equipment.node_id} not found")

        return errors

    def clear(self) -> None:
        """Очищает сеть."""
        self.nodes.clear()
        self.fibers.clear()
        self.channels.clear()
        self.equipment.clear()

    def __str__(self) -> str:
        return (
            f"Network '{self.name}': "
            f"{len(self.nodes)} nodes, {len(self.fibers)} fibers, {len(self.channels)} channels"
        )
