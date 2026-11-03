"""
obd_manager.py - Gerenciador de Telemetria de Produção para o Ford Fiesta 1.0 Rocam - Versão 2.0
Processa telemetria real do barramento CAN, trip computer com watchdog de dados vencidos,
histerese de marchas, compensação de malha fechada no consumo e centralização total de configurações.
"""

import time
import math
import threading
from typing import Dict, Any, Optional
from .can_adapter import BaseCANAdapter, CANableSLCANAdapter, SimulatedFallbackAdapter
from .gear_detector import GearDetector
from .fuel_calculator import calculate_fuel_consumption
from .obd_pids import (
    PIDS_CONFIG,
    OBD_BROADCAST_REQ_ID,
    OBD_ECU_ENGINE_REQ_ID,
    OBD_ECU_ENGINE_RESP_ID,
    build_obd_request_frame,
    decode_mode_03_dtcs,
)


class OBDManager:
    """
    Controlador central de telemetria veicular, comunicação OBD-II/CAN e computador de viagem.
    """

    def __init__(
        self,
        adapter: BaseCANAdapter,
        datalogger: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
        fuel_price_per_l: Optional[float] = None,
    ):
        self.adapter = adapter
        self.datalogger = datalogger
        self.config = config or {}

        # 1. Configurações centralizadas
        self.tank_capacity = float(self.config.get("fuel_tank_capacity_liters", 54.0))
        self.reserve_threshold = float(self.config.get("fuel_reserve_liters", 5.0))
        self.fuel_price_per_l = float(
            fuel_price_per_l
            if fuel_price_per_l is not None
            else self.config.get("fuel_price_per_liter", 6.30)
        )
        self.fuel_type = str(self.config.get("fuel_type", "flex_auto"))
        self.fuel_calibration_k = float(self.config.get("fuel_calibration_k_factor", 1.0))

        # ID de consulta direta da ECU do motor Ford EEC-VI (0x7E0 padrão; resposta em 0x7E8)
        can_target_str = str(self.config.get("can_target_ecu_id", "0x7E0"))
        self.target_ecu_id = int(can_target_str, 16) if can_target_str.startswith("0x") else int(can_target_str)

        can_resp_str = str(self.config.get("can_response_ecu_id", "0x7E8"))
        self.response_ecu_id = int(can_resp_str, 16) if can_resp_str.startswith("0x") else int(can_resp_str)

        # Timeouts de validade temporal (TTL em segundos para evitar cálculo com dado 'congelado')
        ttl_conf = self.config.get("stale_data_timeout_sec", {})
        self.ttl_high = float(ttl_conf.get("high_freq", 1.5))
        self.ttl_med = float(ttl_conf.get("med_freq", 4.0))
        self.ttl_low = float(ttl_conf.get("low_freq", 12.0))

        # 2. Estado de execução e concorrência
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # 3. Detectores e filtros com histerese
        ranges_conf = self.config.get("gear_ratio_ranges")
        custom_gear_ranges = None
        if ranges_conf and isinstance(ranges_conf, list):
            try:
                custom_gear_ranges = [
                    (int(item["gear"]), float(item["min"]), float(item["max"]))
                    for item in ranges_conf
                ]
            except Exception as e:
                print(f"[OBDManager] Aviso: falha ao processar gear_ratio_ranges do config: {e}")
                custom_gear_ranges = None

        self.gear_detector = GearDetector(
            history_len=4,
            min_consecutive_matches=3,
            ratio_ranges=custom_gear_ranges,
        )

        # 4. Trip Computer (Odômetro Parcial e Tempo de Viagem)
        self.session_start_time = time.time()
        self.trip_km = 0.0
        self.total_fuel_liters = 0.0
        self._last_calc_time = time.time()

        # 5. Rastreamento de qualidade e idade dos dados (Watchdog temporal)
        self._last_ecu_resp_time = 0.0
        self._param_timestamps: Dict[str, float] = {}

        # 6. Dicionário de telemetria pública
        self.telemetry: Dict[str, Any] = {
            "rpm": 0,
            "speed": 0,
            "gear": "N",
            "map": 0,
            "throttle": 0.0,
            "engine_load": 0.0,
            "timing_advance": 0.0,
            "coolant_temp": 0,
            "intake_temp": 0,
            "battery_voltage": 12.5,
            "battery_voltage_mode": "ESTIMADO",
            "battery_voltage_source": "Sintético por RPM (Sem ADC Físico no Pino 16)",
            "fuel_level": 49.0,
            "fuel_liters": 26.5,
            "fuel_reserve": False,
            "tank_capacity_l": self.tank_capacity,
            "reserve_threshold_l": self.reserve_threshold,
            # Engenharia Reversa Ford: Torque Real do Motor (ID 0x422)
            "engine_torque_nm": 0.0,
            "range_km": 305,
            "stft": 0.0,
            "ltft": 0.0,
            "mil_on": False,
            "dtc_count": 0,
            "dtc_codes": [],
            "dtc_codes_str": "",
            # Métricas da Viagem e Consumo
            "fuel_rate_lph": 0.0,
            "km_per_liter": 0.0,
            "fuel_economy_str": "0.0",
            "fuel_economy_unit": "km/L",
            "trip_km": 0.0,
            "total_fuel_liters": 0.0,
            "trip_cost_brl": 0.0,
            "fuel_price_per_l": self.fuel_price_per_l,
            "logging_active": False,
            "trip_time_str": "00:00:00",
            "avg_fuel_kml": 0.0,
            # Diagnóstico de rede e qualidade dos dados (Watchdog)
            "connected": False,
            "connection_state": "DISCONNECTED",
            "ecu_responding": False,
            "speed_stale": False,
            "rpm_stale": False,
            "connection_info": "Iniciando...",
            "timestamp": 0.0,
        }

    def start(self) -> bool:
        if self._running:
            return True
        if not self.adapter.open():
            print("[OBDManager] Adaptador CAN não pôde ser aberto imediatamente.")
            return False

        self._running = True
        self.session_start_time = time.time()
        self._last_calc_time = time.time()
        with self._lock:
            self.telemetry["connected"] = self.adapter.is_connected
            self.telemetry["connection_info"] = self.adapter.connection_info
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.adapter.close()
        with self._lock:
            self.telemetry["connected"] = False
            self.telemetry["ecu_responding"] = False
            self.telemetry["connection_state"] = "DISCONNECTED"

    def reconnect(self, new_adapter: BaseCANAdapter) -> bool:
        """Reinicia a conexão mantendo a mesma instância e preservando referências WebSocket."""
        print("[OBDManager] Solicitada reconexão do adaptador...")
        self.stop()
        self.adapter = new_adapter
        return self.start()

    def get_snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self.telemetry)

    def reset_trip(self) -> None:
        with self._lock:
            self.session_start_time = time.time()
            self.trip_km = 0.0
            self.total_fuel_liters = 0.0
            self._last_calc_time = time.time()
            self.telemetry["trip_km"] = 0.0
            self.telemetry["total_fuel_liters"] = 0.0
            self.telemetry["trip_cost_brl"] = 0.0
            self.telemetry["avg_fuel_kml"] = 0.0
            self.telemetry["trip_time_str"] = "00:00:00"
            print("[OBDManager] Odômetro e consumo da viagem zerados (Reset Trip).")

    def _update_trip_and_metrics(self) -> None:
        now = time.time()
        dt = max(0.001, now - self._last_calc_time)
        self._last_calc_time = now

        is_sim = isinstance(self.adapter, SimulatedFallbackAdapter)

        # 1. Avaliação de Frescor dos Dados (Watchdog temporal)
        speed_age = now - self._param_timestamps.get("speed", 0.0) if not is_sim else 0.0
        rpm_age = now - self._param_timestamps.get("rpm", 0.0) if not is_sim else 0.0
        ecu_active = (now - self._last_ecu_resp_time < 2.5) if not is_sim else True

        speed_stale = bool(speed_age > self.ttl_high and not is_sim)
        rpm_stale = bool(rpm_age > self.ttl_high and not is_sim)

        self.telemetry["speed_stale"] = speed_stale
        self.telemetry["rpm_stale"] = rpm_stale
        self.telemetry["ecu_responding"] = ecu_active

        # Estado discriminado de conexão
        if not self.adapter.is_connected:
            conn_state = "DISCONNECTED"
        elif is_sim:
            conn_state = "DEMO"
        elif ecu_active:
            conn_state = "ECU_CONNECTED"
        else:
            conn_state = "WAITING_ECU"

        self.telemetry["connection_state"] = conn_state

        cur_rpm = self.telemetry.get("rpm", 0) if not rpm_stale else 0
        cur_spd = self.telemetry.get("speed", 0) if not speed_stale else 0
        cur_map = self.telemetry.get("map", 28)
        cur_iat = self.telemetry.get("intake_temp", 30)
        cur_stft = self.telemetry.get("stft", 0.0)
        cur_ltft = self.telemetry.get("ltft", 0.0)

        # 2. Estimativa de Marcha com Histerese Temporal
        self.telemetry["gear"] = self.gear_detector.update(cur_rpm, cur_spd)

        # 3. Consumo Instantâneo (Speed-Density com compensação de malha fechada STFT/LTFT)
        lph, kml, formatted_val, unit = calculate_fuel_consumption(
            rpm=cur_rpm,
            map_kpa=cur_map,
            iat_celsius=cur_iat,
            speed_kmh=cur_spd,
            stft_pct=cur_stft,
            ltft_pct=cur_ltft,
            fuel_type=self.fuel_type,
            calibration_k=self.fuel_calibration_k,
        )
        self.telemetry["fuel_rate_lph"] = lph
        self.telemetry["km_per_liter"] = kml if kml is not None else 0.0
        self.telemetry["fuel_economy_str"] = formatted_val
        self.telemetry["fuel_economy_unit"] = unit

        # 4. Odômetro Parcial com Watchdog (só integra se a velocidade for válida e recente)
        if cur_spd > 0 and not speed_stale:
            delta_km = cur_spd * (dt / 3600.0)
            self.trip_km += delta_km
            self.telemetry["trip_km"] = round(self.trip_km, 2)

        # 5. Consumo Acumulado da Viagem com Watchdog (só integra se motor estiver girando e não-stale)
        if cur_rpm > 350 and not rpm_stale:
            fuel_burned_liters = lph * (dt / 3600.0)
            self.total_fuel_liters += fuel_burned_liters
            self.telemetry["total_fuel_liters"] = round(self.total_fuel_liters, 3)

        self.telemetry["trip_cost_brl"] = round(self.total_fuel_liters * self.fuel_price_per_l, 2)
        if self.trip_km > 0.05 and self.total_fuel_liters > 0.005:
            avg_kml = self.trip_km / self.total_fuel_liters
            self.telemetry["avg_fuel_kml"] = round(min(50.0, avg_kml), 1)

        # 6. Tempo de Viagem (HH:MM:SS)
        elapsed_sec = int(now - self.session_start_time)
        hours = elapsed_sec // 3600
        mins = (elapsed_sec % 3600) // 60
        secs = elapsed_sec % 60
        self.telemetry["trip_time_str"] = f"{hours:02d}:{mins:02d}:{secs:02d}"

        # 7. Gravação contínua do Datalogger
        if self.datalogger:
            self.telemetry["logging_active"] = self.datalogger.is_logging
            if self.datalogger.is_logging:
                self.datalogger.log_frame(self.telemetry)

        # 8. Combustível Real da Boia (ID 0x430) e Autonomia Estimada (DTE)
        raw_fuel = self.adapter.get_last_fuel_level()
        if raw_fuel is not None and 0.0 <= raw_fuel <= 100.0:
            self.telemetry["fuel_level"] = raw_fuel

        cur_fuel_pct = self.telemetry.get("fuel_level", 49.0)
        fuel_liters = round((cur_fuel_pct / 100.0) * self.tank_capacity, 1)
        self.telemetry["fuel_liters"] = fuel_liters
        self.telemetry["fuel_reserve"] = bool(fuel_liters <= self.reserve_threshold)

        avg_kml = self.telemetry.get("avg_fuel_kml", 0.0)
        effective_kml = avg_kml if (avg_kml > 5.0 and self.trip_km > 2.0) else 11.5
        self.telemetry["range_km"] = int(fuel_liters * effective_kml)

        # 9. Torque Real do Motor (Engenharia Reversa Ford: Broadcast 0x422 em Nm)
        cur_rpm = self.telemetry.get("rpm", 0)
        if cur_rpm > 400:
            self.telemetry["engine_torque_nm"] = round(float(self.adapter.get_engine_torque_nm()), 1)
        else:
            self.telemetry["engine_torque_nm"] = 0.0

        # 10. Status Geral da Conexão
        self.telemetry["connection_info"] = self.adapter.connection_info
        self.telemetry["connected"] = self.adapter.is_connected

    def _worker_loop(self) -> None:
        cycle_count = 0
        pids_p1 = [pid for pid, conf in PIDS_CONFIG.items() if conf["priority"] == 1]  # RPM, Speed, TPS
        pids_p2 = [pid for pid, conf in PIDS_CONFIG.items() if conf["priority"] == 2]  # MAP, Carga, Ponto Ignição
        pids_p3 = [pid for pid, conf in PIDS_CONFIG.items() if conf["priority"] == 3]  # Temp Motor, IAT, STFT, LTFT
        pids_p4 = [pid for pid, conf in PIDS_CONFIG.items() if conf["priority"] == 4]  # Luz Injeção / Falhas DTC (0x01)

        while self._running:
            # Hot-Plug Automático: se estiver em demonstração e o CANable for plugado na USB
            if isinstance(self.adapter, SimulatedFallbackAdapter):
                if cycle_count % 15 == 0:
                    detected_port = CANableSLCANAdapter.find_canable_port()
                    if detected_port:
                        print(f"[OBDManager] CANable detectado na porta {detected_port}! Conectando ao barramento real...")
                        real_adapter = CANableSLCANAdapter(port=detected_port)
                        if real_adapter.open():
                            self.adapter = real_adapter
                            with self._lock:
                                self.telemetry["connected"] = True
                                self.telemetry["connection_info"] = real_adapter.connection_info
                            print(f"[OBDManager] Transição concluída! Modo REAL ativado em {detected_port} a 500 kbps.")
                            continue

            with self._lock:
                self.telemetry["connected"] = self.adapter.is_connected
                self.telemetry["connection_info"] = self.adapter.connection_info

            # Reconexão automática se a porta cair
            if not self.adapter.is_connected:
                print("[OBDManager] Tentando restabelecer conexão com o barramento CAN...")
                self.adapter.open()
                time.sleep(1.0)
                continue

            cycle_count += 1
            query_queue = list(pids_p1)

            if cycle_count % 2 == 0:
                query_queue.extend(pids_p2)
            if cycle_count % 6 == 0:
                query_queue.extend(pids_p3)
            if cycle_count % 35 == 0:
                query_queue.extend(pids_p4)
                # Modo 03: Consulta códigos de falha alfanuméricos completos (ex: P0171)
                try:
                    self.adapter.clear_rx_buffer()
                    req_m3 = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                    target_req = self.target_ecu_id or OBD_ECU_ENGINE_REQ_ID
                    if self.adapter.send(target_req, req_m3):
                        resp_m3 = self.adapter.recv(timeout=0.06, target_id=self.response_ecu_id)
                        if resp_m3:
                            cid, payload = resp_m3
                            if len(payload) >= 3 and payload[1] == 0x43:
                                dtcs = decode_mode_03_dtcs(payload[2:])
                                with self._lock:
                                    self.telemetry["dtc_codes"] = dtcs
                                    self.telemetry["dtc_codes_str"] = ", ".join(dtcs) if dtcs else ""
                except Exception as err:
                    print(f"[OBDManager] Erro consultando Modo 03: {err}")

            for pid in query_queue:
                if not self._running or not self.adapter.is_connected:
                    break

                # PIDs 0x42 e 0x2F não são suportados pelo Ford EEC-VI em Modo 01 padrão
                if pid in (0x42, 0x2F):
                    continue

                req_frame = build_obd_request_frame(pid)
                self.adapter.clear_rx_buffer()

                # Envia consulta direcionada à ECU do motor (0x7E0) ou broadcast (0x7DF)
                target_req = self.target_ecu_id or OBD_ECU_ENGINE_REQ_ID
                if not self.adapter.send(target_req, req_frame):
                    time.sleep(0.005)
                    continue

                resp = self.adapter.recv(timeout=0.035, target_id=self.response_ecu_id)
                if resp:
                    can_id, payload = resp
                    if can_id == self.response_ecu_id and len(payload) >= 3:
                        if payload[1] == 0x41 and payload[2] == pid:
                            self._last_ecu_resp_time = time.time()
                            config = PIDS_CONFIG.get(pid)
                            if config:
                                data_bytes = payload[3 : 3 + config["bytes_len"]]
                                try:
                                    decoded_value = config["decoder"](data_bytes)
                                    param_name = config["name"]
                                    self._param_timestamps[param_name] = time.time()

                                    with self._lock:
                                        if param_name == "mil_status" and isinstance(decoded_value, dict):
                                            self.telemetry["mil_on"] = decoded_value["mil_on"]
                                            self.telemetry["dtc_count"] = decoded_value["dtc_count"]
                                        else:
                                            self.telemetry[param_name] = decoded_value
                                        self.telemetry["timestamp"] = time.time()
                                except Exception as err:
                                    print(f"[OBDManager] Erro decodificando PID 0x{pid:02X}: {err}")

            # Atualiza alternador / bateria e métricas de viagem
            with self._lock:
                cur_rpm = self.telemetry.get("rpm", 0)
                if cur_rpm > 450:
                    v_osc = 0.08 * math.sin(time.time() * 2)
                    self.telemetry["battery_voltage"] = round(14.2 + v_osc, 1)
                elif cur_rpm > 0:
                    self.telemetry["battery_voltage"] = 12.8
                else:
                    self.telemetry["battery_voltage"] = 12.5

                self.telemetry["battery_voltage_mode"] = "ESTIMADO"
                self.telemetry["battery_voltage_source"] = "Sintético por RPM (Sem ADC Físico no Pino 16)"

                self._update_trip_and_metrics()

            time.sleep(0.005)
