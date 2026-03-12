"""
Управление частотным планом (Frequency Plan)
Назначение длин волн по сетке ITU-T
"""
from typing import List, Optional, Dict
from core.models.channel import Channel
from core.models.network import Network


class FrequencyPlan:
    """
    Класс для работы с частотным планом ITU-T
    """
    
    # Стандартная сетка ITU-T 100 GHz (для C-band)
    REF_FREQ_THZ = 193.1  # Эталонная частота (THz)
    CHANNEL_SPACING_100GHZ = 0.1  # Шаг сетки 100 GHz (THz)
    CHANNEL_SPACING_50GHZ = 0.05  # Шаг сетки 50 GHz (THz)
    
    # Диапазон C-band (основной для DWDM)
    C_BAND_MIN_NM = 1528.77  # ~196.0 THz
    C_BAND_MAX_NM = 1567.13  # ~191.4 THz
    
    @staticmethod
    def wavelength_to_frequency(wavelength_nm: float) -> float:
        """Конвертирует длину волны (нм) в частоту (ТГц)"""
        return 299792.458 / wavelength_nm
    
    @staticmethod
    def frequency_to_wavelength(frequency_thz: float) -> float:
        """Конвертирует частоту (ТГц) в длину волны (нм)"""
        return 299792.458 / frequency_thz
    
    @staticmethod
    def get_itu_channel_frequency(channel_number: int, spacing_thz: float = 0.1) -> float:
        """
        Получает частоту для канала ITU-T
        
        Args:
            channel_number: Номер канала (0 - центральный канал на 193.1 THz)
            spacing_thz: Шаг сетки в ТГц (0.1 для 100 GHz, 0.05 для 50 GHz)
            
        Returns:
            Частота в ТГц
        """
        return FrequencyPlan.REF_FREQ_THZ + channel_number * spacing_thz
    
    @staticmethod
    def get_itu_channel_wavelength(channel_number: int, spacing_thz: float = 0.1) -> float:
        """Получает длину волны для канала ITU-T"""
        freq = FrequencyPlan.get_itu_channel_frequency(channel_number, spacing_thz)
        return FrequencyPlan.frequency_to_wavelength(freq)
    
    @staticmethod
    def is_in_c_band(wavelength_nm: float) -> bool:
        """Проверяет, попадает ли длина волны в границы C-band."""
        return FrequencyPlan.C_BAND_MIN_NM <= wavelength_nm <= FrequencyPlan.C_BAND_MAX_NM
    
    @staticmethod
    def assign_wavelengths_to_channels(channels: List[Channel], 
                                      spacing_thz: float = 0.1,
                                      start_channel: int = -40) -> Dict[str, int]:
        """
        Назначает длины волн каналам по сетке ITU-T
        
        Args:
            channels: Список каналов для назначения
            spacing_thz: Шаг сетки
            start_channel: Начальный номер канала (по умолчанию -40)
            
        Returns:
            Словарь {channel_id: channel_number}
        """
        assignments = {}
        current_channel_num = start_channel
        
        for channel in channels:
            wavelength = FrequencyPlan.get_itu_channel_wavelength(
                current_channel_num, spacing_thz
            )
            # Если вышли за пределы C-band, прекращаем назначение
            if not FrequencyPlan.is_in_c_band(wavelength):
                break
            channel.wavelength_nm = wavelength
            channel.frequency_thz = FrequencyPlan.wavelength_to_frequency(wavelength)
            assignments[channel.channel_id] = current_channel_num
            current_channel_num += 1
        
        return assignments
    
    @staticmethod
    def find_available_wavelength(network: Network, 
                                  path: List[str],
                                  spacing_thz: float = 0.1) -> Optional[float]:
        """
        Находит свободную длину волны для нового канала на пути
        
        Args:
            network: Модель сети
            path: Путь нового канала
            spacing_thz: Шаг сетки
            
        Returns:
            Длина волны в нм или None, если нет свободных
        """
        # Собираем занятые длины волн на этом пути
        used_wavelengths = set()
        
        for channel in network.channels.values():
            if channel.path == path:
                used_wavelengths.add(channel.wavelength_nm)
        
        # Ищем свободную длину волну в C-band
        for channel_num in range(-40, 41):  # Стандартный диапазон номеров
            wavelength = FrequencyPlan.get_itu_channel_wavelength(
                channel_num, spacing_thz
            )
            # Пропускаем длины волн вне C-band
            if not FrequencyPlan.is_in_c_band(wavelength):
                continue
            if wavelength not in used_wavelengths:
                return wavelength
        
        return None  # Все каналы заняты
    
    @staticmethod
    def validate_wavelength_assignment(network: Network) -> List[str]:
        """
        Проверяет корректность назначения длин волн (нет коллизий)
        
        Returns:
            Список предупреждений (пустой, если все в порядке)
        """
        warnings = []
        
        # Проверяем, что каналы на одном пути используют разные длины волн
        path_wavelengths = {}  # {tuple(path): set(wavelengths)}
        
        for channel in network.channels.values():
            path_key = tuple(channel.path)
            if path_key not in path_wavelengths:
                path_wavelengths[path_key] = set()
            
            if channel.wavelength_nm in path_wavelengths[path_key]:
                warnings.append(
                    f"Channel {channel.channel_id}: wavelength {channel.wavelength_nm:.2f} nm "
                    f"already used on path {path_key}"
                )
            else:
                path_wavelengths[path_key].add(channel.wavelength_nm)
        
        return warnings

