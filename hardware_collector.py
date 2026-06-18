import psutil
import platform
import socket
import time
from datetime import datetime
from typing import Dict, Any, List
import threading

# Пытаемся импортировать LibreHardwareMonitor
LIBRE_AVAILABLE = False
try:
    import clr
    import os
    import sys
    
    libre_path = os.path.join(os.path.dirname(__file__), "LibreHardwareMonitorLib")
    if os.path.exists(libre_path):
        sys.path.append(libre_path)
    
    clr.AddReference("LibreHardwareMonitorLib")
    from LibreHardwareMonitor.Hardware import Computer, SensorType
    LIBRE_AVAILABLE = True
    print("✅ LibreHardwareMonitor загружен")
except Exception as e:
    print(f"⚠️ LibreHardwareMonitor не доступен: {e}")

# Пытаемся импортировать py3nvml для GPU
NVML_AVAILABLE = False
try:
    from py3nvml import py3nvml
    py3nvml.nvmlInit()
    NVML_AVAILABLE = True
    print("✅ py3nvml загружен")
except Exception as e:
    print(f"⚠️ py3nvml не доступен: {e}")

# Пытаемся импортировать WMI
WMI_AVAILABLE = False
try:
    import wmi
    WMI_AVAILABLE = True
    print("✅ WMI загружен")
except Exception as e:
    print(f"⚠️ WMI не доступен: {e}")

class HardwareCollector:
    def __init__(self):
        self.computer = None
        self.temperatures = {
            'cpu': 0.0,
            'gpu': 0.0,
            'disks': {}
        }
        self._init_libre_hardware()
    
    def _init_libre_hardware(self):
        """Инициализирует LibreHardwareMonitor"""
        if LIBRE_AVAILABLE:
            try:
                self.computer = Computer()
                self.computer.IsCpuEnabled = True
                self.computer.IsGpuEnabled = True
                self.computer.IsMemoryEnabled = True
                self.computer.IsStorageEnabled = True
                self.computer.Open()
                print("✅ LibreHardwareMonitor инициализирован")
            except Exception as e:
                print(f"⚠️ Ошибка инициализации LibreHardwareMonitor: {e}")
                self.computer = None
    
    def update_temperatures(self):
        """Обновляет данные о температурах"""
        if self.computer:
            try:
                self.computer.Update()
                
                for hardware in self.computer.Hardware:
                    hardware.Update()
                    
                    for sensor in hardware.Sensors:
                        if sensor.SensorType == SensorType.Temperature and sensor.Value is not None:
                            temp = float(sensor.Value)
                            name = sensor.Name.lower()
                            
                            if any(word in name for word in ['cpu', 'core', 'package']):
                                self.temperatures['cpu'] = max(self.temperatures['cpu'], temp)
                            elif any(word in name for word in ['gpu', 'graphics']):
                                self.temperatures['gpu'] = max(self.temperatures['gpu'], temp)
                            elif any(word in name for word in ['ssd', 'hdd', 'nvme', 'drive']):
                                disk_name = hardware.Name
                                self.temperatures['disks'][disk_name] = temp
                                
            except Exception as e:
                print(f"Ошибка обновления температур: {e}")
    
    def get_system_info(self) -> Dict[str, Any]:
        """Собирает общую информацию о системе"""
        boot_time = psutil.boot_time()
        uptime = time.time() - boot_time
        
        return {
            'os_name': platform.system(),
            'os_version': platform.release(),
            'os_build': platform.version(),
            'platform': platform.platform(),
            'architecture': platform.machine(),
            'computer_name': socket.gethostname(),
            'processor': platform.processor(),
            'uptime': uptime,
            'uptime_formatted': self._format_uptime(uptime)
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """Форматирует время работы"""
        days = int(seconds // 86400)
        hours = int((seconds % 86400) // 3600)
        minutes = int((seconds % 3600) // 60)
        
        if days > 0:
            return f"{days}д {hours}ч {minutes}м"
        elif hours > 0:
            return f"{hours}ч {minutes}м"
        else:
            return f"{minutes}м"
    
    def get_cpu_info(self) -> Dict[str, Any]:
        """Собирает информацию о CPU"""
        cpu_info = {
            'model': platform.processor(),
            'manufacturer': 'Unknown',
            'physical_cores': psutil.cpu_count(logical=False),
            'logical_cores': psutil.cpu_count(logical=True),
            'load': psutil.cpu_percent(interval=0.5),
            'temperature': self.temperatures.get('cpu', 0)
        }
        
        # Получаем частоту CPU
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            cpu_info['current_freq'] = cpu_freq.current
            cpu_info['max_freq'] = cpu_freq.max
            cpu_info['min_freq'] = cpu_freq.min
        
        # Получаем информацию о кэше
        try:
            cpu_info['l2_cache'] = self._get_cache_size(2)
            cpu_info['l3_cache'] = self._get_cache_size(3)
        except:
            cpu_info['l2_cache'] = 0
            cpu_info['l3_cache'] = 0
        
        # Пытаемся получить更多 информации через WMI
        if WMI_AVAILABLE:
            try:
                w = wmi.WMI()
                for processor in w.Win32_Processor():
                    cpu_info['model'] = processor.Name
                    cpu_info['manufacturer'] = processor.Manufacturer
                    cpu_info['max_freq'] = processor.MaxClockSpeed
                    cpu_info['socket'] = processor.SocketDesignation
                    break
            except:
                pass
        
        return cpu_info
    
    def _get_cache_size(self, level: int) -> int:
        """Получает размер кэша CPU"""
        try:
            import subprocess
            result = subprocess.run(
                ['wmic', 'cpu', 'get', f'L{level}CacheSize', '/value'],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if f'L{level}CacheSize' in line:
                    return int(line.split('=')[1])
        except:
            pass
        return 0
    
    def get_ram_info(self) -> Dict[str, Any]:
        """Собирает информацию о RAM"""
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        
        ram_info = {
            'total': mem.total / (1024**3),
            'available': mem.available / (1024**3),
            'used': mem.used / (1024**3),
            'percent': mem.percent,
            'swap_total': swap.total / (1024**3),
            'swap_used': swap.used / (1024**3),
            'swap_percent': swap.percent
        }
        
        # Получаем информацию о модулях RAM
        ram_modules = []
        if WMI_AVAILABLE:
            try:
                w = wmi.WMI()
                for module in w.Win32_PhysicalMemory():
                    ram_modules.append({
                        'bank': module.BankLabel,
                        'size': int(module.Capacity) / (1024**3),
                        'speed': module.Speed,
                        'manufacturer': module.Manufacturer,
                        'model': module.PartNumber
                    })
                ram_info['modules'] = ram_modules
                ram_info['total_slots'] = len(ram_modules)
                ram_info['max_capacity'] = sum(m['size'] for m in ram_modules)
            except:
                pass
        
        return ram_info
    
    def get_gpu_info(self) -> List[Dict[str, Any]]:
        """Собирает информацию о GPU"""
        gpus = []
        
        # Пытаемся получить данные через py3nvml (NVIDIA)
        if NVML_AVAILABLE:
            try:
                py3nvml.nvmlInit()
                device_count = py3nvml.nvmlDeviceGetCount()
                
                for i in range(device_count):
                    handle = py3nvml.nvmlDeviceGetHandleByIndex(i)
                    name = py3nvml.nvmlDeviceGetName(handle)
                    memory_info = py3nvml.nvmlDeviceGetMemoryInfo(handle)
                    utilization = py3nvml.nvmlDeviceGetUtilizationRates(handle)
                    temperature = py3nvml.nvmlDeviceGetTemperature(handle, py3nvml.NVML_TEMPERATURE_GPU)
                    
                    # Получаем версию драйвера
                    driver_version = py3nvml.nvmlSystemGetDriverVersion()
                    
                    gpus.append({
                        'index': i,
                        'name': name.decode('utf-8') if isinstance(name, bytes) else name,
                        'memory': memory_info.total / (1024**3),
                        'memory_used': memory_info.used / (1024**3),
                        'memory_free': memory_info.free / (1024**3),
                        'load': utilization.gpu,
                        'temperature': temperature,
                        'driver_version': driver_version.decode('utf-8') if isinstance(driver_version, bytes) else driver_version
                    })
                
                py3nvml.nvmlShutdown()
            except Exception as e:
                print(f"Ошибка получения данных GPU через NVML: {e}")
        
        # Если нет GPU через NVML, пробуем GPUtil
        if not gpus:
            try:
                import GPUtil
                gpu_devices = GPUtil.getGPUs()
                for i, gpu in enumerate(gpu_devices):
                    gpus.append({
                        'index': i,
                        'name': gpu.name,
                        'memory': gpu.memoryTotal / 1024,
                        'memory_used': gpu.memoryUsed / 1024,
                        'memory_free': (gpu.memoryTotal - gpu.memoryUsed) / 1024,
                        'load': gpu.load * 100,
                        'temperature': gpu.temperature,
                        'driver_version': 'Unknown'
                    })
            except Exception as e:
                print(f"Ошибка получения данных GPU через GPUtil: {e}")
        
        # Если ничего не получили, используем температуру из Libre
        if not gpus and self.temperatures.get('gpu', 0) > 0:
            gpus.append({
                'index': 0,
                'name': 'Unknown GPU',
                'memory': 0,
                'memory_used': 0,
                'memory_free': 0,
                'load': 0,
                'temperature': self.temperatures['gpu'],
                'driver_version': 'Unknown'
            })
        
        return gpus
    
    def get_disk_info(self) -> List[Dict[str, Any]]:
        """Собирает информацию о дисках"""
        disks = []
        
        partitions = psutil.disk_partitions()
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info = {
                    'letter': partition.device,
                    'mount': partition.mountpoint,
                    'fs': partition.fstype,
                    'total': usage.total / (1024**3),
                    'used': usage.used / (1024**3),
                    'free': usage.free / (1024**3),
                    'percent': usage.percent,
                    'temperature': 0
                }
                
                # Пытаемся получить температуру диска
                for disk_name, temp in self.temperatures['disks'].items():
                    if disk_name.lower() in partition.device.lower() or disk_name.lower() in partition.mountpoint.lower():
                        disk_info['temperature'] = temp
                        break
                
                # Получаем информацию о физическом диске через WMI
                if WMI_AVAILABLE:
                    try:
                        w = wmi.WMI()
                        for disk in w.Win32_DiskDrive():
                            if partition.device.replace('\\', '').replace(':', '') in disk.DeviceID:
                                disk_info['model'] = disk.Model
                                disk_info['interface'] = disk.InterfaceType
                                disk_info['media_type'] = disk.MediaType
                                break
                    except:
                        pass
                
                disks.append(disk_info)
            except Exception as e:
                print(f"Ошибка получения информации о диске {partition.device}: {e}")
                continue
        
        return disks
    
    def get_network_info(self) -> List[Dict[str, Any]]:
        """Собирает информацию о сетевых адаптерах"""
        adapters = []
        
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        net_io = psutil.net_io_counters(pernic=True)
        
        for name, addrs in net_if_addrs.items():
            adapter_info = {
                'name': name,
                'status': 'Активен' if net_if_stats.get(name, {}).isup else 'Неактивен',
                'mac_address': '',
                'ipv4_address': '',
                'ipv6_address': '',
                'subnet_mask': '',
                'speed': net_if_stats.get(name, {}).speed if name in net_if_stats else 0
            }
            
            # Добавляем сетевую активность
            if name in net_io:
                adapter_info['bytes_sent'] = net_io[name].bytes_sent
                adapter_info['bytes_recv'] = net_io[name].bytes_recv
                adapter_info['packets_sent'] = net_io[name].packets_sent
                adapter_info['packets_recv'] = net_io[name].packets_recv
            
            for addr in addrs:
                if addr.family == psutil.AF_LINK:
                    adapter_info['mac_address'] = addr.address
                elif addr.family == socket.AF_INET:
                    adapter_info['ipv4_address'] = addr.address
                    adapter_info['subnet_mask'] = addr.netmask
                elif addr.family == socket.AF_INET6:
                    adapter_info['ipv6_address'] = addr.address
            
            adapters.append(adapter_info)
        
        return adapters
    
    def get_motherboard_info(self) -> Dict[str, Any]:
        """Собирает информацию о материнской плате"""
        motherboard_info = {
            'manufacturer': 'Unknown',
            'model': 'Unknown',
            'version': 'Unknown',
            'serial_number': 'Unknown',
            'bios_version': 'Unknown',
            'bios_date': 'Unknown'
        }
        
        if WMI_AVAILABLE:
            try:
                w = wmi.WMI()
                
                # Информация о материнской плате
                for board in w.Win32_BaseBoard():
                    motherboard_info['manufacturer'] = board.Manufacturer
                    motherboard_info['model'] = board.Product
                    motherboard_info['version'] = board.Version
                    motherboard_info['serial_number'] = board.SerialNumber
                    break
                
                # Информация о BIOS
                for bios in w.Win32_BIOS():
                    motherboard_info['bios_version'] = bios.SMBIOSBIOSVersion
                    motherboard_info['bios_date'] = bios.ReleaseDate
                    break
                    
            except Exception as e:
                print(f"Ошибка получения информации о материнской плате: {e}")
        
        return motherboard_info
    
    def get_monitor_info(self) -> List[Dict[str, Any]]:
        """Собирает информацию о мониторах"""
        monitors = []
        
        try:
            from screeninfo import get_monitors
            screen_monitors = get_monitors()
            for i, monitor in enumerate(screen_monitors):
                monitors.append({
                    'name': monitor.name if hasattr(monitor, 'name') else f"Monitor {i+1}",
                    'resolution': f"{monitor.width}x{monitor.height}",
                    'width': monitor.width,
                    'height': monitor.height,
                    'is_primary': i == 0,
                    'refresh_rate': monitor.refresh_rate if hasattr(monitor, 'refresh_rate') else 60
                })
        except Exception as e:
            print(f"Ошибка получения информации о мониторах: {e}")
            
            # Fallback через tkinter
            try:
                import tkinter as tk
                root = tk.Tk()
                monitors.append({
                    'name': 'Primary Monitor',
                    'resolution': f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}",
                    'width': root.winfo_screenwidth(),
                    'height': root.winfo_screenheight(),
                    'is_primary': True,
                    'refresh_rate': 60
                })
                root.destroy()
            except:
                pass
        
        return monitors
    
    def collect_all_data(self) -> Dict[str, Any]:
        """Собирает все данные о системе"""
        # Обновляем температуры
        self.update_temperatures()
        
        data = {
            'timestamp': datetime.now().isoformat(),
            'system': self.get_system_info(),
            'cpu': self.get_cpu_info(),
            'ram': self.get_ram_info(),
            'gpu': self.get_gpu_info(),
            'disks': self.get_disk_info(),
            'network': self.get_network_info(),
            'motherboard': self.get_motherboard_info(),
            'monitors': self.get_monitor_info()
        }
        
        return data
    
    def close(self):
        """Закрывает соединения"""
        if self.computer:
            try:
                self.computer.Close()
                print("✅ LibreHardwareMonitor закрыт")
            except:
                pass
        
        if NVML_AVAILABLE:
            try:
                py3nvml.nvmlShutdown()
                print("✅ NVML закрыт")
            except:
                pass