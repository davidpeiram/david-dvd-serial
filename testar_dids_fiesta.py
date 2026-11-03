"""
testar_dids_fiesta.py - Scanner de Identificadores de Dados UDS (Service 22)
Ford Fiesta 2010 Sedan 1.0 Flex Zetec Rocam
Hardware: LC_CANABLE_V2.1 (STM32G431) em modo SLCAN a 500 kbps

Este script envia requisições de Diagnóstico Estendido Ford (UDS Service 0x22 - ReadDataByIdentifier)
baseado no banco de dados aberto da Pelican / OBDb (Open On-Board Diagnostics Database).
Objetivo: Descobrir quais DIDs proprietários a ECU Ford EEC-VI (0x7E0), o Painel (0x720)
e o Módulo de Carroceria (0x726) respondem no Fiesta 2010.
"""

import os
import sys
import time
import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple

import serial
import serial.tools.list_ports

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

SESSION_TS = time.strftime("%Y-%m-%d_%H-%M-%S")
LOG_JSON_FILE = LOG_DIR / f"scan_dids_{SESSION_TS}.json"
LOG_TXT_FILE = LOG_DIR / f"scan_dids_{SESSION_TS}.txt"

# Tabela de NRCs UDS (Negative Response Codes)
NRC_NAMES = {
    0x10: "GeneralReject",
    0x11: "ServiceNotSupported",
    0x12: "SubFunctionNotSupported",
    0x13: "IncorrectMessageLengthOrInvalidFormat",
    0x22: "ConditionsNotCorrect",
    0x31: "RequestOutOfRange (DID não suportado)",
    0x33: "SecurityAccessDenied",
    0x78: "ResponsePending (ECU ocupada)",
}

# Lista prioritária de DIDs candidatos extraídos da Pelican / OBDb para o Ford Fiesta
CANDIDATE_DIDS = [
    # =========================================================================
    # 1. MOTOR / INJEÇÃO ELETRÔNICA (PCM Ford EEC-VI: Requisição 0x7E0 -> Resposta 0x7E8)
    # =========================================================================
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x1172,
        "name": "Tensão Real da Bateria 12V",
        "unit": "V",
        "decoder": lambda d: round(int.from_bytes(d, "big") / 100.0, 2) if len(d) >= 2 else (round(d[0] / 10.0, 1) if len(d) == 1 else None),
        "desc": "Tensão medida internamente pela ECU (elimina necessidade de ADC físico no pino 16)",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x0334,
        "name": "Temp. Cabeçote CHT (Cylinder Head Temp)",
        "unit": "°C",
        "decoder": lambda d: d[0] - 40 if len(d) >= 1 else None,
        "desc": "Sensor metálico CHT do motor Rocam (parafusado no cabeçote de alumínio)",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x051D,
        "name": "Temp. Cabeçote CHT (Alternativa 16-bit)",
        "unit": "°C",
        "decoder": lambda d: round((int.from_bytes(d[:2], "big") / 10.0) - 40.0, 1) if len(d) >= 2 else None,
        "desc": "Leitura de alta resolução do CHT",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x1310,
        "name": "Temperatura do Óleo do Motor",
        "unit": "°C",
        "decoder": lambda d: d[0] - 40 if len(d) >= 1 else None,
        "desc": "Temperatura de óleo do motor",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x0393,
        "name": "Pressão do Gás do Ar-Condicionado (psi)",
        "unit": "psi",
        "decoder": lambda d: round(int.from_bytes(d[:2], "big") * (245251.0 / 845473.0), 1) if len(d) >= 2 else None,
        "desc": "Pressão de linha do gás R134a em psi",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0xFD18,
        "name": "Pressão do Ar-Condicionado (kPa)",
        "unit": "kPa",
        "decoder": lambda d: round(d[0] * 12.156863, 1) if len(d) >= 1 else None,
        "desc": "Pressão do compressor em kPa",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x099B,
        "name": "Estado da Embreagem do Compressor A/C",
        "unit": "Estado",
        "decoder": lambda d: "LIGADO (Acoplado)" if d[0] == 1 else "DESLIGADO" if len(d) >= 1 else None,
        "desc": "Flag binária se a embreagem do compressor está acoplada",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0xF462,
        "name": "Porcentagem de Torque Atual do Motor",
        "unit": "%",
        "decoder": lambda d: d[0] - 125 if len(d) >= 1 else None,
        "desc": "Torque instantâneo calculado pela ECU em percentual (-125 a +125%)",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0xF463,
        "name": "Torque de Referência do Motor",
        "unit": "Nm",
        "decoder": lambda d: int.from_bytes(d[:2], "big") if len(d) >= 2 else None,
        "desc": "Constante de torque nominal calibrada no mapa da ECU",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x03AF,
        "name": "Solicitação de Torque",
        "unit": "%",
        "decoder": lambda d: round((d[0] / 255.0) * 100.0, 1) if len(d) >= 1 else None,
        "desc": "Demanda de torque pelo pedal do acelerador",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0xF45E,
        "name": "Taxa de Consumo de Combustível (Fuel Rate)",
        "unit": "L/h",
        "decoder": lambda d: round(int.from_bytes(d[:2], "big") / 20.0, 2) if len(d) >= 2 else None,
        "desc": "Vazão de combustível calculada pela injeção",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x168B,
        "name": "Tempo de Injeção (Pulse Width)",
        "unit": "ms",
        "decoder": lambda d: round(int.from_bytes(d[:2], "big") / 1000.0, 3) if len(d) >= 2 else None,
        "desc": "Largura de pulso dos bicos injetores",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x1127,
        "name": "Pressão Barométrica Local (BARO)",
        "unit": "kPa",
        "decoder": lambda d: d[0] if len(d) >= 1 else None,
        "desc": "Pressão atmosférica medida na partida",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x0304,
        "name": "Tensão Comandada do Alternador (Smart Charge)",
        "unit": "V",
        "decoder": lambda d: round(d[0] / 10.0, 1) if len(d) >= 1 else None,
        "desc": "Tensão regulada dinamicamente pelo PCM para carregar a bateria",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x03B9,
        "name": "Comando da Ventoinha do Radiador",
        "unit": "%",
        "decoder": lambda d: round((d[0] / 255.0) * 100.0, 1) if len(d) >= 1 else None,
        "desc": "Duty cycle do eletroventilador de arrefecimento",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0x16C1,
        "name": "Nível de Combustível (PCM)",
        "unit": "%",
        "decoder": lambda d: round((d[0] / 255.0) * 100.0, 1) if len(d) >= 1 else None,
        "desc": "Porcentagem da boia de combustível lida pela injeção",
    },
    {
        "module": "PCM (Motor)",
        "tx_id": 0x7E0,
        "rx_id": 0x7E8,
        "did": 0xF4A6,
        "name": "Hodômetro Gravado no PCM",
        "unit": "km",
        "decoder": lambda d: round(int.from_bytes(d[:4], "big") / 10.0, 1) if len(d) >= 4 else None,
        "desc": "Quilometragem total registrada na memória da ECU",
    },

    # =========================================================================
    # 2. PAINEL DE INSTRUMENTOS (Cluster IPC: Requisição 0x720 -> Resposta 0x728)
    # =========================================================================
    {
        "module": "Painel (Cluster IPC)",
        "tx_id": 0x720,
        "rx_id": 0x728,
        "did": 0x404C,
        "name": "Hodômetro Total do Painel (Odometer)",
        "unit": "km",
        "decoder": lambda d: round(int.from_bytes(d[:3], "big") / 10.0, 1) if len(d) >= 3 else None,
        "desc": "Quilometragem real exibida no display digital do painel",
    },
    {
        "module": "Painel (Cluster IPC)",
        "tx_id": 0x720,
        "rx_id": 0x728,
        "did": 0x6180,
        "name": "Hodômetro do Painel (Alternativa 6180)",
        "unit": "km",
        "decoder": lambda d: round(int.from_bytes(d[:3], "big") / 10.0, 1) if len(d) >= 3 else None,
        "desc": "Hodômetro variante Ford",
    },
    {
        "module": "Painel (Cluster IPC)",
        "tx_id": 0x720,
        "rx_id": 0x728,
        "did": 0xDD01,
        "name": "Hodômetro Parcial (Trip Distance)",
        "unit": "km",
        "decoder": lambda d: round(int.from_bytes(d[:3], "big") / 10.0, 1) if len(d) >= 3 else None,
        "desc": "Distância da viagem parcial no painel",
    },
    {
        "module": "Painel (Cluster IPC)",
        "tx_id": 0x720,
        "rx_id": 0x728,
        "did": 0x6185,
        "name": "Nível de Combustível no Ponteiro do Painel",
        "unit": "%",
        "decoder": lambda d: round((d[0] / 255.0) * 100.0, 1) if len(d) >= 1 else None,
        "desc": "Valor filtrado enviado para o ponteiro de combustível",
    },

    # =========================================================================
    # 3. MÓDULO DE CARROCERIA / CONFORTO (BCM / GEM: Requisição 0x726 -> Resposta 0x72E)
    # =========================================================================
    {
        "module": "Carroceria (BCM)",
        "tx_id": 0x726,
        "rx_id": 0x72E,
        "did": 0xC150,
        "name": "Status das Portas (Door Ajar)",
        "unit": "Bitmask",
        "decoder": lambda d: f"0x{d.hex().upper()}" if len(d) >= 1 else None,
        "desc": "Interruptores de portas abertas (Motorista / Passageiro / Traseiras)",
    },
    {
        "module": "Carroceria (BCM)",
        "tx_id": 0x726,
        "rx_id": 0x72E,
        "did": 0xC154,
        "name": "Sensor do Capô (Hood Ajar)",
        "unit": "Estado",
        "decoder": lambda d: "ABERTO" if d[0] == 1 else "FECHADO" if len(d) >= 1 else None,
        "desc": "Interruptor do capô do motor",
    },
    {
        "module": "Carroceria (BCM)",
        "tx_id": 0x726,
        "rx_id": 0x72E,
        "did": 0xC259,
        "name": "Status das Travas Elétricas",
        "unit": "Estado",
        "decoder": lambda d: "TRAVADO" if d[0] == 2 else "DESTRAVADO" if len(d) >= 1 else None,
        "desc": "Estado de travamento das fechaduras",
    },
    {
        "module": "Carroceria (BCM)",
        "tx_id": 0x726,
        "rx_id": 0x72E,
        "did": 0x407E,
        "name": "Iluminação Externa (Faróis/Lanternas)",
        "unit": "Bitmask",
        "decoder": lambda d: f"0x{d.hex().upper()}" if len(d) >= 1 else None,
        "desc": "Estado dos faróis e lanternas",
    },
    {
        "module": "Carroceria (BCM)",
        "tx_id": 0x726,
        "rx_id": 0x72E,
        "did": 0x402A,
        "name": "Tensão da Bateria no BCM",
        "unit": "V",
        "decoder": lambda d: round((d[0] / 20.0) + 6.0, 2) if len(d) >= 1 else None,
        "desc": "Tensão de alimentação medida na caixa de fusíveis / BCM",
    },
]


def detectar_porta() -> Optional[str]:
    """Identifica estritamente a porta serial do CANable."""
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None
    for p in ports:
        hwid = (p.hwid or "").lower()
        if "16d0:117e" in hwid:
            return p.device
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ["canable", "candle", "slcan", "stm32"]):
            return p.device
    return None


class UDSScanner:
    def __init__(self, port: str):
        self.port = port
        self.ser: Optional[serial.Serial] = None
        self._rx_buf = bytearray()

    def open(self) -> bool:
        try:
            self.ser = serial.Serial(self.port, baudrate=115200, timeout=0.04, write_timeout=0.04)
            time.sleep(0.08)
            self.ser.write(b"C\r")
            time.sleep(0.02)
            self.ser.write(b"S6\r")  # 500 kbps HS-CAN
            time.sleep(0.02)
            self.ser.write(b"O\r")   # Open
            time.sleep(0.02)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            return True
        except Exception as e:
            print(f"[-] Erro ao abrir porta serial {self.port}: {e}")
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"C\r")
                self.ser.close()
            except Exception:
                pass

    def send_frame(self, can_id: int, payload: bytes) -> bool:
        if not self.ser:
            return False
        cmd = f"t{can_id:03X}{len(payload):1X}{payload.hex().upper()}\r".encode("ascii")
        try:
            self.ser.write(cmd)
            return True
        except Exception:
            return False

    def recv_frame(self, target_id: int, timeout: float = 0.06) -> Optional[bytes]:
        if not self.ser:
            return None
        deadline = time.time() + timeout
        while time.time() < deadline:
            avail = self.ser.in_waiting
            if avail > 0:
                chunk = self.ser.read(avail)
                for b in chunk:
                    if b in (13, 10):
                        if self._rx_buf:
                            line = self._rx_buf.decode("ascii", errors="ignore").strip()
                            self._rx_buf.clear()
                            if line.startswith("t") and len(line) >= 5:
                                try:
                                    cid = int(line[1:4], 16)
                                    dlc = int(line[4], 16)
                                    payload = bytes.fromhex(line[5 : 5 + (dlc * 2)])
                                    if cid == target_id:
                                        return payload
                                except ValueError:
                                    pass
                    else:
                        self._rx_buf.append(b)
            else:
                time.sleep(0.001)
        return None

    def query_did(self, tx_id: int, rx_id: int, did: int, timeout: float = 0.08) -> Tuple[str, Optional[bytes], Optional[str], float]:
        """
        Envia requisição UDS Service 22 para um DID específico e trata respostas:
        - Single Frame positiva (0x62)
        - Multi-frame positiva com controle de fluxo ISO-TP
        - Resposta negativa (NRC 0x7F)
        - Timeout / Sem resposta
        """
        did_h = (did >> 8) & 0xFF
        did_l = did & 0xFF
        req = bytes([0x03, 0x22, did_h, did_l, 0x00, 0x00, 0x00, 0x00])

        self.ser.reset_input_buffer()
        self._rx_buf.clear()

        t0 = time.time()
        if not self.send_frame(tx_id, req):
            return "ERROR_TX", None, "Falha ao enviar frame", 0.0

        resp = self.recv_frame(target_id=rx_id, timeout=timeout)
        elapsed_ms = round((time.time() - t0) * 1000.0, 1)

        if not resp:
            return "TIMEOUT", None, "Sem resposta do módulo", elapsed_ms

        # 1. Resposta Negativa (NRC: 0x7F 0x22 <code>)
        if len(resp) >= 4 and resp[1] == 0x7F and resp[2] == 0x22:
            nrc = resp[3]
            nrc_desc = NRC_NAMES.get(nrc, f"NRC 0x{nrc:02X}")
            return "NEGATIVE", None, nrc_desc, elapsed_ms

        # 2. Resposta Positiva Single Frame: [0x0X, 0x62, DID_H, DID_L, DADOS...]
        if len(resp) >= 4 and (resp[0] & 0xF0) == 0x00:
            if resp[1] == 0x62 and resp[2] == did_h and resp[3] == did_l:
                data_len = resp[0] & 0x0F
                payload_data = resp[4 : 1 + data_len]
                return "POSITIVE", payload_data, None, elapsed_ms

        # 3. Resposta Positiva Multi-Frame (First Frame: 0x10):
        if len(resp) >= 5 and (resp[0] & 0xF0) == 0x10:
            if resp[2] == 0x62 and resp[3] == did_h and resp[4] == did_l:
                total_len = ((resp[0] & 0x0F) << 8) | resp[1]
                collected_data = bytearray(resp[5:])

                # Envia Flow Control (ContinueToSend, BlockSize=0, SeparationTime=0)
                fc_frame = bytes([0x30, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
                self.send_frame(tx_id, fc_frame)

                # Coleta Consecutive Frames (0x2X)
                expected_seq = 1
                cf_deadline = time.time() + 0.15
                while len(collected_data) < (total_len - 3) and time.time() < cf_deadline:
                    cf = self.recv_frame(target_id=rx_id, timeout=0.03)
                    if cf and (cf[0] & 0xF0) == 0x20:
                        collected_data.extend(cf[1:])
                        expected_seq = (expected_seq + 1) & 0x0F

                elapsed_ms = round((time.time() - t0) * 1000.0, 1)
                final_data = bytes(collected_data[: total_len - 3])
                return "POSITIVE_MULTIFRAME", final_data, None, elapsed_ms

        return "UNKNOWN_RESPONSE", resp, f"Frame inesperado: {resp.hex()}", elapsed_ms


def main():
    os.system("")  # Habilita cores ANSI no Windows 10/11
    print("=" * 76)
    print("   SCANNER UDS FORD SERVICE 22 (DID EXPLORER) - FIESTA ROCAM 1.0")
    print("   Investigação de Parâmetros Avançados (Pelican / OBDb / Ford UDS)")
    print("=" * 76)

    porta = detectar_porta()
    if not porta:
        print("\n[-] Nenhuma porta CANable V2.1 identificada.")
        print("    Certifique-se de conectar a CANable na USB do computador.")
        input("\nPressione Enter para sair...")
        return

    print(f"[*] Porta identificada: {porta}")
    print(f"[*] Conectando ao barramento HS-CAN a 500 kbps...")

    scanner = UDSScanner(porta)
    if not scanner.open():
        input("\nPressione Enter para sair...")
        return

    print(f"[+] Conexão estabelecida com sucesso na porta {porta}!")
    print(f"[*] Total de DIDs a testar: {len(CANDIDATE_DIDS)}")
    print(f"[*] Logs de auditoria serão salvos em: logs/{LOG_JSON_FILE.name}")
    print("\nIniciando varredura direcionada (PCM 0x7E0, Cluster 0x720, BCM 0x726)...")
    print("-" * 76)
    print(f"  {'DID':<8} | {'MÓDULO':<18} | {'NOME DO SINAL':<34} | STATUS")
    print("-" * 76)

    confirmed_list = []
    results_dict = {
        "timestamp": SESSION_TS,
        "car": "Ford Fiesta 2010 Sedan 1.0 Zetec Rocam",
        "total_tested": len(CANDIDATE_DIDS),
        "dids_confirmed": [],
        "dids_not_supported": [],
        "dids_timeout": [],
    }

    txt_lines = [
        f"Relatório de Diagnóstico UDS Ford (Service 22) - Fiesta 2010",
        f"Data da Varredura: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Porta COM: {porta} | Baudrate CAN: 500 kbps",
        "=" * 76,
    ]

    try:
        for idx, item in enumerate(CANDIDATE_DIDS, 1):
            tx = item["tx_id"]
            rx = item["rx_id"]
            did = item["did"]
            name = item["name"]
            mod = item["module"]
            unit = item["unit"]
            decoder = item["decoder"]

            did_str = f"0x{did:04X}"
            status, raw_bytes, err_msg, ms = scanner.query_did(tx, rx, did)

            if status in ("POSITIVE", "POSITIVE_MULTIFRAME"):
                decoded_val = None
                try:
                    if raw_bytes is not None:
                        decoded_val = decoder(raw_bytes)
                except Exception as e:
                    decoded_val = f"Erro decode: {e}"

                val_display = f"{decoded_val} {unit}" if decoded_val is not None else "OK (sem decoder)"
                raw_hex = raw_bytes.hex().upper() if raw_bytes else ""
                print(f"  \033[92m{did_str:<8}\033[0m | {mod:<18} | {name:<34} | \033[92m✅ {val_display:<18} ({ms}ms)\033[0m")

                entry = {
                    "did_hex": did_str,
                    "did_int": did,
                    "module": mod,
                    "tx_id": f"0x{tx:03X}",
                    "rx_id": f"0x{rx:03X}",
                    "name": name,
                    "raw_hex": raw_hex,
                    "decoded_value": decoded_val,
                    "unit": unit,
                    "response_time_ms": ms,
                    "description": item["desc"],
                }
                confirmed_list.append(entry)
                results_dict["dids_confirmed"].append(entry)
                txt_lines.append(f"[CONFIRMADO] {did_str} ({mod}): {name} = {val_display} [RAW: {raw_hex}] em {ms}ms")

            elif status == "NEGATIVE":
                print(f"  \033[93m{did_str:<8}\033[0m | {mod:<18} | {name:<34} | \033[93m⚠️ NRC: {err_msg}\033[0m")
                results_dict["dids_not_supported"].append({
                    "did": did_str,
                    "module": mod,
                    "name": name,
                    "nrc": err_msg,
                    "ms": ms,
                })
                txt_lines.append(f"[NÃO SUPORTADO] {did_str} ({mod}): {name} -> {err_msg}")

            else:  # TIMEOUT / UNKNOWN
                print(f"  \033[90m{did_str:<8}\033[0m | {mod:<18} | {name:<34} | \033[90m❌ Sem Resposta (Timeout)\033[0m")
                results_dict["dids_timeout"].append({
                    "did": did_str,
                    "module": mod,
                    "name": name,
                    "ms": ms,
                })
                txt_lines.append(f"[TIMEOUT] {did_str} ({mod}): {name}")

            time.sleep(0.015)  # Pausa entre comandos para não sobrecarregar barramento

    except KeyboardInterrupt:
        print("\n\n[*] Varredura interrompida pelo usuário.")
    finally:
        scanner.close()

    # Salva arquivos de log
    with open(LOG_JSON_FILE, "w", encoding="utf-8") as f_json:
        json.dump(results_dict, f_json, indent=2, ensure_ascii=False)

    with open(LOG_TXT_FILE, "w", encoding="utf-8") as f_txt:
        f_txt.write("\n".join(txt_lines) + "\n")

    # Resumo final
    print("\n" + "=" * 76)
    print("   RESUMO DA VARREDURA UDS (SERVICE 22) NO FORD FIESTA")
    print("=" * 76)
    print(f"  Total de DIDs Testados:     {len(CANDIDATE_DIDS)}")
    print(f"  \033[92mDIDs Confirmados (Sucesso):  {len(confirmed_list)}\033[0m")
    print(f"  \033[93mDIDs Não Suportados (NRC):   {len(results_dict['dids_not_supported'])}\033[0m")
    print(f"  \033[90mDIDs sem Resposta (Timeout): {len(results_dict['dids_timeout'])}\033[0m")
    print("-" * 76)

    if confirmed_list:
        print("\n🎉 DIDs DESCOBERTOS E PRONTOS PARA INTEGRAÇÃO:")
        for c in confirmed_list:
            print(f"  • {c['did_hex']} ({c['module']}): {c['name']} -> {c['decoded_value']} {c['unit']} (Resp: {c['response_time_ms']}ms)")
    else:
        print("\nℹ️ Nenhum DID UDS respondeu nesta sessão.")
        print("  Dica: Certifique-se de que a ignição do Fiesta esteja ligada (KOEO ou motor funcionando).")

    print(f"\n[+] Relatório JSON salvo em: logs/{LOG_JSON_FILE.name}")
    print(f"[+] Relatório Texto salvo em: logs/{LOG_TXT_FILE.name}")
    input("\nPressione Enter para sair...")


if __name__ == "__main__":
    main()
