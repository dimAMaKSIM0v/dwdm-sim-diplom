"""
Менеджер симуляции
Оркестрация всех расчетов и симуляций
"""
from typing import Dict, List
from core.models.network import Network
from core.calculators.power_budget import calculate_all_power_budgets, PowerBudgetResult
from core.calculators.amplifier_placer import AmplifierPlacer
from core.calculators.frequency_plan import FrequencyPlan


class SimulationManager:
    """Класс для управления симуляцией сети"""
    
    def __init__(self, network: Network):
        """
        Args:
            network: Модель сети
        """
        self.network = network
        self.power_budget_results: Dict[str, PowerBudgetResult] = {}
    
    def run_simulation(self, auto_place_amplifiers: bool = True) -> dict:
        """
        Запускает полную симуляцию сети
        
        Args:
            auto_place_amplifiers: Автоматически расставлять усилители
            
        Returns:
            Словарь с результатами симуляции
        """
        results = {
            'power_budgets': {},
            'amplifiers_placed': 0,
            'warnings': []
        }
        
        # 1. Валидация сети
        errors = self.network.validate()
        if errors:
            results['warnings'].extend([f"Ошибка: {e}" for e in errors])
            return results
        
        # 2. Назначение длин волн (если еще не назначены)
        channels_without_wavelength = [
            ch for ch in self.network.channels.values() 
            if ch.wavelength_nm == 0 or ch.wavelength_nm is None
        ]
        if channels_without_wavelength:
            FrequencyPlan.assign_wavelengths_to_channels(channels_without_wavelength)
        
        # 3. Автоматическая расстановка усилителей (если нужно)
        if auto_place_amplifiers:
            placer = AmplifierPlacer(self.network)
            results['amplifiers_placed'] = placer.place_amplifiers_for_all_channels()
        
        # 4. Расчет оптического бюджета для всех каналов
        self.power_budget_results = calculate_all_power_budgets(self.network)
        results['power_budgets'] = {
            ch_id: {
                'rx_power_dbm': res.rx_power_dbm,
                'power_margin_db': res.power_margin_db,
                # total_loss_db теперь трактуем как \"сырые\" потери без учета усиления
                'total_loss_db': res.total_loss_db,
                'raw_loss_db': res.raw_loss_db,
                'net_loss_db': res.net_loss_db,
                'is_valid': res.is_valid
            }
            for ch_id, res in self.power_budget_results.items()
        }
        
        # 5. Проверка частотного плана
        freq_warnings = FrequencyPlan.validate_wavelength_assignment(self.network)
        results['warnings'].extend(freq_warnings)
        
        return results
    
    def get_channel_statistics(self) -> Dict[str, any]:
        """Возвращает статистику по каналам"""
        if not self.power_budget_results:
            return {}
        
        valid_channels = sum(1 for r in self.power_budget_results.values() if r.is_valid)
        total_channels = len(self.power_budget_results)
        
        avg_margin = sum(r.power_margin_db for r in self.power_budget_results.values()) / total_channels if total_channels > 0 else 0
        
        return {
            'total_channels': total_channels,
            'valid_channels': valid_channels,
            'invalid_channels': total_channels - valid_channels,
            'average_power_margin_db': avg_margin
        }

