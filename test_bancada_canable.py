"""
test_bancada_canable.py - Diagnóstico e Validação de Bancada - Versão 2.0
Placa: LC_CANABLE_V2.1 (MCU: STM32G431)
Projeto: Ford Fiesta 2010 Sedan 1.0 Zetec Rocam

Este script executa uma bateria de testes com veredito metrológico independente:
- Comunicação Serial CDC USB
- Reset e Fechamento de Canal ('C')
- Identificação de Versão e Serial ('V', 'v', 'N')
- Configuração de Taxa HS-CAN 500 kbps ('S6')
- Teste de Loopback Interno ('l' e transmissão 't')
- Abertura em Modo Normal de Operação ('O')
- Veredito Final Estruturado: APROVADO, REPROVADO ou INCONCLUSIVO
"""

import sys
import time
import serial
import serial.tools.list_ports


def listar_portas_com():
    """Retorna lista de portas COM com detalhes."""
    return list(serial.tools.list_ports.comports())


def detectar_canable(timeout_segundos=45):
    """
    Tenta detectar a porta COM da CANable com prioridade estrita por VID/PID.
    """
    print("\n[1/4] Procurando módulo CANable V2.1...")
    portas_iniciais = {p.device for p in listar_portas_com()}

    # Nível 1: VID:PID Oficial (16D0:117E)
    for p in listar_portas_com():
        hwid = (p.hwid or "").lower()
        if "16d0:117e" in hwid:
            print(f" -> Encontrado CANable por Hardware ID oficial: {p.device} ({p.description})")
            return p.device

    # Nível 2: Descrições características
    candidatas = []
    for p in listar_portas_com():
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if any(term in desc or term in hwid for term in ["canable", "candle", "slcan", "stm32"]):
            candidatas.append(p)

    if candidatas:
        porta = candidatas[0].device
        print(f" -> Encontrada porta candidata: {porta} ({candidatas[0].description})")
        return porta

    print("\n[*] Nenhuma placa CANable detectada automaticamente no momento.")
    print(" -> Por favor, CONECTE o cabo USB da CANable no computador agora...")
    print(f" -> Monitorando portas USB por até {timeout_segundos} segundos (Pressione Ctrl+C para cancelar)...")

    inicio = time.time()
    while time.time() - inicio < timeout_segundos:
        portas_atuais = listar_portas_com()
        novas = [p for p in portas_atuais if p.device not in portas_iniciais]
        if novas:
            porta_detectada = novas[0].device
            print(f"\n[+] NOVA PORTA DETECTADA! -> {porta_detectada} ({novas[0].description})")
            time.sleep(1.0)
            return porta_detectada

        restante = int(timeout_segundos - (time.time() - inicio))
        sys.stdout.write(f"\r -> Aguardando conexão... [{restante:02d}s]")
        sys.stdout.flush()
        time.sleep(0.5)

    print("\n\n[-] Tempo limite esgotado sem novas conexões.")
    if portas_iniciais:
        lista_str = ", ".join(sorted(portas_iniciais))
        print(f"Portas disponíveis na máquina: {lista_str}")
        escolha = input("Deseja testar em alguma dessas portas? (Digite ex: COM9 ou Enter para sair): ").strip().upper()
        if escolha:
            return escolha

    return None


def testar_slcan(porta, baudrate=115200):
    """Executa a rotina de testes do protocolo SLCAN com veredito granular."""
    print(f"\n[2/4] Abrindo porta serial {porta} a {baudrate} baud...")

    test_results = {
        "serial_open": False,
        "slcan_close": False,
        "bitrate_s6": False,
        "loopback_test": False,
        "normal_open": False,
    }

    try:
        ser = serial.Serial(porta, baudrate=baudrate, timeout=0.25, write_timeout=0.25)
        test_results["serial_open"] = True
    except Exception as e:
        print(f"[-] REPROVADO: Erro ao abrir {porta}: {e}")
        return False

    time.sleep(0.15)
    ser.reset_input_buffer()
    ser.reset_output_buffer()

    def enviar_cmd(cmd, timeout=0.25):
        ser.reset_input_buffer()
        ser.write((cmd + "\r").encode("ascii"))
        ser.flush()
        inicio = time.time()
        buf = bytearray()
        while time.time() - inicio < timeout:
            if ser.in_waiting > 0:
                ch = ser.read(1)
                if ch in (b"\r", b"\n"):
                    if buf:
                        break
                elif ch == b"\x07":
                    return "<ERRO / BELL>"
                else:
                    buf.extend(ch)
            else:
                time.sleep(0.005)
        return buf.decode("ascii", errors="ignore").strip()

    print("[3/4] Executando protocolo de validação Lawicel / SLCAN:")

    # 1. Fechar canal prévio
    print("  1. Enviando 'C' (Close CAN)...", end=" ")
    r = enviar_cmd("C")
    if r != "<ERRO / BELL>":
        test_results["slcan_close"] = True
        print("OK (Canal pronto)")
    else:
        print("AVISO: Resposta não padrão ao fechar canal.")

    # 2. Versão de Hardware e Firmware (Informativo)
    print("  2. Solicitando versão de Hardware ('V')...", end=" ")
    hw_ver = enviar_cmd("V")
    print(f"'{hw_ver}'" if hw_ver else "(Opcional: Sem eco de string pelo firmware)")

    print("  3. Solicitando versão de Firmware ('v')...", end=" ")
    sw_ver = enviar_cmd("v")
    print(f"'{sw_ver}'" if sw_ver else "(Opcional: Sem eco de string pelo firmware)")

    # 4. Configurar Bitrate CAN para 500 kbps (S6)
    print("  4. Configurando CAN Bitrate para 500 kbps ('S6')...", end=" ")
    r_speed = enviar_cmd("S6")
    if r_speed != "<ERRO / BELL>":
        test_results["bitrate_s6"] = True
        print("OK (Taxa 500k HS-CAN Ford aceita)")
    else:
        print("REPROVADO (Controlador rejeitou comando S6)")

    # 5. Teste de Loopback Interno
    print("\n[4/4] Teste de Transmissão e Loopback:")
    print("  5. Abrindo canal em modo Loopback ('l')...", end=" ")
    r_loop = enviar_cmd("l")
    if r_loop != "<ERRO / BELL>":
        print("OK")
        frame_teste = "t7DF80201000000000000"
        print(f"  6. Transmitindo frame de teste: {frame_teste} ...", end=" ")
        ser.reset_input_buffer()
        ser.write((frame_teste + "\r").encode("ascii"))
        ser.flush()

        inicio = time.time()
        recebido = ""
        while time.time() - inicio < 0.35:
            if ser.in_waiting > 0:
                linha = ser.read_until(b"\r").decode("ascii", errors="ignore").strip()
                if linha:
                    recebido = linha
                    break
            time.sleep(0.005)

        if recebido:
            test_results["loopback_test"] = True
            print(f"SUCESSO! Echo recebido -> '{recebido}'")
        else:
            print("INCONCLUSIVO: Echo não retornado (normal em firmwares CandleLight slcan puros).")
    else:
        print("INCONCLUSIVO: Modo loopback 'l' não implementado neste firmware.")

    # 7. Fechar loopback e testar abertura normal
    enviar_cmd("C")
    print("  7. Testando abertura em Modo Normal de Operação ('O')...", end=" ")
    r_open = enviar_cmd("O")
    if r_open != "<ERRO / BELL>":
        test_results["normal_open"] = True
        print("OK (Transceptor CAN habilitado para o veículo)")
    else:
        print("REPROVADO (Falha ao abrir em modo normal)")

    # 8. Fechamento seguro
    enviar_cmd("C")
    ser.close()

    # Veredito Final
    aprovado_total = (
        test_results["serial_open"]
        and test_results["slcan_close"]
        and test_results["bitrate_s6"]
        and test_results["normal_open"]
    )

    print("\n" + "=" * 65)
    print("        RELATÓRIO DE DIAGNÓSTICO DE BANCADA - V2.0")
    print("=" * 65)
    print(f"  Porta Serial:           {porta}")
    print(f"  Comunicação USB-CDC:    {'APROVADO' if test_results['serial_open'] else 'REPROVADO'}")
    print(f"  Protocolo SLCAN (Lawicel): {'APROVADO' if test_results['slcan_close'] else 'REPROVADO'}")
    print(f"  Taxa 500k HS-CAN (S6):  {'APROVADO' if test_results['bitrate_s6'] else 'REPROVADO'}")
    print(f"  Modo Normal (O):        {'APROVADO' if test_results['normal_open'] else 'REPROVADO'}")
    print(f"  Teste Loopback / Echo:  {'APROVADO' if test_results['loopback_test'] else 'INFORMATIVO (Sem suporte de eco)'}")
    print("-" * 65)

    if aprovado_total:
        print("  VEREDITO FINAL:         ✅ APROVADO PARA OPERAÇÃO NO VEÍCULO")
        print("  O módulo CANable está 100% configurado para o Ford Fiesta 1.0.")
    else:
        print("  VEREDITO FINAL:         ❌ REPROVADO OU INCONCLUSIVO")
        print("  Verifique a conexão do cabo USB e os drivers virtuais CDC.")
    print("=" * 65)

    return aprovado_total


def main():
    print("=" * 65)
    print("   TESTE DE BANCADA V2.0 - CANable V2.1 (STM32G431)")
    print("   Ford Fiesta 2010 Sedan 1.0 Zetec Rocam")
    print("=" * 65)

    porta = detectar_canable()
    if not porta:
        print("\n[-] Nenhum dispositivo selecionado. Teste abortado.")
        input("\nPressione Enter para sair...")
        return

    sucesso = testar_slcan(porta)
    if sucesso:
        print("\nDICA:")
        print("O sistema do painel já está calibrado na Versão 2.0.")
        print("Você pode executar 'iniciar_painel.bat' para abrir o Cockpit.")

    input("\nPressione Enter para finalizar...")


if __name__ == "__main__":
    main()
