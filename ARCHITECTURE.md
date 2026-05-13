# Архитектура DWDM Network Simulator

Документация архитектуры проекта: структура модулей, паттерны проектирования и взаимодействие компонентов.

---

## Содержание

1. [Обзор архитектуры](#обзор-архитектуры)
2. [Структура проекта](#структура-проекта)
3. [Слои приложения](#слои-приложения)
4. [Модели данных](#модели-данных)
5. [Бизнес-логика](#бизнес-логика)
6. [Графический интерфейс](#графический-интерфейс)
7. [Паттерны проектирования](#паттерны-проектирования)
8. [Потоки данных](#потоки-данных)
9. [Расширяемость](#расширяемость)

---

## Обзор архитектуры

DWDM Network Simulator построен по **трехслойной архитектуре**:

```
┌─────────────────────────────────────────────┐
│         Presentation Layer (GUI)            │
│  PyQt5, Folium, Matplotlib, WebEngine       │
├─────────────────────────────────────────────┤
│       Business Logic Layer (Core)           │
│  Managers, Calculators, Simulation Engine   │
├─────────────────────────────────────────────┤
│         Data Layer (Models)                 │
│  Network, Node, Fiber, Channel, Equipment   │
└─────────────────────────────────────────────┘
```

### Принципы проектирования

1. **Separation of Concerns** - разделение ответственности между слоями
2. **Single Responsibility** - каждый класс отвечает за одну задачу
3. **Dependency Injection** - зависимости передаются через конструктор
4. **Data Classes** - использование `@dataclass` для моделей
5. **Type Hints** - строгая типизация для читаемости и безопасности

---

## Структура проекта

```
PROTO/
├── main.py                      # Точка входа
├── requirements.txt             # Зависимости
├── README.md                    # Документация
├── PHYSICS.md                   # Физические модели
├── ARCHITECTURE.md              # Этот файл
├── USER_GUIDE.md                # Руководство пользователя
├── API.md                       # API документация
│
├── core/                        # Ядро приложения
│   ├── __init__.py
│   │
│   ├── models/                  # Модели данных
│   │   ├── __init__.py
│   │   ├── network.py           # Контейнер сети
│   │   ├── node.py              # Узел сети
│   │   ├── fiber.py             # Волоконная линия
│   │   ├── channel.py           # DWDM канал
│   │   ├── equipment.py         # Оборудование
│   │   └── traffic.py           # Трафик
│   │
│   ├── calculators/             # Физические расчеты
│   │   ├── __init__.py
│   │   ├── dispersion.py        # Расчет дисперсии
│   │   ├── dispersion_visualizer.py  # Визуализация дисперсии
│   │   ├── attenuation.py       # Расчет затухания
│   │   ├── power_budget.py      # Бюджет мощности
│   │   ├── amplifier_placer.py  # Размещение усилителей
│   │   └── frequency_plan.py    # Частотный план ITU-T
│   │
│   └── managers/                # Менеджеры бизнес-логики
│       ├── __init__.py
│       ├── topology_manager.py  # Управление топологией
│       ├── topology_analyzer.py # Анализ топологии
│       ├── traffic_manager.py   # Управление трафиком
│       └── simulation_manager.py # Оркестрация симуляции
│
├── gui/                         # Графический интерфейс
│   ├── __init__.py
│   ├── main_window.py           # Главное окно
│   └── map_widget.py            # Виджет карты и вкладок
│
├── utils/                       # Утилиты
│   ├── __init__.py
│   └── project_io.py            # Сохранение/загрузка JSON
│
└── examples/                    # Примеры схем
    └── test_scheme_variant_01.json
```

---

## Слои приложения

### 1. Data Layer (Модели данных)

**Назначение:** Представление данных сети в виде Python объектов.

**Компоненты:**

- `Network` - контейнер для всех объектов
- `Node` - узел сети (город, точка присутствия)
- `Fiber` - волоконная линия между узлами
- `Channel` - DWDM канал (лямбда)
- `Equipment` - оборудование в узле
- `Traffic` - требования по трафику

**Особенности:**

- Используются `@dataclass` для автоматической генерации `__init__`, `__repr__`
- Все модели immutable где возможно
- Валидация данных в `__post_init__`
- Методы расчета базовых параметров (например, `calculate_fiber_loss()`)

**Пример:**

```python
@dataclass
class Fiber:
    fiber_id: str
    source_node_id: str
    target_node_id: str
    length_km: float
    fiber_type: FiberType = FiberType.G652

    def calculate_fiber_loss(self) -> float:
        # Логика расчета потерь
        pass
```

---

### 2. Business Logic Layer (Бизнес-логика)

**Назначение:** Реализация алгоритмов и бизнес-правил.

#### Calculators (Калькуляторы)

Отвечают за физические расчеты:

- **DispersionCalculator** - расчет ХД и ПМД
  - Формулы из ITU-T стандартов
  - Учет типа волокна, длины, битрейта
  - Проверка лимитов

- **PowerBudgetCalculator** - расчет бюджета мощности
  - Затухание в волокнах
  - Усиление в EDFA
  - Запас по мощности

- **AmplifierPlacer** - автоматическое размещение усилителей
  - Алгоритм разбиения на пролеты
  - Оптимизация позиций EDFA

- **FrequencyPlan** - частотный план ITU-T
  - Сетка 50/100 GHz
  - Преобразование частота ↔ длина волны

#### Managers (Менеджеры)

Отвечают за управление объектами и оркестрацию:

- **TopologyManager** - управление топологией
  - Построение графа NetworkX
  - Поиск маршрутов (Dijkstra, A\*)
  - Валидация связности

- **TopologyAnalyzer** - анализ топологии
  - Метрики связности
  - Диаметр сети
  - Критические узлы

- **TrafficManager** - управление трафиком
  - Матрица трафика
  - Загрузка линий
  - Маршрутизация потоков

- **SimulationManager** - оркестрация симуляции
  - Координация всех расчетов
  - Сбор результатов
  - Обработка ошибок

**Паттерн:** Manager координирует работу нескольких Calculator'ов.

---

### 3. Presentation Layer (GUI)

**Назначение:** Взаимодействие с пользователем.

**Технологии:**

- **PyQt5** - основной фреймворк GUI
- **QtWebEngineView** - встраивание веб-контента
- **Folium** - интерактивные карты (Leaflet.js)
- **Matplotlib** - графики и визуализация

**Компоненты:**

#### MainWindow

Главное окно приложения:

- Меню (Файл, Правка, Вид, Симуляция, Справка)
- Панель инструментов
- Статус-бар
- Центральный виджет (MapWidget)

#### MapWidget

Основной виджет с вкладками:

- **Карта** - интерактивная карта Folium
- **Топология** - граф сети, таблицы узлов/линий
- **Трафик** - матрица трафика, загрузка линий
- **Дисперсия** - результаты расчетов, графики
- **Бюджет мощности** - таблица бюджета, запасы

**Взаимодействие GUI ↔ Core:**

```python
# GUI вызывает Core
simulation_manager = SimulationManager(network)
results = simulation_manager.run_simulation()

# GUI отображает результаты
self.display_results(results)
```

---

## Модели данных

### Иерархия моделей

```
Network (контейнер)
├── nodes: Dict[str, Node]
├── fibers: Dict[str, Fiber]
├── channels: Dict[str, Channel]
└── equipment: Dict[str, Equipment]
```

### Связи между моделями

```
Node ←──── Fiber ────→ Node
  ↑                      ↑
  │                      │
Equipment            Channel (path: List[Node])
```

### Жизненный цикл объектов

1. **Создание** - через конструктор или фабричный метод
2. **Добавление в Network** - через `network.add_*()`
3. **Использование** - передача в Calculator/Manager
4. **Сериализация** - сохранение в JSON через `project_io`
5. **Десериализация** - загрузка из JSON

---

## Бизнес-логика

### Алгоритм симуляции

```
1. Валидация входных данных
   ├── Проверка связности топологии
   ├── Проверка маршрутов каналов
   └── Проверка параметров оборудования

2. Расчет топологии
   ├── Построение графа
   ├── Поиск маршрутов
   └── Анализ связности

3. Расчет трафика
   ├── Матрица потоков
   ├── Загрузка линий
   └── Маршрутизация

4. Физические расчеты для каждого канала
   ├── Расчет дисперсии (ХД + ПМД)
   ├── Расчет затухания
   ├── Расчет бюджета мощности
   └── Визуализация уширения импульса

5. Агрегация результатов
   ├── Сбор метрик
   ├── Выявление проблем
   └── Формирование отчета
```

### Расчет дисперсии (детально)

```python
def calculate_dispersion(channel: Channel, path_fibers: List[Fiber]):
    # 1. Получить параметры источника
    laser_type = channel.laser_type
    spectral_width = get_spectral_width(laser_type)

    # 2. Рассчитать ХД для каждого сегмента
    total_cd = 0.0
    for fiber in path_fibers:
        D = fiber.get_dispersion_coefficient()
        L = fiber.length_km
        cd_segment = D * L  # пс/нм
        total_cd += cd_segment

    # 3. Рассчитать ПМД (RSS метод)
    pmd_squared_sum = 0.0
    for fiber in path_fibers:
        D_pmd = get_pmd_coefficient(fiber.fiber_type)
        L = fiber.length_km
        pmd_squared_sum += (D_pmd * sqrt(L)) ** 2
    total_pmd = sqrt(pmd_squared_sum)

    # 4. Проверить лимиты
    cd_limit = get_cd_limit(channel.bitrate_gbps)
    pmd_limit = get_pmd_limit(channel.bitrate_gbps)

    return DispersionResult(
        total_cd=total_cd,
        total_pmd=total_pmd,
        cd_ok=(abs(total_cd) <= cd_limit),
        pmd_ok=(total_pmd <= pmd_limit)
    )
```

---

## Графический интерфейс

### Архитектура GUI

```
MainWindow (QMainWindow)
└── MapWidget (QWidget)
    ├── QSplitter (horizontal)
    │   ├── Left Panel
    │   │   └── QTreeWidget (объекты сети)
    │   └── Right Panel
    │       ├── QWebEngineView (карта Folium)
    │       └── QTabWidget (вкладки результатов)
    │           ├── Топология
    │           ├── Трафик
    │           ├── Дисперсия
    │           └── Бюджет мощности
    └── Dialogs
        ├── AddNodeDialog
        ├── AddFiberDialog
        ├── AddChannelDialog
        └── SettingsDialog
```

### Взаимодействие с картой

**Проблема:** Folium генерирует HTML, PyQt5 отображает через QtWebEngine.

**Решение:** QWebChannel для двустороннего взаимодействия Python ↔ JavaScript.

```python
# Python → JavaScript
self.web_view.page().runJavaScript(
    f"addMarker({lat}, {lon}, '{label}');"
)

# JavaScript → Python (через QWebChannel)
class Bridge(QObject):
    @pyqtSlot(float, float)
    def onMapClick(self, lat, lon):
        # Обработка клика на карте
        pass

channel = QWebChannel()
channel.registerObject("bridge", Bridge())
self.web_view.page().setWebChannel(channel)
```

### Обновление UI

**Паттерн:** Observer (через Qt Signals/Slots)

```python
class SimulationManager(QObject):
    progress_updated = pyqtSignal(int)  # Signal

    def run_simulation(self):
        for i, step in enumerate(steps):
            # Выполнение шага
            self.progress_updated.emit(i)  # Emit signal

# В GUI
sim_manager.progress_updated.connect(self.update_progress_bar)  # Connect slot
```

---

## Паттерны проектирования

### 1. Repository Pattern

**Применение:** `Network` как репозиторий для всех объектов.

```python
class Network:
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.fibers: Dict[str, Fiber] = {}

    def add_node(self, node: Node):
        self.nodes[node.node_id] = node

    def get_node(self, node_id: str) -> Optional[Node]:
        return self.nodes.get(node_id)
```

### 2. Strategy Pattern

**Применение:** Разные алгоритмы расчета дисперсии для разных типов волокон.

```python
class DispersionCalculator:
    def calculate(self, fiber: Fiber):
        strategy = self._get_strategy(fiber.fiber_type)
        return strategy.calculate(fiber)
```

### 3. Factory Pattern

**Применение:** Создание оборудования разных типов.

```python
class EquipmentFactory:
    @staticmethod
    def create_edfa(node_id: str, gain_db: float) -> Equipment:
        return Equipment(
            equipment_id=f"EDFA-{node_id}",
            equipment_type=EquipmentType.EDFA,
            node_id=node_id,
            parameters={"gain_db": gain_db}
        )
```

### 4. Observer Pattern

**Применение:** Qt Signals/Slots для обновления GUI.

```python
class SimulationManager(QObject):
    finished = pyqtSignal(dict)  # Observer pattern

    def run(self):
        results = self._do_simulation()
        self.finished.emit(results)  # Notify observers
```

### 5. Facade Pattern

**Применение:** `SimulationManager` как фасад для всех расчетов.

```python
class SimulationManager:
    def run_simulation(self):
        # Фасад скрывает сложность
        topology = self.topology_analyzer.analyze()
        dispersion = self.dispersion_calculator.calculate_all()
        power = self.power_budget_calculator.calculate_all()
        return {"topology": topology, "dispersion": dispersion, "power": power}
```

---

## Потоки данных

### Создание новой схемы

```
User Action (GUI)
    ↓
AddNodeDialog.accept()
    ↓
MapWidget.add_node(node_data)
    ↓
Network.add_node(Node(...))
    ↓
MapWidget.update_map()
    ↓
Folium map regeneration
    ↓
QWebEngineView.setHtml(html)
```

### Запуск симуляции

```
User clicks "Run Simulation"
    ↓
MainWindow.on_run_simulation()
    ↓
SimulationManager.run_simulation()
    ├── TopologyAnalyzer.analyze()
    ├── DispersionCalculator.calculate_all()
    │   └── for each channel:
    │       ├── get path fibers
    │       ├── calculate CD
    │       ├── calculate PMD
    │       └── check limits
    ├── PowerBudgetCalculator.calculate_all()
    └── TrafficManager.analyze()
    ↓
Results aggregation
    ↓
MapWidget.display_results(results)
    ├── Update tables
    ├── Generate plots
    └── Highlight issues
```

### Сохранение проекта

```
User clicks "Save"
    ↓
MainWindow.on_save()
    ↓
QFileDialog.getSaveFileName()
    ↓
project_io.save_network_to_json(network, filepath)
    ├── Serialize nodes
    ├── Serialize fibers
    ├── Serialize channels
    └── Serialize equipment
    ↓
json.dump(data, file)
```

---

## Расширяемость

### Добавление нового типа волокна

1. Добавить в `FiberType` enum:

```python
class FiberType(Enum):
    G658 = "G.658"  # Новый тип
```

2. Добавить параметры в словари:

```python
ATTENUATION_MAP = {
    FiberType.G658: 0.20,
}

DISPERSION_COEFF_MAP = {
    FiberType.G658: 15.0,
}
```

3. Обновить GUI (выпадающий список типов волокон)

### Добавление нового калькулятора

1. Создать класс в `core/calculators/`:

```python
class NonlinearEffectsCalculator:
    def __init__(self, network: Network):
        self.network = network

    def calculate_spm(self, channel: Channel) -> float:
        # Self-Phase Modulation
        pass
```

2. Интегрировать в `SimulationManager`:

```python
class SimulationManager:
    def run_simulation(self):
        # ...
        nonlinear = self.nonlinear_calculator.calculate_all()
        results["nonlinear"] = nonlinear
```

3. Добавить вкладку в GUI для отображения результатов

### Добавление нового формата экспорта

1. Создать функцию в `utils/`:

```python
def export_to_excel(network: Network, results: dict, filepath: str):
    import pandas as pd
    # Экспорт в Excel
```

2. Добавить пункт меню в `MainWindow`:

```python
export_excel_action = QAction("Экспорт в Excel", self)
export_excel_action.triggered.connect(self.on_export_excel)
```

---

## Зависимости

### Внешние библиотеки

```
PyQt5 (5.15+)
├── QtCore - базовые классы
├── QtWidgets - виджеты GUI
├── QtWebEngineWidgets - встраивание веб-контента
└── QtWebChannel - Python ↔ JavaScript

NetworkX (3.0+)
└── Анализ графов, поиск путей

NumPy (1.24+)
└── Научные вычисления

SciPy (1.10+)
└── Специальные функции

Matplotlib (3.7+)
└── Визуализация графиков

Folium (0.14+)
└── Интерактивные карты
```

### Граф зависимостей модулей

```
gui/
├── depends on → core/models/
├── depends on → core/managers/
└── depends on → utils/

core/managers/
├── depends on → core/models/
└── depends on → core/calculators/

core/calculators/
└── depends on → core/models/

utils/
└── depends on → core/models/
```

**Правило:** Зависимости только вниз по иерархии (нет циклических зависимостей).

---

## Производительность

### Оптимизации

1. **Кэширование графа топологии**
   - Граф строится один раз при изменении топологии
   - Переиспользуется для всех расчетов маршрутов

2. **Ленивая загрузка карты**
   - HTML карты генерируется только при открытии вкладки
   - Избегаем лишних рендерингов

3. **Batch расчеты**
   - Все каналы рассчитываются за один проход
   - Избегаем повторных обходов графа

### Узкие места

1. **Генерация HTML карты** - O(n) где n = количество узлов
2. **Рендеринг QtWebEngine** - зависит от сложности карты
3. **Расчет всех путей** - экспоненциальная сложность, используется cutoff

---

## Тестирование

### Структура тестов

```
tests/
├── test_models/
│   ├── test_network.py
│   ├── test_fiber.py
│   └── test_channel.py
├── test_calculators/
│   ├── test_dispersion.py
│   └── test_power_budget.py
└── test_managers/
    └── test_topology_manager.py
```

### Пример теста

```python
import unittest
from core.models.fiber import Fiber, FiberType

class TestFiberLoss(unittest.TestCase):
    def test_g652_attenuation(self):
        fiber = Fiber(
            fiber_id="test",
            source_node_id="A",
            target_node_id="B",
            length_km=100.0,
            fiber_type=FiberType.G652
        )

        loss = fiber.calculate_fiber_loss()
        expected = 100 * 0.22 + 3 * 0.02 + 2 * 0.3  # fiber + splices + connectors
        self.assertAlmostEqual(loss, expected, places=2)
```

---

## Безопасность

### Валидация входных данных

```python
def add_fiber(self, fiber: Fiber):
    # Проверка существования узлов
    if fiber.source_node_id not in self.nodes:
        raise ValueError(f"Source node {fiber.source_node_id} not found")

    # Проверка корректности длины
    if fiber.length_km <= 0:
        raise ValueError("Fiber length must be positive")

    self.fibers[fiber.fiber_id] = fiber
```

### Обработка ошибок

```python
try:
    results = simulation_manager.run_simulation()
except NetworkNotConnectedError as e:
    QMessageBox.warning(self, "Ошибка", f"Сеть не связна: {e}")
except Exception as e:
    QMessageBox.critical(self, "Ошибка", f"Неожиданная ошибка: {e}")
    logger.exception("Simulation failed")
```

---

## Логирование

```python
import logging

logger = logging.getLogger(__name__)

class SimulationManager:
    def run_simulation(self):
        logger.info("Starting simulation")
        try:
            results = self._do_simulation()
            logger.info(f"Simulation completed: {len(results)} channels")
            return results
        except Exception as e:
            logger.error(f"Simulation failed: {e}", exc_info=True)
            raise
```

---

## Будущие улучшения

### Краткосрочные (v1.1)

- [ ] Добавить расчет нелинейных эффектов (SPM, XPM)
- [ ] Реализовать автоматическую маршрутизацию трафика
- [ ] Добавить экспорт в Excel/PDF
- [x] Улучшить визуализацию дисперсии (Eye Diagram) — добавлен учет SNR/OSNR

### Среднесрочные (v1.5)

- [ ] Поддержка многопоточности для больших сетей
- [ ] Интеграция с реальными API операторов
- [ ] Веб-версия симулятора
- [ ] Плагинная архитектура для расширений

### Долгосрочные (v2.0)

- [ ] Машинное обучение для оптимизации маршрутов
- [ ] Симуляция отказов и резервирования
- [ ] Интеграция с системами мониторинга
- [ ] Поддержка SDN/NFV

---

## Заключение

Архитектура DWDM Network Simulator спроектирована с учетом:

- **Модульности** - легко добавлять новые компоненты
- **Тестируемости** - каждый модуль можно тестировать независимо
- **Расширяемости** - простое добавление новых типов оборудования и расчетов
- **Поддерживаемости** - чистый код, документация, типизация

Проект подходит как для учебных целей, так и для дальнейшего развития в промышленное решение.

---

**Версия документа:** 1.0  
**Дата:** 2026-05-12  
**Автор:** DWDM Network Simulator Team  
**Статус:** Актуально
