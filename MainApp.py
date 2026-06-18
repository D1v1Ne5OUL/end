import sqlite3
import os
import psutil
import platform
import socket
from datetime import datetime
from typing import Dict, Any, List

DB_PATH = "system_monitor.db"

class DatabaseManager:
    def __init__(self):
        self.conn = None
        self.session_id = None
        self._init_database()
    
    def _init_database(self):
        """Инициализирует базу данных"""
        schema_sql = """
        PRAGMA foreign_keys = ON;
        PRAGMA journal_mode = WAL;
        
        CREATE TABLE IF NOT EXISTS monitoring_sessions (
            session_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            start_time      DATETIME DEFAULT CURRENT_TIMESTAMP,
            end_time        DATETIME,
            notes           TEXT
        );
        
        CREATE TABLE IF NOT EXISTS operating_system (
            os_id           INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            system_name     TEXT,
            version         TEXT,
            build           TEXT,
            platform        TEXT,
            architecture    TEXT,
            computer_name   TEXT,
            manufacturer    TEXT,
            install_date    TEXT,
            uptime          TEXT,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS cpu (
            cpu_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            model           TEXT,
            manufacturer    TEXT,
            architecture    TEXT,
            physical_cores  INTEGER,
            logical_cores   INTEGER,
            max_frequency_mhz INTEGER,
            l2_cache_kb     INTEGER,
            l3_cache_kb     INTEGER,
            socket          TEXT,
            current_frequency_mhz REAL,
            load_percent    REAL,
            temperature     REAL,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS ram_summary (
            ram_summary_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            total_gb        REAL,
            used_gb         REAL,
            available_gb    REAL,
            usage_percent   REAL,
            total_pagefile_gb REAL,
            used_pagefile_gb REAL,
            pagefile_usage_percent REAL,
            max_capacity_gb REAL,
            total_slots     INTEGER,
            physically_installed_gb REAL,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS ram_modules (
            module_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            bank_label      TEXT,
            size_gb         REAL,
            manufacturer    TEXT,
            speed_mhz       INTEGER,
            model           TEXT,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS gpus (
            gpu_id          INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            gpu_index       INTEGER,
            model           TEXT,
            memory_gb       REAL,
            driver_version  TEXT,
            temperature     REAL,
            load_percent    REAL,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS disk_drives (
            disk_id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            drive_letter    TEXT,
            mount_point     TEXT,
            filesystem      TEXT,
            total_size_gb   REAL,
            used_percent    REAL,
            free_gb         REAL,
            used_gb         REAL,
            temperature     REAL,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS network_adapters (
            adapter_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            name            TEXT,
            status          TEXT,
            mac_address     TEXT,
            ipv4_address    TEXT,
            ipv6_address    TEXT,
            speed_mbps      INTEGER,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS motherboard (
            motherboard_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            manufacturer    TEXT,
            model           TEXT,
            version         TEXT,
            serial_number   TEXT,
            bios_version    TEXT,
            bios_date       TEXT,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE TABLE IF NOT EXISTS monitors (
            monitor_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id      INTEGER NOT NULL,
            monitor_name    TEXT,
            resolution      TEXT,
            is_primary      BOOLEAN DEFAULT 0,
            FOREIGN KEY (session_id) REFERENCES monitoring_sessions(session_id) ON DELETE CASCADE
        );
        
        CREATE INDEX IF NOT EXISTS idx_os_session ON operating_system(session_id);
        CREATE INDEX IF NOT EXISTS idx_cpu_session ON cpu(session_id);
        CREATE INDEX IF NOT EXISTS idx_gpus_session ON gpus(session_id);
        """
        
        try:
            self.conn = sqlite3.connect(DB_PATH)
            self.conn.executescript(schema_sql)
            self.conn.commit()
            print("✅ База данных инициализирована")
        except Exception as e:
            print(f"❌ Ошибка инициализации БД: {e}")
            raise
    
    def start_session(self, notes: str = ""):
        """Начинает новую сессию мониторинга"""
        cursor = self.conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_sessions (start_time, notes)
            VALUES (?, ?)
        """, (datetime.now().isoformat(), notes))
        self.session_id = cursor.lastrowid
        self.conn.commit()
        print(f"✅ Начата сессия мониторинга #{self.session_id}")
        return self.session_id
    
    def end_session(self):
        """Завершает текущую сессию"""
        if self.session_id:
            cursor = self.conn.cursor()
            cursor.execute("""
                UPDATE monitoring_sessions 
                SET end_time = ? 
                WHERE session_id = ?
            """, (datetime.now().isoformat(), self.session_id))
            self.conn.commit()
            print(f"✅ Завершена сессия мониторинга #{self.session_id}")
    
    def save_system_data(self, data: Dict[str, Any]):
        """Сохраняет данные о системе"""
        if not self.session_id:
            self.start_session()
        
        cursor = self.conn.cursor()
        
        # Сохраняем ОС
        cursor.execute("""
            INSERT INTO operating_system (
                session_id, system_name, version, build, platform, 
                architecture, computer_name, manufacturer, uptime
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            self.session_id,
            data.get('os_name', platform.system()),
            data.get('os_version', platform.release()),
            data.get('os_build', platform.version()),
            platform.platform(),
            platform.machine(),
            socket.gethostname(),
            data.get('os_manufacturer', 'Unknown'),
            str(data.get('uptime', 'Unknown'))
        ))
        
        # Сохраняем CPU
        if 'cpu' in data:
            cpu_data = data['cpu']
            cursor.execute("""
                INSERT INTO cpu (
                    session_id, model, manufacturer, architecture, physical_cores,
                    logical_cores, max_frequency_mhz, current_frequency_mhz, 
                    load_percent, temperature
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                self.session_id,
                cpu_data.get('model', platform.processor()),
                cpu_data.get('manufacturer', 'Unknown'),
                platform.machine(),
                cpu_data.get('physical_cores', psutil.cpu_count(logical=False)),
                cpu_data.get('logical_cores', psutil.cpu_count(logical=True)),
                cpu_data.get('max_freq', 0),
                cpu_data.get('current_freq', 0),
                cpu_data.get('load', 0),
                cpu_data.get('temperature', 0)
            ))
        
        # Сохраняем RAM
        if 'ram' in data:
            ram_data = data['ram']
            cursor.execute("""
                INSERT INTO ram_summary (
                    session_id, total_gb, used_gb, available_gb, usage_percent
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                self.session_id,
                ram_data.get('total', 0),
                ram_data.get('used', 0),
                ram_data.get('available', 0),
                ram_data.get('percent', 0)
            ))
            
            # Сохраняем модули RAM
            if 'modules' in ram_data:
                for module in ram_data['modules']:
                    cursor.execute("""
                        INSERT INTO ram_modules (
                            session_id, bank_label, size_gb, manufacturer, speed_mhz
                        ) VALUES (?, ?, ?, ?, ?)
                    """, (
                        self.session_id,
                        module.get('bank', 'Unknown'),
                        module.get('size', 0),
                        module.get('manufacturer', 'Unknown'),
                        module.get('speed', 0)
                    ))
        
        # Сохраняем GPU
        if 'gpu' in data:
            for gpu in data['gpu']:
                cursor.execute("""
                    INSERT INTO gpus (
                        session_id, gpu_index, model, memory_gb, 
                        temperature, load_percent
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    self.session_id,
                    gpu.get('index', 0),
                    gpu.get('name', 'Unknown'),
                    gpu.get('memory', 0),
                    gpu.get('temperature', 0),
                    gpu.get('load', 0)
                ))
        
        # Сохраняем диски
        if 'disks' in data:
            for disk in data['disks']:
                cursor.execute("""
                    INSERT INTO disk_drives (
                        session_id, drive_letter, mount_point, filesystem,
                        total_size_gb, used_percent, free_gb, used_gb, temperature
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.session_id,
                    disk.get('letter', ''),
                    disk.get('mount', ''),
                    disk.get('fs', ''),
                    disk.get('total', 0),
                    disk.get('percent', 0),
                    disk.get('free', 0),
                    disk.get('used', 0),
                    disk.get('temperature', 0)
                ))
        
        # Сохраняем сетевые адаптеры
        if 'network' in data:
            for adapter in data['network']:
                cursor.execute("""
                    INSERT INTO network_adapters (
                        session_id, name, status, mac_address, ipv4_address, ipv6_address, speed_mbps
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    self.session_id,
                    adapter.get('name', 'Unknown'),
                    adapter.get('status', 'Unknown'),
                    adapter.get('mac_address', ''),
                    adapter.get('ipv4_address', ''),
                    adapter.get('ipv6_address', ''),
                    adapter.get('speed', 0)
                ))
        
        self.conn.commit()
        print(f"✅ Данные сохранены в БД для сессии #{self.session_id}")
    
    def get_latest_session_data(self) -> Dict[str, Any]:
        """Получает данные последней сессии из БД"""
        if not self.conn:
            return {}
        
        cursor = self.conn.cursor()
        
        # Получаем последнюю сессию
        cursor.execute("""
            SELECT * FROM monitoring_sessions 
            ORDER BY session_id DESC LIMIT 1
        """)
        session = cursor.fetchone()
        
        if not session:
            return {}
        
        session_id = session[0]
        result = {
            'session_id': session_id,
            'start_time': session[1],
            'end_time': session[2],
            'notes': session[3]
        }
        
        # Получаем данные ОС
        cursor.execute("""
            SELECT * FROM operating_system 
            WHERE session_id = ? LIMIT 1
        """, (session_id,))
        os_data = cursor.fetchone()
        if os_data:
            result['os'] = dict(zip([desc[0] for desc in cursor.description], os_data))
        
        # Получаем данные CPU
        cursor.execute("""
            SELECT * FROM cpu 
            WHERE session_id = ? LIMIT 1
        """, (session_id,))
        cpu_data = cursor.fetchone()
        if cpu_data:
            result['cpu'] = dict(zip([desc[0] for desc in cursor.description], cpu_data))
        
        # Получаем данные RAM
        cursor.execute("""
            SELECT * FROM ram_summary 
            WHERE session_id = ? LIMIT 1
        """, (session_id,))
        ram_data = cursor.fetchone()
        if ram_data:
            result['ram'] = dict(zip([desc[0] for desc in cursor.description], ram_data))
        
        # Получаем модули RAM
        cursor.execute("""
            SELECT * FROM ram_modules 
            WHERE session_id = ?
        """, (session_id,))
        ram_modules = cursor.fetchall()
        if ram_modules:
            result['ram_modules'] = [dict(zip([desc[0] for desc in cursor.description], module)) for module in ram_modules]
        
        # Получаем данные GPU
        cursor.execute("""
            SELECT * FROM gpus 
            WHERE session_id = ?
        """, (session_id,))
        gpus = cursor.fetchall()
        if gpus:
            result['gpus'] = [dict(zip([desc[0] for desc in cursor.description], gpu)) for gpu in gpus]
        
        # Получаем данные дисков
        cursor.execute("""
            SELECT * FROM disk_drives 
            WHERE session_id = ?
        """, (session_id,))
        disks = cursor.fetchall()
        if disks:
            result['disks'] = [dict(zip([desc[0] for desc in cursor.description], disk)) for disk in disks]
        
        # Получаем сетевые адаптеры
        cursor.execute("""
            SELECT * FROM network_adapters 
            WHERE session_id = ?
        """, (session_id,))
        networks = cursor.fetchall()
        if networks:
            result['network'] = [dict(zip([desc[0] for desc in cursor.description], net)) for net in networks]
        
        return result
    
    def get_session_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получает историю сессий"""
        cursor = self.conn.cursor()
        cursor.execute("""
            SELECT session_id, start_time, end_time, notes 
            FROM monitoring_sessions 
            ORDER BY session_id DESC LIMIT ?
        """, (limit,))
        
        sessions = cursor.fetchall()
        return [dict(zip([desc[0] for desc in cursor.description], session)) for session in sessions]
    
    def delete_session(self, session_id: int):
        """Удаляет сессию и все связанные данные"""
        cursor = self.conn.cursor()
        cursor.execute("DELETE FROM monitoring_sessions WHERE session_id = ?", (session_id,))
        self.conn.commit()
        print(f"✅ Удалена сессия #{session_id}")
    
    def close(self):
        """Закрывает соединение с БД"""
        if self.conn:
            self.end_session()
            self.conn.close()
            print("✅ Соединение с БД закрыто")