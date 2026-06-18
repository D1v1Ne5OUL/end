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
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import Dict, Any, List

# Настройка внешнего вида
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Константы
DB_PATH = "system_monitor.db"
USERS = {"a": "1"}

# ==================== БАЗА ДАННЫХ ====================
class Database:
    def __init__(self):
        self.conn = None
        self.session_id = None
        self._init_db()
    
    def _init_db(self):
        try:
            self.conn = sqlite3.connect(DB_PATH)
            cursor = self.conn.cursor()
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
                    computer_name TEXT
                )
            """)
            self.conn.commit()
            print("✅ База данных инициализирована")
        except Exception as e:
            print(f"❌ Ошибка инициализации БД: {e}")
    
    def start_session(self, username: str = ""):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO monitoring_sessions (start_time, username, os_name, computer_name)
                VALUES (?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                username,
                platform.system(),
                socket.gethostname()
            ))
            self.session_id = cursor.lastrowid
            self.conn.commit()
            print(f"✅ Начата сессия #{self.session_id}")
            return self.session_id
        except Exception as e:
            print(f"❌ Ошибка начала сессии: {e}")
            return None
    
    def end_session(self):
        if self.session_id:
            try:
                cursor = self.conn.cursor()
                cursor.execute("""
                    UPDATE monitoring_sessions 
                    SET end_time = ? 
                    WHERE id = ?
                """, (datetime.now().isoformat(), self.session_id))
                self.conn.commit()
                print(f"✅ Завершена сессия #{self.session_id}")
            except Exception as e:
                print(f"Ошибка завершения сессии: {e}")
    
    def save_data(self, data: Dict[str, Any]):
        if not self.session_id:
            self.start_session()
        
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE monitoring_sessions 
                SET cpu_model=?, cpu_load=?, cpu_temp=?, 
                    ram_total=?, ram_used=?, ram_percent=?,
                    gpu_model=?, gpu_temp=?, gpu_load=?
                WHERE id=?
            """, (
                data.get('cpu_model', ''),
                data.get('cpu_load', 0),
                data.get('cpu_temp', 0),
                data.get('ram_total', 0),
                data.get('ram_used', 0),
                data.get('ram_percent', 0),
                data.get('gpu_model', ''),
                data.get('gpu_temp', 0),
                data.get('gpu_load', 0),
                self.session_id
            ))
            self.conn.commit()
            print(f"✅ Данные сохранены в сессию #{self.session_id}")
        except Exception as e:
            print(f"❌ Ошибка сохранения данных: {e}")
    
    def get_last_session(self):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM monitoring_sessions 
                ORDER BY id DESC LIMIT 1
            """)
            row = cursor.fetchone()
            if row:
                columns = [desc[0] for desc in cursor.description]
                return dict(zip(columns, row))
            return {}
        except Exception as e:
            print(f"Ошибка получения данных: {e}")
            return {}
    
    def get_all_sessions(self, limit: int = 10):
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT id, start_time, end_time, username, cpu_load, ram_percent 
                FROM monitoring_sessions 
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"Ошибка получения списка сессий: {e}")
            return []
    
    def export_to_json(self, filepath: str):
        try:
            data = {
                'sessions': self.get_all_sessions(100),
                'last_session': self.get_last_session(),
                'export_date': datetime.now().isoformat()
            }
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False, default=str)
            print(f"✅ Данные экспортированы в {filepath}")
            return True
        except Exception as e:
            print(f"❌ Ошибка экспорта: {e}")
            return False
    
    def close(self):
        if self.conn:
            self.end_session()
            self.conn.close()
            print("✅ Соединение с БД закрыто")

# ==================== СБОРЩИК ДАННЫХ ====================
class HardwareCollector:
    def __init__(self):
        self.temp_cache = {}
    
    def get_cpu_info(self):
        try:
            cpu_model = platform.processor()
            if not cpu_model or cpu_model == "":
                cpu_model = "Unknown CPU"
            
            cpu_load = psutil.cpu_percent(interval=0.5)
            cpu_temp = self._get_cpu_temperature()
            
            return {
                'model': cpu_model,
                'load': cpu_load,
                'temperature': cpu_temp
            }
        except Exception as e:
            print(f"Ошибка получения CPU info: {e}")
            return {'model': 'Unknown', 'load': 0, 'temperature': 45}
    
    def _get_cpu_temperature(self):
        """Получение температуры CPU различными методами"""
        # Метод 1: через WMI
        try:
            import wmi
            w = wmi.WMI(namespace="root\\WMI")
            temperatures = w.MSAcpi_ThermalZoneTemperature()
            if temperatures:
                temp = temperatures[0].CurrentTemperature / 10.0 - 273.15
                if 20 < temp < 100:
                    return temp
        except:
            pass
        
        # Метод 2: через psutil (некоторые системы)
        try:
            if hasattr(psutil, "sensors_temperatures"):
                temps = psutil.sensors_temperatures()
                if 'coretemp' in temps:
                    return temps['coretemp'][0].current
                elif 'cpu-thermal' in temps:
                    return temps['cpu-thermal'][0].current
        except:
            pass
        
        # Значение по умолчанию
        return 45.0
    
    def get_ram_info(self):
        try:
            mem = psutil.virtual_memory()
            return {
                'total': mem.total / (1024**3),
                'used': mem.used / (1024**3),
                'available': mem.available / (1024**3),
                'percent': mem.percent
            }
        except Exception as e:
            print(f"Ошибка получения RAM info: {e}")
            return {'total': 0, 'used': 0, 'available': 0, 'percent': 0}
    
    def get_gpu_info(self):
        try:
            # Метод 1: через GPUtil
            import GPUtil
            gpus = GPUtil.getGPUs()
            if gpus:
                gpu = gpus[0]
                return {
                    'model': gpu.name,
                    'temperature': gpu.temperature,
                    'load': gpu.load * 100,
                    'memory_total': gpu.memoryTotal / 1024,
                    'memory_used': gpu.memoryUsed / 1024
                }
        except:
            pass
        
        # Метод 2: через WMI
        try:
            import wmi
            w = wmi.WMI()
            for gpu in w.Win32_VideoController():
                if gpu.Name and "Intel" not in gpu.Name and "Microsoft" not in gpu.Name:
                    return {
                        'model': gpu.Name,
                        'temperature': 0,
                        'load': 0,
                        'memory_total': 0,
                        'memory_used': 0
                    }
        except:
            pass
        
        return {'model': 'No dedicated GPU', 'temperature': 0, 'load': 0, 'memory_total': 0, 'memory_used': 0}
    
    def get_disk_info(self):
        try:
            disks = []
            partitions = psutil.disk_partitions()
            for partition in partitions:
                try:
                    usage = psutil.disk_usage(partition.mountpoint)
                    disks.append({
                        'device': partition.device,
                        'mount': partition.mountpoint,
                        'filesystem': partition.fstype,
                        'total': usage.total / (1024**3),
                        'used': usage.used / (1024**3),
                        'free': usage.free / (1024**3),
                        'percent': usage.percent
                    })
                except:
                    continue
            return disks
        except Exception as e:
            print(f"Ошибка получения disk info: {e}")
            return []
    
    def get_network_info(self):
        try:
            net_io = psutil.net_io_counters()
            return {
                'bytes_sent': net_io.bytes_sent,
                'bytes_recv': net_io.bytes_recv,
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            }
        except Exception as e:
            print(f"Ошибка получения network info: {e}")
            return {}
    
    def collect_all(self):
        # Обновляем все температуры в реальном времени (расширенный сбор)
        self.get_all_temperatures_enhanced()
        
        cpu = self.get_detailed_cpu_info()
        ram = self.get_detailed_ram_info()
        gpu_list = self.get_detailed_gpu_info()
        disks = self.get_detailed_disk_info()
        network = self.get_network_info()
        
        # Обновляем температуру CPU в данных
        cpu['temperature'] = self.all_temperatures.get('CPU', 0)
        
        return {
            'timestamp': datetime.now().isoformat(),
            'system_info': self.system_info,
            'cpu': cpu,
            'ram': ram,
            'gpu': gpu_list,
            'disks': disks,
            'network': network,
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

# ==================== ОКНО ВХОДА ====================
class LoginWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Вход в систему - Системный монитор")
        self.geometry("450x350")
        self.resizable(False, False)
        
        # Центрируем окно
        self.center_window()
        
        # Основной фрейм
        self.main_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.main_frame.pack(fill="both", expand=True, padx=40, pady=30)
        
        # Заголовок
        self.title_label = ctk.CTkLabel(
            self.main_frame,
            text="🔧 СИСТЕМНЫЙ МОНИТОР",
            font=ctk.CTkFont(size=24, weight="bold")
        )
        self.title_label.pack(pady=(0, 10))
        
        self.subtitle_label = ctk.CTkLabel(
            self.main_frame,
            text="Панель управления системой",
            font=ctk.CTkFont(size=12),
            text_color="gray"
        )
        self.subtitle_label.pack(pady=(0, 30))
        
        # Поля ввода
        self.username_label = ctk.CTkLabel(
            self.main_frame,
            text="Имя пользователя",
            font=ctk.CTkFont(size=14)
        )
        self.username_label.pack(anchor="w", pady=(0, 5))
        
        self.username_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Введите имя пользователя",
            width=350,
            height=40
        )
        self.username_entry.pack(pady=(0, 15))
        
        self.password_label = ctk.CTkLabel(
            self.main_frame,
            text="Пароль",
            font=ctk.CTkFont(size=14)
        )
        self.password_label.pack(anchor="w", pady=(0, 5))
        
        self.password_entry = ctk.CTkEntry(
            self.main_frame,
            placeholder_text="Введите пароль",
            show="*",
            width=350,
            height=40
        )
        self.password_entry.pack(pady=(0, 20))
        
        # Кнопки
        self.button_frame = ctk.CTkFrame(self.main_frame, fg_color="transparent")
        self.button_frame.pack(fill="x", pady=10)
        
        self.login_btn = ctk.CTkButton(
            self.button_frame,
            text="🚪 Войти",
            command=self.login,
            width=150,
            height=40,
            fg_color="#2E8B57",
            hover_color="#3CB371",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.login_btn.pack(side="left", padx=(0, 10), expand=True, fill="x")
        
        self.exit_btn = ctk.CTkButton(
            self.button_frame,
            text="❌ Выход",
            command=self.destroy,
            width=150,
            height=40,
            fg_color="#8B0000",
            hover_color="#A52A2A",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.exit_btn.pack(side="left", padx=(10, 0), expand=True, fill="x")
        
        # Сообщение об ошибке
        self.error_label = ctk.CTkLabel(
            self.main_frame,
            text="",
            text_color="#FF4444",
            font=ctk.CTkFont(size=12)
        )
        self.error_label.pack(pady=10)
        
        # Подсказка
        self.hint_frame = ctk.CTkFrame(self.main_frame, fg_color="#2B2B2B", corner_radius=8)
        self.hint_frame.pack(fill="x", pady=(20, 0))
        
        self.hint_label = ctk.CTkLabel(
            self.hint_frame,
            font=ctk.CTkFont(size=12),
            text_color="#FFD700",
            padx=10,
            pady=5
        )
        self.hint_label.pack()
        
        # Устанавливаем фокус
        self.username_entry.focus()
        
        # Привязываем Enter
        self.username_entry.bind("<Return>", lambda e: self.password_entry.focus())
        self.password_entry.bind("<Return>", lambda e: self.login())
    
    def center_window(self):
        self.update_idletasks()
        width = 450
        height = 350
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
            self.error_label.configure(text="❌ Неверное имя пользователя или пароль")
            self.password_entry.delete(0, 'end')
            self.username_entry.focus()

# ==================== ГЛАВНОЕ ОКНО ====================
class MainApp(ctk.CTkToplevel):
    def __init__(self, parent, username: str):
        super().__init__(parent)
        self.title(f"Системный монитор - {username}")
        self.geometry("1100x700")
        self.minsize(900, 550)
        
        # Инициализация
        self.username = username
        self.db = Database()
        self.collector = HardwareCollector()
        self.running = True
        self.update_count = 0
        self.start_time = time.time()
        self.current_data = {}
        
        # Центрируем окно
        self.center_window()
        
        # Создаем интерфейс
        self.create_ui()
        
        # Запускаем мониторинг
        self.start_monitoring()
        
        # Загружаем начальные данные ПОСЛЕ создания UI
        self.after(100, self.load_initial_data)
        
        # Настройка горячих клавиш
        self.bind_shortcuts()
        
        # Обработчик закрытия
        self.protocol("WM_DELETE_WINDOW", self.on_close)
    
    def center_window(self):
        self.update_idletasks()
        width = 1100
        height = 700
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'{width}x{height}+{x}+{y}')
    
    def create_ui(self):
        # Создаем Tabview
        self.tabview = ctk.CTkTabview(self)
        self.tabview.pack(fill="both", expand=True, padx=10, pady=(10, 5))
        
        # Вкладка "Информация о системе"
        self.create_info_tab()
        
        # Вкладка "Мониторинг"
        self.create_monitor_tab()
        
        # Вкладка "База данных"
        self.create_database_tab()
        
        # Вкладка "Настройки"
        self.create_settings_tab()
        
        # Вкладка "Помощь"
        self.create_help_tab()
        
        # Статусная строка (создаем после всех вкладок)
        self.status_frame = ctk.CTkFrame(self, height=30, fg_color="#2B2B2B")
        self.status_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 10))
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="Готов",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.status_label.pack(side="left", padx=10, pady=5)
        
        # Индикатор времени
        self.time_label = ctk.CTkLabel(
            self.status_frame,
            text="",
            font=ctk.CTkFont(size=11),
            text_color="gray"
        )
        self.time_label.pack(side="right", padx=10, pady=5)
        
        # Обновляем время
        self.update_time()
    
    def update_time(self):
        """Обновляет отображение времени"""
        current_time = datetime.now().strftime("%H:%M:%S")
        self.time_label.configure(text=current_time)
        self.after(1000, self.update_time)
    
    def create_info_tab(self):
        self.info_tab = self.tabview.add("📊 Информация о системе")
        
        # Создаем фрейм для информации
        info_frame = ctk.CTkFrame(self.info_tab)
        info_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Заголовок
        title_label = ctk.CTkLabel(
            info_frame,
            text="Системная информация",
            font=ctk.CTkFont(size=18, weight="bold")
        )
        title_label.pack(pady=(10, 5))
        
        # Разделитель
        separator = ctk.CTkFrame(info_frame, height=2, fg_color="#2B2B2B")
        separator.pack(fill="x", padx=20, pady=(0, 10))
        
        # Текстовое поле для информации
        self.info_text = ctk.CTkTextbox(
            info_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word"
        )
        self.info_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        
        # Кнопка обновления
        refresh_btn = ctk.CTkButton(
            info_frame,
            text="🔄 Обновить информацию",
            command=self.refresh_info,
            width=200,
            height=35
        )
        refresh_btn.pack(pady=(0, 10))
    
    def create_monitor_tab(self):
        self.monitor_tab = self.tabview.add("📈 Мониторинг")
        
        # Верхняя часть - метрики
        metrics_frame = ctk.CTkFrame(self.monitor_tab)
        metrics_frame.pack(fill="x", padx=10, pady=10)
        
        metrics_title = ctk.CTkLabel(
            metrics_frame,
            text="Загрузка системы",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        metrics_title.pack(pady=10)
        
        # Фрейм для прогресс-баров
        self.progress_frame = ctk.CTkFrame(metrics_frame, fg_color="transparent")
        self.progress_frame.pack(fill="x", padx=20, pady=10)
        
        # Прогресс-бары для CPU, RAM, GPU
        self.progress_bars = {}
        self.progress_labels = {}
        
        metrics = [
            ("CPU", "#6A5D7B", "Процессор"),
            ("RAM", "#3F4C6B", "Оперативная память"),
            ("GPU", "#7A5C61", "Видеокарта")
        ]
        
        for key, color, name in metrics:
            frame = ctk.CTkFrame(self.progress_frame)
            frame.pack(side="left", expand=True, fill="both", padx=10, pady=10)
            
            label = ctk.CTkLabel(frame, text=name, font=ctk.CTkFont(size=14, weight="bold"))
            label.pack(pady=(10, 5))
            
            progress = ctk.CTkProgressBar(frame, width=200, height=25, progress_color=color)
            progress.pack(pady=5)
            progress.set(0)
            
            value_label = ctk.CTkLabel(frame, text="0%", font=ctk.CTkFont(size=18, weight="bold"))
            value_label.pack(pady=5)
            
            self.progress_bars[key] = progress
            self.progress_labels[key] = value_label
        
        # Нижняя часть - температуры
        temp_frame = ctk.CTkFrame(self.monitor_tab)
        temp_frame.pack(fill="x", padx=10, pady=10)
        
        temp_title = ctk.CTkLabel(
            temp_frame,
            text="Температуры",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        temp_title.pack(pady=10)
        
        # Фрейм для температур
        self.temp_frame_inner = ctk.CTkFrame(temp_frame, fg_color="transparent")
        self.temp_frame_inner.pack(fill="x", padx=20, pady=10)
        
        self.temp_labels = {}
        
        temps = [
            ("CPU_TEMP", "🌡️ CPU", "#FF6B6B"),
            ("GPU_TEMP", "🎮 GPU", "#4ECDC4")
        ]
        
        for key, name, color in temps:
            frame = ctk.CTkFrame(self.temp_frame_inner)
            frame.pack(side="left", expand=True, fill="both", padx=10, pady=10)
            
            label = ctk.CTkLabel(frame, text=name, font=ctk.CTkFont(size=14))
            label.pack(pady=(10, 5))
            
            value = ctk.CTkLabel(
                frame,
                text="--°C",
                font=ctk.CTkFont(size=24, weight="bold"),
                text_color=color
            )
            value.pack(pady=5)
            
            self.temp_labels[key] = value
    
    def create_database_tab(self):
        self.db_tab = self.tabview.add("💾 База данных")
        
        # Кнопки управления
        btn_frame = ctk.CTkFrame(self.db_tab)
        btn_frame.pack(fill="x", padx=10, pady=10)
        
        export_btn = ctk.CTkButton(
            btn_frame,
            text="📤 Экспорт данных в JSON",
            command=self.export_data,
            fg_color="#2E8B57",
            hover_color="#3CB371"
        )
        export_btn.pack(side="left", padx=5)
        
        refresh_btn = ctk.CTkButton(
            btn_frame,
            text="🔄 Обновить",
            command=self.refresh_db_data,
            fg_color="#4169E1",
            hover_color="#5B7FE3"
        )
        refresh_btn.pack(side="left", padx=5)
        
        clear_btn = ctk.CTkButton(
            btn_frame,
            text="🗑️ Очистить",
            command=self.clear_db_display,
            fg_color="#DC143C",
            hover_color="#E82E4C"
        )
        clear_btn.pack(side="left", padx=5)
        
        # Информация о текущей сессии
        session_frame = ctk.CTkFrame(self.db_tab)
        session_frame.pack(fill="x", padx=10, pady=(0, 10))
        
        self.session_info_label = ctk.CTkLabel(
            session_frame,
            text="",
            font=ctk.CTkFont(size=12)
        )
        self.session_info_label.pack(pady=5)
        
        # Текстовое поле для данных
        self.db_text = ctk.CTkTextbox(
            self.db_tab,
            font=ctk.CTkFont(family="Consolas", size=11),
            wrap="word"
        )
        self.db_text.pack(fill="both", expand=True, padx=10, pady=(0, 10))
    
    def create_settings_tab(self):
        self.settings_tab = self.tabview.add("⚙️ Настройки")
        
        # Фрейм для настроек
        settings_frame = ctk.CTkScrollableFrame(self.settings_tab)
        settings_frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Режим отображения
        display_frame = ctk.CTkFrame(settings_frame)
        display_frame.pack(fill="x", pady=10)
        
        display_label = ctk.CTkLabel(
            display_frame,
            text="Отображение",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        display_label.pack(pady=(10, 15))
        
        # Тема
        theme_frame = ctk.CTkFrame(display_frame, fg_color="transparent")
        theme_frame.pack(fill="x", padx=20, pady=5)
        
        theme_label = ctk.CTkLabel(theme_frame, text="Тема:", width=150)
        theme_label.pack(side="left")
        
        self.theme_var = tk.StringVar(value="dark")
        theme_menu = ctk.CTkOptionMenu(
            theme_frame,
            values=["dark", "light"],
            variable=self.theme_var,
            command=self.change_theme
        )
        theme_menu.pack(side="left", fill="x", expand=True)
        
        # Обновление
        update_frame = ctk.CTkFrame(settings_frame)
        update_frame.pack(fill="x", pady=10)
        
        update_label = ctk.CTkLabel(
            update_frame,
            text="Обновление",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        update_label.pack(pady=(10, 15))
        
        # Интервал обновления
        interval_frame = ctk.CTkFrame(update_frame, fg_color="transparent")
        interval_frame.pack(fill="x", padx=20, pady=5)
        
        interval_label = ctk.CTkLabel(interval_frame, text="Интервал обновления (сек):", width=200)
        interval_label.pack(side="left")
        
        self.interval_var = tk.StringVar(value="2")
        interval_menu = ctk.CTkOptionMenu(
            interval_frame,
            values=["1", "2", "3", "5", "10"],
            variable=self.interval_var,
            command=self.change_interval
        )
        interval_menu.pack(side="left", fill="x", expand=True)
        
        # Система
        system_frame = ctk.CTkFrame(settings_frame)
        system_frame.pack(fill="x", pady=10)
        
        system_label = ctk.CTkLabel(
            system_frame,
            text="Система",
            font=ctk.CTkFont(size=16, weight="bold")
        )
        system_label.pack(pady=(10, 15))
        
        # О программе
        about_frame = ctk.CTkFrame(settings_frame)
        about_frame.pack(fill="x", pady=10)
        
        about_btn = ctk.CTkButton(
            about_frame,
            text="ℹ️ О программе",
            command=self.show_about,
            width=200
        )
        about_btn.pack(pady=10)
    
    def create_help_tab(self):
        self.help_tab = self.tabview.add("❓ Помощь")
        
        help_text = ctk.CTkTextbox(self.help_tab, font=ctk.CTkFont(size=12), wrap="word")
        help_text.pack(fill="both", expand=True, padx=10, pady=10)
        
        help_content = f"""
Системный монитор - Руководство пользователя

📌 ОСНОВНЫЕ ВОЗМОЖНОСТИ:

1. МОНИТОРИНГ СИСТЕМЫ
   • Отображение загрузки CPU, RAM, GPU в реальном времени
   • Отслеживание температур компонентов
   • Информация о дисках и сети

2. БАЗА ДАННЫХ
   • Автоматическое сохранение данных каждой сессии
   • Экспорт данных в JSON формат
   • Просмотр истории сессий

3. ИНТЕРФЕЙС
   • Вкладки для навигации
   • Настройка темы оформления
   • Адаптивный дизайн

📌 БЫСТРЫЙ СТАРТ:

1. Вход в систему:
   Логин: a
   Пароль: 1

2. Просмотр информации:
   • Вкладка "Информация о системе" - детальная информация о ПК
   • Вкладка "Мониторинг" -实时监控
   • Вкладка "База данных" - история и экспорт

3. Экспорт данных:
   • Перейдите на вкладку "База данных"
   • Нажмите "Экспорт данных в JSON"
   • Выберите место сохранения

📌 ГОРЯЧИЕ КЛАВИШИ:

• F5 - Обновить информацию
• Ctrl+Q - Выход из программы

📌 ТЕХНИЧЕСКАЯ ПОДДЕРЖКА:

При возникновении проблем:
1. Проверьте подключение к интернету
2. Убедитесь что все зависимости установлены
3. Перезапустите программу

Версия: 1.0.0
Дата сборки: {datetime.now().strftime('%d.%m.%Y')}
"""
        
        help_text.insert("1.0", help_content)
        help_text.configure(state="disabled")
    
    def load_initial_data(self):
        """Загружает начальные данные"""
        try:
            # Начинаем новую сессию
            session_id = self.db.start_session(self.username)
            
            # Собираем данные
            data = self.collector.collect_all()
            self.current_data = data
            
            # Сохраняем в БД
            self.db.save_data(data)
            
            # Отображаем информацию
            self.display_system_info(data)
            
            # Обновляем информацию о сессии
            if session_id:
                self.session_info_label.configure(
                    text=f"Активная сессия: #{session_id} | Пользователь: {self.username}"
                )
            
            self.update_status("✅ Данные загружены")
            
            # Обновляем данные в БД вкладке
            self.refresh_db_data()
            
        except Exception as e:
            error_msg = f"Ошибка загрузки данных: {str(e)}"
            print(error_msg)
            if hasattr(self, 'info_text'):
                self.info_text.insert("1.0", error_msg)
            self.update_status("❌ Ошибка загрузки данных")
    
    def display_system_info(self, data):
        """Отображает системную информацию"""
        uptime = time.time() - self.start_time
        hours = int(uptime // 3600)
        minutes = int((uptime % 3600) // 60)
        
        info_text = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                            СИСТЕМНАЯ ИНФОРМАЦИЯ                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

📅 ДАТА И ВРЕМЯ
   └─ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

👤 ПОЛЬЗОВАТЕЛЬ
   ├─ Имя: {self.username}
   └─ Статус: Активен

💻 ОПЕРАЦИОННАЯ СИСТЕМА
   ├─ Название: {platform.system()} {platform.release()}
   ├─ Версия: {platform.version()}
   ├─ Архитектура: {platform.machine()}
   └─ Имя компьютера: {socket.gethostname()}

⏱️ ВРЕМЯ РАБОТЫ
   ├─ Программы: {hours}ч {minutes}м
   ├─ Количество обновлений: {self.update_count}
   └─ Сессия БД: #{self.db.session_id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🖥️ ПРОЦЕССОР (CPU)
   ├─ Модель: {data['cpu_model']}
   ├─ Загрузка: {data['cpu_load']:.1f}%
   ├─ Температура: {data['cpu_temp']:.1f}°C
   ├─ Физических ядер: {psutil.cpu_count(logical=False)}
   └─ Логических ядер: {psutil.cpu_count(logical=True)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💾 ОПЕРАТИВНАЯ ПАМЯТЬ (RAM)
   ├─ Всего: {data['ram_total']:.2f} GB
   ├─ Используется: {data['ram_used']:.2f} GB ({data['ram_percent']:.1f}%)
   ├─ Доступно: {data['ram_total'] - data['ram_used']:.2f} GB
   └─ Страничный файл: {psutil.swap_memory().total / (1024**3):.2f} GB

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎮 ВИДЕОКАРТА (GPU)
   ├─ Модель: {data['gpu_model']}
   ├─ Загрузка: {data['gpu_load']:.1f}%
   └─ Температура: {data['gpu_temp']:.1f}°C

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💿 ДИСКИ
"""
        
        for disk in data.get('disks', []):
            info_text += f"""
   ├─ {disk['device']} ({disk['mount']})
   │  ├─ Тип: {disk.get('filesystem', 'Unknown')}
   │  ├─ Всего: {disk['total']:.1f} GB
   │  ├─ Использовано: {disk['used']:.1f} GB ({disk['percent']:.1f}%)
   │  └─ Свободно: {disk['free']:.1f} GB
"""
        
        info_text += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🌐 СЕТЬ
   ├─ Отправлено: {:.2f} MB
   ├─ Получено: {:.2f} MB
   └─ Всего трафика: {:.2f} MB

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""".format(
    data.get('network', {}).get('bytes_sent', 0) / (1024**2),
    data.get('network', {}).get('bytes_recv', 0) / (1024**2),
    (data.get('network', {}).get('bytes_sent', 0) + data.get('network', {}).get('bytes_recv', 0)) / (1024**2)
)
        
        self.info_text.delete("1.0", "end")
        self.info_text.insert("1.0", info_text)
    
    def start_monitoring(self):
        """Запускает потоки мониторинга"""
        # Поток для сбора данных
        self.monitor_thread = threading.Thread(target=self.monitoring_loop, daemon=True)
        self.monitor_thread.start()
        
        # Поток для обновления UI
        self.update_ui_loop()
    
    def monitoring_loop(self):
        """Цикл сбора данных"""
        last_db_save = time.time()
        
        while self.running:
            try:
                # Собираем данные
                data = self.collector.collect_all()
                
                # Обновляем прогресс-бары
                self.current_data = data
                
                # Сохраняем в БД каждые 60 секунд
                current_time = time.time()
                if current_time - last_db_save >= 60:
                    self.db.save_data(data)
                    last_db_save = current_time
                    print("Автосохранение данных")
                
                # Обновляем счетчик
                self.update_count += 1
                
            except Exception as e:
                print(f"Ошибка в monitoring_loop: {e}")
            
            # Ждем указанный интервал
            interval = int(self.interval_var.get())
            time.sleep(interval)
    
    def update_ui_loop(self):
        """Обновляет UI данными из мониторинга"""
        if self.current_data:
            data = self.current_data
            
            # Обновляем прогресс-бары
            if 'cpu_load' in data:
                self.progress_bars['CPU'].set(data['cpu_load'] / 100)
                self.progress_labels['CPU'].configure(text=f"{data['cpu_load']:.1f}%")
            
            if 'ram_percent' in data:
                self.progress_bars['RAM'].set(data['ram_percent'] / 100)
                self.progress_labels['RAM'].configure(text=f"{data['ram_percent']:.1f}%")
            
            if 'gpu_load' in data:
                self.progress_bars['GPU'].set(data['gpu_load'] / 100)
                self.progress_labels['GPU'].configure(text=f"{data['gpu_load']:.1f}%")
            
            # Обновляем температуры
            if 'cpu_temp' in data and data['cpu_temp'] > 0:
                self.temp_labels['CPU_TEMP'].configure(text=f"{data['cpu_temp']:.1f}°C")
            
            if 'gpu_temp' in data and data['gpu_temp'] > 0:
                self.temp_labels['GPU_TEMP'].configure(text=f"{data['gpu_temp']:.1f}°C")
        
        # Планируем следующее обновление
        self.after(1000, self.update_ui_loop)
    
    def refresh_info(self):
        """Обновляет информацию вручную"""
        data = self.collector.collect_all()
        self.display_system_info(data)
        self.update_status("🔄 Информация обновлена")
    
    def refresh_db_data(self):
        """Обновляет отображение данных из БД"""
        sessions = self.db.get_all_sessions(10)
        
        if sessions:
            db_text = "╔════════════════════════════════════════════════════════════════════════════╗\n"
            db_text += "║                         ИСТОРИЯ СЕССИЙ МОНИТОРИНГА                         ║\n"
            db_text += "╚════════════════════════════════════════════════════════════════════════════╝\n\n"
            
            for session in sessions:
                db_text += f"""
┌─ СЕССИЯ #{session.get('id', 'N/A')}
│  ├─ Пользователь: {session.get('username', 'N/A')}
│  ├─ Время начала: {session.get('start_time', 'N/A')}
│  ├─ Время окончания: {session.get('end_time', 'Не завершена')}
│  ├─ Загрузка CPU: {session.get('cpu_load', 0):.1f}%
│  └─ Загрузка RAM: {session.get('ram_percent', 0):.1f}%
│
"""
            
            self.db_text.delete("1.0", "end")
            self.db_text.insert("1.0", db_text)
        else:
            self.db_text.delete("1.0", "end")
            self.db_text.insert("1.0", "Нет данных в базе")
    
    def clear_db_display(self):
        """Очищает отображение БД"""
        self.db_text.delete("1.0", "end")
        self.db_text.insert("1.0", "Отображение очищено")
        self.update_status("🗑️ Отображение очищено")
    
    def export_data(self):
        """Экспортирует данные в JSON"""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Экспорт данных"
        )
        
        if file_path:
            if self.db.export_to_json(file_path):
                messagebox.showinfo("Успех", f"Данные успешно экспортированы в:\n{file_path}")
                self.update_status("📤 Данные экспортированы")
            else:
                messagebox.showerror("Ошибка", "Не удалось экспортировать данные")
    
    def change_theme(self, choice):
        """Изменяет тему приложения"""
        ctk.set_appearance_mode(choice)
        self.update_status(f"🎨 Тема изменена на {choice}")
    
    def change_interval(self, choice):
        """Изменяет интервал обновления"""
        self.update_status(f"⏱️ Интервал обновления изменен на {choice} сек")
    
    def show_about(self):
        """Показывает информацию о программе"""
        about_text = f"""Системный монитор v1.0.0

Разработчик: System Monitor Team
Лицензия: MIT

Используемые библиотеки:
• customtkinter - GUI Framework
• psutil - Системный мониторинг
• sqlite3 - База данных

Функции:
• Мониторинг CPU, RAM, GPU
• Отслеживание температур
• Сохранение данных в БД
• Экспорт в JSON

Путь к программе:
{os.path.dirname(os.path.abspath(__file__))}

Время работы: {int((time.time() - self.start_time) // 60)} минут
Всего обновлений: {self.update_count}
"""
        
        messagebox.showinfo("О программе", about_text)
    
    def bind_shortcuts(self):
        """Настраивает горячие клавиши"""
        self.bind("<F5>", lambda e: self.refresh_info())
        self.bind("<Control-q>", lambda e: self.on_close())
    
    def update_status(self, message: str):
        """Обновляет статусную строку"""
        if hasattr(self, 'status_label'):
            self.status_label.configure(text=f"{datetime.now().strftime('%H:%M:%S')} | {message}")
    
    def on_close(self):
        """Обработчик закрытия окна"""
        self.running = False
        self.db.close()
        self.destroy()

# ==================== ТОЧКА ВХОДА ====================
if __name__ == "__main__":
    try:
        app = LoginWindow()
        app.mainloop()
    except Exception as e:
        import traceback
        traceback.print_exc()
        input("Нажмите Enter для выхода...")