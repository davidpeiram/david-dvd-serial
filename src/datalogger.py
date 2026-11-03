"""
datalogger.py - Gravador de Logs e Telemetria de Viagem para Ford Fiesta 1.0 Rocam
Registra dados brutos e calculados em formato CSV para análise de consumo, desempenho e engenharia.
"""

import os
import csv
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"


class TripDatalogger:
    def __init__(self, logs_dir: Optional[Path] = None):
        self.logs_dir = logs_dir or LOGS_DIR
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        
        self.is_logging = False
        self.current_file: Optional[Path] = None
        self._file_handle = None
        self._csv_writer = None
        
        # Estatísticas da sessão atual de log
        self.session_start_time = 0.0
        self.records_count = 0
        self.start_trip_km = 0.0
        self.start_fuel_liters = 0.0
        self.max_speed = 0
        self.max_rpm = 0
        self.last_log_time = 0.0
        self.log_interval_s = 0.1  # Registra a até 10 Hz para capturar transientes de acelerador

    def start_logging(self, session_prefix: str = "viagem_fiesta", initial_km: float = 0.0, initial_fuel: float = 0.0) -> Dict[str, Any]:
        with self._lock:
            if self.is_logging:
                return {"status": "already_running", "filename": self.current_file.name if self.current_file else ""}

            now = datetime.now()
            time_str = now.strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"{session_prefix}_{time_str}.csv"
            file_path = self.logs_dir / filename

            self._file_handle = open(file_path, "w", newline="", encoding="utf-8")
            self._csv_writer = csv.writer(self._file_handle)

            # Cabeçalho completo automotivo
            headers = [
                "timestamp",
                "datetime",
                "rpm",
                "speed_kmh",
                "gear",
                "throttle_pct",
                "engine_load_pct",
                "map_kpa",
                "coolant_temp_c",
                "intake_temp_c",
                "timing_advance_deg",
                "stft_pct",
                "ltft_pct",
                "fuel_level_pct",
                "fuel_liters_tank",
                "battery_voltage_v",
                "fuel_rate_lph",
                "fuel_economy_str",
                "trip_fuel_liters",
                "trip_km",
                "avg_kml",
                "mil_on",
                "dtc_count",
                "ecu_responding",
                "engine_torque_nm",
            ]
            self._csv_writer.writerow(headers)
            self._file_handle.flush()

            self.is_logging = True
            self.current_file = file_path
            self.session_start_time = time.time()
            self.records_count = 0
            self.start_trip_km = initial_km
            self.start_fuel_liters = initial_fuel
            self.max_speed = 0
            self.max_rpm = 0
            self.last_log_time = 0.0

            print(f"[Datalogger] Gravação de log iniciada: {filename}")
            return {
                "status": "started",
                "filename": filename,
                "file_path": str(file_path),
                "start_time": time_str,
            }

    def log_frame(self, telemetry: Dict[str, Any]) -> None:
        if not self.is_logging or not self._csv_writer:
            return

        now = time.time()
        # Controle de taxa para não saturar I/O
        if now - self.last_log_time < self.log_interval_s:
            return
        self.last_log_time = now

        with self._lock:
            if not self.is_logging or not self._file_handle:
                return

            speed = telemetry.get("speed", 0)
            rpm = telemetry.get("rpm", 0)
            if speed > self.max_speed:
                self.max_speed = speed
            if rpm > self.max_rpm:
                self.max_rpm = rpm

            row = [
                round(now, 3),
                datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                rpm,
                speed,
                telemetry.get("gear", "N"),
                telemetry.get("throttle", 0.0),
                telemetry.get("engine_load", 0.0),
                telemetry.get("map", 0),
                telemetry.get("coolant_temp", 0),
                telemetry.get("intake_temp", 0),
                telemetry.get("timing_advance", 0.0),
                telemetry.get("stft", 0.0),
                telemetry.get("ltft", 0.0),
                telemetry.get("fuel_level", 0.0),
                telemetry.get("fuel_liters", 0.0),
                telemetry.get("battery_voltage", 0.0),
                telemetry.get("fuel_rate_lph", 0.0),
                telemetry.get("fuel_economy_str", "0.0"),
                telemetry.get("total_fuel_liters", 0.0),
                telemetry.get("trip_km", 0.0),
                telemetry.get("avg_fuel_kml", 0.0),
                1 if telemetry.get("mil_on") else 0,
                telemetry.get("dtc_count", 0),
                1 if telemetry.get("ecu_responding") else 0,
                telemetry.get("engine_torque_nm", 0.0),
            ]

            try:
                self._csv_writer.writerow(row)
                self.records_count += 1
                # Flush a cada 10 registros para garantir integridade caso feche de repente
                if self.records_count % 10 == 0:
                    self._file_handle.flush()
            except Exception as e:
                print(f"[Datalogger] Erro ao gravar linha no CSV: {e}")

    def stop_logging(self, final_km: float = 0.0, final_fuel: float = 0.0, fuel_price_per_liter: float = 6.30) -> Dict[str, Any]:
        with self._lock:
            if not self.is_logging:
                return {"status": "not_logging"}

            self.is_logging = False
            filename = self.current_file.name if self.current_file else "desconhecido.csv"
            filepath = str(self.current_file) if self.current_file else ""

            if self._file_handle:
                try:
                    self._file_handle.flush()
                    self._file_handle.close()
                except Exception:
                    pass
                self._file_handle = None
                self._csv_writer = None

            elapsed_sec = max(1, int(time.time() - self.session_start_time))
            hours = elapsed_sec // 3600
            mins = (elapsed_sec % 3600) // 60
            secs = elapsed_sec % 60
            duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

            # Métricas da viagem registrada
            trip_distance = max(0.0, round(final_km - self.start_trip_km, 2))
            fuel_spent = max(0.0, round(final_fuel - self.start_fuel_liters, 3))
            avg_consumption = round(trip_distance / fuel_spent, 2) if fuel_spent > 0.01 else 0.0
            avg_speed = round((trip_distance / (elapsed_sec / 3600.0)), 1) if elapsed_sec > 10 else 0.0
            estimated_cost = round(fuel_spent * fuel_price_per_liter, 2)

            summary = {
                "status": "stopped",
                "filename": filename,
                "file_path": filepath,
                "records_count": self.records_count,
                "duration_seconds": elapsed_sec,
                "duration_str": duration_str,
                "distance_km": trip_distance,
                "fuel_spent_liters": fuel_spent,
                "avg_consumption_kml": avg_consumption,
                "avg_speed_kmh": avg_speed,
                "max_speed_kmh": self.max_speed,
                "max_rpm": self.max_rpm,
                "estimated_cost_brl": estimated_cost,
                "fuel_price_applied": fuel_price_per_liter,
            }

            print(f"[Datalogger] Gravação finalizada: {filename} ({self.records_count} linhas, {trip_distance} km, {fuel_spent} L)")
            return summary

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            elapsed_sec = int(time.time() - self.session_start_time) if self.is_logging else 0
            hours = elapsed_sec // 3600
            mins = (elapsed_sec % 3600) // 60
            secs = elapsed_sec % 60
            return {
                "is_logging": self.is_logging,
                "filename": self.current_file.name if (self.is_logging and self.current_file) else None,
                "records_count": self.records_count,
                "duration_str": f"{hours:02d}:{mins:02d}:{secs:02d}",
                "elapsed_seconds": elapsed_sec,
                "max_speed": self.max_speed,
                "max_rpm": self.max_rpm,
            }

    def list_logs(self) -> List[Dict[str, Any]]:
        results = []
        if not self.logs_dir.exists():
            return results

        files = sorted(self.logs_dir.glob("*.csv"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files:
            stat = f.stat()
            size_kb = round(stat.st_size / 1024.0, 1)
            date_str = datetime.fromtimestamp(stat.st_mtime).strftime("%d/%m/%Y %H:%M")
            results.append({
                "filename": f.name,
                "size_kb": size_kb,
                "modified": date_str,
                "path": str(f),
            })
        return results
