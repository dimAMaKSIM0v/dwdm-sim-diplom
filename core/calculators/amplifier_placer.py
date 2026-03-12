"""
РђР»РіРѕСЂРёС‚Рј Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРѕР№ СЂР°СЃСЃС‚Р°РЅРѕРІРєРё РѕРїС‚РёС‡РµСЃРєРёС… СѓСЃРёР»РёС‚РµР»РµР№ (EDFA)
Р­С‚Рѕ РєР»СЋС‡РµРІРѕР№ РјРѕРґСѓР»СЊ РїСЂРёР»РѕР¶РµРЅРёСЏ - СЃРµСЂРґС†Рµ РїСЂРѕРµРєС‚Р°
"""
from typing import List, Tuple, Optional
from math import asin, cos, radians, sin, sqrt
import networkx as nx
from core.models.network import Network
from core.models.node import Node, NodeType
from core.models.fiber import Fiber
from core.models.equipment import Equipment, EquipmentType
from core.calculators.attenuation import calculate_path_attenuation
from core.calculators.power_budget import calculate_power_profile


class AmplifierPlacer:
    """
    РљР»Р°СЃСЃ РґР»СЏ Р°РІС‚РѕРјР°С‚РёС‡РµСЃРєРѕР№ СЂР°СЃСЃС‚Р°РЅРѕРІРєРё РѕРїС‚РёС‡РµСЃРєРёС… СѓСЃРёР»РёС‚РµР»РµР№
    """
    
    def __init__(self, network: Network, 
                 max_span_loss_db: float = 22.0,
                 amplifier_gain_db: float = 22.0,
                 amplifier_noise_figure_db: float = 5.0):
        """
        Args:
            network: РњРѕРґРµР»СЊ СЃРµС‚Рё
            max_span_loss_db: РњР°РєСЃРёРјР°Р»СЊРЅРѕ РґРѕРїСѓСЃС‚РёРјРѕРµ Р·Р°С‚СѓС…Р°РЅРёРµ СѓС‡Р°СЃС‚РєР° (РґР‘)
            amplifier_gain_db: РљРѕСЌС„С„РёС†РёРµРЅС‚ СѓСЃРёР»РµРЅРёСЏ СѓСЃРёР»РёС‚РµР»СЏ (РґР‘)
            amplifier_noise_figure_db: РЁСѓРјРѕРІР°СЏ С„РёРіСѓСЂР° СѓСЃРёР»РёС‚РµР»СЏ (РґР‘)
        """
        self.network = network
        self.max_span_loss_db = max_span_loss_db
        self.amplifier_gain_db = amplifier_gain_db
        self.amplifier_noise_figure_db = amplifier_noise_figure_db

    @staticmethod
    def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Р Р°СЃСЃС‚РѕСЏРЅРёРµ РјРµР¶РґСѓ РґРІСѓРјСЏ С‚РѕС‡РєР°РјРё РІ РєРј (С„РѕСЂРјСѓР»Р° РҐР°РІРµСЂСЃРёРЅР°)."""
        radius_km = 6371.0
        d_lat = radians(lat2 - lat1)
        d_lon = radians(lon2 - lon1)
        lat1_rad = radians(lat1)
        lat2_rad = radians(lat2)
        a = sin(d_lat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(d_lon / 2) ** 2
        return 2 * radius_km * asin(sqrt(max(a, 0.0)))

    @classmethod
    def _polyline_cumulative_lengths(cls, points: List[Tuple[float, float]]) -> List[float]:
        """РќР°РєРѕРїР»РµРЅРЅС‹Рµ СЂР°СЃСЃС‚РѕСЏРЅРёСЏ РїРѕ РїРѕР»РёР»РёРЅРёРё."""
        if not points:
            return [0.0]
        cumulative = [0.0]
        for idx in range(len(points) - 1):
            lat1, lon1 = points[idx]
            lat2, lon2 = points[idx + 1]
            seg_len = cls._haversine_km(lat1, lon1, lat2, lon2)
            cumulative.append(cumulative[-1] + seg_len)
        return cumulative

    @staticmethod
    def _interpolate_point(
        start: Tuple[float, float],
        end: Tuple[float, float],
        ratio: float,
    ) -> Tuple[float, float]:
        lat = start[0] + (end[0] - start[0]) * ratio
        lon = start[1] + (end[1] - start[1]) * ratio
        return (lat, lon)

    @classmethod
    def _point_on_polyline(
        cls,
        points: List[Tuple[float, float]],
        cumulative_lengths: List[float],
        distance_km: float,
    ) -> Tuple[float, float]:
        """РўРѕС‡РєР° РЅР° РїРѕР»РёР»РёРЅРёРё РЅР° Р·Р°РґР°РЅРЅРѕР№ РґР»РёРЅРµ РѕС‚ РЅР°С‡Р°Р»Р°."""
        if not points:
            return (0.0, 0.0)
        if len(points) == 1:
            return points[0]

        total_km = cumulative_lengths[-1] if cumulative_lengths else 0.0
        if total_km <= 0:
            return points[0]

        target = min(max(distance_km, 0.0), total_km)
        for idx in range(len(points) - 1):
            start_km = cumulative_lengths[idx]
            end_km = cumulative_lengths[idx + 1]
            if target <= end_km or idx == len(points) - 2:
                seg_len = max(end_km - start_km, 1e-9)
                ratio = (target - start_km) / seg_len
                return cls._interpolate_point(points[idx], points[idx + 1], ratio)
        return points[-1]

    @classmethod
    def _slice_polyline(
        cls,
        points: List[Tuple[float, float]],
        cumulative_lengths: List[float],
        start_km: float,
        end_km: float,
    ) -> List[Tuple[float, float]]:
        """Р¤СЂР°РіРјРµРЅС‚ РїРѕР»РёР»РёРЅРёРё РјРµР¶РґСѓ РґРІСѓРјСЏ СЂР°СЃСЃС‚РѕСЏРЅРёСЏРјРё РѕС‚ РЅР°С‡Р°Р»Р°."""
        if not points:
            return []
        if len(points) == 1:
            return [points[0], points[0]]

        total_km = cumulative_lengths[-1] if cumulative_lengths else 0.0
        if total_km <= 0:
            return [points[0], points[-1]]

        start = min(max(start_km, 0.0), total_km)
        end = min(max(end_km, 0.0), total_km)
        if end < start:
            start, end = end, start

        start_point = cls._point_on_polyline(points, cumulative_lengths, start)
        end_point = cls._point_on_polyline(points, cumulative_lengths, end)

        result: List[Tuple[float, float]] = [start_point]
        for idx in range(1, len(points) - 1):
            point_km = cumulative_lengths[idx]
            if start < point_km < end:
                result.append(points[idx])
        result.append(end_point)

        # РЈР±РёСЂР°РµРј РїРѕРІС‚РѕСЂСЏСЋС‰РёРµСЃСЏ РїРѕРґСЂСЏРґ С‚РѕС‡РєРё.
        cleaned: List[Tuple[float, float]] = []
        for lat, lon in result:
            if not cleaned:
                cleaned.append((lat, lon))
                continue
            prev_lat, prev_lon = cleaned[-1]
            if abs(prev_lat - lat) > 1e-9 or abs(prev_lon - lon) > 1e-9:
                cleaned.append((lat, lon))
        if len(cleaned) == 1:
            cleaned.append(cleaned[0])
        return cleaned
    
    def place_amplifiers_on_path(self, path: List[str]) -> List[Tuple[str, int]]:
        """
        Р Р°СЃСЃС‚Р°РІР»СЏРµС‚ СѓСЃРёР»РёС‚РµР»Рё РЅР° Р·Р°РґР°РЅРЅРѕРј РїСѓС‚Рё
        
        РђР»РіРѕСЂРёС‚Рј:
        1. РџСЂРѕС…РѕРґРёРј РїРѕ РїСѓС‚Рё, СЃСѓРјРјРёСЂСѓСЏ Р·Р°С‚СѓС…Р°РЅРёРµ
        2. РљРѕРіРґР° РЅР°РєРѕРїР»РµРЅРЅРѕРµ Р·Р°С‚СѓС…Р°РЅРёРµ РїСЂРµРІС‹С€Р°РµС‚ max_span_loss_db, СЃС‚Р°РІРёРј EDFA
        3. РЎР±СЂР°СЃС‹РІР°РµРј СЃС‡РµС‚С‡РёРє Р·Р°С‚СѓС…Р°РЅРёСЏ Рё РїСЂРѕРґРѕР»Р¶Р°РµРј
        
        Args:
            path: РЎРїРёСЃРѕРє node_id, РѕР±СЂР°Р·СѓСЋС‰РёС… РїСѓС‚СЊ
            
        Returns:
            РЎРїРёСЃРѕРє РєРѕСЂС‚РµР¶РµР№ (node_id, amplifier_count) - РіРґРµ СЂР°Р·РјРµСЃС‚РёС‚СЊ СѓСЃРёР»РёС‚РµР»Рё
        """
        amplifier_positions = []
        
        if len(path) < 2:
            return amplifier_positions
        
        accumulated_loss = 0.0
        fibers = self.network.get_path_fibers(path)
        
        for i, fiber in enumerate(fibers):
            fiber_loss = fiber.calculate_fiber_loss()
            accumulated_loss += fiber_loss
            
            # РџСЂРѕРІРµСЂСЏРµРј, РЅСѓР¶РЅРѕ Р»Рё РїРѕСЃС‚Р°РІРёС‚СЊ СѓСЃРёР»РёС‚РµР»СЊ РїРµСЂРµРґ СЃР»РµРґСѓСЋС‰РёРј СѓС‡Р°СЃС‚РєРѕРј
            if accumulated_loss > self.max_span_loss_db:
                # РЎС‚Р°РІРёРј СѓСЃРёР»РёС‚РµР»СЊ РІ С†РµР»РµРІРѕРј СѓР·Р»Рµ РїСЂРµРґС‹РґСѓС‰РµРіРѕ РІРѕР»РѕРєРЅР°
                target_node_id = fiber.target_node_id
                amplifier_positions.append((target_node_id, 1))
                
                # РЈС‡РёС‚С‹РІР°РµРј, С‡С‚Рѕ СѓСЃРёР»РёС‚РµР»СЊ РєРѕРјРїРµРЅСЃРёСЂСѓРµС‚ РїРѕС‚РµСЂРё РїСЂРµРґС‹РґСѓС‰РµРіРѕ СѓС‡Р°СЃС‚РєР°
                # РќРѕ РѕСЃС‚Р°РІР»СЏРµРј РЅРµР±РѕР»СЊС€РѕР№ Р·Р°РїР°СЃ РґР»СЏ СЃР»РµРґСѓСЋС‰РµРіРѕ СѓС‡Р°СЃС‚РєР°
                accumulated_loss = fiber_loss
        
        return amplifier_positions

    def split_long_fibers_and_insert_inline_edfa(
        self,
        path: List[str],
        equipment_budget_db: Optional[float] = None,
    ) -> int:
        """
        Разбивает длинные волокна на участки и вставляет промежуточные EDFA-узлы.

        Если передан equipment_budget_db, длина усилительного участка считается как в Excel:
        P = ROUND((B - E - M) / alpha + (H / D), 0)
        где B - энергетический запас аппаратуры, E - резерв линии,
        M = 2 * потери на коннекторах, H - потери на сварке, D - строительная длина.
        """
        if len(path) < 2:
            return 0

        inline_gain_db = self.amplifier_gain_db
        if equipment_budget_db is not None and equipment_budget_db > 0:
            inline_gain_db = float(equipment_budget_db)

        fibers = self.network.get_path_fibers(path)
        added = 0

        for fiber in list(fibers):
            alpha = fiber.get_attenuation_per_km()
            if alpha <= 0:
                continue

            max_span_km: Optional[float] = None
            if equipment_budget_db is not None and equipment_budget_db > 0:
                construction_len = max(float(getattr(fiber, "splice_interval_km", 25.0)), 0.001)
                splice_loss = float(getattr(fiber, "splice_losses_db", 0.02))
                reserve_loss = float(getattr(fiber, "line_reserve_db", 0.0))
                connector_loss = 2.0 * float(getattr(fiber, "connector_losses_db", 0.3))
                available_budget = equipment_budget_db - reserve_loss - connector_loss
                if available_budget > 0:
                    excel_span = Fiber._excel_round(
                        (available_budget / alpha) + (splice_loss / construction_len)
                    )
                    if excel_span > 0:
                        max_span_km = float(excel_span)

            if max_span_km is None:
                loss_per_km = fiber.loss_per_km_estimate()
                if loss_per_km <= 0:
                    continue
                max_span_km = self.max_span_loss_db / loss_per_km

            if max_span_km <= 0 or fiber.length_km <= max_span_km:
                continue

            segment_lengths: List[float] = []
            remaining = float(fiber.length_km)
            while remaining > max_span_km:
                segment_lengths.append(float(max_span_km))
                remaining -= max_span_km
            segment_lengths.append(float(remaining))
            num_segments = len(segment_lengths)

            if fiber.fiber_id in self.network.fibers:
                del self.network.fibers[fiber.fiber_id]

            src_node = self.network.get_node(fiber.source_node_id)
            dst_node = self.network.get_node(fiber.target_node_id)
            if not src_node or not dst_node:
                continue

            polyline_points: List[Tuple[float, float]] = []
            if fiber.route_points and len(fiber.route_points) >= 2:
                polyline_points = [(float(lat), float(lon)) for lat, lon in fiber.route_points]
            elif (
                src_node.latitude is not None
                and src_node.longitude is not None
                and dst_node.latitude is not None
                and dst_node.longitude is not None
            ):
                polyline_points = [
                    (float(src_node.latitude), float(src_node.longitude)),
                    (float(dst_node.latitude), float(dst_node.longitude)),
                ]

            cumulative_lengths = self._polyline_cumulative_lengths(polyline_points) if polyline_points else [0.0]
            polyline_total_km = cumulative_lengths[-1] if cumulative_lengths else 0.0

            original_splice_count = fiber.calculate_splice_count()
            splice_positions: List[float] = []
            if original_splice_count > 0 and fiber.length_km > 0:
                interval_km = max(float(getattr(fiber, "splice_interval_km", 25.0)), 0.001)
                for idx in range(1, original_splice_count + 1):
                    pos = idx * interval_km
                    if pos <= fiber.length_km + 1e-9:
                        splice_positions.append(min(pos, float(fiber.length_km)))

            def segment_splices(start_km: float, end_km: float) -> int:
                return sum(1 for pos in splice_positions if start_km < pos <= end_km + 1e-9)

            prev_node_id = fiber.source_node_id
            start_km = 0.0

            for seg_idx in range(1, num_segments):
                segment_len = segment_lengths[seg_idx - 1]
                end_km = start_km + segment_len
                end_fraction = (end_km / fiber.length_km) if fiber.length_km > 0 else 0.0
                start_fraction = (start_km / fiber.length_km) if fiber.length_km > 0 else 0.0

                edfa_node_id = f"EDFA_{fiber.fiber_id}_{seg_idx}"
                edfa_lat: Optional[float] = None
                edfa_lon: Optional[float] = None
                seg_route_points: List[Tuple[float, float]] = []
                if polyline_points and polyline_total_km > 0:
                    point_km = polyline_total_km * end_fraction
                    edfa_lat, edfa_lon = self._point_on_polyline(
                        polyline_points,
                        cumulative_lengths,
                        point_km,
                    )
                    seg_route_points = self._slice_polyline(
                        polyline_points,
                        cumulative_lengths,
                        polyline_total_km * start_fraction,
                        point_km,
                    )

                edfa_node = Node(
                    node_id=edfa_node_id,
                    node_type=NodeType.EDFA,
                    name=f"EDFA {seg_idx}",
                    latitude=edfa_lat,
                    longitude=edfa_lon,
                )
                self.network.add_node(edfa_node)

                eq_id = f"EQ_{edfa_node_id}"
                amplifier = Equipment(
                    equipment_id=eq_id,
                    equipment_type=EquipmentType.EDFA,
                    node_id=edfa_node_id,
                    parameters={
                        "gain": inline_gain_db,
                        "noise_figure": self.amplifier_noise_figure_db,
                        "insertion_loss": 0.5,
                    },
                )
                self.network.add_equipment(amplifier)

                seg_fiber_id = f"{fiber.fiber_id}_S{seg_idx}"
                seg_fiber = Fiber(
                    fiber_id=seg_fiber_id,
                    source_node_id=prev_node_id,
                    target_node_id=edfa_node_id,
                    length_km=segment_len,
                    fiber_type=fiber.fiber_type,
                    attenuation_db_per_km=fiber.attenuation_db_per_km,
                    splice_losses_db=fiber.splice_losses_db,
                    splice_interval_km=getattr(fiber, "splice_interval_km", 4.0),
                    connector_losses_db=0.0,
                    line_reserve_db=0.0,
                    splice_count_override=segment_splices(start_km, end_km),
                    route_points=seg_route_points,
                )
                self.network.add_fiber(seg_fiber)

                prev_node_id = edfa_node_id
                start_km = end_km
                added += 1

            last_len = segment_lengths[-1]
            last_fiber_id = f"{fiber.fiber_id}_S{num_segments}"
            last_route_points: List[Tuple[float, float]] = []
            if polyline_points and polyline_total_km > 0 and fiber.length_km > 0:
                last_route_points = self._slice_polyline(
                    polyline_points,
                    cumulative_lengths,
                    polyline_total_km * (start_km / fiber.length_km),
                    polyline_total_km,
                )

            last_seg = Fiber(
                fiber_id=last_fiber_id,
                source_node_id=prev_node_id,
                target_node_id=fiber.target_node_id,
                length_km=last_len,
                fiber_type=fiber.fiber_type,
                attenuation_db_per_km=fiber.attenuation_db_per_km,
                splice_losses_db=fiber.splice_losses_db,
                splice_interval_km=getattr(fiber, "splice_interval_km", 4.0),
                connector_losses_db=fiber.connector_losses_db,
                line_reserve_db=fiber.line_reserve_db,
                splice_count_override=segment_splices(start_km, float(fiber.length_km)),
                route_points=last_route_points,
            )
            self.network.add_fiber(last_seg)

        return added

    def place_amplifiers_for_channel(self, channel_id: str) -> int:
        """
        Р Р°СЃСЃС‚Р°РІР»СЏРµС‚ СѓСЃРёР»РёС‚РµР»Рё РґР»СЏ РєРѕРЅРєСЂРµС‚РЅРѕРіРѕ РєР°РЅР°Р»Р°
        
        Args:
            channel_id: ID РєР°РЅР°Р»Р°
            
        Returns:
            РљРѕР»РёС‡РµСЃС‚РІРѕ СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅС‹С… СѓСЃРёР»РёС‚РµР»РµР№
        """
        channel = self.network.channels.get(channel_id)
        if not channel or not channel.path:
            return 0
        
        positions = self.place_amplifiers_on_path(channel.path)
        count = 0
        
        for node_id, amplifier_count in positions:
            # РџСЂРѕРІРµСЂСЏРµРј, РЅРµС‚ Р»Рё СѓР¶Рµ СѓСЃРёР»РёС‚РµР»СЏ РІ СЌС‚РѕРј СѓР·Р»Рµ
            node = self.network.get_node(node_id)
            if not node:
                continue
            
            has_amplifier = any(
                self.network.equipment.get(eq_id).equipment_type == EquipmentType.EDFA
                for eq_id in node.equipment
                if self.network.equipment.get(eq_id)
            )
            
            if not has_amplifier:
                # РЎРѕР·РґР°РµРј Рё РґРѕР±Р°РІР»СЏРµРј СѓСЃРёР»РёС‚РµР»СЊ
                amplifier_id = f"EDFA_{node_id}_{channel_id}_{count}"
                amplifier = Equipment(
                    equipment_id=amplifier_id,
                    equipment_type=EquipmentType.EDFA,
                    node_id=node_id,
                    parameters={
                        'gain': self.amplifier_gain_db,
                        'noise_figure': self.amplifier_noise_figure_db,
                        'insertion_loss': 0.5
                    }
                )
                self.network.add_equipment(amplifier)
                count += amplifier_count
        
        return count
    
    def place_amplifiers_for_all_channels(self) -> int:
        """
        Р Р°СЃСЃС‚Р°РІР»СЏРµС‚ СѓСЃРёР»РёС‚РµР»Рё РґР»СЏ РІСЃРµС… РєР°РЅР°Р»РѕРІ РІ СЃРµС‚Рё
        
        Returns:
            РћР±С‰РµРµ РєРѕР»РёС‡РµСЃС‚РІРѕ СѓСЃС‚Р°РЅРѕРІР»РµРЅРЅС‹С… СѓСЃРёР»РёС‚РµР»РµР№
        """
        total_count = 0
        
        for channel_id in self.network.channels.keys():
            count = self.place_amplifiers_for_channel(channel_id)
            total_count += count
        
        return total_count

    # --- РќРѕРІР°СЏ Р»РѕРіРёРєР°: СЂР°Р·Р±РёРµРЅРёРµ РІРѕР»РѕРєРѕРЅ + РїРµСЂРµСЃС‚СЂРѕРµРЅРёРµ РїСѓС‚РµР№ РєР°РЅР°Р»РѕРІ ---

    def _build_graph(self) -> nx.Graph:
        """РЎС‚СЂРѕРёС‚ РіСЂР°С„ СЃРµС‚Рё РїРѕ РІРѕР»РѕРєРЅР°Рј РґР»СЏ РїРѕРёСЃРєР° РїСѓС‚РµР№."""
        g = nx.Graph()
        for fiber in self.network.fibers.values():
            g.add_edge(
                fiber.source_node_id,
                fiber.target_node_id,
                weight=fiber.length_km,
            )
        return g

    def rebuild_path_with_inline_nodes(self, start_id: str, end_id: str) -> List[str]:
        """РќР°С…РѕРґРёС‚ РєСЂР°С‚С‡Р°Р№С€РёР№ РїСѓС‚СЊ РїРѕ РґР»РёРЅРµ РјРµР¶РґСѓ РґРІСѓРјСЏ СѓР·Р»Р°РјРё СЃ СѓС‡РµС‚РѕРј РІСЃС‚Р°РІР»РµРЅРЅС‹С… EDFA."""
        g = self._build_graph()
        try:
            return nx.shortest_path(g, start_id, end_id, weight="weight")
        except nx.NetworkXNoPath:
            return []

    def split_fibers_and_update_channel_path(self, channel_id: str) -> int:
        """
        Р”Р»СЏ Р·Р°РґР°РЅРЅРѕРіРѕ РєР°РЅР°Р»Р°:
        - СЂР°Р·Р±РёРІР°РµС‚ РґР»РёРЅРЅС‹Рµ РІРѕР»РѕРєРЅР° РІРґРѕР»СЊ РµРіРѕ РїСѓС‚Рё РЅР° РїСЂРѕР»РµС‚С‹ СЃ EDFA-СѓР·Р»Р°РјРё;
        - РїРµСЂРµСЃС‚СЂР°РёРІР°РµС‚ path РєР°РЅР°Р»Р° С‚Р°Рє, С‡С‚РѕР±С‹ РѕРЅ РїСЂРѕС…РѕРґРёР» С‡РµСЂРµР· РЅРѕРІС‹Рµ СѓР·Р»С‹.

        Returns:
            РљРѕР»РёС‡РµСЃС‚РІРѕ РґРѕР±Р°РІР»РµРЅРЅС‹С… Р»РёРЅРµР№РЅС‹С… СѓСЃРёР»РёС‚РµР»РµР№ (СѓР·Р»РѕРІ EDFA).
        """
        channel = self.network.channels.get(channel_id)
        if not channel or not channel.path or len(channel.path) < 2:
            return 0

        equipment_budget_db = max(0.0, channel.get_energy_budget_db())
        added = self.split_long_fibers_and_insert_inline_edfa(
            channel.path,
            equipment_budget_db=equipment_budget_db,
        )
        # РџРµСЂРµСЃРѕР±РёСЂР°РµРј РјР°СЂС€СЂСѓС‚ СЃ СѓС‡РµС‚РѕРј РЅРѕРІС‹С… EDFA-СѓР·Р»РѕРІ
        new_path = self.rebuild_path_with_inline_nodes(channel.path[0], channel.path[-1])
        if new_path:
            channel.path = new_path
        return added
    
    def optimize_amplifier_placement(self, path: List[str]) -> List[str]:
        """
        РћРїС‚РёРјРёР·РёСЂСѓРµС‚ СЂР°СЃСЃС‚Р°РЅРѕРІРєСѓ СѓСЃРёР»РёС‚РµР»РµР№ РЅР° РїСѓС‚Рё
        (РЈР»СѓС‡С€РµРЅРЅС‹Р№ Р°Р»РіРѕСЂРёС‚Рј - РјРѕР¶РЅРѕ СЂР°Р·РІРёРІР°С‚СЊ РґР°Р»СЊС€Рµ)
        
        Args:
            path: РџСѓС‚СЊ РґР»СЏ РѕРїС‚РёРјРёР·Р°С†РёРё
            
        Returns:
            РЎРїРёСЃРѕРє node_id, РіРґРµ РЅСѓР¶РЅРѕ СЂР°Р·РјРµСЃС‚РёС‚СЊ СѓСЃРёР»РёС‚РµР»Рё
        """
        # Р‘Р°Р·РѕРІС‹Р№ Р°Р»РіРѕСЂРёС‚Рј - РјРѕР¶РЅРѕ СѓР»СѓС‡С€РёС‚СЊ:
        # - Р“СЂСѓРїРїРёСЂРѕРІРєР° РЅРµСЃРєРѕР»СЊРєРёС… СѓС‡Р°СЃС‚РєРѕРІ
        # - РЈС‡РµС‚ РјР°РєСЃРёРјР°Р»СЊРЅРѕР№ РґР»РёРЅС‹ СѓС‡Р°СЃС‚РєР°
        # - РЈС‡РµС‚ РјРѕС‰РЅРѕСЃС‚Рё СЃРёРіРЅР°Р»Р° (РЅРµ С‚РѕР»СЊРєРѕ Р·Р°С‚СѓС…Р°РЅРёСЏ)
        positions = self.place_amplifiers_on_path(path)
        return [pos[0] for pos in positions]
    
    def calculate_amplifier_positions_for_path(self, path: List[str]) -> List[dict]:
        """
        Р Р°СЃСЃС‡РёС‚С‹РІР°РµС‚ Рё РІРѕР·РІСЂР°С‰Р°РµС‚ РёРЅС„РѕСЂРјР°С†РёСЋ Рѕ РїРѕР·РёС†РёСЏС… СѓСЃРёР»РёС‚РµР»РµР№
        
        Returns:
            РЎРїРёСЃРѕРє СЃР»РѕРІР°СЂРµР№ СЃ РёРЅС„РѕСЂРјР°С†РёРµР№ Рѕ РїРѕР·РёС†РёСЏС…:
            [{'node_id': '...', 'position_km': 0.0, 'accumulated_loss_db': 22.0}, ...]
        """
        positions_info = []
        
        if len(path) < 2:
            return positions_info
        
        accumulated_loss = 0.0
        current_distance = 0.0
        fibers = self.network.get_path_fibers(path)
        
        for fiber in fibers:
            fiber_loss = fiber.calculate_fiber_loss()
            current_distance += fiber.length_km
            accumulated_loss += fiber_loss
            
            if accumulated_loss > self.max_span_loss_db:
                positions_info.append({
                    'node_id': fiber.target_node_id,
                    'position_km': current_distance,
                    'accumulated_loss_db': accumulated_loss,
                    'fiber_id': fiber.fiber_id
                })
                
                # РЎР±СЂР°СЃС‹РІР°РµРј РЅР°РєРѕРїР»РµРЅРЅРѕРµ Р·Р°С‚СѓС…Р°РЅРёРµ
                accumulated_loss = fiber_loss
        
        return positions_info

