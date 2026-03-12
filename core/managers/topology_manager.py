"""
Менеджер топологии сети.
Управление узлами/волокнами, автопостроение сетки, трассировка и поиск магистрали.
"""
from __future__ import annotations

from itertools import combinations
import json
import math
from typing import Dict, Iterable, List, Optional, Set, Tuple
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

import networkx as nx
import numpy as np

from core.models.network import Network
from core.models.node import Node, NodeType
from core.models.fiber import Fiber, FiberType


class TopologyManager:
    """Класс для управления топологией сети."""

    def __init__(self, network: Network):
        self.network = network

    def create_node(
        self,
        node_id: str,
        name: str,
        node_type: NodeType,
        latitude: Optional[float] = None,
        longitude: Optional[float] = None,
        territory: str = "",
        organization: str = "",
    ) -> Node:
        """Создает и добавляет новый узел."""
        node = Node(
            node_id=node_id,
            node_type=node_type,
            name=name,
            latitude=latitude,
            longitude=longitude,
            territory=territory,
            organization=organization,
        )
        self.network.add_node(node)
        return node

    def create_fiber(
        self,
        fiber_id: str,
        source_id: str,
        target_id: str,
        length_km: float,
        fiber_type: FiberType = FiberType.G652,
    ) -> Optional[Fiber]:
        """Создает и добавляет новое волокно."""
        if source_id not in self.network.nodes:
            return None
        if target_id not in self.network.nodes:
            return None

        fiber = Fiber(
            fiber_id=fiber_id,
            source_node_id=source_id,
            target_node_id=target_id,
            length_km=length_km,
            fiber_type=fiber_type,
        )
        self.network.add_fiber(fiber)
        return fiber

    def calculate_fiber_length_from_coordinates(
        self, source_id: str, target_id: str
    ) -> Optional[float]:
        """Вычисляет длину волокна из координат узлов."""
        source_node = self.network.get_node(source_id)
        target_node = self.network.get_node(target_id)

        if not source_node or not target_node:
            return None

        return source_node.distance_to(target_node)

    def get_connected_nodes(self, node_id: str) -> List[str]:
        """Получает список узлов, соединенных с данным узлом."""
        connected = set()

        for fiber in self.network.fibers.values():
            if fiber.source_node_id == node_id:
                connected.add(fiber.target_node_id)
            elif fiber.target_node_id == node_id:
                connected.add(fiber.source_node_id)

        return list(connected)

    @staticmethod
    def calculate_great_circle_distance(
        lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Вычисляет расстояние между двумя точками на Земле (формула Хаверсина).
        Возвращает расстояние в километрах.
        """
        r = 6371.0

        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.asin(math.sqrt(a))

        return r * c

    def _nodes_with_coords(self) -> Dict[str, Tuple[float, float]]:
        coords: Dict[str, Tuple[float, float]] = {}
        for node in self.network.nodes.values():
            if node.latitude is None or node.longitude is None:
                continue
            coords[node.node_id] = (float(node.latitude), float(node.longitude))
        return coords

    @staticmethod
    def _edge_key(u: str, v: str) -> Tuple[str, str]:
        return (u, v) if u < v else (v, u)

    def _all_candidate_edges(
        self, coords: Dict[str, Tuple[float, float]]
    ) -> Dict[Tuple[str, str], float]:
        edges: Dict[Tuple[str, str], float] = {}
        ids = list(coords.keys())
        for i, src in enumerate(ids):
            for dst in ids[i + 1 :]:
                lat1, lon1 = coords[src]
                lat2, lon2 = coords[dst]
                dist = self.calculate_great_circle_distance(lat1, lon1, lat2, lon2)
                edges[self._edge_key(src, dst)] = dist
        return edges

    def build_minimum_spanning_tree(self) -> List[Fiber]:
        """
        Строит минимальное остовное дерево (МОД) по узловой основе.
        Возвращает список добавленных волокон.
        """
        coords = self._nodes_with_coords()
        if len(coords) < 2:
            return []

        all_edges = self._all_candidate_edges(coords)
        g = nx.Graph()
        g.add_nodes_from(coords.keys())
        for (u, v), w in all_edges.items():
            g.add_edge(u, v, weight=w)

        mst = nx.minimum_spanning_tree(g, weight="weight")

        self.network.fibers.clear()
        created: List[Fiber] = []
        for idx, (u, v, data) in enumerate(mst.edges(data=True), start=1):
            fiber = Fiber(
                fiber_id=f"MST_{idx}",
                source_node_id=u,
                target_node_id=v,
                length_km=float(data.get("weight", 0.0)),
                fiber_type=FiberType.G652,
            )
            self.network.add_fiber(fiber)
            created.append(fiber)
        return created

    def _triangulation_seed(
        self,
        coords: Dict[str, Tuple[float, float]],
        all_edges: Dict[Tuple[str, str], float],
    ) -> Set[Tuple[str, str]]:
        edge_keys: Set[Tuple[str, str]] = set()
        node_ids = list(coords.keys())

        if len(node_ids) < 3:
            for u, v in combinations(node_ids, 2):
                edge_keys.add(self._edge_key(u, v))
            return edge_keys

        try:
            from scipy.spatial import Delaunay

            points = np.array([[coords[n][1], coords[n][0]] for n in node_ids])  # lon, lat
            tri = Delaunay(points)
            for simplex in tri.simplices:
                pairs = [
                    (simplex[0], simplex[1]),
                    (simplex[1], simplex[2]),
                    (simplex[0], simplex[2]),
                ]
                for i, j in pairs:
                    edge_keys.add(self._edge_key(node_ids[i], node_ids[j]))
        except Exception:
            # Fallback: k-ближайших соседей (k=3)
            for src in node_ids:
                sorted_neighbors = sorted(
                    (ek for ek in all_edges.keys() if src in ek),
                    key=lambda ek: all_edges[ek],
                )
                for ek in sorted_neighbors[:3]:
                    edge_keys.add(ek)

        return edge_keys

    @staticmethod
    def _segment_intersection(
        a1: Tuple[float, float],
        a2: Tuple[float, float],
        b1: Tuple[float, float],
        b2: Tuple[float, float],
    ) -> bool:
        # Используем lon/lat как декартовы координаты для эвристики пересечения.
        def orient(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

        o1 = orient(a1, a2, b1)
        o2 = orient(a1, a2, b2)
        o3 = orient(b1, b2, a1)
        o4 = orient(b1, b2, a2)

        return (o1 * o2 < 0) and (o3 * o4 < 0)

    def _crossing_seed(
        self,
        coords: Dict[str, Tuple[float, float]],
        all_edges: Dict[Tuple[str, str], float],
    ) -> Set[Tuple[str, str]]:
        node_ids = list(coords.keys())
        if len(node_ids) < 3:
            return set(all_edges.keys())

        # Базовый цикл вокруг центра.
        center_lat = sum(c[0] for c in coords.values()) / len(coords)
        center_lon = sum(c[1] for c in coords.values()) / len(coords)
        ordered = sorted(
            node_ids,
            key=lambda n: math.atan2(coords[n][0] - center_lat, coords[n][1] - center_lon),
        )

        selected: Set[Tuple[str, str]] = set()
        for i in range(len(ordered)):
            u = ordered[i]
            v = ordered[(i + 1) % len(ordered)]
            selected.add(self._edge_key(u, v))

        remaining = [ek for ek in all_edges.keys() if ek not in selected]
        scored: List[Tuple[int, float, Tuple[str, str]]] = []
        for ek in remaining:
            u, v = ek
            ua = (coords[u][1], coords[u][0])  # lon, lat
            va = (coords[v][1], coords[v][0])
            intersections = 0
            for ex in selected:
                x, y = ex
                if len({u, v, x, y}) < 4:
                    continue
                xb = (coords[x][1], coords[x][0])
                yb = (coords[y][1], coords[y][0])
                if self._segment_intersection(ua, va, xb, yb):
                    intersections += 1
            scored.append((intersections, all_edges[ek], ek))

        scored.sort(key=lambda x: (-x[0], x[1]))
        for intersections, _, ek in scored:
            if intersections <= 0:
                continue
            selected.add(ek)

        return selected

    @staticmethod
    def _spanning_tree_log_count(g: nx.Graph) -> float:
        if g.number_of_nodes() < 2 or not nx.is_connected(g):
            return float("-inf")
        nodes = list(g.nodes())
        lap = nx.laplacian_matrix(g, nodelist=nodes, weight=None).astype(float).toarray()
        minor = lap[1:, 1:]
        sign, logdet = np.linalg.slogdet(minor + 1e-12 * np.eye(minor.shape[0]))
        if sign <= 0:
            return float("-inf")
        return float(logdet)

    def _spanning_tree_maximization_seed(
        self,
        coords: Dict[str, Tuple[float, float]],
        all_edges: Dict[Tuple[str, str], float],
        target_edges: int,
    ) -> Set[Tuple[str, str]]:
        g = nx.Graph()
        g.add_nodes_from(coords.keys())
        for (u, v), w in all_edges.items():
            g.add_edge(u, v, weight=w)
        mst = nx.minimum_spanning_tree(g, weight="weight")

        selected: Set[Tuple[str, str]] = {
            self._edge_key(u, v) for u, v in mst.edges()
        }

        while len(selected) < target_edges:
            base = nx.Graph()
            base.add_nodes_from(coords.keys())
            for u, v in selected:
                base.add_edge(u, v)
            current_score = self._spanning_tree_log_count(base)

            best_edge: Optional[Tuple[str, str]] = None
            best_gain = float("-inf")
            for ek in all_edges.keys():
                if ek in selected:
                    continue
                u, v = ek
                base.add_edge(u, v)
                new_score = self._spanning_tree_log_count(base)
                base.remove_edge(u, v)
                gain = new_score - current_score
                if gain > best_gain:
                    best_gain = gain
                    best_edge = ek

            if not best_edge:
                break
            selected.add(best_edge)

        return selected

    @staticmethod
    def _edge_connectivity_safe(g: nx.Graph) -> int:
        if g.number_of_nodes() < 2 or not nx.is_connected(g):
            return 0
        try:
            return int(nx.edge_connectivity(g))
        except nx.NetworkXError:
            return 0

    def _prune_edges(
        self,
        edge_keys: Set[Tuple[str, str]],
        all_edges: Dict[Tuple[str, str], float],
        target_connectivity: int,
        max_edges: Optional[int],
        node_ids: Iterable[str],
    ) -> Set[Tuple[str, str]]:
        g = nx.Graph()
        g.add_nodes_from(node_ids)
        for u, v in edge_keys:
            g.add_edge(u, v, weight=all_edges[self._edge_key(u, v)])

        # Догарантируем связность (если seed оказался разреженным).
        if not nx.is_connected(g):
            for (u, v), _ in sorted(all_edges.items(), key=lambda item: item[1]):
                if g.has_edge(u, v):
                    continue
                g.add_edge(u, v, weight=all_edges[(u, v)])
                if nx.is_connected(g):
                    break

        # Если connectivity недотягивает - наращиваем кратчайшими линиями.
        while self._edge_connectivity_safe(g) < max(1, target_connectivity):
            added = False
            for (u, v), _ in sorted(all_edges.items(), key=lambda item: item[1]):
                if g.has_edge(u, v):
                    continue
                g.add_edge(u, v, weight=all_edges[(u, v)])
                added = True
                if self._edge_connectivity_safe(g) >= max(1, target_connectivity):
                    break
            if not added:
                break

        # Удаляем длинные линии, если свойства сети сохраняются.
        removable_edges = sorted(g.edges(data=True), key=lambda e: float(e[2]["weight"]), reverse=True)
        for u, v, data in removable_edges:
            if max_edges is not None and g.number_of_edges() <= max_edges:
                break
            if g.number_of_edges() <= (g.number_of_nodes() - 1):
                break
            g.remove_edge(u, v)
            if not nx.is_connected(g) or self._edge_connectivity_safe(g) < max(1, target_connectivity):
                g.add_edge(u, v, weight=float(data["weight"]))

        return {self._edge_key(u, v) for u, v in g.edges()}

    def build_line_grid(
        self,
        method: str = "triangulation",
        target_connectivity: int = 2,
        max_edges: Optional[int] = None,
        replace_existing: bool = True,
    ) -> List[Fiber]:
        """
        Автоматическое построение сетки линий (раздел 3.1.2.3).

        Args:
            method: triangulation | spanning_tree_maximization | crossing_segments
            target_connectivity: требуемая реберная связность (минимум 1)
            max_edges: ограничение на число линий (None - автоматический подбор)
            replace_existing: если True, существующие волокна очищаются
        """
        coords = self._nodes_with_coords()
        if len(coords) < 2:
            return []

        all_edges = self._all_candidate_edges(coords)
        if not all_edges:
            return []

        n = len(coords)
        total_possible = len(all_edges)
        if max_edges is None:
            max_edges = min(total_possible, max(n - 1, int(target_connectivity * n / 2) + n - 1))
        max_edges = max(n - 1, min(total_possible, int(max_edges)))

        method = method.strip().lower()
        if method == "triangulation":
            edge_keys = self._triangulation_seed(coords, all_edges)
        elif method == "spanning_tree_maximization":
            edge_keys = self._spanning_tree_maximization_seed(coords, all_edges, target_edges=max_edges)
        elif method == "crossing_segments":
            edge_keys = self._crossing_seed(coords, all_edges)
        else:
            raise ValueError(f"Неизвестный метод автосетки: {method}")

        edge_keys = self._prune_edges(
            edge_keys=edge_keys,
            all_edges=all_edges,
            target_connectivity=max(1, int(target_connectivity)),
            max_edges=max_edges,
            node_ids=coords.keys(),
        )

        if replace_existing:
            self.network.fibers.clear()

        created: List[Fiber] = []
        for idx, (u, v) in enumerate(
            sorted(edge_keys, key=lambda ek: all_edges[ek]),
            start=1,
        ):
            fiber = Fiber(
                fiber_id=f"AUTO_{idx}",
                source_node_id=u,
                target_node_id=v,
                length_km=float(all_edges[(u, v)]),
                fiber_type=FiberType.G652,
            )
            self.network.add_fiber(fiber)
            created.append(fiber)

        return created

    @staticmethod
    def _route_url(src_lat: float, src_lon: float, dst_lat: float, dst_lon: float) -> str:
        return (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{src_lon:.6f},{src_lat:.6f};{dst_lon:.6f},{dst_lat:.6f}"
            "?overview=full&geometries=geojson"
        )

    def trace_fiber(self, fiber_id: str, use_roads: bool = True) -> bool:
        """
        Трассирует линию связи.
        use_roads=True - авто-трассировка по дорожному графу (OSRM),
        use_roads=False - прямая линия между узлами.
        """
        fiber = self.network.get_fiber(fiber_id)
        if not fiber:
            return False

        src = self.network.get_node(fiber.source_node_id)
        dst = self.network.get_node(fiber.target_node_id)
        if not src or not dst:
            return False
        if src.latitude is None or src.longitude is None:
            return False
        if dst.latitude is None or dst.longitude is None:
            return False

        if not use_roads:
            fiber.route_points = []
            fiber.length_km = self.calculate_great_circle_distance(
                src.latitude, src.longitude, dst.latitude, dst.longitude
            )
            return True

        url = self._route_url(src.latitude, src.longitude, dst.latitude, dst.longitude)
        try:
            with urlopen(url, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (URLError, HTTPError, TimeoutError, OSError, ValueError):
            return False

        routes = payload.get("routes", [])
        if not routes:
            return False

        best = routes[0]
        coords = best.get("geometry", {}).get("coordinates", [])
        if len(coords) < 2:
            return False

        # OSRM отдает [lon, lat]
        fiber.route_points = [(float(lat), float(lon)) for lon, lat in coords]
        distance_m = float(best.get("distance", 0.0))
        if distance_m > 0:
            fiber.length_km = distance_m / 1000.0
        else:
            fiber.length_km = self.calculate_great_circle_distance(
                src.latitude, src.longitude, dst.latitude, dst.longitude
            )

        return True

    def trace_all_fibers(self, use_roads: bool = True) -> Tuple[int, int]:
        """Трассирует все волокна. Возвращает (успешно, всего)."""
        ok = 0
        total = len(self.network.fibers)
        for fiber_id in list(self.network.fibers.keys()):
            if self.trace_fiber(fiber_id, use_roads=use_roads):
                ok += 1
        return ok, total

    def clear_trunk_marks(self) -> None:
        for fiber in self.network.fibers.values():
            fiber.is_trunk = False

    def find_trunk_network(
        self,
        min_regions: int = 2,
        percentile: float = 0.75,
    ) -> Tuple[List[str], Dict[str, float]]:
        """
        Находит магистральную часть сети (3.1.4) по межрегиональным кратчайшим путям.

        Returns:
            (список trunk fiber_id, словарь score по fiber_id)
        """
        self.clear_trunk_marks()

        g = nx.Graph()
        for node_id in self.network.nodes.keys():
            g.add_node(node_id)

        edge_to_fiber: Dict[Tuple[str, str], str] = {}
        for fiber in self.network.fibers.values():
            ek = self._edge_key(fiber.source_node_id, fiber.target_node_id)
            g.add_edge(
                fiber.source_node_id,
                fiber.target_node_id,
                weight=float(fiber.length_km),
            )
            # при мульти-ребрах оставляем более короткое
            prev = edge_to_fiber.get(ek)
            if prev is None:
                edge_to_fiber[ek] = fiber.fiber_id
            else:
                prev_f = self.network.get_fiber(prev)
                if prev_f and fiber.length_km < prev_f.length_km:
                    edge_to_fiber[ek] = fiber.fiber_id

        territories: Dict[str, List[str]] = {}
        for node in self.network.nodes.values():
            territory = (node.territory or "").strip()
            if not territory:
                continue
            territories.setdefault(territory, []).append(node.node_id)

        if len(territories) < min_regions:
            return [], {}

        scores_by_edge: Dict[Tuple[str, str], float] = {}
        region_items = list(territories.items())
        for i, (_, nodes_a) in enumerate(region_items):
            for _, nodes_b in region_items[i + 1 :]:
                for src in nodes_a:
                    for dst in nodes_b:
                        if src == dst:
                            continue
                        try:
                            path = nx.shortest_path(g, src, dst, weight="weight")
                        except nx.NetworkXNoPath:
                            continue
                        for u, v in zip(path[:-1], path[1:]):
                            ek = self._edge_key(u, v)
                            scores_by_edge[ek] = scores_by_edge.get(ek, 0.0) + 1.0

        if not scores_by_edge:
            return [], {}

        values = np.array(list(scores_by_edge.values()), dtype=float)
        threshold = float(np.quantile(values, min(max(percentile, 0.0), 1.0)))

        trunk_ids: List[str] = []
        score_by_fiber_id: Dict[str, float] = {}
        for ek, score in scores_by_edge.items():
            if score < threshold:
                continue
            fiber_id = edge_to_fiber.get(ek)
            if not fiber_id:
                continue
            fiber = self.network.get_fiber(fiber_id)
            if not fiber:
                continue
            fiber.is_trunk = True
            trunk_ids.append(fiber_id)
            score_by_fiber_id[fiber_id] = score

        trunk_ids.sort(key=lambda fid: score_by_fiber_id.get(fid, 0.0), reverse=True)
        return trunk_ids, score_by_fiber_id
