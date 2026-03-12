"""
Анализ топологии сети: построение минимального остовного дерева и
оценка структурной надежности.
"""
from typing import Tuple
import networkx as nx
from core.models.network import Network
from core.models.fiber import FiberType, Fiber


class TopologyAnalyzer:
    """Модуль анализа топологии сети (упрощенный аналог модулей Сетевика)."""

    def __init__(self, network: Network):
        self.network = network

    def _build_graph(self) -> nx.Graph:
        g = nx.Graph()
        for fiber in self.network.fibers.values():
            g.add_edge(
                fiber.source_node_id,
                fiber.target_node_id,
                weight=fiber.length_km,
                fiber_id=fiber.fiber_id,
            )
        return g

    def build_minimum_spanning_tree(self, clear_existing: bool = True) -> int:
        """
        Строит минимальное остовное дерево (МОД) по текущей узловой основе.

        Args:
            clear_existing: Если True - удалить существующие волокна и
                            заменить их ребрами МОД.

        Returns:
            Количество созданных волокон.
        """
        g = nx.Graph()
        # Узлы добавляем с нулевыми весами
        for node_id in self.network.nodes.keys():
            g.add_node(node_id)

        # Если уже есть волокна - используем их длины,
        # иначе построим полный граф по расстояниям (если есть координаты).
        if self.network.fibers:
            for fiber in self.network.fibers.values():
                g.add_edge(
                    fiber.source_node_id,
                    fiber.target_node_id,
                    weight=fiber.length_km,
                )
        else:
            # Полносвязный граф по координатам
            for i, src in enumerate(self.network.nodes.values()):
                for j, dst in enumerate(self.network.nodes.values()):
                    if j <= i:
                        continue
                    if src.latitude is None or src.longitude is None:
                        continue
                    if dst.latitude is None or dst.longitude is None:
                        continue
                    dist = src.distance_to(dst)
                    g.add_edge(src.node_id, dst.node_id, weight=dist)

        if g.number_of_edges() == 0 or g.number_of_nodes() == 0:
            return 0

        mst = nx.minimum_spanning_tree(g, weight="weight")

        if clear_existing:
            self.network.fibers.clear()

        created = 0
        for u, v, data in mst.edges(data=True):
            length = float(data.get("weight", 0.0))
            fiber_id = f"F_MST_{created+1}"
            fiber = Fiber(
                fiber_id=fiber_id,
                source_node_id=u,
                target_node_id=v,
                length_km=length,
                fiber_type=FiberType.G652,
            )
            self.network.add_fiber(fiber)
            created += 1

        return created

    def compute_structural_reliability(self) -> Tuple[float, int]:
        """
        Упрощенная оценка структурной надежности сети.

        Возвращает индекс R в диапазоне [0, 1] и минимальное
        реберное связывание сети (edge connectivity).

        Интерпретация:
        - edge_connectivity = 0 или 1 → сеть уязвима (любая линия может "разорвать" граф);
        - чем выше edge_connectivity, тем надежнее сеть.
        """
        g = self._build_graph()
        if g.number_of_nodes() < 2:
            return 0.0, 0

        # Минимальное число ребер, которые нужно удалить, чтобы граф стал несвязным
        try:
            k_edge = nx.edge_connectivity(g)
        except nx.NetworkXError:
            k_edge = 0

        # Нормируем на (N-1) — максимум для полного графа
        n = g.number_of_nodes()
        max_possible = max(n - 1, 1)
        reliability_index = min(1.0, max(0.0, k_edge / max_possible))

        return reliability_index, k_edge
