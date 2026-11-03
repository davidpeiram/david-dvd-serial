"""
obd_pids.py - Definições e decodificadores de PIDs OBD-II (SAE J1979 / ISO 15765-4)
Ford Fiesta 1.0 Zetec Rocam
"""

from typing import Dict, Any, Callable

# CAN IDs padrão para OBD-II
OBD_BROADCAST_REQ_ID = 0x7DF
OBD_ECU_ENGINE_REQ_ID = 0x7E0
OBD_ECU_ENGINE_RESP_ID = 0x7E8


def decode_load(data: bytes) -> float:
    # PID 0x04: Engine Load (0 a 100%)
    return round((data[0] * 100.0) / 255.0, 1)


def decode_coolant_temp(data: bytes) -> int:
    # PID 0x05: Coolant Temp (-40 a 215 °C)
    return int(data[0] - 40)


def decode_map(data: bytes) -> int:
    # PID 0x0B: Intake Manifold Absolute Pressure (0 a 255 kPa)
    return int(data[0])


def decode_rpm(data: bytes) -> int:
    # PID 0x0C: Engine RPM (0 a 16383.75 rpm)
    return int(((data[0] * 256) + data[1]) / 4)


def decode_speed(data: bytes) -> int:
    # PID 0x0D: Vehicle Speed (0 a 255 km/h)
    return int(data[0])


def decode_timing_advance(data: bytes) -> float:
    # PID 0x0E: Timing Advance (-64 a 63.5 ° APMS)
    return round((data[0] / 2.0) - 64.0, 1)


def decode_stft(data: bytes) -> float:
    # PID 0x06: Short Term Fuel Trim (-100 a +99.2%)
    return round((data[0] - 128) * 100.0 / 128.0, 1)


def decode_ltft(data: bytes) -> float:
    # PID 0x07: Long Term Fuel Trim (-100 a +99.2%)
    return round((data[0] - 128) * 100.0 / 128.0, 1)


def decode_mil_status(data: bytes) -> Dict[str, Any]:
    # PID 0x01: Monitor status since DTCs cleared
    # Byte A: Bit 7 = MIL (1=luz acesa, 0=apagada), Bits 0-6 = quantidade de DTCs
    mil_on = bool(data[0] & 0x80)
    dtc_count = int(data[0] & 0x7F)
    return {"mil_on": mil_on, "dtc_count": dtc_count}


def decode_iat(data: bytes) -> int:
    # PID 0x0F: Intake Air Temp (-40 a 215 °C)
    return int(data[0] - 40)


def decode_throttle_pos(data: bytes) -> float:
    # PID 0x11: Throttle Position / TPS (0 a 100%)
    return round((data[0] * 100.0) / 255.0, 1)


def decode_fuel_level(data: bytes) -> float:
    # PID 0x2F: Fuel Tank Level Input (0 a 100%)
    return round((data[0] * 100.0) / 255.0, 1)


def decode_battery_voltage(data: bytes) -> float:
    # PID 0x42: Control Module Voltage (0 a 65.535 V)
    return round(((data[0] * 256) + data[1]) / 1000.0, 2)


PIDS_CONFIG: Dict[int, Dict[str, Any]] = {
    0x0C: {
        "name": "rpm",
        "description": "Rotação do Motor",
        "unit": "RPM",
        "bytes_len": 2,
        "decoder": decode_rpm,
        "priority": 1,  # Alta frequência
    },
    0x0D: {
        "name": "speed",
        "description": "Velocidade",
        "unit": "km/h",
        "bytes_len": 1,
        "decoder": decode_speed,
        "priority": 1,
    },
    0x11: {
        "name": "throttle",
        "description": "Posição da Borboleta (TPS)",
        "unit": "%",
        "bytes_len": 1,
        "decoder": decode_throttle_pos,
        "priority": 1,  # Alta frequência para resposta instantânea ao pedal
    },
    0x04: {
        "name": "engine_load",
        "description": "Carga Calculada do Motor",
        "unit": "%",
        "bytes_len": 1,
        "decoder": decode_load,
        "priority": 2,
    },
    0x0B: {
        "name": "map",
        "description": "Pressão Coletor (MAP)",
        "unit": "kPa",
        "bytes_len": 1,
        "decoder": decode_map,
        "priority": 2,
    },
    0x0E: {
        "name": "timing_advance",
        "description": "Ponto de Ignição",
        "unit": "°",
        "bytes_len": 1,
        "decoder": decode_timing_advance,
        "priority": 2,  # Prioridade 2 para acompanhar giro e carga
    },
    0x05: {
        "name": "coolant_temp",
        "description": "Temperatura do Motor",
        "unit": "°C",
        "bytes_len": 1,
        "decoder": decode_coolant_temp,
        "priority": 3,  # Baixa frequência
    },
    0x0F: {
        "name": "intake_temp",
        "description": "Temperatura do Ar Admissão",
        "unit": "°C",
        "bytes_len": 1,
        "decoder": decode_iat,
        "priority": 3,
    },
    0x06: {
        "name": "stft",
        "description": "Ajuste Curto Prazo (STFT)",
        "unit": "%",
        "bytes_len": 1,
        "decoder": decode_stft,
        "priority": 3,
    },
    0x07: {
        "name": "ltft",
        "description": "Ajuste Longo Prazo (LTFT)",
        "unit": "%",
        "bytes_len": 1,
        "decoder": decode_ltft,
        "priority": 3,
    },
    0x01: {
        "name": "mil_status",
        "description": "Luz Injeção e Falhas DTC",
        "unit": "",
        "bytes_len": 4,
        "decoder": decode_mil_status,
        "priority": 4,  # Baixa frequência (a cada ~10-15s)
    },
    0x42: {
        "name": "battery_voltage",
        "description": "Tensão da Bateria",
        "unit": "V",
        "bytes_len": 2,
        "decoder": decode_battery_voltage,
        "priority": 3,
    },
    0x2F: {
        "name": "fuel_level",
        "description": "Nível de Combustível",
        "unit": "%",
        "bytes_len": 1,
        "decoder": decode_fuel_level,
        "priority": 4,
    },
}


def build_obd_request_frame(pid: int, mode: int = 0x01) -> bytes:
    """
    Constrói os 8 bytes de um quadro CAN de requisição OBD-II:
    Byte 0: Comprimento dos dados válidos (0x02)
    Byte 1: Modo (0x01)
    Byte 2: PID
    Bytes 3-7: Padding (0xCC ou 0x55)
    """
    return bytes([0x02, mode, pid, 0xCC, 0xCC, 0xCC, 0xCC, 0xCC])


def decode_dtc(b1: int, b2: int) -> str:
    """Decodifica 2 bytes em código de falha padrão SAE J1979 / ISO 15765 (ex: P0171)."""
    if b1 == 0 and b2 == 0:
        return ""
    type_code = (b1 & 0xC0) >> 6
    letters = {0: "P", 1: "C", 2: "B", 3: "U"}
    prefix = letters.get(type_code, "P")
    d1 = (b1 & 0x30) >> 4
    d2 = b1 & 0x0F
    d3 = (b2 & 0xF0) >> 4
    d4 = b2 & 0x0F
    return f"{prefix}{d1:X}{d2:X}{d3:X}{d4:X}"


def decode_mode_03_dtcs(data: bytes) -> list:
    """Decodifica o payload de resposta do Modo 03 (0x43) em lista de DTCs."""
    dtcs = []
    for i in range(0, len(data) - 1, 2):
        code = decode_dtc(data[i], data[i + 1])
        if code and code not in dtcs:
            dtcs.append(code)
    return dtcs
