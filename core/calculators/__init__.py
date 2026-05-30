"""Пакет расчётных модулей (core.calculators).

Важно: этот пакет используется и в моделях. Не импортируйте тут тяжёлые модули,
которые тянут `core.models.*`, чтобы не создавать циклические импорты.
"""

from core.calculators.dispersion import DispersionCalculator, DispersionResult
from core.calculators.power_budget import PowerBudgetResult, calculate_power_budget
from core.calculators.attenuation import calculate_channel_attenuation, calculate_power_profile
from core.calculators.frequency_plan import FrequencyPlan
from core.calculators.amplifier_placer import AmplifierPlacer
from core.calculators.ber_calculator import BERCalculator, BERResult, calculate_channel_ber

__all__ = [
    "DispersionCalculator",
    "DispersionResult",
    "PowerBudgetResult",
    "calculate_power_budget",
    "calculate_channel_attenuation",
    "calculate_power_profile",
    "FrequencyPlan",
    "AmplifierPlacer",
    "BERCalculator",
    "BERResult",
    "calculate_channel_ber",
]
