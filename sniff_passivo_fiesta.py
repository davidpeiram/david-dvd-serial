"""
sniff_passivo_fiesta.py - Monitor e Sniffer Passivo do Barramento CAN
Ford Fiesta 2010 Sedan 1.0 Zetec Rocam
Hardware: LC_CANABLE_V2.1 (STM32G431) em modo SLCAN a 500 kbps

Este script opera em modo LISTEN-ONLY (comando 'L' do SLCAN):
O controlador CAN apenas escuta o barramento elétrico HS-CAN do veículo,
sem gerar pulsos de transmissão e SEM GERAR ACK no barramento.
Se o firmware recusar o comando 'L', o script aborta por segurança.

Recursos integrados (Revisão Claude & GPT):
- Modo Listen-Only ('L') estrito e seguro
- Tecla [M]: Gravação de Marcador de Evento com timestamp em ms e descrição
- Tecla [C]: Zeragem instantânea de contadores para isolar testes de componentes
- Renderização ANSI (sem piscar a tela com 'cls')
- Detecção exata de quais bytes mudaram em cada frame (ex: bytes [0, 5])
- Cálculo real de taxa instantânea de mensagens (MSG/S em Hz)
- Duplo salvamento: Log legível de deltas (.txt) + Log bruto completo (.csv)
- Detecção estrita de porta COM por VID/PID (16D0:117E) ou assinaturas CANable
"""

import os
import sys
import time
from pathlib import Path
from typing import Dict, Any, Optional, List

import serial
import serial.tools.list_ports

try:
    import msvcrt  # Teclado interativo nativo no Windows (sem bloqueio)
except ImportError:
    msvcrt = None

BASE_DIR = Path(__file__).resolve().parent
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

SESSION_TS = time.strftime("%Y-%m-%d_%H-%M-%S")
LOG_DELTA_FILE = LOG_DIR / f"sniff_passivo_{SESSION_TS}.txt"
LOG_RAW_CSV_FILE = LOG_DIR / f"sniff_bruto_{SESSION_TS}.csv"


def ts_ms() -> str:
    """Retorna timestamp formatado com milissegundos: HH:MM:SS.mmm"""
    t = time.time()
    return time.strftime("%H:%M:%S") + f".{int(t % 1 * 1000):03d}"


def detectar_porta() -> Optional[str]:
    """
    Identificação estrita e segura da porta serial da CANable.
    Nunca conecta em portas desconhecidas ou genéricas.
    """
    ports = list(serial.tools.list_ports.comports())
    if not ports:
        return None

    # Nível 1: VID:PID Oficial do CANable STM32G431 (16D0:117E)
    for p in ports:
        hwid = (p.hwid or "").lower()
        if "16d0:117e" in hwid:
            return p.device

    # Nível 2: Nomes de descritor USB conhecidos
    for p in ports:
        desc = (p.description or "").lower()
        if any(k in desc for k in ["canable", "candle", "slcan", "stm32"]):
            return p.device

    return None


def slcan_cmd(ser: serial.Serial, cmd: bytes, wait: float = 0.04) -> bytes:
    """Envia um comando SLCAN e retorna a resposta terminada."""
    ser.reset_input_buffer()
    ser.write(cmd + b"\r")
    time.sleep(wait)
    avail = ser.in_waiting
    return ser.read(avail or 1)


def bytes_alterados(old_hex: str, new_hex: str) -> List[int]:
    """Compara duas strings hexadecimais e retorna a lista de índices de bytes que mudaram."""
    n = max(len(old_hex), len(new_hex)) // 2
    return [i for i in range(n) if old_hex[i * 2 : i * 2 + 2] != new_hex[i * 2 : i * 2 + 2]]


def main():
    # Habilita Virtual Terminal Processing (ANSI) no CMD / PowerShell do Windows
    os.system("")

    print("=" * 72)
    print("   SNIFFER PASSIVO DE BARRAMENTO CAN - FORD FIESTA ROCAM 1.0")
    print("   Modo LISTEN-ONLY (Zero Transmissão / Sem ACK / 100% Passivo)")
    print("=" * 72)

    porta = detectar_porta()
    if not porta:
        print("\n[-] Nenhuma porta CANable V2.1 encontrada.")
        print("    Verifique a conexão USB do adaptador LC_CANABLE.")
        input("\nPressione Enter para sair...")
        return

    print(f"[*] Adaptador CANable identificado na porta {porta}.")
    print(f"[*] Configurando barramento HS-CAN a 500 kbps em modo Listen-Only ('L')...")

    try:
        ser = serial.Serial(porta, baudrate=115200, timeout=0.01)
        slcan_cmd(ser, b"C")        # Fecha qualquer canal aberto anteriormente
        slcan_cmd(ser, b"S6")       # Configura bitrate CAN para 500 kbps
        resp_l = slcan_cmd(ser, b"L")  # Abre canal em modo Listen-Only

        if b"\x07" in resp_l:
            print("[-] ALERTA: O firmware do adaptador recusou o modo Listen-Only ('L').")
            print("    Abortando por segurança para não abrir em modo normal com ACK no barramento.")
            ser.write(b"C\r")
            ser.close()
            input("\nPressione Enter para sair...")
            return

        ser.reset_input_buffer()
        print(f"[+] Canal CAN aberto com sucesso em modo PASSIVO na {porta}!")
    except Exception as e:
        print(f"[-] Erro ao inicializar porta serial {porta}: {e}")
        input("\nPressione Enter para sair...")
        return

    print(f"[+] Arquivo de Deltas/Eventos: {LOG_DELTA_FILE.name}")
    print(f"[+] Arquivo de Captura Bruta:  {LOG_RAW_CSV_FILE.name}")
    print("\nComandos interativos durante o teste:")
    print("  [M] - Marcar evento (ex: 'Liguei A/C', 'Pisei no Freio', 'Acelerei a 3000 RPM')")
    print("  [C] - Zerar contadores (para isolar uma nova ação sem poluição)")
    print("  [Ctrl+C] - Finalizar sniffer e salvar arquivos\n")
    time.sleep(1.5)

    # Dicionário de estado por CAN ID
    id_records: Dict[int, Dict[str, Any]] = {}
    rx_buf = bytearray()
    last_display_time = 0.0

    # Abre arquivos de log
    f_delta = open(LOG_DELTA_FILE, "w", encoding="utf-8")
    f_delta.write("# Sniffer Passivo CAN - Ford Fiesta Zetec Rocam 1.0\n")
    f_delta.write(f"# Data/Hora Início: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    f_delta.write(f"# Modo: SLCAN Listen-Only a 500 kbps (Porta: {porta})\n\n")
    f_delta.flush()

    f_raw = open(LOG_RAW_CSV_FILE, "w", encoding="utf-8")
    f_raw.write("timestamp,can_id,dlc,payload\n")
    f_raw.flush()

    total_frames_received = 0

    try:
        while True:
            # 1. Leitura de pacotes da CANable
            avail = ser.in_waiting
            if avail > 0:
                chunk = ser.read(avail)
                for b in chunk:
                    if b in (13, 10):
                        if not rx_buf:
                            continue
                        line = rx_buf.decode("ascii", errors="ignore").strip()
                        rx_buf.clear()

                        is_std = line.startswith("t")
                        is_ext = line.startswith("T")
                        if not (is_std or is_ext) or len(line) < 5:
                            continue

                        try:
                            if is_std:
                                can_id = int(line[1:4], 16)
                                dlc = int(line[4], 16)
                                payload = line[5 : 5 + dlc * 2]
                            else:
                                can_id = int(line[1:9], 16)
                                dlc = int(line[9], 16)
                                payload = line[10 : 10 + dlc * 2]

                            if not (0 <= dlc <= 8) or len(payload) != dlc * 2:
                                continue
                        except ValueError:
                            continue

                        now = time.time()
                        now_ts = ts_ms()
                        total_frames_received += 1

                        # Grava no log de captura bruta (CSV)
                        f_raw.write(f"{now_ts},0x{can_id:03X},{dlc},{payload}\n")

                        # Atualiza registro de ID
                        rec = id_records.get(can_id)
                        if rec is None:
                            rec = id_records[can_id] = {
                                "dlc": dlc,
                                "count": 0,
                                "prev_count": 0,
                                "rate": 0.0,
                                "changes": 0,
                                "last_payload": payload,
                                "change_time": 0.0,
                            }

                        rec["count"] += 1

                        # Detecção de alteração de payload
                        if rec["last_payload"] != payload:
                            changed_idx = bytes_alterados(rec["last_payload"], payload)
                            rec["changes"] += 1
                            rec["change_time"] = now
                            f_delta.write(
                                f"[{now_ts}] DELTA 0x{can_id:03X}: "
                                f"{rec['last_payload']} -> {payload}  bytes {changed_idx}\n"
                            )
                            f_delta.flush()

                        rec["last_payload"] = payload
                    else:
                        rx_buf.append(b)

            # 2. Leitura de teclado interativo (Windows)
            if msvcrt and msvcrt.kbhit():
                key = msvcrt.getwch().lower()
                if key == "m":
                    marca = ts_ms()
                    f_delta.write(f"[{marca}] ===== MARCADOR =====\n")
                    f_delta.flush()
                    print(f"\n[{marca}] Marcador criado. Digite a descrição do teste: ", end="", flush=True)
                    desc = input().strip()
                    f_delta.write(f"[{marca}] >>> {desc}\n")
                    f_delta.flush()
                    f_raw.write(f"{marca},MARKER,0,{desc}\n")
                    f_raw.flush()
                    last_display_time = 0.0
                elif key == "c":
                    for r_ in id_records.values():
                        r_["count"] = 0
                        r_["prev_count"] = 0
                        r_["changes"] = 0
                        r_["change_time"] = 0.0
                    marca = ts_ms()
                    f_delta.write(f"[{marca}] (contadores zerados pelo usuário)\n")
                    f_delta.flush()
                    last_display_time = 0.0

            # 3. Atualização visual do painel de monitoramento (ANSI sem flicker)
            now = time.time()
            dt = now - last_display_time
            if dt >= 0.5:
                last_display_time = now
                out = ["\033[H\033[J"]
                out.append("=" * 72)
                out.append(f"  SNIFFER CAN PASSIVO - IDs: {len(id_records)} | Frames Totais: {total_frames_received}")
                out.append("  Teclas: [M] Criar Marcador  |  [C] Zerar Contadores  |  Ctrl+C Sair")
                out.append("=" * 72)
                out.append(f"  {'CAN ID':<8}| {'DLC':<4}| {'PAYLOAD':<18}| {'MSG/S':<7}| {'MUD.':<6}| STATUS")
                out.append("-" * 72)

                for cid in sorted(id_records.keys()):
                    r = id_records[cid]
                    r["rate"] = (r["count"] - r["prev_count"]) / dt
                    r["prev_count"] = r["count"]
                    recente = r["change_time"] > 0 and (now - r["change_time"] < 2.0)
                    status = "🔥 MUDOU!" if recente else ""
                    out.append(
                        f"  0x{cid:03X}   | {r['dlc']:<4}| "
                        f"{r['last_payload']:<18}| {r['rate']:<7.1f}| {r['changes']:<6}| {status}"
                    )

                sys.stdout.write("\n".join(out) + "\n")
                sys.stdout.flush()

            time.sleep(0.002)

    except KeyboardInterrupt:
        print("\n\n[*] Finalizando sniffer e gravando logs pendentes...")
    finally:
        try:
            ser.write(b"C\r")
            ser.close()
        except Exception:
            pass
        f_delta.close()
        f_raw.close()
        print(f"[+] Log de eventos salvo: {LOG_DELTA_FILE.name}")
        print(f"[+] Log bruto salvo:     {LOG_RAW_CSV_FILE.name}")
        input("\nPressione Enter para sair...")


if __name__ == "__main__":
    main()
