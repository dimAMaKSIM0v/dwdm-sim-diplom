# API Documentation - DWDM Network Simulator

Документация API для разработчиков, желающих расширить или интегрировать симулятор.

---

## 📑 Содержание

1. [Модели данных](#модели-данных)
2. [Калькуляторы](#калькуляторы)
3. [Менеджеры](#менеджеры)
4. [Утилиты](#утилиты)
5. [Примеры использования](#примеры-использования)

---

## Модели данных

### Network

**Путь:** `core/models/network.py`

Контейнер для всех объектов сети.

```python
from core.models.network import Network

network = Network(name="My DWDM Network")
```

**Атрибуты:**
- `nodes: Dict[str, Node]` - словарь узлов
- `fibers: Dict[str, Fiber]` - словарь волокон
- `channels: Dict[str, Channel]` - словарь каналов
- `equipment: Dict[str, Equipment]` - словарь оборудования
- `name: str` - название сети

**Методы:**

#### `add_node(node: Node) -> None`
Добавляет узел в сеть.

```python
from core.models.node import Node

node = Node(node_id="MSK", name="Москва", lat=55.7558, lon=37.6173)
network.add_node(node)
```

#### `add_fiber(fiber: Fiber) -> None`
Добавляет волокно в сеть.

#### `add_channel(channel: Channel) -> None`
Добавляет канал в сеть.

#### `add_equipment(equipment: Equipment) -> None`
Добавляет оборудование в сеть и привязывает к узлу.

#### `get_node(node_id: str) -> Optional[Node]`
Возвращает узел по ID.

#### `get_fiber(fiber_id: str) -> Optional[Fiber]`
Возвращает волокно по ID.

---

### Node

**Путь:** `core/models/node.py`

Узел сети (город, точка присутствия).

```python
from core.models.node import Node, NodeType

node = Node(
    node_id="MSK",
    name="Москва",
    node_type=NodeType.HUB,
    lat=55.7558,
    lon=37.6173
)
```

**Атрибуты:**
- `node_id: str` - уникальный идентификатор
- `name: str` - название узла
- `node_type: NodeType` - тип узла (source, sink, transit, hub)
- `lat: float` - широта
- `lon: float` - долгота
- `equipment: List[str]` - список ID оборудования

**Enum NodeType:**
- `SOURCE` - источник трафика
- `SINK` - приемник трафика
- `TRANSIT` - транзитный узел
- `HUB` - узел-концентратор

---

### Fiber

**Путь:** `core/models/fiber.py`

Волоконная линия между двумя узлами.

```python
from core.models.fiber import Fiber, FiberType

fiber = Fiber(
    fiber_id="MSK-SPB",
    source_node_id="MSK",
    target_node_id="SPB",
    length_km=700.0,
    fiber_type=FiberType.G652
)
```

**Атрибуты:**
- `fiber_id: str` - уникальный идентификатор
- `source_node_id: str` - ID узла источника
- `target_node_id: str` - ID узла назначения
- `length_km: float` - длина в км
- `fiber_type: FiberType` - тип волокна
- `attenuation_db_per_km: Optional[float]` - затухание (дБ/км)
- `splice_losses_db: float` - потери на сварке (по умолчанию 0.02 дБ)
- `splice_interval_km: float` - строительная длина (по умолчанию 25 км)
- `connector_losses_db: float` - потери на коннекторе (по умолчанию 0.3 дБ)
- `line_reserve_db: float` - линейный резерв (дБ)

**Enum FiberType:**
- `G652` - стандартное одномодовое волокно (SMF)
- `G653` - волокно со смещенной дисперсией (DSF)
- `G654` - волокно со сдвинутой отсечкой
- `G655` - ненулевая дисперсионная смещенная (NZ-DSF)
- `G656` - широкополосное NZ-DSF
- `G657` - изгибоустойчивое

**Методы:**

#### `get_attenuation_per_km() -> float`
Возвращает затухание в дБ/км для данного типа волокна.

```python
attenuation = fiber.get_attenuation_per_km()  # 0.22 для G.652
```

#### `get_dispersion_coefficient_ps_per_nm_km() -> float`
Возвращает коэффициент хроматической дисперсии D(λ) в пс/(нм·км).

```python
dispersion = fiber.get_dispersion_coefficient_ps_per_nm_km()  # 17.0 для G.652
```

#### `calculate_fiber_loss() -> float`
Рассчитывает общие потери в волокне (дБ).

```python
total_loss = fiber.calculate_fiber_loss()
# Включает: затухание + сварки + коннекторы + резерв
```

#### `calculate_splice_count() -> int`
Рассчитывает количество сварок по длине и строительной длине.

```python
splices = fiber.calculate_splice_count()
# ceil(L / L_construction) - 1
```

---

### Channel

**Путь:** `core/models/channel.py`

DWDM канал (лямбда).

```python
from core.models.channel import Channel, LaserType, ModulationType

channel = Channel(
    channel_id="Ch1",
    wavelength_nm=1550.0,
    tx_power_dbm=0.0,
    rx_sensitivity_dbm=-20.0,
    bitrate_gbps=10.0,
    laser_type=LaserType.DFB,
    modulation_type=ModulationType.NRZ,
    path=["MSK", "SPB"]
)
```

**Атрибуты:**
- `channel_id: str` - уникальный идентификатор
- `wavelength_nm: float` - длина волны (нм)
- `frequency_thz: Optional[float]` - частота (ТГц), вычисляется автоматически
- `tx_power_dbm: float` - мощность передатчика (дБм)
- `rx_sensitivity_dbm: float` - чувствительность приемника (дБм)
- `bitrate_gbps: float` - скорость передачи (Гбит/с)
- `laser_type: LaserType` - тип лазера
- `modulation_type: ModulationType` - тип модуляции
- `path: List[str]` - маршрут (список ID узлов)

**Enum LaserType:**
- `DFB` - Distributed Feedback (узкий спектр, 0.0005 нм)
- `EML` - Electro-absorption Modulated Laser (0.002 нм)
- `FP` - Fabry-Perot (широкий спектр, 2.0 нм)

**Enum ModulationType:**
- `NRZ` - Non-Return-to-Zero
- `RZ` - Return-to-Zero

**Методы:**

#### `calculate_frequency_from_wavelength() -> float`
Вычисляет частоту (ТГц) из длины волны (нм).

```python
freq = channel.calculate_frequency_from_wavelength()
# f = c / λ = 299792.458 / wavelength_nm
```

#### `get_energy_budget_db() -> float`
Возвращает энергетический бюджет (дБ).

```python
budget = channel.get_energy_budget_db()
# TX_power - RX_sensitivity
```

#### `get_itu_channel_number() -> Optional[int]`
Определяет номер канала по сетке ITU-T.

```python
ch_num = channel.get_itu_channel_number()
# Относительно 193.1 ТГц
```

---

### Equipment

**Путь:** `core/models/equipment.py`

Оборудование в узле.

```python
from core.models.equipment import Equipment, EquipmentType

edfa = Equipment(
    equipment_id="EDFA-MSK-1",
    equipment_type=EquipmentType.EDFA,
    node_id="MSK",
    parameters={"gain_db": 20.0, "noise_figure_db": 5.0}
)
```

**Атрибуты:**
- `equipment_id: str` - уникальный идентификатор
- `equipment_type: EquipmentType` - тип оборудования
- `node_id: str` - ID узла
- `parameters: dict` - параметры (зависят от типа)

**Enum EquipmentType:**
- `MUX` - мультиплексор
- `DEMUX` - демультиплексор
- `OADM` - оптический мультиплексор ввода/вывода
- `TRANSPONDER` - транспондер
- `EDFA` - оптический усилитель
- `REGEN` - регенератор

**Методы:**

#### `get_insertion_loss() -> float`
Возвращает вносимые потери оборудования (дБ).

```python
loss = edfa.get_insertion_loss()  # 0.5 дБ для EDFA
```

#### `get_gain() -> float`
Возвращает усиление (дБ) для усилителей.

```python
gain = edfa.get_gain()  # Из parameters["gain_db"]
```

---

## Калькуляторы

### DispersionCalculator

**Путь:** `core/calculators/dispersion.py`

Расчет хроматической и поляризационной модовой дисперсии.

```python
from core.calculators.dispersion import DispersionCalculator

calculator = DispersionCalculator()
result = calculator.channel_dispersion(network, channel)
```

**Методы:**

#### `channel_dispersion(network: Network, channel: Channel) -> DispersionResult`
Рассчитывает дисперсию для канала.

**Возвращает:** `DispersionResult`
- `channel_id: str`
- `path: List[str]`
- `total_cd_ps_per_nm: float` - накопленная ХД (пс/нм)
- `total_pmd_ps: float` - накопленная ПМД (пс)
- `cd_limit_ps_per_nm: float` - лимит ХД
- `pmd_limit_ps: float` - лимит ПМД
- `cd_ok: bool` - ХД в пределах лимита
- `pmd_ok: bool` - ПМД в пределах лимита
- `segments: List[DispersionSegment]` - детали по сегментам

**Формулы:**

Хроматическая дисперсия:
```
D_total = Σ D(λ, тип_i) · L_i  [пс/нм]
```

Поляризационная модовая дисперсия (RSS):
```
PMD_total = √(Σ (D_PMD_i · √L_i)²)  [пс]
```

---

### DispersionVisualizer

**Путь:** `core/calculators/dispersion_visualizer.py`

Визуализация уширения импульса.

```python
from core.calculators.dispersion_visualizer import DispersionVisualizer

visualizer = DispersionVisualizer()
fig = visualizer.plot_pulse_broadening(
    dispersion_result=result,
    bitrate_gbps=10.0,
    laser_type="dfb",
    modulation="nrz"
)
```

**Методы:**

#### `plot_pulse_broadening(...) -> matplotlib.figure.Figure`
Создает график уширения импульса.

**Параметры:**
- `dispersion_result: DispersionResult`
- `bitrate_gbps: float`
- `laser_type: str` - "dfb", "eml", "fp"
- `modulation: str` - "nrz", "rz"
- `net_loss_db: float` - суммарные потери

**Возвращает:** matplotlib Figure с графиками

---

### PowerBudgetCalculator

**Путь:** `core/calculators/power_budget.py`

Расчет бюджета мощности.

```python
from core.calculators.power_budget import calculate_power_budget

result = calculate_power_budget(
    channel=channel,
    path_fibers=[fiber1, fiber2],
    path_equipment=[edfa1, edfa2]
)
```

**Функция:** `calculate_power_budget(...) -> PowerBudgetResult`

**Параметры:**
- `channel: Channel`
- `path_fibers: List[Fiber]`
- `path_equipment: List[Equipment]`

**Возвращает:** `PowerBudgetResult`
- `channel_id: str`
- `tx_power_dbm: float`
- `total_loss_db: float`
- `total_gain_db: float`
- `rx_power_dbm: float`
- `rx_sensitivity_dbm: float`
- `power_margin_db: float` - запас по мощности
- `is_valid: bool` - линия работоспособна

**Формулы:**
```
RX_power = TX_power - Total_loss + Total_gain
Power_margin = RX_power - RX_sensitivity
```

---

### AmplifierPlacer

**Путь:** `core/calculators/amplifier_placer.py`

Автоматическое размещение усилителей.

```python
from core.calculators.amplifier_placer import AmplifierPlacer

placer = AmplifierPlacer(network)
# Размещает усилители для всех каналов
count = placer.place_amplifiers_for_all_channels()
print(f"Размещено усилителей: {count}")
```

**Методы:**

#### `place_amplifiers_for_all_channels() -> int`
Размещает EDFA на линиях для всех каналов.

**Возвращает:** количество размещенных усилителей

#### `place_amplifiers_for_channel(channel_id: str) -> int`
Размещает EDFA для конкретного канала.

**Параметры:**
- `channel_id: str` - ID канала

**Возвращает:** количество размещенных усилителей

---

### FrequencyPlan

**Путь:** `core/calculators/frequency_plan.py`

Частотный план ITU-T.

```python
from core.calculators.frequency_plan import FrequencyPlan

plan = FrequencyPlan(
    center_frequency_thz=193.1,
    channel_spacing_ghz=50.0,
    num_channels=80
)

wavelength = plan.get_wavelength_nm(channel_index=0)
frequency = plan.get_frequency_thz(channel_index=0)
```

**Методы:**

#### `get_frequency_thz(channel_index: int) -> float`
Возвращает частоту канала (ТГц).

```python
freq = plan.get_frequency_thz(0)  # 193.1 ТГц
```

#### `get_wavelength_nm(channel_index: int) -> float`
Возвращает длину волны канала (нм).

```python
wavelength = plan.get_wavelength_nm(0)  # ~1552.52 нм
```

#### `get_all_channels() -> List[Tuple[int, float, float]]`
Возвращает список всех каналов: (индекс, частота, длина волны).

---

## Менеджеры

### TopologyManager

**Путь:** `core/managers/topology_manager.py`

Управление топологией сети.

```python
from core.managers.topology_manager import TopologyManager

manager = TopologyManager(network)
graph = manager.build_graph()
path = manager.find_shortest_path("MSK", "SPB")
```

**Методы:**

#### `build_graph() -> nx.Graph`
Строит граф NetworkX из сети.

#### `find_shortest_path(source: str, target: str) -> List[str]`
Находит кратчайший путь между узлами.

```python
path = manager.find_shortest_path("MSK", "SPB")
# ["MSK", "SPB"] или ["MSK", "EKB", "SPB"]
```

#### `get_all_paths(source: str, target: str, cutoff: int = None) -> List[List[str]]`
Находит все пути между узлами.

---

### TopologyAnalyzer

**Путь:** `core/managers/topology_analyzer.py`

Анализ топологии сети.

```python
from core.managers.topology_analyzer import TopologyAnalyzer

analyzer = TopologyAnalyzer(network)
metrics = analyzer.analyze()
```

**Методы:**

#### `analyze() -> Dict`
Анализирует топологию и возвращает метрики.

**Возвращает:**
```python
{
    "num_nodes": int,
    "num_edges": int,
    "num_components": int,  # компоненты связности
    "diameter": int,  # диаметр сети
    "avg_degree": float,  # средняя степень узла
    "is_connected": bool
}
```

---

### TrafficManager

**Путь:** `core/managers/traffic_manager.py`

Управление трафиком.

```python
from core.managers.traffic_manager import TrafficManager

manager = TrafficManager(network)
manager.add_traffic_demand("MSK", "SPB", 100.0)  # 100 Гбит/с
matrix = manager.get_traffic_matrix()
```

**Методы:**

#### `add_traffic_demand(source: str, target: str, demand_gbps: float)`
Добавляет требование по трафику.

#### `get_traffic_matrix() -> Dict[Tuple[str, str], float]`
Возвращает матрицу трафика.

```python
matrix = manager.get_traffic_matrix()
# {("MSK", "SPB"): 100.0, ("SPB", "EKB"): 40.0, ...}
```

---

### SimulationManager

**Путь:** `core/managers/simulation_manager.py`

Управление симуляцией.

```python
from core.managers.simulation_manager import SimulationManager

sim = SimulationManager(network)
results = sim.run_simulation()
```

**Методы:**

#### `run_simulation() -> Dict`
Запускает полную симуляцию.

**Возвращает:**
```python
{
    "topology": {...},  # метрики топологии
    "dispersion": [...],  # результаты дисперсии
    "power_budget": [...],  # результаты бюджета
    "traffic": {...}  # анализ трафика
}
```

---

## Утилиты

### project_io

**Путь:** `utils/project_io.py`

Сохранение и загрузка проектов.

```python
from utils.project_io import save_network_to_json, load_network_from_json

# Сохранение
save_network_to_json(network, "my_project.json")

# Загрузка
network = load_network_from_json("my_project.json")
```

**Функции:**

#### `save_network_to_json(network: Network, filepath: str) -> None`
Сохраняет сеть в JSON файл.

#### `load_network_from_json(filepath: str) -> Network`
Загружает сеть из JSON файла.

**Формат JSON:**
```json
{
  "name": "My Network",
  "nodes": [
    {
      "node_id": "MSK",
      "name": "Москва",
      "node_type": "hub",
      "lat": 55.7558,
      "lon": 37.6173
    }
  ],
  "fibers": [...],
  "channels": [...],
  "equipment": [...]
}
```

---

## Примеры использования

### Пример 1: Создание простой сети

```python
from core.models.network import Network
from core.models.node import Node, NodeType
from core.models.fiber import Fiber, FiberType
from core.models.channel import Channel, LaserType, ModulationType

# Создаем сеть
network = Network(name="Test Network")

# Добавляем узлы
msk = Node("MSK", "Москва", NodeType.HUB, 55.7558, 37.6173)
spb = Node("SPB", "Санкт-Петербург", NodeType.HUB, 59.9343, 30.3351)
network.add_node(msk)
network.add_node(spb)

# Добавляем волокно
fiber = Fiber(
    fiber_id="MSK-SPB",
    source_node_id="MSK",
    target_node_id="SPB",
    length_km=700.0,
    fiber_type=FiberType.G652
)
network.add_fiber(fiber)

# Добавляем канал
channel = Channel(
    channel_id="Ch1",
    wavelength_nm=1550.0,
    tx_power_dbm=0.0,
    rx_sensitivity_dbm=-20.0,
    bitrate_gbps=10.0,
    laser_type=LaserType.DFB,
    modulation_type=ModulationType.NRZ,
    path=["MSK", "SPB"]
)
network.add_channel(channel)

# Сохраняем
from utils.project_io import save_network_to_json
save_network_to_json(network, "test_network.json")
```

### Пример 2: Расчет дисперсии

```python
from core.calculators.dispersion import DispersionCalculator

# Создаем калькулятор
calculator = DispersionCalculator()

# Рассчитываем для канала
result = calculator.channel_dispersion(network, channel)

# Проверяем результаты
print(f"Накопленная ХД: {result.total_cd_ps_per_nm:.2f} пс/нм")
print(f"Лимит ХД: {result.cd_limit_ps_per_nm:.2f} пс/нм")
print(f"ХД OK: {result.cd_ok}")

print(f"Накопленная ПМД: {result.total_pmd_ps:.2f} пс")
print(f"Лимит ПМД: {result.pmd_limit_ps:.2f} пс")
print(f"ПМД OK: {result.pmd_ok}")
```

### Пример 3: Расчет бюджета мощности

```python
from core.calculators.power_budget import calculate_power_budget

# Получаем волокна на маршруте
path_fibers = [network.get_fiber("MSK-SPB")]

# Рассчитываем бюджет
result = calculate_power_budget(
    channel=channel,
    path_fibers=path_fibers,
    path_equipment=[]
)

# Проверяем результаты
print(f"Мощность на приемнике: {result.rx_power_dbm:.2f} дБм")
print(f"Чувствительность: {result.rx_sensitivity_dbm:.2f} дБм")
print(f"Запас по мощности: {result.power_margin_db:.2f} дБ")
print(f"Линия работоспособна: {result.is_valid}")
```

### Пример 4: Автоматическое размещение усилителей

```python
from core.calculators.amplifier_placer import AmplifierPlacer

# Создаем placer
placer = AmplifierPlacer(network)

# Размещаем усилители
amplifiers = placer.place_amplifiers(
    max_span_km=80.0,
    edfa_gain_db=20.0,
    edfa_output_power_dbm=17.0
)

print(f"Размещено усилителей: {len(amplifiers)}")
for amp in amplifiers:
    print(f"  {amp.equipment_id} в узле {amp.node_id}")
```

### Пример 5: Анализ топологии

```python
from core.managers.topology_analyzer import TopologyAnalyzer

# Создаем анализатор
analyzer = TopologyAnalyzer(network)

# Анализируем
metrics = analyzer.analyze()

print(f"Узлов: {metrics['num_nodes']}")
print(f"Линий: {metrics['num_edges']}")
print(f"Компонент связности: {metrics['num_components']}")
print(f"Диаметр сети: {metrics['diameter']}")
print(f"Средняя степень узла: {metrics['avg_degree']:.2f}")
print(f"Сеть связна: {metrics['is_connected']}")
```

### Пример 6: Поиск маршрутов

```python
from core.managers.topology_manager import TopologyManager

# Создаем менеджер
manager = TopologyManager(network)

# Находим кратчайший путь
shortest = manager.find_shortest_path("MSK", "SPB")
print(f"Кратчайший путь: {' -> '.join(shortest)}")

# Находим все пути
all_paths = manager.get_all_paths("MSK", "SPB", cutoff=5)
print(f"Всего путей: {len(all_paths)}")
for i, path in enumerate(all_paths, 1):
    print(f"  Путь {i}: {' -> '.join(path)}")
```

---

## Расширение функциональности

### Добавление нового типа оборудования

```python
# В core/models/equipment.py
class EquipmentType(Enum):
    # ... существующие типы
    DCM = "dcm"  # Dispersion Compensation Module

# Добавить обработку в get_insertion_loss()
default_losses = {
    # ...
    EquipmentType.DCM: 2.0,
}
```

### Добавление нового калькулятора

```python
# core/calculators/my_calculator.py
from core.models.network import Network
from dataclasses import dataclass

@dataclass
class MyResult:
    value: float
    is_ok: bool

class MyCalculator:
    def __init__(self, network: Network):
        self.network = network
    
    def calculate(self) -> MyResult:
        # Ваша логика
        return MyResult(value=42.0, is_ok=True)
```

---

## Тестирование

### Пример unit-теста

```python
import unittest
from core.models.fiber import Fiber, FiberType

class TestFiber(unittest.TestCase):
    def test_attenuation(self):
        fiber = Fiber(
            fiber_id="test",
            source_node_id="A",
            target_node_id="B",
            length_km=100.0,
            fiber_type=FiberType.G652
        )
        
        attenuation = fiber.get_attenuation_per_km()
        self.assertEqual(attenuation, 0.22)
        
        total_loss = fiber.calculate_fiber_loss()
        self.assertGreater(total_loss, 22.0)  # > 100 * 0.22

if __name__ == '__main__':
    unittest.main()
```

---

## Версионирование

API следует семантическому версионированию (SemVer):
- **MAJOR** - несовместимые изменения API
- **MINOR** - новая функциональность с обратной совместимостью
- **PATCH** - исправления ошибок

**Текущая версия:** 1.0.0

---

## Обратная связь

Нашли ошибку в API или есть предложение? Создайте issue в репозитории.

---

**Версия документа:** 1.0  
**Дата:** 2026-05-12  
**Статус:** Актуально
