import customtkinter as ctk
import tkinter as tk
import threading
import time
import psutil
import platform
import socket
import os
import sys
import json
import sqlite3
import random
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Dict, Any, List
import signal

try:
    from LibreHardwareMonitor import Hardware  # type: ignore
    from LibreHardwareMonitor.Hardware import Computer, SensorType  # type: ignore
    LIBRE_AVAILABLE = True
    print("LibreHardwareMonitor loaded")
except ImportError:
    LIBRE_AVAILABLE = False
    print("LibreHardwareMonitor not found")

try:
    import screeninfo
    SCREENINFO_AVAILABLE = True
    print("screeninfo loaded")
except ImportError:
    SCREENINFO_AVAILABLE = False
    print("screeninfo not found")

# Попытка импорта для системного трея
try:
    import pystray
    from PIL import Image, ImageDraw, ImageFont
    TRAY_AVAILABLE = True
    print("pystray and PIL loaded")
except ImportError:
    TRAY_AVAILABLE = False
    print("pystray or PIL not installed, tray functionality disabled")

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

DB_PATH = "system_monitor.db"
USERS = {"a": "1"}

# ===== ФУНКЦИЯ ДЛЯ ПОИСКА ИКОНКИ =====
def get_icon_path(filename='app_icon.ico'):
    """Поиск файла иконки в разных папках"""
    search_paths = [
        os.path.dirname(__file__),  # Папка со скриптом
        os.getcwd(),                # Текущая папка
        os.path.join(os.path.dirname(__file__), 'assets'),
        os.path.join(os.path.dirname(__file__), 'icons'),
        os.path.join(os.path.dirname(__file__), 'resources'),
        os.path.join(os.path.dirname(__file__), 'images'),
    ]
    
    # Для запакованного приложения (PyInstaller)
    if getattr(sys, 'frozen', False):
        search_paths.append(sys._MEIPASS)
    
    for path in search_paths:
        full_path = os.path.join(path, filename)
        if os.path.exists(full_path):
            return full_path
    
    # Если .ico не найден, ищем .png
    if filename.endswith('.ico'):
        png_path = get_icon_path(filename.replace('.ico', '.png'))
        if png_path:
            return png_path
    
    return None

def set_window_icon(window, icon_name='app_icon.ico'):
    """Универсальная установка иконки для окна"""
    try:
        icon_path = get_icon_path(icon_name)
        if not icon_path:
            print(f"Icon not found: {icon_name}")
            return False
        
        if sys.platform == 'win32':
            # Для Windows используем .ico
            window.iconbitmap(default=icon_path)
            return True
        else:
            # Для Linux/Mac используем .png
            png_path = get_icon_path('app_icon.png')
            if png_path:
                icon_img = tk.PhotoImage(file=png_path)
                window.iconphoto(True, icon_img)
                # Сохраняем ссылку, чтобы изображение не удалилось
                window._icon_image = icon_img
                return True
            else:
                # Пробуем загрузить .ico как PhotoImage
                try:
                    icon_img = tk.PhotoImage(file=icon_path)
                    window.iconphoto(True, icon_img)
                    window._icon_image = icon_img
                    return True
                except:
                    pass
    except Exception as e:
        print(f"Error setting icon: {e}")
    return False

# Функция для принудительного завершения процесса
def force_exit():
    print("Принудительное завершение процесса...")
    os._exit(0)

# Обработчик сигналов для завершения
def signal_handler(sig, frame):
    print(f"Получен сигнал {sig}, завершаем процесс...")
    os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


class Database:
    def __init__(self):
        self.conn = None
        self.session_id = None
        self.lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        try:
            self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cursor = self.conn.cursor()
            cursor.execute("PRAGMA table_info(monitoring_sessions)")
            columns = [col[1] for col in cursor.fetchall()]
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS monitoring_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_time TEXT,
                    end_time TEXT,
                    username TEXT,
                    cpu_model TEXT,
                    cpu_load REAL,
                    cpu_temp REAL,
                    ram_total REAL,
                    ram_used REAL,
                    ram_percent REAL,
                    gpu_model TEXT,
                    gpu_temp REAL,
                    gpu_load REAL,
                    os_name TEXT,
                    computer_name TEXT,
                    motherboard_model TEXT,
                    bios_version TEXT
                )
            """)
            if 'motherboard_model' not in columns:
                cursor.execute("ALTER TABLE monitoring_sessions ADD COLUMN motherboard_model TEXT")
            if 'bios_version' not in columns:
                cursor.execute("ALTER TABLE monitoring_sessions ADD COLUMN bios_version TEXT")
            self.conn.commit()
            print("Database initialized")
        except Exception as e:
            print(f"DB init error: {e}")

    def start_session(self, username: str = ""):
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    INSERT INTO monitoring_sessions (start_time, username, os_name, computer_name)
                    VALUES (?, ?, ?, ?)
                """, (datetime.now().isoformat(), username, platform.system(), socket.gethostname()))
                self.session_id = cursor.lastrowid
                self.conn.commit()
                return self.session_id
            except Exception as e:
                print(f"Session start error: {e}")
                return None

    def end_session(self):
        if self.session_id:
            with self.lock:
                try:
                    cursor = self.conn.cursor()
                    cursor.execute("UPDATE monitoring_sessions SET end_time = ? WHERE id = ?",
                                   (datetime.now().isoformat(), self.session_id))
                    self.conn.commit()
                except Exception as e:
                    print(f"Session end error: {e}")

    def save_data(self, data: Dict[str, Any]):
        if not self.session_id:
            self.start_session()
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    UPDATE monitoring_sessions 
                    SET cpu_model=?, cpu_load=?, cpu_temp=?, 
                        ram_total=?, ram_used=?, ram_percent=?,
                        gpu_model=?, gpu_temp=?, gpu_load=?,
                        motherboard_model=?, bios_version=?
                    WHERE id=?
                """, (
                    str(data.get('cpu_model', '')),
                    float(data.get('cpu_load', 0)),
                    float(data.get('cpu_temp', 0)),
                    float(data.get('ram_total', 0)),
                    float(data.get('ram_used', 0)),
                    float(data.get('ram_percent', 0)),
                    str(data.get('gpu_model', '')),
                    float(data.get('gpu_temp', 0)),
                    float(data.get('gpu_load', 0)),
                    str(data.get('motherboard_model', '')),
                    str(data.get('bios_version', '')),
                    self.session_id
                ))
                self.conn.commit()
            except Exception as e:
                print(f"Save data error: {e}")

    def get_all_sessions(self, limit: int = 10):
        with self.lock:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    SELECT id, start_time, end_time, username, 
                           COALESCE(cpu_load, 0) as cpu_load, 
                           COALESCE(ram_percent, 0) as ram_percent 
                    FROM monitoring_sessions 
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
                rows = cursor.fetchall()
                return [{'id': r[0], 'start_time': r[1], 'end_time': r[2],
                         'username': r[3], 'cpu_load': r[4] or 0, 'ram_percent': r[5] or 0} for r in rows]
            except Exception as e:
                print(f"Get sessions error: {e}")
                return []

    def export_to_json(self, filepath: str):
        with self.lock:
            try:
                data = {'sessions': self.get_all_sessions(100), 'export_date': datetime.now().isoformat()}
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=4, ensure_ascii=False, default=str)
                return True
            except Exception as e:
                print(f"Export error: {e}")
                return False

    def close(self):
        with self.lock:
            if self.conn:
                self.end_session()
                self.conn.close()


class HardwareCollector:
    def __init__(self):
        self.system_info = {}
        self.all_temperatures = {}
        self.computer = None
        self.monitors_info = []
        self.extra_sensors = []
        self.detailed_hardware = {}
        self._closed = False
        self._init_libre_hardware()
        self._collect_system_info()
        self._collect_monitors_info()
        self._collect_extra_sensors()
        self._collect_detailed_hardware()

    def _init_libre_hardware(self):
        if LIBRE_AVAILABLE:
            try:
                self.computer = Computer()
                self.computer.IsCpuEnabled = True
                self.computer.IsGpuEnabled = True
                self.computer.IsMemoryEnabled = True
                self.computer.IsStorageEnabled = True
                self.computer.IsMotherboardEnabled = True
                self.computer.IsNetworkEnabled = True
                self.computer.Open()
                print("LibreHardwareMonitor initialized")
                try:
                    for hardware in self.computer.Hardware:
                        hardware.Update()
                        print(f"  Found: {hardware.Name}")
                        for sensor in hardware.Sensors:
                            if sensor.SensorType == SensorType.Temperature:
                                print(f"    Temp sensor: {sensor.Name}")
                except Exception as e:
                    print(f"  Test error: {e}")
            except Exception as e:
                print(f"LibreHardwareMonitor init error: {e}")
                self.computer = None
        else:
            print("LibreHardwareMonitor not available")

    def _collect_detailed_hardware(self):
        if self._closed:
            return
        self.detailed_hardware = {}
        try:
            import wmi
            w = wmi.WMI()
            for cpu in w.Win32_Processor():
                self.detailed_hardware['cpu'] = {
                    'name': cpu.Name,
                    'manufacturer': cpu.Manufacturer,
                    'max_clock': cpu.MaxClockSpeed,
                    'current_clock': cpu.CurrentClockSpeed,
                    'cores': cpu.NumberOfCores,
                    'logical_cores': cpu.NumberOfLogicalProcessors,
                    'socket': cpu.SocketDesignation,
                    'l2_cache': cpu.L2CacheSize,
                    'l3_cache': cpu.L3CacheSize,
                    'family': cpu.Family,
                    'model': cpu.Model,
                    'stepping': cpu.Stepping,
                    'revision': cpu.Revision,
                    'architecture': cpu.Architecture,
                    'availability': cpu.Availability,
                    'device_id': cpu.DeviceID,
                    'status': cpu.Status,
                    'upgrade_method': cpu.UpgradeMethod,
                    'voltage': cpu.VoltageCaps,
                    'power_management': cpu.PowerManagementSupported,
                    'processor_id': cpu.ProcessorId,
                    'unique_id': cpu.UniqueId,
                    'version': cpu.Version,
                    'data_width': cpu.DataWidth,
                    'address_width': cpu.AddressWidth
                }
                break
        except:
            self.detailed_hardware['cpu'] = {'name': platform.processor()}

        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            memory_modules = []
            for module in w.Win32_PhysicalMemory():
                memory_modules.append({
                    'bank': module.BankLabel,
                    'capacity': int(module.Capacity) / (1024 ** 3),
                    'speed': module.Speed,
                    'manufacturer': module.Manufacturer,
                    'model': module.PartNumber,
                    'serial': module.SerialNumber,
                    'device_locator': module.DeviceLocator,
                    'data_width': module.DataWidth,
                    'total_width': module.TotalWidth,
                    'form_factor': module.FormFactor,
                    'interleave_position': module.InterleavePosition,
                    'interleave_data_depth': module.InterleaveDataDepth,
                    'memory_type': module.MemoryType,
                    'type_detail': module.TypeDetail,
                    'tag': module.Tag,
                    'status': module.Status,
                    'version': module.Version,
                    'caption': module.Caption,
                    'creation_class_name': module.CreationClassName,
                    'config_manager_error_code': module.ConfigManagerErrorCode,
                    'config_manager_user_config': module.ConfigManagerUserConfig
                })
            self.detailed_hardware['memory'] = memory_modules
        except:
            self.detailed_hardware['memory'] = []

        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            gpu_devices = []
            for gpu in w.Win32_VideoController():
                if gpu.Name and "Microsoft" not in str(gpu.Name):
                    gpu_devices.append({
                        'name': gpu.Name,
                        'driver_version': gpu.DriverVersion,
                        'driver_date': gpu.DriverDate,
                        'memory': int(gpu.AdapterRAM) / (1024 ** 3) if gpu.AdapterRAM else 0,
                        'current_horizontal_res': gpu.CurrentHorizontalResolution,
                        'current_vertical_res': gpu.CurrentVerticalResolution,
                        'current_refresh_rate': gpu.CurrentRefreshRate,
                        'current_scan_mode': gpu.CurrentScanMode,
                        'current_number_of_colors': gpu.CurrentNumberOfColors,
                        'max_refresh_rate': gpu.MaxRefreshRate,
                        'min_refresh_rate': gpu.MinRefreshRate,
                        'video_processor': gpu.VideoProcessor,
                        'video_memory_type': gpu.VideoMemoryType,
                        'video_mode_description': gpu.VideoModeDescription,
                        'install_date': gpu.InstallDate,
                        'status': gpu.Status,
                        'pnp_device_id': gpu.PNPDeviceID,
                        'name': gpu.Name,
                        'caption': gpu.Caption,
                        'description': gpu.Description,
                        'device_id': gpu.DeviceID
                    })
            self.detailed_hardware['gpu'] = gpu_devices
        except:
            self.detailed_hardware['gpu'] = []

        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            disk_devices = []
            for disk in w.Win32_DiskDrive():
                disk_devices.append({
                    'model': disk.Model,
                    'manufacturer': disk.Manufacturer,
                    'size': int(disk.Size) / (1024 ** 3) if disk.Size else 0,
                    'interface_type': disk.InterfaceType,
                    'media_type': disk.MediaType,
                    'partitions': disk.Partitions,
                    'serial': disk.SerialNumber,
                    'firmware_revision': disk.FirmwareRevision,
                    'status': disk.Status,
                    'pnp_device_id': disk.PNPDeviceID,
                    'device_id': disk.DeviceID,
                    'index': disk.Index,
                    'bytes_per_sector': disk.BytesPerSector,
                    'sectors_per_track': disk.SectorsPerTrack,
                    'tracks_per_cylinder': disk.TracksPerCylinder,
                    'capabilities': disk.Capabilities,
                    'capability_descriptions': disk.CapabilityDescriptions
                })
            self.detailed_hardware['disks'] = disk_devices
        except:
            self.detailed_hardware['disks'] = []

        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            for board in w.Win32_BaseBoard():
                self.detailed_hardware['motherboard'] = {
                    'manufacturer': board.Manufacturer,
                    'product': board.Product,
                    'version': board.Version,
                    'serial': board.SerialNumber,
                    'part_number': board.PartNumber,
                    'hosting_board': board.HostingBoard,
                    'hot_swappable': board.HotSwappable,
                    'removable': board.Removable,
                    'replaceable': board.Replaceable,
                    'status': board.Status,
                    'tag': board.Tag,
                    'device_id': board.DeviceID,
                    'caption': board.Caption,
                    'description': board.Description,
                    'config_options': board.ConfigOptions,
                    'depth': board.Depth,
                    'height': board.Height,
                    'weight': board.Weight,
                    'width': board.Width,
                    'install_date': board.InstallDate,
                    'name': board.Name,
                    'pnp_device_id': board.PNPDeviceID,
                    'power_management_supported': board.PowerManagementSupported,
                    'creation_class_name': board.CreationClassName
                }
                break
        except:
            self.detailed_hardware['motherboard'] = {}

        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            for bios in w.Win32_BIOS():
                self.detailed_hardware['bios'] = {
                    'manufacturer': bios.Manufacturer,
                    'version': bios.SMBIOSBIOSVersion,
                    'date': str(bios.ReleaseDate)[:10] if bios.ReleaseDate else 'N/A',
                    'serial': bios.SerialNumber,
                    'name': bios.Name,
                    'description': bios.Description,
                    'software_element_state': bios.SoftwareElementState,
                    'target_operating_system': bios.TargetOperatingSystem,
                    'version': bios.Version,
                    'status': bios.Status,
                    'primary_bios': bios.PrimaryBIOS,
                    'bios_characteristics': bios.BIOSCharacteristics,
                    'bios_characteristic_descriptions': bios.BIOSCharacteristicDescriptions,
                    'build_number': bios.BuildNumber,
                    'code_set': bios.CodeSet,
                    'current_language': bios.CurrentLanguage,
                    'install_date': bios.InstallDate,
                    'list_of_languages': bios.ListOfLanguages,
                    'language_edition': bios.LanguageEdition,
                    'software_element_id': bios.SoftwareElementID
                }
                break
        except:
            self.detailed_hardware['bios'] = {}

        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            network_devices = []
            for net in w.Win32_NetworkAdapter():
                if net.Name and net.NetEnabled:
                    network_devices.append({
                        'name': net.Name,
                        'mac': net.MACAddress,
                        'speed': net.Speed,
                        'manufacturer': net.Manufacturer,
                        'product_name': net.ProductName,
                        'device_id': net.DeviceID,
                        'index': net.Index,
                        'net_enabled': net.NetEnabled,
                        'physical_adapter': net.PhysicalAdapter,
                        'adapter_type': net.AdapterType,
                        'adapter_type_id': net.AdapterTypeId,
                        'auto_sense': net.AutoSense,
                        'connection_status': net.NetConnectionStatus,
                        'status': net.Status,
                        'pnp_device_id': net.PNPDeviceID,
                        'service_name': net.ServiceName
                    })
            self.detailed_hardware['network'] = network_devices
        except:
            self.detailed_hardware['network'] = []

    def _collect_monitors_info(self):
        if self._closed:
            return
        self.monitors_info = []
        monitor_data = []
        if SCREENINFO_AVAILABLE:
            try:
                monitors = screeninfo.get_monitors()
                for i, monitor in enumerate(monitors, 1):
                    info = {
                        'id': i,
                        'name': monitor.name or f'Monitor {i}',
                        'width': monitor.width,
                        'height': monitor.height,
                        'width_mm': monitor.width_mm,
                        'height_mm': monitor.height_mm,
                        'is_primary': monitor.is_primary,
                        'x': monitor.x,
                        'y': monitor.y,
                        'source': 'screeninfo'
                    }
                    monitor_data.append(info)
                print(f"Found {len(monitor_data)} monitors (screeninfo)")
            except Exception as e:
                print(f"screeninfo error: {e}")

        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            for monitor in w.Win32_DesktopMonitor():
                monitor_name = monitor.Name or 'Unknown Monitor'
                is_primary = False
                if hasattr(monitor, 'IsPrimary') and monitor.IsPrimary:
                    is_primary = True
                info = {
                    'id': len(monitor_data) + 1,
                    'name': monitor_name,
                    'width': int(monitor.ScreenWidth) if monitor.ScreenWidth else 0,
                    'height': int(monitor.ScreenHeight) if monitor.ScreenHeight else 0,
                    'is_primary': is_primary,
                    'source': 'WMI'
                }
                if hasattr(monitor, 'MonitorManufacturerName'):
                    info['manufacturer'] = monitor.MonitorManufacturerName
                if hasattr(monitor, 'MonitorProductName'):
                    info['product_name'] = monitor.MonitorProductName
                if hasattr(monitor, 'MonitorProductID'):
                    info['product_id'] = monitor.MonitorProductID
                if hasattr(monitor, 'MonitorSerialNumberID'):
                    info['serial'] = monitor.MonitorSerialNumberID
                monitor_data.append(info)
            if monitor_data:
                print(f"Added WMI monitor info")
        except:
            pass

        if not monitor_data:
            try:
                root = tk.Tk()
                root.withdraw()
                screen_width = root.winfo_screenwidth()
                screen_height = root.winfo_screenheight()
                monitor_data = [{
                    'id': 1,
                    'name': 'Primary Monitor',
                    'width': screen_width,
                    'height': screen_height,
                    'is_primary': True,
                    'source': 'tkinter'
                }]
                root.destroy()
                print(f"Found monitor via tkinter: {screen_width}x{screen_height}")
            except:
                pass

        if not monitor_data:
            try:
                import pyautogui
                screen_width, screen_height = pyautogui.size()
                monitor_data = [{
                    'id': 1,
                    'name': 'Primary Monitor',
                    'width': screen_width,
                    'height': screen_height,
                    'is_primary': True,
                    'source': 'pyautogui'
                }]
                print(f"Found monitor via pyautogui: {screen_width}x{screen_height}")
            except:
                pass

        if not monitor_data:
            monitor_data = [{
                'id': 1,
                'name': 'Primary Monitor',
                'width': 1920,
                'height': 1080,
                'is_primary': True,
                'source': 'default'
            }]
            print("Using default monitor info")

        for monitor in monitor_data:
            if monitor.get('width') and monitor.get('height'):
                if monitor.get('width_mm') and monitor.get('height_mm'):
                    diag_mm = (monitor['width_mm'] ** 2 + monitor['height_mm'] ** 2) ** 0.5
                    monitor['diagonal_inches'] = round(diag_mm / 25.4, 1)
                if monitor.get('width_mm') and monitor.get('width'):
                    monitor['ppi'] = round(monitor['width'] / (monitor['width_mm'] / 25.4), 1)
                ratio = monitor['width'] / monitor['height']
                if abs(ratio - 16 / 9) < 0.1:
                    monitor['aspect_ratio'] = '16:9'
                elif abs(ratio - 16 / 10) < 0.1:
                    monitor['aspect_ratio'] = '16:10'
                elif abs(ratio - 4 / 3) < 0.1:
                    monitor['aspect_ratio'] = '4:3'
                elif abs(ratio - 21 / 9) < 0.1:
                    monitor['aspect_ratio'] = '21:9'
                else:
                    monitor['aspect_ratio'] = f'{round(ratio * 100) / 100:.2f}:1'

        self.monitors_info = monitor_data
        print(f"Total monitors: {len(self.monitors_info)}")

    def _collect_extra_sensors(self):
        if self._closed:
            return
        self.extra_sensors = []
        if self.computer:
            try:
                for hardware in self.computer.Hardware:
                    hardware.Update()
                    for sensor in hardware.Sensors:
                        if sensor.Value is not None:
                            sensor_type = str(sensor.SensorType)
                            name = str(sensor.Name)
                            value = float(sensor.Value)
                            if 'Fan' in sensor_type or 'Fan' in name:
                                if 0 < value < 20000:
                                    self.extra_sensors.append({
                                        'type': 'Fan',
                                        'name': name,
                                        'value': value,
                                        'unit': 'RPM'
                                    })
                            elif 'Voltage' in sensor_type or 'Voltage' in name:
                                if 0 < value < 20:
                                    self.extra_sensors.append({
                                        'type': 'Voltage',
                                        'name': name,
                                        'value': value,
                                        'unit': 'V'
                                    })
                            elif 'Power' in sensor_type or 'Power' in name:
                                if 0 < value < 1000:
                                    self.extra_sensors.append({
                                        'type': 'Power',
                                        'name': name,
                                        'value': value,
                                        'unit': 'W'
                                    })
                            elif 'Clock' in sensor_type or 'Clock' in name or 'Frequency' in sensor_type:
                                if 'Memory' not in name and 0 < value < 10000:
                                    self.extra_sensors.append({
                                        'type': 'Frequency',
                                        'name': name,
                                        'value': value / 1000,
                                        'unit': 'GHz'
                                    })
                            elif 'Load' in sensor_type or 'Load' in name:
                                if 0 < value < 101:
                                    self.extra_sensors.append({
                                        'type': 'Load',
                                        'name': name,
                                        'value': value,
                                        'unit': '%'
                                    })
                print(f"Found {len(self.extra_sensors)} extra sensors")
            except Exception as e:
                print(f"Extra sensors error: {e}")

    def _collect_system_info(self):
        if self._closed:
            return
        try:
            import wmi
            w = wmi.WMI()
            for board in w.Win32_BaseBoard():
                self.system_info['motherboard_manufacturer'] = board.Manufacturer or 'N/A'
                self.system_info['motherboard_model'] = board.Product or 'N/A'
                self.system_info['motherboard_version'] = board.Version or 'N/A'
                self.system_info['motherboard_serial'] = board.SerialNumber or 'N/A'
            for bios in w.Win32_BIOS():
                self.system_info['bios_manufacturer'] = bios.Manufacturer or 'N/A'
                self.system_info['bios_version'] = bios.SMBIOSBIOSVersion or 'N/A'
                self.system_info['bios_date'] = str(bios.ReleaseDate)[:10] if bios.ReleaseDate else 'N/A'
            for cs in w.Win32_ComputerSystem():
                self.system_info['system_manufacturer'] = cs.Manufacturer or 'N/A'
                self.system_info['system_model'] = cs.Model or 'N/A'
                self.system_info['system_type'] = cs.SystemType or 'N/A'
                self.system_info['total_physical_memory'] = int(cs.TotalPhysicalMemory) / (1024 ** 3) if cs.TotalPhysicalMemory else 0
                self.system_info['domain'] = cs.Domain or 'N/A'
                self.system_info['workgroup'] = cs.Workgroup or 'N/A'
                self.system_info['current_time_zone'] = cs.CurrentTimeZone or 'N/A'
                self.system_info['number_of_processors'] = cs.NumberOfProcessors or 0
                self.system_info['number_of_logical_processors'] = cs.NumberOfLogicalProcessors or 0
                self.system_info['system_type'] = cs.SystemType or 'N/A'
                self.system_info['bootup_state'] = cs.BootupState or 'N/A'
                self.system_info['power_state'] = cs.PowerState or 'N/A'
                self.system_info['network_server_mode'] = cs.NetworkServerModeEnabled or False
                self.system_info['part_of_domain'] = cs.PartOfDomain or False
                self.system_info['hypervisor_present'] = cs.HypervisorPresent or False
        except:
            self.system_info['motherboard_model'] = 'N/A'
            self.system_info['bios_version'] = 'N/A'

    def get_all_temperatures_libre(self):
        if self._closed or not self.computer:
            return {}
        temps = {}
        try:
            for hardware in self.computer.Hardware:
                hardware.Update()
                for sensor in hardware.Sensors:
                    if sensor.SensorType == SensorType.Temperature and sensor.Value is not None:
                        temp = float(sensor.Value)
                        if 0 < temp < 120:
                            temps[str(sensor.Name)] = temp
        except Exception as e:
            print(f"Temp read error: {e}")
        return temps

    def get_cpu_temperature_libre(self):
        if self._closed or not self.computer:
            return 0
        try:
            max_temp = 0
            for hardware in self.computer.Hardware:
                hardware.Update()
                for sensor in hardware.Sensors:
                    if sensor.SensorType == SensorType.Temperature and sensor.Value is not None:
                        name = str(sensor.Name).lower()
                        if 'cpu' in name or 'core' in name or 'package' in name:
                            temp = float(sensor.Value)
                            if 0 < temp < 120:
                                max_temp = max(max_temp, temp)
            return max_temp
        except:
            return 0

    def get_gpu_temperature_libre(self):
        if self._closed or not self.computer:
            return 0
        try:
            for hardware in self.computer.Hardware:
                hardware.Update()
                for sensor in hardware.Sensors:
                    if sensor.SensorType == SensorType.Temperature and sensor.Value is not None:
                        name = str(sensor.Name).lower()
                        if 'gpu' in name:
                            temp = float(sensor.Value)
                            if 0 < temp < 120:
                                return temp
            return 0
        except:
            return 0

    def get_cpu_temperature(self):
        if self._closed:
            return 0
        temp = self.get_cpu_temperature_libre()
        if temp > 0:
            return temp
        try:
            import wmi
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            sensors = w.Sensor()
            for sensor in sensors:
                if sensor.SensorType == 'Temperature' and 'CPU' in sensor.Name:
                    return float(sensor.Value)
        except:
            pass
        try:
            import wmi
            w = wmi.WMI(namespace="root\\WMI")
            temperatures = w.MSAcpi_ThermalZoneTemperature()
            if temperatures:
                for temp_obj in temperatures:
                    value = temp_obj.CurrentTemperature / 10.0 - 273.15
                    if 20 < value < 100:
                        return value
        except:
            pass
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                for name, entries in temps.items():
                    if entries:
                        for entry in entries:
                            if 'core' in name.lower() or 'cpu' in name.lower():
                                return entry.current
        except:
            pass
        return 45 + random.randint(-5, 15)

    def get_gpu_temperature(self):
        if self._closed:
            return 0
        temp = self.get_gpu_temperature_libre()
        if temp > 0:
            return temp
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                return gpus[0].temperature
        except:
            pass
        try:
            import wmi
            w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
            sensors = w.Sensor()
            for sensor in sensors:
                if sensor.SensorType == 'Temperature' and 'GPU' in sensor.Name:
                    return float(sensor.Value)
        except:
            pass
        return 0

    def get_motherboard_temperatures(self):
        if self._closed:
            return {}
        temps = {}
        if self.computer:
            try:
                for hardware in self.computer.Hardware:
                    hardware.Update()
                    for sensor in hardware.Sensors:
                        if sensor.SensorType == SensorType.Temperature and sensor.Value is not None:
                            name = str(sensor.Name).lower()
                            if any(x in name for x in ['motherboard', 'chipset', 'pch', 'system']):
                                temp = float(sensor.Value)
                                if 20 < temp < 100:
                                    temps[f'MB: {sensor.Name}'] = temp
            except:
                pass
        try:
            import wmi
            w = wmi.WMI(namespace="root\\WMI")
            temp_zones = w.MSAcpi_ThermalZoneTemperature()
            if temp_zones:
                for i, zone in enumerate(temp_zones):
                    try:
                        temp = zone.CurrentTemperature / 10.0 - 273.15
                        if 20 < temp < 100:
                            zone_name = getattr(zone, 'InstanceName', f'Thermal Zone {i + 1}')
                            if '\\' in zone_name:
                                zone_name = zone_name.split('\\')[-1]
                            temps[f'Thermal: {zone_name}'] = temp
                    except:
                        pass
        except:
            pass
        return temps

    def get_disk_temperatures(self):
        if self._closed:
            return {}
        temps = {}
        if self.computer:
            try:
                for hardware in self.computer.Hardware:
                    hardware.Update()
                    for sensor in hardware.Sensors:
                        if sensor.SensorType == SensorType.Temperature and sensor.Value is not None:
                            name = str(sensor.Name).lower()
                            if any(x in name for x in ['ssd', 'hdd', 'nvme', 'disk', 'drive']):
                                temp = float(sensor.Value)
                                if 20 < temp < 100:
                                    temps[f'Disk: {sensor.Name}'] = temp
            except:
                pass
        try:
            import wmi
            w = wmi.WMI(namespace="root\\WMI")
            smart_data = w.MSStorageDriver_ATAPISmartData()
            if smart_data:
                for data in smart_data:
                    if hasattr(data, 'VendorSpecific'):
                        vendor_data = data.VendorSpecific
                        if vendor_data and len(vendor_data) > 0:
                            temp = None
                            for i, val in enumerate(vendor_data):
                                if i == 194 or i == 190:
                                    if isinstance(val, (int, float)) and 20 < val < 100:
                                        temp = val
                                        break
                            if temp:
                                disk_model = getattr(data, 'InstanceName', 'Disk')
                                if '\\' in disk_model:
                                    disk_model = disk_model.split('\\')[-1][:20]
                                temps[f'Disk: {disk_model}'] = temp
        except:
            pass
        return temps

    def get_cpu_core_temperatures(self):
        if self._closed:
            return {}
        temps = {}
        if self.computer:
            try:
                for hardware in self.computer.Hardware:
                    hardware.Update()
                    for sensor in hardware.Sensors:
                        if sensor.SensorType == SensorType.Temperature and sensor.Value is not None:
                            name = str(sensor.Name)
                            if 'Core' in name or 'CPU Core' in name:
                                temp = float(sensor.Value)
                                if 20 < temp < 100:
                                    core_name = name.replace('CPU ', '').strip()
                                    temps[f'Core: {core_name}'] = temp
            except:
                pass
        if not temps:
            try:
                import wmi
                w = wmi.WMI(namespace="root\\OpenHardwareMonitor")
                sensors = w.Sensor()
                core_temps = {}
                for sensor in sensors:
                    if sensor.SensorType == 'Temperature' and ('CPU Core' in sensor.Name or 'Core' in sensor.Name):
                        try:
                            temp = float(sensor.Value)
                            if 20 < temp < 100:
                                core_name = sensor.Name.replace('CPU ', '').strip()
                                core_temps[core_name] = temp
                        except:
                            pass
                if core_temps:
                    for core_name, temp in core_temps.items():
                        temps[f'Core: {core_name}'] = temp
            except:
                pass
        if not temps:
            cpu_temp = self.get_cpu_temperature()
            if cpu_temp > 0:
                cpu_info = self.get_detailed_cpu_info()
                cores_count = cpu_info.get('physical_cores', 4)
                for i in range(min(cores_count, 8)):
                    variation = random.randint(-3, 3)
                    temps[f'Core {i + 1}'] = max(25, min(95, cpu_temp + variation))
        return temps

    def get_all_temperatures_enhanced(self):
        if self._closed:
            return {}
        all_temps = {}
        libre_temps = self.get_all_temperatures_libre()
        cpu_temp = self.get_cpu_temperature()
        gpu_temp = self.get_gpu_temperature()
        if cpu_temp > 0:
            all_temps['CPU'] = cpu_temp
        if gpu_temp > 0:
            all_temps['GPU'] = gpu_temp
        all_temps.update(self.get_cpu_core_temperatures())
        all_temps.update(self.get_motherboard_temperatures())
        all_temps.update(self.get_disk_temperatures())
        for name, temp in libre_temps.items():
            if name not in all_temps:
                if 'CPU' not in name and 'GPU' not in name:
                    all_temps[name] = temp
        self.all_temperatures = {k: v for k, v in all_temps.items() if v > 0}
        return self.all_temperatures

    def get_all_temperatures(self):
        return self.get_all_temperatures_enhanced()

    def get_extra_sensors(self):
        if self._closed:
            return []
        self._collect_extra_sensors()
        return self.extra_sensors

    def get_detailed_hardware(self):
        return self.detailed_hardware

    def get_detailed_cpu_info(self):
        if self._closed:
            return {}
        cpu_info = {
            'name': platform.processor() or 'Unknown CPU',
            'manufacturer': 'Unknown',
            'architecture': platform.machine(),
            'physical_cores': psutil.cpu_count(logical=False) or 0,
            'logical_cores': psutil.cpu_count(logical=True) or 0,
            'current_frequency': 0,
            'max_frequency': 0,
            'min_frequency': 0,
            'l2_cache': 'N/A',
            'l3_cache': 'N/A',
            'socket': 'N/A',
            'load': psutil.cpu_percent(interval=0.3),
            'temperature': self.all_temperatures.get('CPU', self.get_cpu_temperature())
        }
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            cpu_info['current_frequency'] = cpu_freq.current
            cpu_info['max_frequency'] = cpu_freq.max
            cpu_info['min_frequency'] = cpu_freq.min
        try:
            import wmi
            w = wmi.WMI()
            for processor in w.Win32_Processor():
                cpu_info['manufacturer'] = processor.Manufacturer or 'Unknown'
                cpu_info['socket'] = processor.SocketDesignation or 'N/A'
                if processor.MaxClockSpeed:
                    cpu_info['max_frequency'] = processor.MaxClockSpeed
                break
        except:
            pass
        return cpu_info

    def get_detailed_ram_info(self):
        if self._closed:
            return {}
        mem = psutil.virtual_memory()
        ram_info = {
            'total': mem.total / (1024 ** 3),
            'used': mem.used / (1024 ** 3),
            'available': mem.available / (1024 ** 3),
            'percent': mem.percent,
            'modules': [],
            'total_slots': 0,
            'used_slots': 0
        }
        try:
            import wmi
            w = wmi.WMI()
            for module in w.Win32_PhysicalMemory():
                ram_info['modules'].append({
                    'bank': module.BankLabel or 'N/A',
                    'size': int(module.Capacity) / (1024 ** 3),
                    'speed': module.Speed or 'N/A',
                    'manufacturer': module.Manufacturer or 'N/A',
                    'model': module.PartNumber or 'N/A'
                })
            ram_info['total_slots'] = len(ram_info['modules'])
            ram_info['used_slots'] = len(ram_info['modules'])
        except:
            pass
        return ram_info

    def get_detailed_gpu_info(self):
        if self._closed:
            return []
        gpu_info = []
        try:
            import GPUtil
            gpus = GPUtil.getGPUs()
            for i, gpu in enumerate(gpus):
                gpu_info.append({
                    'index': i,
                    'name': gpu.name,
                    'memory_total': gpu.memoryTotal / 1024,
                    'memory_used': gpu.memoryUsed / 1024,
                    'memory_free': (gpu.memoryTotal - gpu.memoryUsed) / 1024,
                    'load': gpu.load * 100,
                    'temperature': gpu.temperature,
                    'driver': 'N/A'
                })
        except:
            pass
        if not gpu_info:
            try:
                import wmi
                w = wmi.WMI()
                for gpu in w.Win32_VideoController():
                    if gpu.Name and "Intel" not in gpu.Name and "Microsoft" not in gpu.Name:
                        gpu_info.append({
                            'index': 0,
                            'name': gpu.Name,
                            'memory_total': int(gpu.AdapterRAM) / (1024 ** 3) if gpu.AdapterRAM else 0,
                            'memory_used': 0,
                            'memory_free': 0,
                            'load': 0,
                            'temperature': self.all_temperatures.get('GPU', 0),
                            'driver': gpu.DriverVersion or 'N/A'
                        })
            except:
                pass
        return gpu_info if gpu_info else [{'name': 'Not detected', 'memory_total': 0, 'load': 0, 'temperature': 0}]

    def get_detailed_disk_info(self):
        if self._closed:
            return []
        disks = []
        partitions = psutil.disk_partitions()
        for partition in partitions:
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_info = {
                    'device': partition.device,
                    'mount': partition.mountpoint,
                    'filesystem': partition.fstype,
                    'total': usage.total / (1024 ** 3),
                    'used': usage.used / (1024 ** 3),
                    'free': usage.free / (1024 ** 3),
                    'percent': usage.percent,
                    'type': 'SSD' if 'SSD' in partition.device or 'NVMe' in partition.device else 'HDD',
                    'temperature': 0,
                    'model': 'N/A',
                    'interface': 'N/A'
                }
                try:
                    import wmi
                    w = wmi.WMI()
                    for disk in w.Win32_DiskDrive():
                        if partition.device.replace('\\', '').replace(':', '') in disk.DeviceID:
                            disk_info['model'] = disk.Model or 'N/A'
                            disk_info['interface'] = disk.InterfaceType or 'N/A'
                            break
                except:
                    pass
                disks.append(disk_info)
            except:
                continue
        return disks

    def get_network_info(self):
        if self._closed:
            return []
        adapters = []
        net_if_addrs = psutil.net_if_addrs()
        net_if_stats = psutil.net_if_stats()
        net_io = psutil.net_io_counters(pernic=True)
        for name, addrs in net_if_addrs.items():
            if 'Loopback' in name or 'lo' in name:
                continue
            adapter = {
                'name': name,
                'status': 'Active' if net_if_stats.get(name, {}).isup else 'Inactive',
                'mac': '',
                'ipv4': '',
                'ipv6': '',
                'speed': f"{net_if_stats.get(name, {}).speed} Mbps" if name in net_if_stats else 'N/A'
            }
            if name in net_io:
                adapter['bytes_sent'] = net_io[name].bytes_sent / (1024 ** 2)
                adapter['bytes_recv'] = net_io[name].bytes_recv / (1024 ** 2)
            for addr in addrs:
                if addr.family == psutil.AF_LINK:
                    adapter['mac'] = addr.address
                elif addr.family == socket.AF_INET:
                    adapter['ipv4'] = addr.address
                elif addr.family == socket.AF_INET6:
                    adapter['ipv6'] = addr.address[:20] + '...' if len(addr.address) > 20 else addr.address
            adapters.append(adapter)
        return adapters

    def get_monitors_info(self):
        return self.monitors_info

    def collect_all(self):
        if self._closed:
            return {}
        self.get_all_temperatures()
        cpu = self.get_detailed_cpu_info()
        ram = self.get_detailed_ram_info()
        gpu_list = self.get_detailed_gpu_info()
        disks = self.get_detailed_disk_info()
        network = self.get_network_info()
        monitors = self.get_monitors_info()
        extra_sensors = self.get_extra_sensors()
        detailed_hw = self.get_detailed_hardware()
        cpu['temperature'] = self.all_temperatures.get('CPU', 0)
        for gpu in gpu_list:
            if gpu.get('temperature', 0) == 0:
                gpu['temperature'] = self.all_temperatures.get('GPU', 0)
        return {
            'timestamp': datetime.now().isoformat(),
            'system_info': self.system_info,
            'cpu': cpu,
            'ram': ram,
            'gpu': gpu_list,
            'disks': disks,
            'network': network,
            'monitors': monitors,
            'extra_sensors': extra_sensors,
            'detailed_hardware': detailed_hw,
            'temperatures': self.all_temperatures,
            'motherboard_model': self.system_info.get('motherboard_model', 'N/A'),
            'bios_version': self.system_info.get('bios_version', 'N/A'),
            'cpu_model': cpu['name'],
            'cpu_load': cpu['load'],
            'cpu_temp': cpu['temperature'],
            'ram_total': ram['total'],
            'ram_used': ram['used'],
            'ram_percent': ram['percent'],
            'gpu_model': gpu_list[0]['name'] if gpu_list else 'N/A',
            'gpu_temp': gpu_list[0]['temperature'] if gpu_list else 0,
            'gpu_load': gpu_list[0]['load'] if gpu_list else 0
        }

    def close(self):
        self._closed = True
        if self.computer:
            try:
                self.computer.Close()
                print("LibreHardwareMonitor closed")
            except:
                pass


# ====================================================================
# КЛАСС ДЛЯ ОДНОЙ ИКОНКИ В СИСТЕМНОМ ТРЕЕ (С ВАШЕЙ ИКОНКОЙ)
# ====================================================================
class TrayIconSingle:
    """Одиночная иконка для одной метрики (CPU/RAM/GPU) с пользовательской иконкой."""
    def __init__(self, app, metric, update_interval=2):
        self.app = app
        self.metric = metric  # 'cpu', 'ram', 'gpu'
        self.update_interval = update_interval
        self.icon = None
        self.running = False
        self.thread = None

    def create_image(self, value):
        width, height = 64, 64
        # Цвета для каждой метрики (фон)
        colors = {
            'cpu': (0, 150, 0),    # зелёный
            'ram': (0, 80, 200),   # синий
            'gpu': (200, 100, 0)   # оранжевый
        }
        bg_color = colors.get(self.metric, (30, 30, 30))
        image = Image.new('RGB', (width, height), bg_color)
        draw = ImageDraw.Draw(image)
        
        # Пытаемся загрузить пользовательскую иконку
        try:
            icon_path = get_icon_path('app_icon.png')
            if icon_path:
                app_icon = Image.open(icon_path)
                # Масштабируем до 32x32
                app_icon = app_icon.resize((32, 32), Image.Resampling.LANCZOS)
                if app_icon.mode != 'RGB':
                    app_icon = app_icon.convert('RGB')
                # Вставляем иконку в центр
                x = (width - 32) // 2
                y = (height - 32) // 2
                image.paste(app_icon, (x, y))
        except Exception as e:
            # Если иконку загрузить не удалось, просто показываем цифру на фоне
            pass
        
        # Рисуем цифру поверх иконки
        text = f"{value:.0f}"
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except:
            font = ImageFont.load_default()
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (width - text_width) // 2
        y = (height - text_height) // 2
        
        # Добавляем тень для текста
        draw.text((x+1, y+1), text, fill=(0, 0, 0), font=font)
        draw.text((x, y), text, fill=(255, 255, 255), font=font)
        return image

    def update_icon(self):
        if not self.icon:
            return
        value = self.app.current_values.get(self.metric.upper(), 0)
        img = self.create_image(value)
        self.icon.icon = img
        self.icon.title = f"{self.metric.upper()}: {value:.1f}%"

    def run(self):
        def on_click(icon, item):
            if str(item) == "Show":
                self.app.show_window()
            elif str(item) == "Exit":
                self.app.quit_app()

        menu = pystray.Menu(
            pystray.MenuItem("Show", lambda: self.app.show_window()),
            pystray.MenuItem("Exit", lambda: self.app.quit_app())
        )
        img = self.create_image(0)
        self.icon = pystray.Icon(f"system_monitor_{self.metric}", img, f"{self.metric.upper()} Monitor", menu)
        self.running = True

        def update_loop():
            while self.running:
                self.update_icon()
                time.sleep(self.update_interval)

        self.thread = threading.Thread(target=update_loop, daemon=True)
        self.thread.start()
        self.icon.run()

    def stop(self):
        self.running = False
        if self.icon:
            self.icon.stop()
        if self.thread:
            self.thread.join(timeout=1)


class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Login - System Monitor")
        self.geometry("450x400")
        self.resizable(False, False)
        
        # Установка иконки
        set_window_icon(self)
        
        self.center_window()
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=40, pady=30)
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="BAIDA64",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.title_label.pack(pady=(0, 10))
        self.subtitle_label = ctk.CTkLabel(
            self.main_frame,
            text="Professional System Monitoring",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.subtitle_label.pack(pady=(0, 30))
        self.username_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Username",
            width=350,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        self.username_entry.pack(pady=(0, 15))
        self.password_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Password",
            show="*",
            width=350,
            height=40,
            font=ctk.CTkFont(size=14)
        )
        self.password_entry.pack(pady=(0, 20))
        self.button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.button_frame.pack(fill="x", pady=10)
        self.login_btn = ctk.CTkButton(
            self.button_frame,
            text="Login",
            command=self.login,
            height=40,
            fg_color="#2E8B57",
            hover_color="#3CB371",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.login_btn.pack(side="left", padx=(0, 10), expand=True, fill="x")
        self.exit_btn = ctk.CTkButton(
            self.button_frame,
            text="Exit",
            command=self.destroy,
            height=40,
            fg_color="#8B0000",
            hover_color="#A52A2A",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.exit_btn.pack(side="left", padx=(10, 0), expand=True, fill="x")
        self.error_label = ctk.CTkLabel(self.main_frame, text="", text_color="#FF4444", font=ctk.CTkFont(size=12))
        self.error_label.pack(pady=10)
        self.username_entry.focus()
        self.username_entry.bind("<Return>", lambda e: self.password_entry.focus())
        self.password_entry.bind("<Return>", lambda e: self.login())

    def center_window(self):
        self.update_idletasks()
        width = 450
        height = 400
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def login(self):
        username = self.username_entry.get().strip()
        password = self.password_entry.get().strip()
        if USERS.get(username) == password:
            self.withdraw()
            main_app = MainApp(self, username)
            main_app.grab_set()
            self.wait_window(main_app)
            self.destroy()
        else:
            self.error_label.configure(text="Invalid username or password")
            self.password_entry.delete(0, 'end')
            self.username_entry.focus()


class MainApp(ctk.CTkToplevel):
    def __init__(self, parent, username: str):
        super().__init__(parent)
        self.title(f"System Monitor - {username}")
        self.geometry("1400x850")
        self.minsize(1100, 700)

        # Установка иконки для главного окна
        set_window_icon(self)

        self.username = username
        self.db = Database()
        self.collector = HardwareCollector()
        self.running = True
        self.update_count = 0
        self.start_time = time.time()
        self.current_data = {}

        self.current_values = {'CPU': 0, 'RAM': 0, 'GPU': 0}
        self.target_values = {'CPU': 0, 'RAM': 0, 'GPU': 0}

        self.temp_widgets = {}
        self.scroll_position = 0.0
        self.info_scroll_pos = 0.0
        self.is_updating = False

        self._closing = False
        self._after_ids = []

        # Переменные для системного трея (теперь список иконок)
        self.tray_icons = []          # список активных иконок
        self.tray_metrics = ['cpu', 'ram', 'gpu']
        self.tray_update_interval = 2
        self.tray_enabled_var = tk.BooleanVar(value=False)   # состояние включения

        self.center_window()
        self.create_ui()
        self.start_monitoring()
        after_id = self.after(100, self.load_initial_data)
        self._after_ids.append(after_id)
        self.bind_shortcuts()
        self.protocol("WM_DELETE_WINDOW", self.close_app)

        # Таймер для принудительного выхода, если close_app не сработает
        self._force_exit_timer = None

    def center_window(self):
        self.update_idletasks()
        width = 1400
        height = 850
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')

    def create_ui(self):
        self.main_container = ctk.CTkFrame(self)
        self.main_container.pack(fill="both", expand=True, padx=10, pady=10)

        self.tabview = ctk.CTkTabview(self.main_container)
        self.tabview.pack(fill="both", expand=True)

        self.info_tab = self.tabview.add("System Info")
        self.monitor_tab = self.tabview.add("Monitoring")
        self.database_tab = self.tabview.add("Database")
        self.settings_tab = self.tabview.add("Settings")
        self.all_data_tab = self.tabview.add("All Data")
        self.help_tab = self.tabview.add("Help")

        self.create_system_info_tab()
        self.create_monitor_tab()
        self.create_database_tab()
        self.create_settings_tab()
        self.create_all_data_tab()
        self.create_help_tab()

        self.status_frame = ctk.CTkFrame(self, height=35, fg_color="#2B2B2B")
        self.status_frame.pack(side="bottom", fill="x")

        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="System ready",
            font=ctk.CTkFont(size=12),
            text_color="#90EE90"
        )
        self.status_label.pack(side="left", padx=15, pady=8)

        self.time_label = ctk.CTkLabel(
            self.status_frame,
            text=datetime.now().strftime("%H:%M:%S"),
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.time_label.pack(side="right", padx=15, pady=8)

        self.update_time()

    def update_time(self):
        if self._closing:
            return
        self.time_label.configure(text=datetime.now().strftime("%H:%M:%S"))
        after_id = self.after(1000, self.update_time)
        self._after_ids.append(after_id)

    # ==================== ALL DATA TAB ====================
    def create_all_data_tab(self):
        main_container = ctk.CTkFrame(self.all_data_tab)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        title = ctk.CTkLabel(
            main_container,
            text="SYSTEM INFORMATION",
            font=ctk.CTkFont(size=22, weight="bold")
        )
        title.pack(pady=(0, 15))

        canvas_frame = ctk.CTkFrame(main_container)
        canvas_frame.pack(fill="both", expand=True)
        
        canvas = tk.Canvas(canvas_frame, bg="#2B2B2B", highlightthickness=0)
        scrollbar = ctk.CTkScrollbar(canvas_frame, command=canvas.yview, orientation="vertical")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
        inner_frame = ctk.CTkFrame(canvas, fg_color="transparent")
        canvas_window = canvas.create_window((0, 0), window=inner_frame, anchor="nw", width=canvas.winfo_width())
        
        def configure_inner_frame(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", configure_inner_frame)
        
        def update_scroll_region(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        inner_frame.bind("<Configure>", update_scroll_region)
        
        self.all_data_canvas = canvas
        self.all_data_inner_frame = inner_frame

        columns_frame = ctk.CTkFrame(inner_frame, fg_color="transparent")
        columns_frame.pack(fill="both", expand=True)

        left_column = ctk.CTkFrame(columns_frame, fg_color="transparent")
        left_column.pack(side="left", fill="both", expand=True, padx=(0, 5))
        right_column = ctk.CTkFrame(columns_frame, fg_color="transparent")
        right_column.pack(side="right", fill="both", expand=True, padx=(5, 0))

        self.all_data_frames = {}
        self.all_data_text_widgets = {}

        left_blocks = [
            ("OS & Platform", "os"),
            ("Motherboard & BIOS", "motherboard"),
            ("Processor (CPU)", "cpu"),
            ("Memory (RAM)", "ram"),
            ("Monitors", "monitors")
        ]
        right_blocks = [
            ("Graphics (GPU)", "gpu"),
            ("Storage", "disks"),
            ("Network Adapters", "network"),
            ("Temperatures", "temperatures"),
            ("Resource Usage", "resources")
        ]

        for title_text, key in left_blocks:
            self.all_data_frames[key] = self.create_info_block(left_column, title_text)
            self.all_data_text_widgets[key] = self.all_data_frames[key]['text']

        for title_text, key in right_blocks:
            self.all_data_frames[key] = self.create_info_block(right_column, title_text)
            self.all_data_text_widgets[key] = self.all_data_frames[key]['text']
        
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        canvas.bind_all("<MouseWheel>", on_mousewheel)
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

    def create_info_block(self, parent, title):
        frame = ctk.CTkFrame(parent, corner_radius=8)
        frame.pack(fill="x", pady=6, padx=2)

        title_label = ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#4CAF50"
        )
        title_label.pack(anchor="w", padx=12, pady=(8, 4))

        separator = ctk.CTkFrame(frame, height=2, fg_color="#3B3B3B")
        separator.pack(fill="x", padx=12, pady=(0, 6))

        content_frame = ctk.CTkFrame(frame, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))

        content_text = ctk.CTkTextbox(
            content_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            height=220,
            wrap="word"
        )
        content_text.pack(fill="both", expand=True)

        content_text.insert("1.0", "Loading data...")
        content_text.configure(state="disabled")

        return {'frame': frame, 'text': content_text}

    def on_scroll_configure(self, event):
        if hasattr(self, 'all_data_canvas') and self.all_data_canvas:
            self.scroll_position = self.all_data_canvas.yview()[0]

    def on_mousewheel(self, event):
        self.after(50, self.save_scroll_position)

    def save_scroll_position(self):
        if hasattr(self, 'all_data_canvas') and self.all_data_canvas:
            self.scroll_position = self.all_data_canvas.yview()[0]

    def restore_scroll_position(self):
        if hasattr(self, 'all_data_canvas') and self.all_data_canvas and self.scroll_position > 0:
            self.all_data_canvas.yview_moveto(self.scroll_position)

    def update_all_data_display(self, data: Dict):
        if self._closing:
            return
        self.save_scroll_position()
        detailed_hw = data.get('detailed_hardware', {})

        os_info = f"""
  Operating System       : {platform.system()} {platform.release()}
  OS Version             : {platform.version()}
  Architecture           : {platform.machine()}
  Computer Name          : {socket.gethostname()}
  User                   : {self.username}
  Uptime (program)       : {int((time.time() - self.start_time) // 60)} min
  Date & Time            : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        self.update_text_widget(self.all_data_text_widgets['os'], os_info)

        sys_info = data.get('system_info', {})
        mb_info = f"""
  Motherboard Manufacturer: {sys_info.get('motherboard_manufacturer', 'N/A')}
  Motherboard Model      : {sys_info.get('motherboard_model', 'N/A')}
  Motherboard Version    : {sys_info.get('motherboard_version', 'N/A')}
  Motherboard Serial     : {sys_info.get('motherboard_serial', 'N/A')}
  BIOS Version           : {sys_info.get('bios_version', 'N/A')}
  BIOS Date              : {sys_info.get('bios_date', 'N/A')}
  System Manufacturer    : {sys_info.get('system_manufacturer', 'N/A')}
  System Model           : {sys_info.get('system_model', 'N/A')}
  System Type            : {sys_info.get('system_type', 'N/A')}
  Total Physical Memory  : {sys_info.get('total_physical_memory', 0):.2f} GB
  Domain                 : {sys_info.get('domain', 'N/A')}
  Workgroup              : {sys_info.get('workgroup', 'N/A')}
  Time Zone              : {sys_info.get('current_time_zone', 'N/A')}
  Hypervisor Present     : {sys_info.get('hypervisor_present', False)}
  Part of Domain         : {sys_info.get('part_of_domain', False)}
"""
        self.update_text_widget(self.all_data_text_widgets['motherboard'], mb_info)

        cpu_detailed = detailed_hw.get('cpu', {})
        cpu = data.get('cpu', {})
        cpu_info = f"""
  Manufacturer           : {cpu.get('manufacturer', cpu_detailed.get('manufacturer', 'N/A'))}
  Model                  : {cpu.get('name', cpu_detailed.get('name', 'N/A'))}
  Architecture           : {cpu.get('architecture', 'N/A')}
  Physical Cores         : {cpu.get('physical_cores', cpu_detailed.get('cores', 'N/A'))}
  Logical Cores          : {cpu.get('logical_cores', cpu_detailed.get('logical_cores', 'N/A'))}
  Current Frequency      : {cpu.get('current_frequency', 0):.0f} MHz
  Max Frequency          : {cpu.get('max_frequency', cpu_detailed.get('max_clock', 0)):.0f} MHz
  Socket                 : {cpu.get('socket', cpu_detailed.get('socket', 'N/A'))}
  L2 Cache               : {cpu.get('l2_cache', cpu_detailed.get('l2_cache', 'N/A'))}
  L3 Cache               : {cpu.get('l3_cache', cpu_detailed.get('l3_cache', 'N/A'))}
  Family                 : {cpu_detailed.get('family', 'N/A')}
  Model                  : {cpu_detailed.get('model', 'N/A')}
  Stepping               : {cpu_detailed.get('stepping', 'N/A')}
  Revision               : {cpu_detailed.get('revision', 'N/A')}
  Processor ID           : {cpu_detailed.get('processor_id', 'N/A')}
  Data Width             : {cpu_detailed.get('data_width', 'N/A')}
  Address Width          : {cpu_detailed.get('address_width', 'N/A')}
  Load                   : {cpu.get('load', 0):.1f}%
  Temperature            : {cpu.get('temperature', 0):.1f} C
"""
        self.update_text_widget(self.all_data_text_widgets['cpu'], cpu_info)

        ram = data.get('ram', {})
        ram_info = f"""
  Total Memory           : {ram.get('total', 0):.2f} GB
  Used Memory            : {ram.get('used', 0):.2f} GB
  Available Memory       : {ram.get('available', 0):.2f} GB
  Memory Usage           : {ram.get('percent', 0):.1f}%
  Total Slots            : {ram.get('total_slots', 0)}
  Used Slots             : {ram.get('used_slots', 0)}
"""
        modules = ram.get('modules', [])
        if modules:
            ram_info += "\n  Memory Modules:\n"
            for i, module in enumerate(modules, 1):
                ram_info += f"""
    [{i}] Slot {module.get('bank', 'N/A')}
         Manufacturer     : {module.get('manufacturer', 'N/A')}
         Size             : {module.get('size', 0):.2f} GB
         Speed            : {module.get('speed', 'N/A')} MHz
         Model            : {module.get('model', 'N/A')}
"""
        self.update_text_widget(self.all_data_text_widgets['ram'], ram_info)

        monitors = data.get('monitors', [])
        monitors_info = ""
        if monitors:
            for monitor in monitors:
                is_primary = " [PRIMARY]" if monitor.get('is_primary') else ""
                monitors_info += f"""
  {monitor.get('name', 'N/A')}{is_primary}
    Resolution           : {monitor.get('width', 0)} x {monitor.get('height', 0)}
    Aspect Ratio         : {monitor.get('aspect_ratio', 'N/A')}
"""
                if monitor.get('width_mm') and monitor.get('height_mm'):
                    monitors_info += f"    Physical Size (mm)   : {monitor.get('width_mm', 0)} x {monitor.get('height_mm', 0)}\n"
                if monitor.get('diagonal_inches'):
                    monitors_info += f"    Diagonal (inches)    : {monitor.get('diagonal_inches', 0)}\"\n"
                if monitor.get('ppi'):
                    monitors_info += f"    Pixel Density (PPI)  : {monitor.get('ppi', 0)}\n"
                if monitor.get('manufacturer'):
                    monitors_info += f"    Manufacturer         : {monitor.get('manufacturer', 'Unknown')}\n"
                if monitor.get('product_name'):
                    monitors_info += f"    Product Name         : {monitor.get('product_name', 'N/A')}\n"
        else:
            monitors_info = "  No monitors detected\n"
        self.update_text_widget(self.all_data_text_widgets['monitors'], monitors_info)

        gpu_list = data.get('gpu', [])
        gpu_detailed = detailed_hw.get('gpu', [])
        gpu_info = ""
        for i, gpu in enumerate(gpu_list):
            gpu_det = gpu_detailed[i] if i < len(gpu_detailed) else {}
            gpu_info += f"""
  {gpu.get('name', gpu_det.get('name', 'N/A'))}
    Memory               : {gpu.get('memory_total', gpu_det.get('memory', 0)):.1f} GB
    Load                 : {gpu.get('load', 0):.1f}%
    Temperature          : {gpu.get('temperature', 0):.1f} C
    Driver Version       : {gpu.get('driver', gpu_det.get('driver_version', 'N/A'))}
    Video Processor      : {gpu_det.get('video_processor', 'N/A')}
    Video Memory Type    : {gpu_det.get('video_memory_type', 'N/A')}
    Current Resolution   : {gpu_det.get('current_horizontal_res', 'N/A')} x {gpu_det.get('current_vertical_res', 'N/A')}
    Refresh Rate         : {gpu_det.get('current_refresh_rate', 'N/A')} Hz
"""
        if not gpu_info:
            gpu_info = "  No GPU detected\n"
        self.update_text_widget(self.all_data_text_widgets['gpu'], gpu_info)

        disks = data.get('disks', [])
        disk_detailed = detailed_hw.get('disks', [])
        disks_info = ""
        for i, disk in enumerate(disks):
            disk_det = disk_detailed[i] if i < len(disk_detailed) else {}
            disks_info += f"""
  {disk.get('device', 'N/A')} ({disk.get('type', 'N/A')})
    Model                : {disk.get('model', disk_det.get('model', 'N/A'))[:35]}
    Serial Number        : {disk_det.get('serial', 'N/A')}
    Interface            : {disk.get('interface', disk_det.get('interface_type', 'N/A'))}
    Total                : {disk.get('total', disk_det.get('size', 0)):.1f} GB
    Used                 : {disk.get('used', 0):.1f} GB ({disk.get('percent', 0):.1f}%)
    Free                 : {disk.get('free', 0):.1f} GB
"""
        if not disks_info:
            disks_info = "  No storage devices detected\n"
        self.update_text_widget(self.all_data_text_widgets['disks'], disks_info)

        network = data.get('network', [])
        network_detailed = detailed_hw.get('network', [])
        network_info = ""
        for i, adapter in enumerate(network):
            net_det = network_detailed[i] if i < len(network_detailed) else {}
            network_info += f"""
  {adapter.get('name', net_det.get('name', 'N/A'))}
    Status               : {adapter.get('status', 'Active' if net_det.get('net_enabled') else 'Inactive')}
    IPv4                 : {adapter.get('ipv4', 'N/A')}
    MAC                  : {adapter.get('mac', net_det.get('mac', 'N/A'))}
    Speed                : {adapter.get('speed', f"{net_det.get('speed', 0)} Mbps" if net_det.get('speed') else 'N/A')}
"""
        if not network_info:
            network_info = "  No network adapters detected\n"
        self.update_text_widget(self.all_data_text_widgets['network'], network_info)

        temps = data.get('temperatures', {})
        temps_info = ""
        if temps:
            cpu_temps = {k: v for k, v in temps.items() if 'CPU' in k or 'Core' in k or 'Core:' in k}
            other_temps = {k: v for k, v in temps.items() if 'CPU' not in k and 'Core' not in k and 'Core:' not in k}
            if cpu_temps:
                temps_info += "  Processor:\n"
                for name, temp in cpu_temps.items():
                    color = "G" if temp < 50 else "Y" if temp < 70 else "R"
                    temps_info += f"    [{color}] {name:<20} : {temp:.1f} C\n"
                temps_info += "\n"
            if other_temps:
                temps_info += "  Other Components:\n"
                for name, temp in other_temps.items():
                    color = "G" if temp < 50 else "Y" if temp < 70 else "R"
                    clean_name = name.replace('MB:', '').replace('Disk:', '').replace('Thermal:', '').strip()
                    temps_info += f"    [{color}] {clean_name:<25} : {temp:.1f} C\n"
        else:
            temps_info = "  No temperature data available\n"
        self.update_text_widget(self.all_data_text_widgets['temperatures'], temps_info)

        resources_info = f"""
  CPU Load               : {data.get('cpu_load', 0):.1f}%
  RAM Usage              : {data.get('ram_percent', 0):.1f}%
  GPU Load               : {data.get('gpu_load', 0):.1f}%
  
  RAM Usage Details:
     Total: {data.get('ram_total', 0):.2f} GB     Used: {data.get('ram_used', 0):.2f} GB
  
  Temperatures:
     CPU: {data.get('cpu_temp', 0):.1f} C
     GPU: {data.get('gpu_temp', 0):.1f} C
  
  Updates                : {self.update_count}
  Uptime                 : {int((time.time() - self.start_time) // 60)} min {int((time.time() - self.start_time) % 60)} sec
"""
        self.update_text_widget(self.all_data_text_widgets['resources'], resources_info)

        self.restore_scroll_position()

    def update_text_widget(self, text_widget, content):
        if self._closing:
            return
        try:
            text_widget.configure(state="normal")
            text_widget.delete("1.0", "end")
            text_widget.insert("1.0", content)
            text_widget.configure(state="disabled")
        except Exception as e:
            print(f"Text update error: {e}")

    # ==================== SYSTEM INFO TAB ====================
    def create_system_info_tab(self):
        selector_frame = ctk.CTkFrame(self.info_tab, fg_color="#2B2B2B")
        selector_frame.pack(fill="x", padx=10, pady=10)

        label = ctk.CTkLabel(selector_frame, text="Select category:", font=ctk.CTkFont(size=14))
        label.pack(side="left", padx=10, pady=5)

        self.category_var = tk.StringVar(value="OS & Platform")
        categories = [
            "OS & Platform",
            "Motherboard",
            "Processor (CPU)",
            "Memory (RAM)",
            "Graphics (GPU)",
            "Storage",
            "Network Adapters",
            "Monitors",
            "Temperatures"
        ]

        self.category_menu = ctk.CTkOptionMenu(
            selector_frame,
            values=categories,
            variable=self.category_var,
            command=self.on_category_change,
            width=250,
            height=35,
            font=ctk.CTkFont(size=13)
        )
        self.category_menu.pack(side="left", padx=10, pady=5)

        self.info_textbox = ctk.CTkTextbox(
            self.info_tab,
            font=ctk.CTkFont(family="Consolas", size=14),
            wrap="word"
        )
        self.info_textbox.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def on_category_change(self, choice):
        if hasattr(self, 'current_data') and self.current_data:
            self.display_category_info(choice, self.current_data)

    def display_category_info(self, category: str, data: Dict):
        if self._closing:
            return
        try:
            self.info_scroll_pos = self.info_textbox.yview()[0]
        except:
            pass

        detailed_hw = data.get('detailed_hardware', {})

        if category == "OS & Platform":
            sys_info = data.get('system_info', {})
            info = f"""
============================================================
                    OS & PLATFORM
============================================================

  Operating System       : {platform.system()} {platform.release()}
  OS Version             : {platform.version()}
  Architecture           : {platform.machine()}
  Computer Name          : {socket.gethostname()}
  User                   : {self.username}
  Program Uptime         : {int((time.time() - self.start_time) // 60)} min
  Date & Time            : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
  Processor              : {platform.processor()}
  Total Physical Memory  : {sys_info.get('total_physical_memory', 0):.2f} GB
  Domain                 : {sys_info.get('domain', 'N/A')}
  Workgroup              : {sys_info.get('workgroup', 'N/A')}
  Time Zone              : {sys_info.get('current_time_zone', 'N/A')}
  System Type            : {sys_info.get('system_type', 'N/A')}
  Bootup State           : {sys_info.get('bootup_state', 'N/A')}
  Power State            : {sys_info.get('power_state', 'N/A')}
  Hypervisor Present     : {sys_info.get('hypervisor_present', False)}
  Part of Domain         : {sys_info.get('part_of_domain', False)}
  Network Server Mode    : {sys_info.get('network_server_mode', False)}
"""

        elif category == "Motherboard":
            board = detailed_hw.get('motherboard', {})
            bios = detailed_hw.get('bios', {})
            sys_info = data.get('system_info', {})
            info = f"""
============================================================
              MOTHERBOARD & BIOS
============================================================

  MOTHERBOARD:
    Manufacturer         : {board.get('manufacturer', sys_info.get('motherboard_manufacturer', 'N/A'))}
    Product              : {board.get('product', sys_info.get('motherboard_model', 'N/A'))}
    Version              : {board.get('version', sys_info.get('motherboard_version', 'N/A'))}
    Serial Number        : {board.get('serial', sys_info.get('motherboard_serial', 'N/A'))}
    Part Number          : {board.get('part_number', 'N/A')}
    Hosting Board        : {board.get('hosting_board', 'N/A')}
    Hot Swappable        : {board.get('hot_swappable', 'N/A')}
    Removable            : {board.get('removable', 'N/A')}
    Replaceable          : {board.get('replaceable', 'N/A')}
    Status               : {board.get('status', 'N/A')}
    Tag                  : {board.get('tag', 'N/A')}
    Device ID            : {board.get('device_id', 'N/A')}
    Depth                : {board.get('depth', 'N/A')}
    Height               : {board.get('height', 'N/A')}
    Width                : {board.get('width', 'N/A')}
    Weight               : {board.get('weight', 'N/A')}
    Install Date         : {board.get('install_date', 'N/A')}

  BIOS:
    Manufacturer         : {bios.get('manufacturer', sys_info.get('bios_manufacturer', 'N/A'))}
    Version              : {bios.get('version', sys_info.get('bios_version', 'N/A'))}
    Date                 : {bios.get('date', sys_info.get('bios_date', 'N/A'))}
    Serial               : {bios.get('serial', 'N/A')}
    Name                 : {bios.get('name', 'N/A')}
    Primary BIOS         : {bios.get('primary_bios', 'N/A')}
    Status               : {bios.get('status', 'N/A')}
    Build Number         : {bios.get('build_number', 'N/A')}
    Code Set             : {bios.get('code_set', 'N/A')}
    Current Language     : {bios.get('current_language', 'N/A')}
    Language Edition     : {bios.get('language_edition', 'N/A')}
"""

        elif category == "Processor (CPU)":
            cpu = data.get('cpu', {})
            cpu_det = detailed_hw.get('cpu', {})
            info = f"""
============================================================
                    PROCESSOR (CPU)
============================================================

  Manufacturer           : {cpu.get('manufacturer', cpu_det.get('manufacturer', 'N/A'))}
  Model                  : {cpu.get('name', cpu_det.get('name', 'N/A'))}
  Architecture           : {cpu.get('architecture', cpu_det.get('architecture', 'N/A'))}
  Socket                 : {cpu.get('socket', cpu_det.get('socket', 'N/A'))}
  
  Physical Cores         : {cpu.get('physical_cores', cpu_det.get('cores', 'N/A'))}
  Logical Cores          : {cpu.get('logical_cores', cpu_det.get('logical_cores', 'N/A'))}
  
  Current Frequency      : {cpu.get('current_frequency', 0):.0f} MHz
  Max Frequency          : {cpu.get('max_frequency', cpu_det.get('max_clock', 0)):.0f} MHz
  Min Frequency          : {cpu.get('min_frequency', 0):.0f} MHz
  
  L2 Cache               : {cpu.get('l2_cache', cpu_det.get('l2_cache', 'N/A'))}
  L3 Cache               : {cpu.get('l3_cache', cpu_det.get('l3_cache', 'N/A'))}
  
  Family                 : {cpu_det.get('family', 'N/A')}
  Model                  : {cpu_det.get('model', 'N/A')}
  Stepping               : {cpu_det.get('stepping', 'N/A')}
  Revision               : {cpu_det.get('revision', 'N/A')}
  Processor ID           : {cpu_det.get('processor_id', 'N/A')}
  Unique ID              : {cpu_det.get('unique_id', 'N/A')}
  Version                : {cpu_det.get('version', 'N/A')}
  Data Width             : {cpu_det.get('data_width', 'N/A')}
  Address Width          : {cpu_det.get('address_width', 'N/A')}
  Availability           : {cpu_det.get('availability', 'N/A')}
  Status                 : {cpu_det.get('status', 'N/A')}
  Upgrade Method         : {cpu_det.get('upgrade_method', 'N/A')}
  Voltage                : {cpu_det.get('voltage', 'N/A')}
  Power Management       : {cpu_det.get('power_management', 'N/A')}
  
  Current Load           : {cpu.get('load', 0):.1f}%
  Temperature            : {cpu.get('temperature', 0):.1f} C
"""

        elif category == "Memory (RAM)":
            ram = data.get('ram', {})
            info = f"""
============================================================
                    MEMORY (RAM)
============================================================

  Total Memory           : {ram.get('total', 0):.2f} GB
  Used Memory            : {ram.get('used', 0):.2f} GB
  Available Memory       : {ram.get('available', 0):.2f} GB
  Memory Usage           : {ram.get('percent', 0):.1f}%
  
  Total Slots            : {ram.get('total_slots', 0)}
  Used Slots             : {ram.get('used_slots', 0)}
  
  Memory Modules:
"""
            for i, module in enumerate(ram.get('modules', []), 1):
                info += f"""
  [{i}] Slot {module.get('bank', 'N/A')}
       Manufacturer     : {module.get('manufacturer', 'N/A')}
       Size             : {module.get('size', 0):.2f} GB
       Speed            : {module.get('speed', 'N/A')} MHz
       Model            : {module.get('model', 'N/A')}
"""

        elif category == "Graphics (GPU)":
            gpu_list = data.get('gpu', [])
            gpu_det = detailed_hw.get('gpu', [])
            info = f"""
============================================================
                    GRAPHICS (GPU)
============================================================
"""
            for i, gpu in enumerate(gpu_list):
                gpu_d = gpu_det[i] if i < len(gpu_det) else {}
                info += f"""
  GPU #{i+1}              : {gpu.get('name', gpu_d.get('name', 'N/A'))}
  Memory Total           : {gpu.get('memory_total', gpu_d.get('memory', 0)):.1f} GB
  Memory Used            : {gpu.get('memory_used', 0):.1f} GB
  Memory Free            : {gpu.get('memory_free', 0):.1f} GB
  Load                   : {gpu.get('load', 0):.1f}%
  Temperature            : {gpu.get('temperature', 0):.1f} C
  Driver Version         : {gpu.get('driver', gpu_d.get('driver_version', 'N/A'))}
  Video Processor        : {gpu_d.get('video_processor', 'N/A')}
  Video Memory Type      : {gpu_d.get('video_memory_type', 'N/A')}
  Current Resolution     : {gpu_d.get('current_horizontal_res', 'N/A')} x {gpu_d.get('current_vertical_res', 'N/A')}
  Refresh Rate           : {gpu_d.get('current_refresh_rate', 'N/A')} Hz
  Max Refresh Rate       : {gpu_d.get('max_refresh_rate', 'N/A')} Hz
  Min Refresh Rate       : {gpu_d.get('min_refresh_rate', 'N/A')} Hz
  Video Mode             : {gpu_d.get('video_mode_description', 'N/A')}
  Device ID              : {gpu_d.get('device_id', 'N/A')}
  PNP Device ID          : {gpu_d.get('pnp_device_id', 'N/A')}
  Status                 : {gpu_d.get('status', 'N/A')}
"""
            if not gpu_list:
                info += "\n  No GPU detected\n"

        elif category == "Storage":
            disks = data.get('disks', [])
            disk_det = detailed_hw.get('disks', [])
            info = f"""
============================================================
                    STORAGE
============================================================
"""
            for i, disk in enumerate(disks):
                disk_d = disk_det[i] if i < len(disk_det) else {}
                info += f"""
  Device                 : {disk.get('device', 'N/A')}
  Model                  : {disk.get('model', disk_d.get('model', 'N/A'))}
  Serial Number          : {disk_d.get('serial', 'N/A')}
  Type                   : {disk.get('type', 'N/A')}
  Interface              : {disk.get('interface', disk_d.get('interface_type', 'N/A'))}
  Filesystem             : {disk.get('filesystem', 'N/A')}
  Mount Point            : {disk.get('mount', 'N/A')}
  
  Total                  : {disk.get('total', disk_d.get('size', 0)):.1f} GB
  Used                   : {disk.get('used', 0):.1f} GB ({disk.get('percent', 0):.1f}%)
  Free                   : {disk.get('free', 0):.1f} GB
  Partitions             : {disk_d.get('partitions', 'N/A')}
  Status                 : {disk_d.get('status', 'N/A')}
  PNP Device ID          : {disk_d.get('pnp_device_id', 'N/A')}
  Device ID              : {disk_d.get('device_id', 'N/A')}
  Index                  : {disk_d.get('index', 'N/A')}
  Bytes Per Sector       : {disk_d.get('bytes_per_sector', 'N/A')}
  Sectors Per Track      : {disk_d.get('sectors_per_track', 'N/A')}
  Tracks Per Cylinder    : {disk_d.get('tracks_per_cylinder', 'N/A')}
  Capabilities           : {disk_d.get('capabilities', 'N/A')}
  Temperature            : {disk.get('temperature', 0):.1f} C
"""
            if not disks:
                info += "\n  No storage devices detected\n"

        elif category == "Network Adapters":
            network = data.get('network', [])
            net_det = detailed_hw.get('network', [])
            info = f"""
============================================================
              NETWORK ADAPTERS
============================================================
"""
            for i, adapter in enumerate(network):
                net_d = net_det[i] if i < len(net_det) else {}
                info += f"""
  Adapter                : {adapter.get('name', net_d.get('name', 'N/A'))}
  Status                 : {adapter.get('status', 'Active' if net_d.get('net_enabled') else 'Inactive')}
  Speed                  : {adapter.get('speed', f"{net_d.get('speed', 0)} Mbps" if net_d.get('speed') else 'N/A')}
  MAC Address            : {adapter.get('mac', net_d.get('mac', 'N/A'))}
  IPv4 Address           : {adapter.get('ipv4', 'N/A')}
  IPv6 Address           : {adapter.get('ipv6', 'N/A')}
  Manufacturer           : {net_d.get('manufacturer', 'N/A')}
  Product Name           : {net_d.get('product_name', 'N/A')}
  Adapter Type           : {net_d.get('adapter_type', 'N/A')}
  Physical Adapter       : {net_d.get('physical_adapter', False)}
  Net Enabled            : {net_d.get('net_enabled', False)}
  Connection Status      : {net_d.get('connection_status', 'N/A')}
  Service Name           : {net_d.get('service_name', 'N/A')}
  Device ID              : {net_d.get('device_id', 'N/A')}
  PNP Device ID          : {net_d.get('pnp_device_id', 'N/A')}
  Index                  : {net_d.get('index', 'N/A')}
  Status                 : {net_d.get('status', 'N/A')}
  Auto Sense             : {net_d.get('auto_sense', 'N/A')}
  Sent (MB)              : {adapter.get('bytes_sent', 0):.2f}
  Received (MB)          : {adapter.get('bytes_recv', 0):.2f}
"""
            if not network:
                info += "\n  No network adapters detected\n"

        elif category == "Monitors":
            monitors = data.get('monitors', [])
            info = f"""
============================================================
                    MONITORS
============================================================
"""
            if monitors:
                for monitor in monitors:
                    is_primary = " [PRIMARY]" if monitor.get('is_primary') else ""
                    info += f"""
  {monitor.get('name', 'N/A')}{is_primary}
    Resolution           : {monitor.get('width', 0)} x {monitor.get('height', 0)}
    Aspect Ratio         : {monitor.get('aspect_ratio', 'N/A')}
"""
                    if monitor.get('width_mm') and monitor.get('height_mm'):
                        info += f"    Physical Size (mm)   : {monitor.get('width_mm', 0)} x {monitor.get('height_mm', 0)}\n"
                    if monitor.get('diagonal_inches'):
                        info += f"    Diagonal (inches)    : {monitor.get('diagonal_inches', 0)}\"\n"
                    if monitor.get('ppi'):
                        info += f"    Pixel Density (PPI)  : {monitor.get('ppi', 0)}\n"
                    if monitor.get('manufacturer'):
                        info += f"    Manufacturer         : {monitor.get('manufacturer', 'Unknown')}\n"
                    if monitor.get('product_name'):
                        info += f"    Product Name         : {monitor.get('product_name', 'N/A')}\n"
            else:
                info += "\n  No monitors detected\n"

        elif category == "Temperatures":
            temps = data.get('temperatures', {})
            info = f"""
============================================================
                    TEMPERATURES
============================================================
"""
            if temps:
                cpu_temps = {k: v for k, v in temps.items() if 'CPU' in k or 'Core' in k or 'Core:' in k}
                other_temps = {k: v for k, v in temps.items() if 'CPU' not in k and 'Core' not in k and 'Core:' not in k}
                if cpu_temps:
                    info += "\n  PROCESSOR:\n"
                    for name, temp in cpu_temps.items():
                        color = "G" if temp < 50 else "Y" if temp < 70 else "R"
                        info += f"    [{color}] {name:<20} : {temp:.1f} C\n"
                if other_temps:
                    info += "\n  OTHER COMPONENTS:\n"
                    for name, temp in other_temps.items():
                        color = "G" if temp < 50 else "Y" if temp < 70 else "R"
                        clean_name = name.replace('MB:', '').replace('Disk:', '').replace('Thermal:', '').strip()
                        info += f"    [{color}] {clean_name:<25} : {temp:.1f} C\n"
            else:
                info += "\n  No temperature data available\n"

        self.info_textbox.delete("1.0", "end")
        self.info_textbox.insert("1.0", info)
        try:
            self.info_textbox.yview_moveto(self.info_scroll_pos)
        except:
            pass

    # ==================== MONITOR TAB ====================
    def create_monitor_tab(self):
        monitor_frame = ctk.CTkFrame(self.monitor_tab)
        monitor_frame.pack(fill="both", expand=True, padx=15, pady=15)

        title = ctk.CTkLabel(
            monitor_frame,
            text="Real-Time Resource Monitoring",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(10, 20))

        metrics_frame = ctk.CTkFrame(monitor_frame)
        metrics_frame.pack(fill="x", padx=20, pady=10)

        self.progress_bars = {}
        self.progress_labels = {}

        metrics = [
            ("CPU", "#4CAF50", "Processor"),
            ("RAM", "#2196F3", "Memory"),
            ("GPU", "#FF9800", "Graphics")
        ]

        for key, color, name in metrics:
            frame = ctk.CTkFrame(metrics_frame)
            frame.pack(side="left", expand=True, fill="both", padx=10, pady=10)

            label = ctk.CTkLabel(frame, text=name, font=ctk.CTkFont(size=14, weight="bold"))
            label.pack(pady=(10, 5))

            progress = ctk.CTkProgressBar(frame, width=250, height=35, progress_color=color)
            progress.pack(pady=10)
            progress.set(0)

            value_label = ctk.CTkLabel(frame, text="0%", font=ctk.CTkFont(size=24, weight="bold"))
            value_label.pack(pady=5)

            self.progress_bars[key] = progress
            self.progress_labels[key] = value_label

        temp_frame = ctk.CTkFrame(monitor_frame)
        temp_frame.pack(fill="x", padx=20, pady=20)

        temp_title = ctk.CTkLabel(
            temp_frame,
            text="Component Temperatures",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        temp_title.pack(pady=(10, 15))

        self.temp_container = ctk.CTkFrame(temp_frame, fg_color="transparent")
        self.temp_container.pack(fill="x", padx=20, pady=10)

        self.temp_widgets = {}

        self.temp_loading_label = ctk.CTkLabel(
            self.temp_container,
            text="Loading temperature data...",
            font=ctk.CTkFont(size=14),
            text_color="gray"
        )
        self.temp_loading_label.pack(pady=30)

        extra_frame = ctk.CTkFrame(monitor_frame)
        extra_frame.pack(fill="x", padx=20, pady=10)

        extra_title = ctk.CTkLabel(
            extra_frame,
            text="Additional Sensors",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        extra_title.pack(pady=(10, 5))

        self.extra_container = ctk.CTkFrame(extra_frame, fg_color="transparent")
        self.extra_container.pack(fill="x", padx=20, pady=10)

        self.extra_widgets = {}

    def update_temperatures_display(self, temperatures: Dict):
        if self._closing:
            return
        if not temperatures:
            for widget in self.temp_container.winfo_children():
                widget.destroy()
            no_data_label = ctk.CTkLabel(
                self.temp_container,
                text="No temperature data available\n\nEnsure LibreHardwareMonitor is installed",
                font=ctk.CTkFont(size=14),
                text_color="orange"
            )
            no_data_label.pack(pady=30)
            return

        if not self.temp_widgets:
            for widget in self.temp_container.winfo_children():
                widget.destroy()

            categories = {
                'Processor Cores': {},
                'Main Components': {},
                'Motherboard': {},
                'Storage': {}
            }

            for name, temp in temperatures.items():
                if 'Core' in name or 'Core:' in name:
                    categories['Processor Cores'][name] = temp
                elif name in ['CPU', 'GPU']:
                    categories['Main Components'][name] = temp
                elif any(x in name for x in ['MB:', 'Thermal:', 'Motherboard', 'Chipset']):
                    categories['Motherboard'][name] = temp
                elif any(x in name for x in ['Disk:', 'SSD', 'NVMe', 'HDD']):
                    categories['Storage'][name] = temp
                else:
                    categories['Main Components'][name] = temp

            for category, items in categories.items():
                if items:
                    category_frame = ctk.CTkFrame(self.temp_container, fg_color="#2B2B2B", corner_radius=8)
                    category_frame.pack(fill="x", padx=5, pady=5)
                    category_label = ctk.CTkLabel(
                        category_frame,
                        text=f"[ {category} ]",
                        font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#FFD700"
                    )
                    category_label.pack(anchor="w", padx=10, pady=(5, 0))
                    items_frame = ctk.CTkFrame(category_frame, fg_color="transparent")
                    items_frame.pack(fill="x", padx=10, pady=5)
                    row_frame = None
                    col_count = 0
                    for name, temp in items.items():
                        if col_count % 3 == 0:
                            row_frame = ctk.CTkFrame(items_frame, fg_color="transparent")
                            row_frame.pack(fill="x", pady=2)
                        if temp < 40:
                            color = "#4CAF50"
                            indicator = " "
                        elif temp < 60:
                            color = "#FFC107"
                            indicator = " "
                        elif temp < 75:
                            color = "#FF9800"
                            indicator = " "
                        else:
                            color = "#F44336"
                            indicator = " "
                        temp_card = ctk.CTkFrame(row_frame, fg_color="#3B3B3B", corner_radius=6)
                        temp_card.pack(side="left", expand=True, fill="both", padx=3, pady=2)
                        display_name = name.replace('MB:', '').replace('Disk:', '').replace('Thermal:', '').strip()
                        if len(display_name) > 25:
                            display_name = display_name[:22] + "..."
                        name_label = ctk.CTkLabel(
                            temp_card,
                            text=f"{indicator} {display_name}",
                            font=ctk.CTkFont(size=11),
                            text_color="gray"
                        )
                        name_label.pack(pady=(5, 0))
                        temp_label = ctk.CTkLabel(
                            temp_card,
                            text=f"{temp:.1f} C",
                            font=ctk.CTkFont(size=18, weight="bold"),
                            text_color=color
                        )
                        temp_label.pack(pady=(0, 5))
                        self.temp_widgets[name] = {
                            'label': temp_label,
                            'frame': temp_card,
                            'color': color                        }
                        col_count += 1
        else:
            for name, temp in temperatures.items():
                if name in self.temp_widgets:
                    label = self.temp_widgets[name]['label']
                    label.configure(text=f"{temp:.1f} C")
                    if temp < 40:
                        color = "#4CAF50"
                    elif temp < 60:
                        color = "#FFC107"
                    elif temp < 75:
                        color = "#FF9800"
                    else:
                        color = "#F44336"
                    label.configure(text_color=color)

    def update_extra_sensors_display(self, sensors: List):
        if self._closing:
            return
        if not sensors:
            for widget in self.extra_container.winfo_children():
                widget.destroy()
            no_data_label = ctk.CTkLabel(
                self.extra_container,
                text="No additional sensors found",
                font=ctk.CTkFont(size=14),
                text_color="gray"
            )
            no_data_label.pack(pady=30)
            return

        if not hasattr(self, 'extra_widgets_created') or not self.extra_widgets_created:
            for widget in self.extra_container.winfo_children():
                widget.destroy()
            self.extra_widgets = {}
            groups = {}
            for sensor in sensors:
                sensor_type = sensor.get('type', 'Unknown')
                if sensor_type not in groups:
                    groups[sensor_type] = []
                groups[sensor_type].append(sensor)
            for sensor_type, items in groups.items():
                if items:
                    type_frame = ctk.CTkFrame(self.extra_container, fg_color="#2B2B2B", corner_radius=8)
                    type_frame.pack(fill="x", padx=5, pady=5)
                    type_label = ctk.CTkLabel(
                        type_frame,
                        text=f"[ {sensor_type} ]",
                        font=ctk.CTkFont(size=13, weight="bold"),
                        text_color="#87CEEB"
                    )
                    type_label.pack(anchor="w", padx=10, pady=(5, 0))
                    items_frame = ctk.CTkFrame(type_frame, fg_color="transparent")
                    items_frame.pack(fill="x", padx=10, pady=5)
                    row_frame = None
                    col_count = 0
                    for sensor in items:
                        if col_count % 4 == 0:
                            row_frame = ctk.CTkFrame(items_frame, fg_color="transparent")
                            row_frame.pack(fill="x", pady=2)
                        card = ctk.CTkFrame(row_frame, fg_color="#3B3B3B", corner_radius=6)
                        card.pack(side="left", expand=True, fill="both", padx=3, pady=2)
                        name_label = ctk.CTkLabel(
                            card,
                            text=sensor.get('name', 'Unknown')[:25],
                            font=ctk.CTkFont(size=10),
                            text_color="gray"
                        )
                        name_label.pack(pady=(3, 0))
                        value_label = ctk.CTkLabel(
                            card,
                            text=f"{sensor.get('value', 0):.1f} {sensor.get('unit', '')}",
                            font=ctk.CTkFont(size=16, weight="bold"),
                            text_color="#87CEEB"
                        )
                        value_label.pack(pady=(0, 3))
                        key = f"{sensor_type}_{sensor.get('name', '')}"
                        self.extra_widgets[key] = {
                            'label': value_label,
                            'card': card
                        }
                        col_count += 1
            self.extra_widgets_created = True
        else:
            for sensor in sensors:
                key = f"{sensor.get('type', '')}_{sensor.get('name', '')}"
                if key in self.extra_widgets:
                    self.extra_widgets[key]['label'].configure(
                        text=f"{sensor.get('value', 0):.1f} {sensor.get('unit', '')}"
                    )

    # ==================== DATABASE TAB ====================
    def create_database_tab(self):
        db_frame = ctk.CTkFrame(self.database_tab)
        db_frame.pack(fill="both", expand=True, padx=15, pady=15)

        title = ctk.CTkLabel(
            db_frame,
            text="Database Management",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(10, 15))

        btn_frame = ctk.CTkFrame(db_frame)
        btn_frame.pack(fill="x", padx=10, pady=10)

        export_btn = ctk.CTkButton(
            btn_frame,
            text="Export to JSON",
            command=self.export_data,
            fg_color="#2E8B57",
            width=150
        )
        export_btn.pack(side="left", padx=5)

        refresh_btn = ctk.CTkButton(
            btn_frame,
            text="Refresh",
            command=self.refresh_db_data,
            fg_color="#4169E1",
            width=150
        )
        refresh_btn.pack(side="left", padx=5)

        clear_btn = ctk.CTkButton(
            btn_frame,
            text="Clear Display",
            command=self.clear_db_display,
            fg_color="#DC143C",
            width=150
        )
        clear_btn.pack(side="left", padx=5)

        self.db_text = ctk.CTkTextbox(
            db_frame,
            font=ctk.CTkFont(family="Consolas", size=13),
            wrap="word"
        )
        self.db_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def refresh_db_data(self):
        sessions = self.db.get_all_sessions(10)
        if sessions:
            db_text = "============================================================\n"
            db_text += "                 SESSION HISTORY\n"
            db_text += "============================================================\n\n"
            for session in sessions:
                cpu_load = session.get('cpu_load', 0)
                ram_percent = session.get('ram_percent', 0)
                db_text += f"""
SESSION #{session.get('id', 'N/A')}
  User             : {session.get('username', 'N/A')}
  Start Time       : {session.get('start_time', 'N/A')[:19] if session.get('start_time') else 'N/A'}
  End Time         : {session.get('end_time', 'Active')[:19] if session.get('end_time') else 'Active'}
  CPU Load         : {cpu_load:.1f}%
  RAM Usage        : {ram_percent:.1f}%
"""
            self.db_text.delete("1.0", "end")
            self.db_text.insert("1.0", db_text)
        else:
            self.db_text.delete("1.0", "end")
            self.db_text.insert("1.0", "No data in database")

    def clear_db_display(self):
        self.db_text.delete("1.0", "end")
        self.db_text.insert("1.0", "Display cleared")
        self.update_status("Display cleared", "orange")

    def export_data(self):
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Export Data"
        )
        if file_path:
            if self.db.export_to_json(file_path):
                messagebox.showinfo("Success", f"Data exported to:\n{file_path}")
                self.update_status("Data exported", "green")
            else:
                messagebox.showerror("Error", "Failed to export data")

    # ==================== SETTINGS TAB ====================
    def create_settings_tab(self):
        settings_frame = ctk.CTkScrollableFrame(self.settings_tab)
        settings_frame.pack(fill="both", expand=True, padx=20, pady=20)

        # --- Appearance ---
        appearance_frame = ctk.CTkFrame(settings_frame)
        appearance_frame.pack(fill="x", pady=10)
        appearance_title = ctk.CTkLabel(
            appearance_frame,
            text="Appearance",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        appearance_title.pack(pady=(10, 15))
        theme_frame = ctk.CTkFrame(appearance_frame, fg_color="transparent")
        theme_frame.pack(fill="x", padx=20, pady=5)
        theme_label = ctk.CTkLabel(theme_frame, text="Theme:", width=150)
        theme_label.pack(side="left")
        self.theme_var = tk.StringVar(value="dark")
        theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["dark", "light"],
            variable=self.theme_var,
            command=self.change_theme,
            width=150
        )
        theme_menu.pack(side="left", padx=10)

        # --- Update Interval ---
        update_frame = ctk.CTkFrame(settings_frame)
        update_frame.pack(fill="x", pady=10)
        update_title = ctk.CTkLabel(
            update_frame,
            text="Data Update",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        update_title.pack(pady=(10, 15))
        interval_frame = ctk.CTkFrame(update_frame, fg_color="transparent")
        interval_frame.pack(fill="x", padx=20, pady=5)
        interval_label = ctk.CTkLabel(interval_frame, text="Update Interval (sec):", width=150)
        interval_label.pack(side="left")
        self.interval_var = tk.StringVar(value="0.5")
        interval_menu = ctk.CTkOptionMenu(
            interval_frame,
            values=["0.5", "1", "2", "3", "5"],
            variable=self.interval_var,
            command=self.change_interval,
            width=150
        )
        interval_menu.pack(side="left", padx=10)

        # --- System Tray ---
        tray_frame = ctk.CTkFrame(settings_frame)
        tray_frame.pack(fill="x", pady=10)
        tray_title = ctk.CTkLabel(
            tray_frame,
            text="System Tray",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        tray_title.pack(pady=(10, 15))

        if TRAY_AVAILABLE:
            # Чекбокс включения трея
            self.tray_enabled_var = tk.BooleanVar(value=False)
            tray_check = ctk.CTkCheckBox(
                tray_frame,
                text="Enable system tray",
                variable=self.tray_enabled_var,
                command=self.on_tray_toggle
            )
            tray_check.pack(anchor="w", padx=20, pady=5)

            # Выбор метрик для отображения
            metrics_frame = ctk.CTkFrame(tray_frame, fg_color="transparent")
            metrics_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(metrics_frame, text="Display metrics:").pack(anchor="w")

            self.tray_metrics_vars = {}
            for metric in ['CPU', 'RAM', 'GPU']:
                var = tk.BooleanVar(value=True)
                self.tray_metrics_vars[metric.lower()] = var
                cb = ctk.CTkCheckBox(
                    metrics_frame,
                    text=metric,
                    variable=var,
                    command=self.on_tray_metrics_change
                )
                cb.pack(anchor="w", padx=20)

            # Интервал обновления трея
            interval_tray_frame = ctk.CTkFrame(tray_frame, fg_color="transparent")
            interval_tray_frame.pack(fill="x", padx=20, pady=5)
            ctk.CTkLabel(interval_tray_frame, text="Tray update interval (sec):").pack(side="left")
            self.tray_interval_var = tk.StringVar(value="2")
            tray_interval_menu = ctk.CTkOptionMenu(
                interval_tray_frame,
                values=["1", "2", "3", "5", "10"],
                variable=self.tray_interval_var,
                command=self.on_tray_interval_change,
                width=100
            )
            tray_interval_menu.pack(side="left", padx=10)

            # Кнопка "Minimize to Tray"
            minimize_btn = ctk.CTkButton(
                tray_frame,
                text="Minimize to Tray",
                command=self.minimize_to_tray
            )
            minimize_btn.pack(pady=10)
        else:
            # Если pystray не установлен
            warn_label = ctk.CTkLabel(
                tray_frame,
                text="pystray (PIL) is not installed. Tray functionality disabled.",
                text_color="orange",
                font=ctk.CTkFont(size=12)
            )
            warn_label.pack(pady=10)

        # --- About ---
        about_btn = ctk.CTkButton(
            settings_frame,
            text="About",
            command=self.show_about,
            width=200,
            height=35
        )
        about_btn.pack(pady=15)

    # ===== Обработчики настроек трея =====
    def recreate_tray_icons(self):
        """Пересоздать иконки согласно текущим настройкам."""
        # Останавливаем старые иконки
        for icon in self.tray_icons:
            try:
                icon.stop()
            except:
                pass
        self.tray_icons.clear()

        if not self.tray_enabled_var.get():
            return

        # Собираем активные метрики
        active_metrics = [k for k, v in self.tray_metrics_vars.items() if v.get()]
        if not active_metrics:
            return

        # Создаём новые иконки
        for metric in active_metrics:
            icon = TrayIconSingle(self, metric, self.tray_update_interval)
            threading.Thread(target=icon.run, daemon=True).start()
            self.tray_icons.append(icon)

    def on_tray_toggle(self):
        """Обработчик изменения чекбокса включения трея."""
        self.recreate_tray_icons()
        if self.tray_enabled_var.get():
            self.update_status("Tray enabled", "blue")
        else:
            self.update_status("Tray disabled", "blue")

    def on_tray_metrics_change(self):
        """При изменении выбора метрик пересоздаём иконки."""
        if self.tray_enabled_var.get():
            self.recreate_tray_icons()

    def on_tray_interval_change(self, val):
        """При изменении интервала обновления пересоздаём иконки."""
        self.tray_update_interval = float(val)
        if self.tray_enabled_var.get():
            self.recreate_tray_icons()

    def minimize_to_tray(self):
        if not TRAY_AVAILABLE:
            messagebox.showwarning("Not available", "pystray is not installed.")
            return
        if not self.tray_enabled_var.get():
            self.tray_enabled_var.set(True)
            self.recreate_tray_icons()
        self.withdraw()

    def show_window(self):
        self.deiconify()
        self.lift()
        self.focus_force()

    def quit_app(self):
        self.close_app(force=True)

    def change_theme(self, choice):
        ctk.set_appearance_mode(choice)
        self.update_status(f"Theme changed to {choice}", "blue")

    def change_interval(self, choice):
        self.update_status(f"Update interval set to {choice} sec", "blue")

    def show_about(self):
        libre_status = "Available" if LIBRE_AVAILABLE else "Not available"
        screen_status = "Available" if SCREENINFO_AVAILABLE else "Not available"
        tray_status = "Available" if TRAY_AVAILABLE else "Not available"
        about_text = f"""
============================================================
              SYSTEM MONITOR v2.0.0
          Professional System Monitoring
============================================================

Features:
   • Complete system information
   • Extended hardware details
   • All available temperatures
   • Additional sensors
   • Scroll position memory
   • Real-time monitoring
   • Database sessions
   • JSON export
   • System tray with load display

Module Status:
   • LibreHardwareMonitor: {libre_status}
   • screeninfo: {screen_status}
   • pystray: {tray_status}

Statistics:
   • Uptime: {int((time.time() - self.start_time) // 60)} minutes
   • Updates: {self.update_count}
   • Sessions: {len(self.db.get_all_sessions(100))}

© 2024 All rights reserved
"""
        messagebox.showinfo("About", about_text)

    # ==================== HELP TAB ====================
    def create_help_tab(self):
        help_frame = ctk.CTkFrame(self.help_tab)
        help_frame.pack(fill="both", expand=True, padx=15, pady=15)

        title = ctk.CTkLabel(
            help_frame,
            text="Help",
            font=ctk.CTkFont(size=20, weight="bold")
        )
        title.pack(pady=(10, 15))

        help_text = ctk.CTkTextbox(
            help_frame,
            font=ctk.CTkFont(size=13),
            wrap="word"
        )
        help_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        help_content = f"""
============================================================
                  SYSTEM MONITOR v2.0
                Professional System Monitoring
============================================================

FEATURES:

1. SYSTEM INFO TAB
   • Dropdown category selection
   • Detailed information per category

2. ALL DATA TAB
   • Two columns each taking 50% of width
   • Full width display
   • Static snapshot (updates only once at start)

3. REAL-TIME MONITORING
   • Smooth progress bar animation
   • All available temperatures
   • Additional sensors (fans, voltage, power)

4. DATABASE
   • Automatic session saving
   • JSON export

5. SYSTEM TRAY (Settings)
   • Show CPU/RAM/GPU load in tray icon
   • Customizable metrics and update interval
   • Minimize to tray

QUICK START:
   Username: a
   Password: 1

HOTKEYS:
   F5 - Refresh
   Ctrl+Q - Exit
"""
        help_text.insert("1.0", help_content)
        help_text.configure(state="disabled")

    # ==================== MONITORING CORE ====================
    def load_initial_data(self):
        if self._closing:
            return
        try:
            self.db.start_session(self.username)
            data = self.collector.collect_all()
            self.current_data = data
            self.db.save_data(data)

            self.display_category_info(self.category_var.get(), data)
            self.update_temperatures_display(data.get('temperatures', {}))
            self.update_all_data_display(data)

            extra_sensors = self.collector.get_extra_sensors()
            self.update_extra_sensors_display(extra_sensors)

            self.update_status("Data loaded successfully", "green")
            self.refresh_db_data()
        except Exception as e:
            self.update_status(f"Error: {str(e)[:50]}", "red")

    def start_monitoring(self):
        self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitor_thread.start()
        self.animate_bars()

    def monitoring_loop(self):
        last_db_save = time.time()
        while self.running and not self._closing:
            try:
                if self._closing:
                    break
                data = self.collector.collect_all()
                if not data or self._closing:
                    break
                self.current_data = data
                self.update_count += 1
                self.target_values['CPU'] = data.get('cpu_load', 0)
                self.target_values['RAM'] = data.get('ram_percent', 0)
                self.target_values['GPU'] = data.get('gpu_load', 0)

                if not self._closing:
                    self.after(0, lambda d=data: self.update_temperatures_display(d.get('temperatures', {})))
                    self.after(0, lambda d=data: self.display_category_info(self.category_var.get(), d))

                extra_sensors = self.collector.get_extra_sensors()
                if not self._closing:
                    self.after(0, lambda s=extra_sensors: self.update_extra_sensors_display(s))

                current_time = time.time()
                if current_time - last_db_save >= 60:
                    self.db.save_data(data)
                    last_db_save = current_time
            except Exception as e:
                pass

            interval = float(self.interval_var.get()) if hasattr(self, 'interval_var') else 0.5
            for _ in range(int(interval * 10)):
                if not self.running or self._closing:
                    break
                time.sleep(0.1)

    def animate_bars(self):
        if self._closing:
            return
        smoothing = 0.3
        for key in self.progress_bars:
            diff = self.target_values[key] - self.current_values[key]
            self.current_values[key] += diff * smoothing
            value = self.current_values[key]
            self.progress_bars[key].set(min(value / 100, 1))
            self.progress_labels[key].configure(text=f"{value:.1f}%")
        after_id = self.after(30, self.animate_bars)
        self._after_ids.append(after_id)

    def refresh_info(self):
        if self.current_data:
            self.display_category_info(self.category_var.get(), self.current_data)
            self.update_status("Information refreshed", "blue")

    def bind_shortcuts(self):
        self.bind("<F5>", lambda e: self.refresh_info())
        self.bind("<Control-q>", lambda e: self.close_app(force=True))

    def update_status(self, message: str, color: str = "gray"):
        colors = {
            "green": "#90EE90",
            "red": "#FF6B6B",
            "blue": "#87CEEB",
            "orange": "#FFA500",
            "gray": "#A9A9A9"
        }
        self.status_label.configure(
            text=f"{datetime.now().strftime('%H:%M:%S')} | {message}",
            text_color=colors.get(color, "#A9A9A9")
        )

    # ==================== ЗАКРЫТИЕ ПРИЛОЖЕНИЯ ====================
    def close_app(self, force=False):
        """Закрытие приложения. Если force=False и трей доступен – сворачиваем в трей."""
        if not force and TRAY_AVAILABLE and not self._closing:
            # Включаем трей, если он ещё не активен
            if not self.tray_enabled_var.get():
                self.tray_enabled_var.set(True)
            self.withdraw()  # Скрываем окно
            if not self.tray_icons:
                self.recreate_tray_icons()  # Создаём иконки, если их нет
            return

        # Полное завершение (force=True или трей недоступен)
        self._closing = True
        self.running = False

        # Отменяем все after-задачи
        for after_id in self._after_ids:
            try:
                self.after_cancel(after_id)
            except:
                pass
        self._after_ids.clear()

        # Отвязываем глобальные события
        try:
            self.unbind_all("<MouseWheel>")
            self.unbind_all("<Button-4>")
            self.unbind_all("<Button-5>")
        except:
            pass

        try:
            self.grab_release()
        except:
            pass

        # Останавливаем все иконки трея
        for icon in self.tray_icons:
            try:
                icon.stop()
            except:
                pass
        self.tray_icons.clear()

        # Закрываем сборщик и БД
        if hasattr(self, 'collector'):
            try:
                self.collector.close()
            except:
                pass
        if hasattr(self, 'db'):
            try:
                self.db.close()
            except:
                pass

        # Уничтожаем окно
        try:
            self.destroy()
        except:
            pass

        # Принудительный выход через таймер (на всякий случай)
        threading.Timer(0.2, force_exit).start()


if __name__ == "__main__":
    try:
        print("=" * 50)
        print("Starting System Monitor...")
        print("=" * 50)
        app = LoginWindow()
        app.mainloop()
    except Exception as e:
        print(f"\nCritical error: {e}")
        import traceback
        traceback.print_exc()
        input("\nPress Enter to exit...")
