"""
can_adapter.py - Adaptador de Comunicação CAN para Hardware LC_CANable_V2.1 (STM32G431)
Ford Fiesta 2010 1.0 Zetec Rocam
"""

import time
import math
import random
import serial
import serial.tools.list_ports
from abc import ABC, abstractmethod
from typing import Optional, Tuple, List
from .obd_pids import OBD_BROADCAST_REQ_ID, OBD_ECU_ENGINE_REQ_ID, OBD_ECU_ENGINE_RESP_ID


class BaseCANAdapter(ABC):
    @abstractmethod
    def open(self) -> bool:
        pass

    @abstractmethod
    def close(self) -> None:
        pass

    @abstractmethod
    def send(self, arbitration_id: int, data: bytes) -> bool:
        pass

    @abstractmethod
    def recv(
        self, timeout: float = 0.05, target_id: Optional[int] = None
    ) -> Optional[Tuple[int, bytes]]:
        pass

    def clear_rx_buffer(self) -> None:
        pass

    def get_last_fuel_level(self) -> Optional[float]:
        return None

    def get_engine_torque_nm(self) -> float:
        """Retorna o torque indicado do motor em Nm (leitura direta via CAN ID 0x422)."""
        return 0.0

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        pass

    @property
    def connection_info(self) -> str:
        return "Desconectado"


class CANableSLCANAdapter(BaseCANAdapter):
    """
    Driver de Produção para o módulo LC_CANable_V2.1 (STM32G431).
    Opera em modo SLCAN (Lawicel) em porta Serial CDC USB a 500 kbps (High Speed CAN Ford).
    """

    def __init__(self, port: str = "AUTO", baudrate: int = 115200, can_bitrate: int = 500000):
        self.requested_port = port
        self.actual_port: Optional[str] = None
        self.baudrate = baudrate
        self.can_bitrate = can_bitrate
        self.ser: Optional[serial.Serial] = None
        self._rx_buffer = bytearray()
        self._last_rx_time = 0.0
        self._tx_count = 0
        self._rx_count = 0
        self.last_fuel_level_pct: Optional[float] = None
        # Engenharia Reversa Ford HS-CAN: Torque Indicado do Motor (ID 0x422 Byte 6 em Nm)
        self.engine_torque_nm: float = 0.0
        self.last_torque_timestamp: float = 0.0

    @staticmethod
    def find_canable_port() -> Optional[str]:
        """Procura rigorosamente pela porta COM associada ao STM32/CANable."""
        ports = list(serial.tools.list_ports.comports())
        if not ports:
            return None

        # Nível 1: VID:PID Oficial do CANable STM32G431 (16D0:117E)
        for p in ports:
            hwid = (p.hwid or "").lower()
            if "16d0:117e" in hwid:
                return p.device

        # Nível 2: Descrições nominais de firmware CANable / CandleLight / slcan
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if any(k in desc or k in hwid for k in ["canable", "candle", "slcan", "cantact"]):
                return p.device

        # Nível 3: Microcontroladores STM32 em CDC
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if "0483:5740" in hwid or ("stm32" in desc and "bluetooth" not in desc):
                return p.device

        # Nível 4: Conversores seriais gerais USB (somente se não forem Bluetooth e responderem a probe)
        for p in ports:
            desc = (p.description or "").lower()
            hwid = (p.hwid or "").lower()
            if "bluetooth" not in desc and "bth" not in desc:
                try:
                    with serial.Serial(p.device, 115200, timeout=0.06) as s_probe:
                        s_probe.write(b"C\r")
                        time.sleep(0.015)
                        return p.device
                except Exception:
                    continue

        return None

    def open(self) -> bool:
        if self.ser and self.ser.is_open:
            return True

        target_port = self.requested_port
        if target_port == "AUTO" or not target_port:
            detected = self.find_canable_port()
            if not detected:
                print("[CANable] Nenhuma porta COM física compatível encontrada no sistema.")
                return False
            target_port = detected

        try:
            print(f"[CANable] Abrindo porta serial {target_port} a {self.baudrate} baud...")
            self.ser = serial.Serial(
                port=target_port,
                baudrate=self.baudrate,
                timeout=0.015,
                write_timeout=0.03,
            )
            self.actual_port = target_port
            time.sleep(0.08)

            # Sequência oficial SLCAN:
            # 1. Fecha canal CAN se estiver aberto
            self.ser.write(b"C\r")
            time.sleep(0.02)
            # 2. Configura velocidade do barramento CAN:
            # S6 = 500 kbps (Barramento padrão OBD-II do Fiesta Rocam)
            # S5 = 250 kbps
            # S4 = 125 kbps
            bitrate_cmd = b"S6\r" if self.can_bitrate == 500000 else b"S5\r"
            self.ser.write(bitrate_cmd)
            time.sleep(0.02)
            # 3. Abre canal CAN (O = Open)
            self.ser.write(b"O\r")
            time.sleep(0.02)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()

            print(f"[CANable] Barramento CAN Aberto com sucesso a {self.can_bitrate // 1000} kbps!")
            return True
        except Exception as e:
            print(f"[CANable] Falha na abertura da porta {target_port}: {e}")
            self.ser = None
            self.actual_port = None
            return False

    def close(self) -> None:
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"C\r")
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self.actual_port = None

    @property
    def is_connected(self) -> bool:
        return self.ser is not None and self.ser.is_open

    @property
    def connection_info(self) -> str:
        if self.is_connected and self.actual_port:
            return f"CANable 500k ({self.actual_port})"
        return "Desconectado"

    @property
    def last_rx_timestamp(self) -> float:
        return self._last_rx_time

    def send(self, arbitration_id: int, data: bytes) -> bool:
        if not self.is_connected or not self.ser:
            return False

        # Formato SLCAN 11-bit standard: tiiildd...
        # Exemplo: t7DF802010C00000000\r
        hex_id = f"{arbitration_id:03X}"
        hex_len = f"{len(data):1X}"
        hex_data = data.hex().upper()
        cmd = f"t{hex_id}{hex_len}{hex_data}\r".encode("ascii")

        try:
            self.ser.write(cmd)
            self._tx_count += 1
            return True
        except Exception as err:
            print(f"[CANable] Erro ao transmitir quadro CAN: {err}")
            return False

    def _parse_and_handle_frame(self, line: str) -> Optional[Tuple[int, bytes]]:
        """
        Interpreta quadros SLCAN standard 't' (11-bit) ou estendidos 'T' (29-bit)
        e atualiza variáveis de engenharia reversa passiva (0x430 boia e 0x422 carga/torque/AC).
        """
        if not line or len(line) < 5:
            return None

        is_std = line.startswith("t")
        is_ext = line.startswith("T")
        if not (is_std or is_ext):
            return None

        try:
            if is_std:
                can_id = int(line[1:4], 16)
                dlc = int(line[4], 16)
                payload_hex = line[5 : 5 + (dlc * 2)]
            else:
                can_id = int(line[1:9], 16)
                dlc = int(line[9], 16)
                payload_hex = line[10 : 10 + (dlc * 2)]

            if len(payload_hex) != dlc * 2:
                return None

            payload = bytes.fromhex(payload_hex)
            self._rx_count += 1
            self._last_rx_time = time.time()

            # Engenharia Reversa Ford: Nível de Combustível da Boia (ID 0x430 Byte 0)
            if can_id == 0x430 and len(payload) >= 1:
                b0 = payload[0]
                self.last_fuel_level_pct = round(b0 / 2.55, 1)

            # Engenharia Reversa Ford HS-CAN: Frame 0x422
            # Byte 0: Demanda instantânea de aceleração / carga do motor (0x00=marcha lenta a 0xF4=aceleração máx)
            #         No Ford Zetec Rocam 1.0 (73 cv / 93 Nm máx a 4750 RPM):
            #         - Marcha lenta com motor ligado: ~8 a 10 Nm
            #         - Aceleração: progride linearmente até o pico de 93 Nm (9.5 kgfm)
            # Byte 5: Bit 3 / Status do Ar-Condicionado (0x47=desligado, 0x48=ligado)
            # Byte 6: Carga/pressão do Ar-Condicionado (0x00=desligado, 0x07 a 0x0A = 7 a 10 bar)
            elif can_id == 0x422 and len(payload) >= 1:
                b0 = payload[0]
                self.engine_load_pct = round((b0 / 255.0) * 100.0, 1)
                if b0 > 0:
                    self.engine_torque_nm = round(8.0 + (85.0 * (b0 / 255.0)), 1)
                else:
                    self.engine_torque_nm = 8.0
                self.last_torque_timestamp = time.time()

                if len(payload) >= 7:
                    b5 = payload[5]
                    b6 = payload[6]
                    self.ac_clutch_engaged = bool(b5 == 0x48 or (b5 & 0x08))
                    self.ac_pressure_bar = float(b6)

            return can_id, payload
        except Exception:
            return None

    def clear_rx_buffer(self) -> None:
        """
        Drena a serial processando quadros espontâneos em background (ex: 0x422 e 0x430)
        em vez de descartar os bytes cegamente, preparando a fila limpa para OBD.
        """
        if self.ser and self.ser.is_open:
            try:
                avail = self.ser.in_waiting
                if avail > 0:
                    chunk = self.ser.read(avail)
                    for byte in chunk:
                        if byte in (13, 10):
                            if self._rx_buffer:
                                line = self._rx_buffer.decode("ascii", errors="ignore").strip()
                                self._rx_buffer.clear()
                                self._parse_and_handle_frame(line)
                        else:
                            self._rx_buffer.append(byte)
            except Exception:
                pass
        self._rx_buffer.clear()

    def recv(
        self, timeout: float = 0.04, target_id: Optional[int] = None
    ) -> Optional[Tuple[int, bytes]]:
        if not self.is_connected or not self.ser:
            return None

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                available = self.ser.in_waiting
                if available > 0:
                    raw_chunk = self.ser.read(available)
                    for byte in raw_chunk:
                        if byte in (13, 10):  # \r ou \n
                            if self._rx_buffer:
                                line = self._rx_buffer.decode("ascii", errors="ignore").strip()
                                self._rx_buffer.clear()
                                frame = self._parse_and_handle_frame(line)
                                if frame:
                                    can_id, payload = frame
                                    if target_id is not None and can_id != target_id:
                                        continue
                                    return can_id, payload
                        else:
                            self._rx_buffer.append(byte)
                else:
                    time.sleep(0.001)
            except Exception as e:
                print(f"[CANable] Erro na recepção serial: {e}")
                return None

        return None

    def get_last_fuel_level(self) -> Optional[float]:
        return self.last_fuel_level_pct

    def get_engine_torque_nm(self) -> float:
        return self.engine_torque_nm


class SimulatedFallbackAdapter(BaseCANAdapter):
    """
    Modo de demonstração suave ativado automaticamente apenas se o cabo não estiver conectado,
    para permitir visualizar a tela final em bancada.
    """

    def __init__(self):
        self._connected = False
        self._last_pid_requested = None
        self._start_time = time.time()

    def open(self) -> bool:
        self._connected = True
        self._start_time = time.time()
        return True

    def close(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def connection_info(self) -> str:
        return "Demonstração (Sem Hardware)"

    def get_last_fuel_level(self) -> Optional[float]:
        return 49.0

    def get_engine_torque_nm(self) -> float:
        # Em simulação, calcula torque proporcional à aceleração virtual
        return 22.0

    def send(self, arbitration_id: int, data: bytes) -> bool:
        if not self._connected or len(data) < 3:
            return False
        if arbitration_id in (OBD_BROADCAST_REQ_ID, OBD_ECU_ENGINE_REQ_ID):
            mode = data[1]
            pid = data[2]
            if mode == 0x01:
                self._last_pid_requested = pid
                return True
        return False

    def recv(
        self, timeout: float = 0.05, target_id: Optional[int] = None
    ) -> Optional[Tuple[int, bytes]]:
        if not self._connected or self._last_pid_requested is None:
            return None

        pid = self._last_pid_requested
        self._last_pid_requested = None

        elapsed = time.time() - self._start_time
        # Simulação suave de um Fiesta andando normalmente em trânsito
        t = elapsed % 40.0
        if t < 10.0:
            sim_rpm = int(850 + (t / 10.0) * 2200)
            sim_speed = int((t / 10.0) * 35)
            sim_map = int(35 + (t / 10.0) * 30)
            sim_throttle = 15.0 + (t / 10.0) * 20.0
        elif t < 25.0:
            sim_rpm = int(2400 + math.sin(t * 0.5) * 500)
            sim_speed = int(60 + math.sin(t * 0.5) * 15)
            sim_map = 48
            sim_throttle = 22.0
        else:
            p = (40.0 - t) / 15.0
            sim_rpm = int(850 + p * 2000)
            sim_speed = int(p * 55)
            sim_map = 28
            sim_throttle = 0.0

        resp_data = bytearray([0x00] * 8)

        if pid == 0x0C:  # RPM
            raw_rpm = int(sim_rpm * 4)
            resp_data[0] = 0x04
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = (raw_rpm >> 8) & 0xFF
            resp_data[4] = raw_rpm & 0xFF
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        elif pid == 0x0D:  # Speed
            resp_data[0] = 0x03
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = max(0, min(255, sim_speed))
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        elif pid == 0x11:  # Throttle
            val = int((sim_throttle * 255.0) / 100.0)
            resp_data[0] = 0x03
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = max(0, min(255, val))
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        elif pid == 0x0B:  # MAP
            resp_data[0] = 0x03
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = max(10, min(255, sim_map))
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        elif pid == 0x05:  # Temp Água (89°C normal do Fiesta)
            resp_data[0] = 0x03
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = 89 + 40
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        elif pid == 0x42:  # Bateria (14.2V alternador)
            raw_v = int(14.22 * 1000)
            resp_data[0] = 0x04
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = (raw_v >> 8) & 0xFF
            resp_data[4] = raw_v & 0xFF
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        elif pid == 0x2F:  # Combustível
            resp_data[0] = 0x03
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = int((65.0 * 255.0) / 100.0)
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        elif pid == 0x0F:  # IAT (28°C)
            resp_data[0] = 0x03
            resp_data[1] = 0x41
            resp_data[2] = pid
            resp_data[3] = 28 + 40
            return OBD_ECU_ENGINE_RESP_ID, bytes(resp_data)

        return None
