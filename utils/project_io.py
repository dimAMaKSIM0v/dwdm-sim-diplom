"""
Загрузка и сохранение проектов DWDM-сети в JSON.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from core.models.channel import Channel
from core.models.equipment import Equipment, EquipmentType
from core.models.fiber import Fiber, FiberType
from core.models.network import Network
from core.models.node import Node, NodeType


class ProjectLoadError(Exception):
    """Ошибка загрузки/валидации проекта."""


def _as_path(path: str | Path) -> Path:
    return path if isinstance(path, Path) else Path(path)


def _parse_node_type(value: Any) -> NodeType:
    raw = str(value or "").strip().lower()
    for node_type in NodeType:
        if node_type.value == raw or node_type.name.lower() == raw:
            return node_type
    raise ProjectLoadError(f"Неизвестный тип узла: {value!r}")


def _parse_fiber_type(value: Any) -> FiberType:
    raw = str(value or "").strip()
    for fiber_type in FiberType:
        if fiber_type.value == raw or fiber_type.name.lower() == raw.lower():
            return fiber_type

    raw_compact = raw.replace(".", "").replace("-", "").replace("_", "").lower()
    raw_digits = "".join(ch for ch in raw_compact if ch.isdigit())
    for fiber_type in FiberType:
        compact = fiber_type.value.replace(".", "").replace("-", "").replace("_", "").lower()
        compact_digits = "".join(ch for ch in compact if ch.isdigit())
        if compact == raw_compact or (raw_digits and compact_digits == raw_digits):
            return fiber_type

    raise ProjectLoadError(f"Неизвестный тип волокна: {value!r}")


def _parse_equipment_type(value: Any) -> EquipmentType:
    raw = str(value or "").strip().lower()
    for equipment_type in EquipmentType:
        if equipment_type.value == raw or equipment_type.name.lower() == raw:
            return equipment_type
    raise ProjectLoadError(f"Неизвестный тип оборудования: {value!r}")


def _parse_route_points(value: Any) -> List[Tuple[float, float]]:
    if not value:
        return []
    if not isinstance(value, list):
        raise ProjectLoadError("Поле 'route_points' должно быть списком.")

    points: List[Tuple[float, float]] = []
    for idx, item in enumerate(value):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ProjectLoadError(f"Точка route_points[{idx}] должна быть [lat, lon].")
        points.append((float(item[0]), float(item[1])))
    return points


def _parse_path_nodes(value: Any, *, field_name: str = "path") -> List[str]:
    if not isinstance(value, list):
        raise ProjectLoadError(f"Поле '{field_name}' должно быть списком ID узлов.")
    path = [str(node_id).strip() for node_id in value if str(node_id).strip()]
    if len(path) < 2:
        raise ProjectLoadError(f"Поле '{field_name}' должно содержать минимум 2 ID узлов.")
    return path


def _safe_float(value: Any, field_name: str, default: float = 0.0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ProjectLoadError(f"Поле '{field_name}' должно быть числом.") from exc


def _safe_optional_float(value: Any, field_name: str) -> float | None:
    if value is None or value == "":
        return None
    return _safe_float(value, field_name, default=0.0)


def _safe_optional_int(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ProjectLoadError(f"Поле '{field_name}' должно быть целым числом.") from exc


def load_network_from_json(path: str | Path) -> Network:
    """
    Загружает объект Network из JSON.

    Ключи верхнего уровня:
    - name: str
    - nodes: list
    - fibers: list
    - channels: list (опционально)
    - equipment: list (опционально)
    """
    file_path = _as_path(path)
    if not file_path.exists():
        raise ProjectLoadError(f"Файл не найден: {file_path}")

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProjectLoadError(f"Некорректный JSON в {file_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ProjectLoadError("Корневой объект JSON должен быть словарем.")

    network = Network(name=str(data.get("name", "DWDM Network")))

    nodes = data.get("nodes", [])
    fibers = data.get("fibers", [])
    channels = data.get("channels", [])
    equipment_items = data.get("equipment", [])

    if not isinstance(nodes, list):
        raise ProjectLoadError("Поле 'nodes' должно быть списком.")
    if not isinstance(fibers, list):
        raise ProjectLoadError("Поле 'fibers' должно быть списком.")
    if not isinstance(channels, list):
        raise ProjectLoadError("Поле 'channels' должно быть списком.")
    if not isinstance(equipment_items, list):
        raise ProjectLoadError("Поле 'equipment' должно быть списком.")

    for idx, item in enumerate(nodes):
        if not isinstance(item, dict):
            raise ProjectLoadError(f"nodes[{idx}] должен быть объектом.")

        node_id = str(item.get("node_id", "")).strip()
        name = str(item.get("name", "")).strip()
        if not node_id:
            raise ProjectLoadError(f"nodes[{idx}] не содержит 'node_id'.")
        if not name:
            raise ProjectLoadError(f"nodes[{idx}] не содержит 'name'.")
        if node_id in network.nodes:
            raise ProjectLoadError(f"Дублирующийся node_id: {node_id}")

        node = Node(
            node_id=node_id,
            name=name,
            node_type=_parse_node_type(item.get("node_type", NodeType.TERMINAL.value)),
            latitude=_safe_float(item.get("latitude"), "latitude", default=0.0),
            longitude=_safe_float(item.get("longitude"), "longitude", default=0.0),
            territory=str(item.get("territory", "")).strip(),
            organization=str(item.get("organization", "")).strip(),
        )
        network.add_node(node)

    for idx, item in enumerate(fibers):
        if not isinstance(item, dict):
            raise ProjectLoadError(f"fibers[{idx}] должен быть объектом.")

        fiber_id = str(item.get("fiber_id", "")).strip()
        src = str(item.get("source_node_id", "")).strip()
        dst = str(item.get("target_node_id", "")).strip()
        if not fiber_id:
            raise ProjectLoadError(f"fibers[{idx}] не содержит 'fiber_id'.")
        if not src or not dst:
            raise ProjectLoadError(f"Волокно {fiber_id}: source/target обязательны.")
        if src not in network.nodes or dst not in network.nodes:
            raise ProjectLoadError(f"Волокно {fiber_id}: неизвестная пара ({src} -> {dst}).")
        if fiber_id in network.fibers:
            raise ProjectLoadError(f"Дублирующийся fiber_id: {fiber_id}")

        coil_length_km = item.get("coil_length_km", item.get("splice_interval_km"))
        line_reserve_db = item.get("line_reserve_db", item.get("reserve_db"))
        fiber = Fiber(
            fiber_id=fiber_id,
            source_node_id=src,
            target_node_id=dst,
            length_km=_safe_float(item.get("length_km"), "length_km", default=0.0),
            fiber_type=_parse_fiber_type(item.get("fiber_type", FiberType.G652.value)),
            attenuation_db_per_km=_safe_optional_float(
                item.get("attenuation_db_per_km"),
                "attenuation_db_per_km",
            ),
            splice_losses_db=_safe_float(
                item.get("splice_losses_db"),
                "splice_losses_db",
                default=0.02,
            ),
            splice_interval_km=_safe_float(
                coil_length_km,
                "coil_length_km",
                default=25.0,
            ),
            connector_losses_db=_safe_float(
                item.get("connector_losses_db"),
                "connector_losses_db",
                default=0.3,
            ),
            line_reserve_db=_safe_float(
                line_reserve_db,
                "line_reserve_db",
                default=0.0,
            ),
            splice_count_override=_safe_optional_int(
                item.get("splice_count_override"),
                "splice_count_override",
            ),
            dispersion_ps_per_nm_km=_safe_optional_float(
                item.get("dispersion_ps_per_nm_km"),
                "dispersion_ps_per_nm_km",
            ),
            route_points=_parse_route_points(item.get("route_points", [])),
            is_trunk=bool(item.get("is_trunk", False)),
        )
        network.add_fiber(fiber)

    for idx, item in enumerate(channels):
        if not isinstance(item, dict):
            raise ProjectLoadError(f"channels[{idx}] должен быть объектом.")

        channel_id = str(item.get("channel_id", "")).strip()
        if not channel_id:
            raise ProjectLoadError(f"channels[{idx}] не содержит 'channel_id'.")
        if channel_id in network.channels:
            raise ProjectLoadError(f"Дублирующийся channel_id: {channel_id}")

        path = _parse_path_nodes(item.get("path", []), field_name=f"channels[{idx}].path")
        for node_id in path:
            if node_id not in network.nodes:
                raise ProjectLoadError(
                    f"Канал {channel_id}: узел '{node_id}' из пути не существует."
                )

        wavelength_nm = _safe_float(item.get("wavelength_nm"), "wavelength_nm", default=0.0)
        if wavelength_nm <= 0:
            raise ProjectLoadError(f"Канал {channel_id}: wavelength_nm должен быть > 0.")

        channel = Channel(
            channel_id=channel_id,
            wavelength_nm=wavelength_nm,
            frequency_thz=_safe_optional_float(item.get("frequency_thz"), "frequency_thz"),
            tx_power_dbm=_safe_float(item.get("tx_power_dbm"), "tx_power_dbm", default=0.0),
            rx_sensitivity_dbm=_safe_float(
                item.get("rx_sensitivity_dbm"),
                "rx_sensitivity_dbm",
                default=-20.0,
            ),
            bitrate_gbps=_safe_float(item.get("bitrate_gbps"), "bitrate_gbps", default=10.0),
            energy_budget_db=_safe_optional_float(
                item.get("energy_budget_db"),
                "energy_budget_db",
            ),
            path=path,
            osnr_db=_safe_optional_float(item.get("osnr_db"), "osnr_db"),
            current_power_dbm=_safe_optional_float(
                item.get("current_power_dbm"),
                "current_power_dbm",
            ),
        )
        network.add_channel(channel)

    for idx, item in enumerate(equipment_items):
        if not isinstance(item, dict):
            raise ProjectLoadError(f"equipment[{idx}] должен быть объектом.")

        equipment_id = str(item.get("equipment_id", "")).strip()
        node_id = str(item.get("node_id", "")).strip()
        if not equipment_id:
            raise ProjectLoadError(f"equipment[{idx}] не содержит 'equipment_id'.")
        if not node_id:
            raise ProjectLoadError(f"Оборудование {equipment_id}: node_id обязателен.")
        if node_id not in network.nodes:
            raise ProjectLoadError(f"Оборудование {equipment_id}: узел '{node_id}' не существует.")
        if equipment_id in network.equipment:
            raise ProjectLoadError(f"Дублирующийся equipment_id: {equipment_id}")

        params = item.get("parameters", {})
        if params is None:
            params = {}
        if not isinstance(params, dict):
            raise ProjectLoadError(f"Оборудование {equipment_id}: parameters должен быть объектом.")

        equipment = Equipment(
            equipment_id=equipment_id,
            equipment_type=_parse_equipment_type(item.get("equipment_type", "")),
            node_id=node_id,
            parameters=params,
        )
        network.add_equipment(equipment)

    return network


def _sorted_values(items: Iterable[Any], key: str):
    return sorted(items, key=lambda item: getattr(item, key))


def save_network_to_json(network: Network, path: str | Path) -> None:
    """Сохраняет объект Network в JSON."""
    file_path = _as_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    payload: Dict[str, Any] = {
        "name": network.name,
        "nodes": [],
        "fibers": [],
        "channels": [],
        "equipment": [],
    }

    for node in _sorted_values(network.nodes.values(), "node_id"):
        payload["nodes"].append(
            {
                "node_id": node.node_id,
                "name": node.name,
                "node_type": node.node_type.value,
                "territory": node.territory,
                "organization": node.organization,
                "latitude": node.latitude,
                "longitude": node.longitude,
            }
        )

    for fiber in _sorted_values(network.fibers.values(), "fiber_id"):
        payload["fibers"].append(
            {
                "fiber_id": fiber.fiber_id,
                "source_node_id": fiber.source_node_id,
                "target_node_id": fiber.target_node_id,
                "length_km": fiber.length_km,
                "fiber_type": fiber.fiber_type.value,
                "attenuation_db_per_km": fiber.attenuation_db_per_km,
                "splice_losses_db": fiber.splice_losses_db,
                "splice_interval_km": fiber.splice_interval_km,
                "connector_losses_db": fiber.connector_losses_db,
                "line_reserve_db": fiber.line_reserve_db,
                "splice_count_override": fiber.splice_count_override,
                "dispersion_ps_per_nm_km": fiber.dispersion_ps_per_nm_km,
                "route_points": [[lat, lon] for lat, lon in fiber.route_points],
                "is_trunk": fiber.is_trunk,
            }
        )

    for channel in _sorted_values(network.channels.values(), "channel_id"):
        energy_budget_db = channel.get_energy_budget_db()
        payload["channels"].append(
            {
                "channel_id": channel.channel_id,
                "wavelength_nm": channel.wavelength_nm,
                "frequency_thz": channel.frequency_thz,
                "tx_power_dbm": channel.tx_power_dbm,
                "rx_sensitivity_dbm": channel.rx_sensitivity_dbm,
                "bitrate_gbps": channel.bitrate_gbps,
                "energy_budget_db": energy_budget_db,
                "path": list(channel.path or []),
                "osnr_db": channel.osnr_db,
                "current_power_dbm": channel.current_power_dbm,
            }
        )

    for equipment in _sorted_values(network.equipment.values(), "equipment_id"):
        payload["equipment"].append(
            {
                "equipment_id": equipment.equipment_id,
                "equipment_type": equipment.equipment_type.value,
                "node_id": equipment.node_id,
                "parameters": dict(equipment.parameters or {}),
            }
        )

    file_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
