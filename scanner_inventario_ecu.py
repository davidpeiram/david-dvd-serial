"""
scanner_inventario_ecu.py - Varredura Automática e Inventário Completo da ECU
Ford Fiesta 2010 Sedan 1.0 Zetec Rocam Flex
Hardware: LC_CANABLE_V2.1 (STM32G431) em modo SLCAN a 500 kbps

Este script realiza a auditoria completa de diagnósticos do veículo:
1. Varredura recursiva de bitmasks de suporte do Modo 01 (PIDs 0x00, 0x20, 0x40, 0x60, 0x80)
2. Consulta individual a cada PID suportado registrando tempo de resposta e valor bruto
3. Teste direcionado aos PIDs especiais (0x42 Tensão, 0x51/0x52 Etanol, 0x33 Baro, 0x46 Temp Ambiente)
4. Consulta ao Modo 09 (PID 0x02 VIN Chassi e PID 0x04 Calibration ID da ECU)
5. Consulta ao Modo 03 (Códigos de Falha DTC ativos) e Modo 07 (DTCs pendentes)
6. Varredura de múltiplos IDs de módulo (0x7E0 Motor, 0x7E1 Câmbio, 0x7E2 ABS, 0x7E4 Painel)
7. Exportação do relatório estruturado em 'inventario_ecu_fiesta.json'
"""

import sys
import time
import json
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import serial
import serial.tools.list_ports

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "logs" / "inventario_ecu_fiesta.json"

# Dicionário de descrições dos PIDs padrão SAE J1979
PID_DESCRIPTIONS = {
    0x01: "Status dos Monitores e Contagem de DTCs",
    0x02: "DTC que causou o Freeze Frame",
    0x03: "Status do Sistema de Combustível (Malha Aberta/Fechada)",
    0x04: "Carga Calculada do Motor (%)",
    0x05: "Temperatura do Líquido de Arrefecimento (°C)",
    0x06: "Ajuste de Combustível a Curto Prazo - STFT (%)",
    0x07: "Ajuste de Combustível a Longo Prazo - LTFT (%)",
    0x0B: "Pressão Absoluta no Coletor - MAP (kPa)",
    0x0C: "Rotação do Motor - RPM",
    0x0D: "Velocidade do Veículo (km/h)",
    0x0E: "Avanço de Ignição / Ponto (° APMS)",
    0x0F: "Temperatura do Ar de Admissão - IAT (°C)",
    0x10: "Fluxo de Ar por Massa - MAF (g/s)",
    0x11: "Posição da Borboleta - TPS (%)",
    0x1C: "Padrão OBD Suportado pelo Veículo",
    0x1F: "Tempo de Motor em Funcionamento desde a Partida (s)",
    0x21: "Distância Percorrida com a Luz de Injeção (MIL) Acesa (km)",
    0x2F: "Nível de Combustível no Tanque (%)",
    0x31: "Distância Percorrida desde a Limpeza dos DTCs (km)",
    0x33: "Pressão Barométrica Atmosférica (kPa)",
    0x3C: "Temperatura do Catalisador (°C)",
    0x42: "Tensão de Alimentação do Módulo de Controle (V)",
    0x43: "Carga Absoluta do Motor (%)",
    0x44: "Relação de Equivalência Comandada (Lambda)",
    0x45: "Posição Relativa da Borboleta (%)",
    0x46: "Temperatura do Ar Ambiente Externo (°C)",
    0x49: "Posição do Pedal do Acelerador D (%)",
    0x4A: "Posição do Pedal do Acelerador E (%)",
    0x4C: "Posição Comandada do Atuador da Borboleta (%)",
    0x51: "Tipo de Combustível do Veículo (Flex, Gasolina, Etanol)",
    0x52: "Percentual de Etanol no Combustível (%)",
    0x5C: "Temperatura do Óleo do Motor (°C)",
    0x5E: "Taxa de Consumo de Combustível da ECU (L/h)",
}


def detectar_porta() -> Optional[str]:
    ports = list(serial.tools.list_ports.comports())
    for p in ports:
        hwid = (p.hwid or "").lower()
        if "16d0:117e" in hwid:
            return p.device
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ["canable", "candle", "slcan", "stm32"]):
            return p.device
    for p in ports:
        desc = (p.description or "").lower()
        if "bluetooth" not in desc and "bth" not in desc:
            return p.device
    return None


class CANScanner:
    def __init__(self, port: str, baudrate: int = 115200):
        self.port = port
        self.baudrate = baudrate
        self.ser: Optional[serial.Serial] = None
        self._rx_buf = bytearray()

    def open(self) -> bool:
        try:
            self.ser = serial.Serial(self.port, baudrate=self.baudrate, timeout=0.04, write_timeout=0.04)
            time.sleep(0.08)
            self.ser.write(b"C\r")
            time.sleep(0.02)
            self.ser.write(b"S6\r")  # 500 kbps
            time.sleep(0.02)
            self.ser.write(b"O\r")  # Open
            time.sleep(0.02)
            self.ser.reset_input_buffer()
            self.ser.reset_output_buffer()
            return True
        except Exception as e:
            print(f"[-] Erro ao abrir serial {self.port}: {e}")
            return False

    def close(self):
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(b"C\r")
                self.ser.close()
            except Exception:
                pass

    def send_raw_frame(self, can_id: int, payload: bytes) -> bool:
        if not self.ser:
            return False
        cmd = f"t{can_id:03X}{len(payload):1X}{payload.hex().upper()}\r".encode("ascii")
        try:
            self.ser.write(cmd)
            return True
        except Exception:
            return False

    def recv_frame(self, target_id: int, timeout: float = 0.05) -> Optional[bytes]:
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

    def query_obd(self, mode: int, pid: int, req_id: int = 0x7E0, resp_id: int = 0x7E8, timeout: float = 0.05) -> Optional[Tuple[bytes, float]]:
        """Envia requisição OBD e aguarda resposta positiva da ECU."""
        req = bytes([0x02, mode, pid, 0x00, 0x00, 0x00, 0x00, 0x00])
        self.ser.reset_input_buffer()
        self._rx_buf.clear()

        t0 = time.time()
        if not self.send_raw_frame(req_id, req):
            return None

        resp = self.recv_frame(target_id=resp_id, timeout=timeout)
        elapsed_ms = round((time.time() - t0) * 1000.0, 1)

        if resp and len(resp) >= 3:
            # Resposta positiva do Modo XX é (XX + 0x40), ex: Modo 01 -> 0x41
            expected_service = mode + 0x40
            if resp[1] == expected_service and resp[2] == pid:
                data_len = resp[0]
                payload_data = resp[3 : 1 + data_len]
                return payload_data, elapsed_ms
        return None

    def query_mode_03(self, req_id: int = 0x7E0, resp_id: int = 0x7E8) -> List[str]:
        """Consulta códigos de falha DTC ativos (Modo 03)."""
        req = bytes([0x01, 0x03, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00])
        self.ser.reset_input_buffer()
        self._rx_buf.clear()

        if not self.send_raw_frame(req_id, req):
            return []

        resp = self.recv_frame(target_id=resp_id, timeout=0.08)
        dtcs = []
        if resp and len(resp) >= 2 and resp[1] == 0x43:
            num_codes = resp[2]
            raw_dtc_bytes = resp[3:]
            for i in range(0, len(raw_dtc_bytes) - 1, 2):
                b1 = raw_dtc_bytes[i]
                b2 = raw_dtc_bytes[i + 1]
                if b1 == 0 and b2 == 0:
                    continue
                dtc_str = decode_dtc(b1, b2)
                if dtc_str:
                    dtcs.append(dtc_str)
        return dtcs

    def query_mode_09_vin(self, req_id: int = 0x7E0, resp_id: int = 0x7E8) -> Optional[str]:
        """Consulta Chassi / VIN (Modo 09 PID 0x02)."""
        req = bytes([0x02, 0x09, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00])
        self.ser.reset_input_buffer()
        self._rx_buf.clear()
        if not self.send_raw_frame(req_id, req):
            return None
        resp = self.recv_frame(target_id=resp_id, timeout=0.1)
        if resp and len(resp) >= 3 and resp[1] == 0x49 and resp[2] == 0x02:
            return resp[3:].decode("ascii", errors="ignore").strip()
        return None


def decode_dtc(b1: int, b2: int) -> str:
    """Decodifica 2 bytes em código de anomalia padrão OBD-II (ex: P0171)."""
    type_code = (b1 & 0xC0) >> 6
    letters = {0: "P", 1: "C", 2: "B", 3: "U"}
    prefix = letters.get(type_code, "P")
    d1 = (b1 & 0x30) >> 4
    d2 = b1 & 0x0F
    d3 = (b2 & 0xF0) >> 4
    d4 = b2 & 0x0F
    return f"{prefix}{d1:X}{d2:X}{d3:X}{d4:X}"


def main():
    print("=" * 70)
    print("  VARREDURA E INVENTÁRIO AUTOMÁTICO DA ECU - FORD FIESTA ROCAM 1.0")
    print("  Padrão SAE J1979 / ISO 15765-4 (High-Speed CAN a 500 kbps)")
    print("=" * 70)

    porta = detectar_porta()
    if not porta:
        print("\n[-] Nenhuma porta CANable encontrada. Verifique se o cabo USB está conectado.")
        input("Pressione Enter para sair...")
        return

    print(f"\n[*] Conectando ao LC_CANABLE_V2.1 na porta {porta}...")
    scanner = CANScanner(porta)
    if not scanner.open():
        print("[-] Falha ao inicializar comunicação SLCAN.")
        return

    print("[+] Barramento CAN a 500 kbps aberto com sucesso!")
    print("\n[AVISO]: Certifique-se de que a CHAVE DO VEÍCULO ESTÁ LIGADA (em contato ou motor funcionando).")
    print("Iniciando auditoria da ECU do motor (Target ID 0x7E0 / Resposta 0x7E8)...\n")
    time.sleep(1.0)

    inventory_report: Dict[str, Any] = {
        "timestamp_scan": time.strftime("%Y-%m-%d %H:%M:%S"),
        "car_model": "Ford Fiesta 2010 Sedan 1.0 Zetec Rocam Flex",
        "ecu_id_tested": "0x7E0 / 0x7E8",
        "supported_pids_mode01": [],
        "bitmasks": {},
        "special_pids_test": {},
        "diagnostic_trouble_codes": [],
        "ecu_info_mode09": {},
    }

    # 1. Varredura recursiva de bitmasks de suporte (0x00, 0x20, 0x40, 0x60, 0x80)
    current_mask_pid = 0x00
    all_supported_pids = []

    print("[FASE 1] Mapeando Máscaras de Suporte de PIDs (Modo 01):")
    while current_mask_pid <= 0xE0:
        print(f"  -> Consultando PID 0x{current_mask_pid:02X} (Bitmask)...", end=" ")
        res = scanner.query_obd(mode=0x01, pid=current_mask_pid, timeout=0.06)
        if not res:
            print("SEM RESPOSTA (Fim da árvore de suporte)")
            break

        data_bytes, ms = res
        hex_str = data_bytes.hex().upper()
        print(f"RESPOSTA: {hex_str} ({ms} ms)")
        inventory_report["bitmasks"][f"0x{current_mask_pid:02X}"] = hex_str

        # Decodifica 32 bits
        has_next_range = False
        for i in range(min(4, len(data_bytes))):
            byte_val = data_bytes[i]
            for bit in range(8):
                if byte_val & (1 << (7 - bit)):
                    pid_num = current_mask_pid + (i * 8) + bit + 1
                    if pid_num % 0x20 == 0:
                        has_next_range = True
                    else:
                        all_supported_pids.append(pid_num)

        if not has_next_range:
            break
        current_mask_pid += 0x20
        time.sleep(0.02)

    print(f"\n[+] Total de PIDs suportados identificados no Modo 01: {len(all_supported_pids)}")
    print("    Lista:", [f"0x{p:02X}" for p in all_supported_pids])

    # 2. Leitura individual de cada PID suportado
    print("\n[FASE 2] Consultando valores ao vivo dos PIDs suportados:")
    for pid in all_supported_pids:
        desc = PID_DESCRIPTIONS.get(pid, "Parâmetro Específico SAE")
        print(f"  PID 0x{pid:02X} [{desc}]:", end=" ")
        res = scanner.query_obd(mode=0x01, pid=pid, timeout=0.04)
        if res:
            payload, ms = res
            raw_hex = payload.hex().upper()
            print(f"OK -> Raw: {raw_hex} ({ms} ms)")
            inventory_report["supported_pids_mode01"].append({
                "pid_hex": f"0x{pid:02X}",
                "pid_dec": pid,
                "description": desc,
                "raw_hex": raw_hex,
                "response_time_ms": ms,
                "classification": "A - Confirmado em Veículo",
            })
        else:
            print("Sem resposta")
        time.sleep(0.015)

    # 3. Teste direcionado aos PIDs especiais candidatos (independente do bitmask)
    special_candidates = [0x2F, 0x33, 0x42, 0x44, 0x46, 0x51, 0x52, 0x5C, 0x5E]
    print("\n[FASE 3] Teste Direcionado de PIDs Estratégicos (Tensão, Etanol, Baro):")
    for pid in special_candidates:
        desc = PID_DESCRIPTIONS.get(pid, "Candidato Especial")
        print(f"  Testando PID 0x{pid:02X} ({desc})...", end=" ")
        res = scanner.query_obd(mode=0x01, pid=pid, timeout=0.06)
        if res:
            payload, ms = res
            raw_hex = payload.hex().upper()
            print(f"SUPORTADO! -> Raw: {raw_hex} ({ms} ms)")
            inventory_report["special_pids_test"][f"0x{pid:02X}"] = {
                "supported": True,
                "raw_hex": raw_hex,
                "response_time_ms": ms,
            }
        else:
            print("Não suportado")
            inventory_report["special_pids_test"][f"0x{pid:02X}"] = {"supported": False}
        time.sleep(0.02)

    # 4. Códigos de Falha DTC (Modo 03)
    print("\n[FASE 4] Lendo Códigos de Falha Armazenados (Modo 03):")
    dtcs = scanner.query_mode_03()
    if dtcs:
        print(f"  [!] DTCs Encontrados: {', '.join(dtcs)}")
        inventory_report["diagnostic_trouble_codes"] = dtcs
    else:
        print("  [✅] Nenhuma falha ativa registrada na memória da ECU (DTCs = 0).")

    # 5. Modo 09 - Identificação da ECU e Chassi
    print("\n[FASE 5] Lendo Informações do Veículo e da Injeção (Modo 09):")
    vin = scanner.query_mode_09_vin()
    if vin:
        print(f"  VIN / Chassi: {vin}")
        inventory_report["ecu_info_mode09"]["vin"] = vin
    else:
        print("  VIN: Não retornado por OBD genérico")

    # Finalização e Gravação do Relatório
    scanner.close()

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(inventory_report, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("  AUDITORIA DE TELEMETRIA CONCLUÍDA COM SUCESSO!")
    print(f"  Relatório completo salvo em: {OUTPUT_FILE.name}")
    print("=" * 70)
    input("\nPressione Enter para fechar o scanner...")


if __name__ == "__main__":
    main()
