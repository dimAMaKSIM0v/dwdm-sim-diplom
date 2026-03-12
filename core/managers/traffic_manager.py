"""
Менеджер информационных направлений и потоковой структуры сети (раздел 3.2).
"""
from __future__ import annotations

from itertools import combinations
from typing import Dict, List, Tuple

import networkx as nx

from core.models.network import Network
from core.models.traffic import FiberLoad, InformationDirection, NodeLoad


class TrafficManager:
    """Управление информационными направлениями, маршрутами и загрузкой сети."""

    CAPACITY_MAP_GBPS = {
        "E1": 0.002048,       # 2.048 Mbps
        "STM-1": 0.15552,     # 155.52 Mbps
        "WDM-CH": 100.0,      # 100 Gbps на спектральный канал (упрощение)
        "ETH-Mbps": 0.001,    # value / 1000
        "Gbps": 1.0,
    }

    def __init__(self, network: Network):
        self.network = network
        self.directions: Dict[str, InformationDirection] = {}
        self.fiber_loads: Dict[str, FiberLoad] = {}
        self.node_loads: Dict[str, NodeLoad] = {}

    # --- Работа с графом ---

    def _build_graph(self) -> nx.Graph:
        g = nx.Graph()
        for node_id in self.network.nodes.keys():
            g.add_node(node_id)
        for fiber in self.network.fibers.values():
            g.add_edge(
                fiber.source_node_id,
                fiber.target_node_id,
                weight=float(fiber.length_km),
                hops=1.0,
                fiber_id=fiber.fiber_id,
            )
        return g

    def _to_gbps(self, value: float, unit: str) -> float:
        unit = unit.strip()
        k = self.CAPACITY_MAP_GBPS.get(unit, 1.0)
        return float(value) * k

    # --- Генерация ИН (3.2.1) ---

    def _create_direction(self, src: str, dst: str, capacity_value: float, capacity_unit: str) -> InformationDirection:
        return InformationDirection(
            direction_id=f"D_{src}_{dst}",
            source_node_id=src,
            target_node_id=dst,
            capacity_gbps=self._to_gbps(capacity_value, capacity_unit),
            capacity_unit=capacity_unit,
            capacity_value=float(capacity_value),
        )

    def generate_directions(
        self,
        mode: str = "full_mesh",
        capacity_value: float = 10.0,
        capacity_unit: str = "Gbps",
        bidirectional: bool = True,
    ) -> int:
        """
        Генерирует ИН по правилу:
        - full_mesh
        - by_territory
        - by_organization
        """
        self.directions.clear()
        node_ids = list(self.network.nodes.keys())
        mode = mode.strip().lower()
        created = 0

        pairs: List[Tuple[str, str]] = []

        if mode == "full_mesh":
            pairs = list(combinations(node_ids, 2))
        elif mode == "by_territory":
            groups: Dict[str, List[str]] = {}
            for node in self.network.nodes.values():
                key = (node.territory or "").strip()
                if not key:
                    continue
                groups.setdefault(key, []).append(node.node_id)
            for members in groups.values():
                pairs.extend(combinations(members, 2))
        elif mode == "by_organization":
            groups = {}
            for node in self.network.nodes.values():
                key = (node.organization or "").strip()
                if not key:
                    continue
                groups.setdefault(key, []).append(node.node_id)
            for members in groups.values():
                pairs.extend(combinations(members, 2))
        else:
            raise ValueError(f"Неизвестный режим генерации ИН: {mode}")

        used = set()
        for src, dst in pairs:
            key = (src, dst)
            if key in used:
                continue
            d = self._create_direction(src, dst, capacity_value, capacity_unit)
            self.directions[d.direction_id] = d
            used.add(key)
            created += 1

            if bidirectional:
                db = self._create_direction(dst, src, capacity_value, capacity_unit)
                self.directions[db.direction_id] = db
                used.add((dst, src))
                created += 1

        return created

    def generate_full_mesh(self, capacity_gbps: float = 10.0, bidirectional: bool = True) -> int:
        """
        Backward-compatible API: генерация full mesh в Гбит/с.
        """
        return self.generate_directions(
            mode="full_mesh",
            capacity_value=float(capacity_gbps),
            capacity_unit="Gbps",
            bidirectional=bidirectional,
        )

    # --- Нахождение потоковой структуры (3.2.2) ---

    @staticmethod
    def _path_length(g: nx.Graph, path: List[str]) -> float:
        if len(path) < 2:
            return 0.0
        length = 0.0
        for u, v in zip(path[:-1], path[1:]):
            length += float(g[u][v].get("weight", 1.0))
        return length

    @staticmethod
    def _path_hops(path: List[str]) -> int:
        return max(0, len(path) - 1)

    def _shortest_path(self, g: nx.Graph, src: str, dst: str, weight: str) -> List[str]:
        try:
            return nx.shortest_path(g, src, dst, weight=weight)
        except nx.NetworkXNoPath:
            return []

    def _direction_paths(
        self,
        g: nx.Graph,
        d: InformationDirection,
        routes_per_direction: int,
        criterion: str,
        dynamic_loads: Dict[Tuple[str, str], float],
    ) -> List[List[str]]:
        work = g.copy()
        paths: List[List[str]] = []
        criterion = criterion.strip().lower()

        for _ in range(max(1, routes_per_direction)):
            if criterion == "min_hops":
                path = self._shortest_path(work, d.source_node_id, d.target_node_id, "hops")
            elif criterion == "min_max_load":
                # Веса обновляем от текущей загрузки для разгрузки "узких мест".
                for u, v in work.edges():
                    key = (u, v) if u < v else (v, u)
                    penalty = dynamic_loads.get(key, 0.0)
                    base = float(work[u][v].get("weight", 1.0))
                    work[u][v]["dyn_weight"] = base * (1.0 + penalty)
                path = self._shortest_path(work, d.source_node_id, d.target_node_id, "dyn_weight")
            else:
                path = self._shortest_path(work, d.source_node_id, d.target_node_id, "weight")

            if not path:
                break

            paths.append(path)

            # Форсируем разнообразие резервных маршрутов.
            for u, v in zip(path[:-1], path[1:]):
                if work.has_edge(u, v):
                    base = float(work[u][v].get("weight", 1.0))
                    work[u][v]["weight"] = base * 2.5

        return paths

    def _shares(
        self,
        g: nx.Graph,
        paths: List[List[str]],
        distribution: str,
    ) -> List[float]:
        if not paths:
            return []
        distribution = distribution.strip().lower()
        if distribution == "duplicate_100":
            return [1.0 for _ in paths]
        if len(paths) == 1:
            return [1.0]

        if distribution == "inverse_hops":
            raw = [1.0 / max(1, self._path_hops(p)) for p in paths]
        else:
            # default: inverse_length
            raw = [1.0 / max(self._path_length(g, p), 1e-6) for p in paths]

        s = sum(raw)
        if s <= 0:
            return [1.0 / len(paths) for _ in paths]
        return [x / s for x in raw]

    def compute_flows(
        self,
        routes_per_direction: int = 1,
        criterion: str = "length",
        distribution: str = "inverse_length",
    ) -> None:
        """
        Находит маршруты для всех ИН и рассчитывает загрузку линий/узлов.

        Args:
            routes_per_direction: число маршрутов на ИН (основной + резервные)
            criterion: length | min_max_load | min_hops
            distribution: inverse_length | inverse_hops | duplicate_100
        """
        g = self._build_graph()
        self.fiber_loads.clear()
        self.node_loads.clear()
        dynamic_loads: Dict[Tuple[str, str], float] = {}

        for d in self.directions.values():
            paths = self._direction_paths(
                g=g,
                d=d,
                routes_per_direction=routes_per_direction,
                criterion=criterion,
                dynamic_loads=dynamic_loads,
            )
            d.routes = paths
            d.is_connected = bool(paths)
            d.route_shares = self._shares(g, paths, distribution)

            for path, share in zip(paths, d.route_shares):
                load_gbps = d.capacity_gbps * share
                if distribution == "duplicate_100":
                    load_gbps = d.capacity_gbps

                # Загрузка линий.
                for u, v in zip(path[:-1], path[1:]):
                    fibers = self.network.get_fibers_between(u, v)
                    if not fibers:
                        continue
                    fiber = min(fibers, key=lambda f: f.length_km)
                    if fiber.fiber_id not in self.fiber_loads:
                        self.fiber_loads[fiber.fiber_id] = FiberLoad(fiber_id=fiber.fiber_id)
                    fl = self.fiber_loads[fiber.fiber_id]
                    fl.total_load_gbps += load_gbps
                    if d.direction_id not in fl.directions:
                        fl.directions.append(d.direction_id)

                    key = (u, v) if u < v else (v, u)
                    dynamic_loads[key] = dynamic_loads.get(key, 0.0) + load_gbps

                # Загрузка узлов (транзитные узлы пути).
                for node_id in path[1:-1]:
                    if node_id not in self.node_loads:
                        self.node_loads[node_id] = NodeLoad(node_id=node_id)
                    nl = self.node_loads[node_id]
                    if d.direction_id not in nl.transit_directions:
                        nl.transit_directions.append(d.direction_id)

        for nl in self.node_loads.values():
            nl.transit_count = len(nl.transit_directions)

        max_fiber_load = max((fl.total_load_gbps for fl in self.fiber_loads.values()), default=0.0)
        if max_fiber_load > 0:
            for fl in self.fiber_loads.values():
                fl.load_ratio = fl.total_load_gbps / max_fiber_load

        max_node_transit = max((nl.transit_count for nl in self.node_loads.values()), default=0)
        if max_node_transit > 0:
            for nl in self.node_loads.values():
                nl.load_ratio = nl.transit_count / max_node_transit

    # --- Нахождение уязвимых элементов (3.2.3) ---

    def find_vulnerable_elements_detailed(
        self,
    ) -> Tuple[List[FiberLoad], List[str], List[NodeLoad], List[str]]:
        """
        Находит уязвимые линии и узлы:
        1) наиболее нагруженные (по относительной/абсолютной нагрузке);
        2) критические по связности для ИН.
        """
        g = self._build_graph()

        # Критичность линий.
        for load in self.fiber_loads.values():
            load.is_critical = False
            fiber = self.network.get_fiber(load.fiber_id)
            if not fiber:
                continue
            if not g.has_edge(fiber.source_node_id, fiber.target_node_id):
                continue

            g.remove_edge(fiber.source_node_id, fiber.target_node_id)
            critical = False
            for d in self.directions.values():
                if not nx.has_path(g, d.source_node_id, d.target_node_id):
                    critical = True
                    break
            load.is_critical = critical
            g.add_edge(fiber.source_node_id, fiber.target_node_id, weight=float(fiber.length_km))

        # Критичность узлов.
        for load in self.node_loads.values():
            load.is_critical = False
            node_id = load.node_id
            if node_id not in g:
                continue

            g_removed = g.copy()
            g_removed.remove_node(node_id)
            critical = False
            for d in self.directions.values():
                if d.source_node_id == node_id or d.target_node_id == node_id:
                    critical = True
                    break
                if d.source_node_id not in g_removed or d.target_node_id not in g_removed:
                    critical = True
                    break
                if not nx.has_path(g_removed, d.source_node_id, d.target_node_id):
                    critical = True
                    break
            load.is_critical = critical

        fiber_sorted = sorted(
            self.fiber_loads.values(),
            key=lambda fl: fl.total_load_gbps,
            reverse=True,
        )
        top_fibers = [fl.fiber_id for fl in fiber_sorted[:10]]

        node_sorted = sorted(
            self.node_loads.values(),
            key=lambda nl: nl.transit_count,
            reverse=True,
        )
        top_nodes = [nl.node_id for nl in node_sorted[:10]]

        return fiber_sorted, top_fibers, node_sorted, top_nodes

    def find_vulnerable_elements(self) -> Tuple[List[FiberLoad], List[str]]:
        """
        Backward-compatible обертка: возвращает только данные по линиям.
        """
        fiber_sorted, top_fibers, _, _ = self.find_vulnerable_elements_detailed()
        return fiber_sorted, top_fibers
