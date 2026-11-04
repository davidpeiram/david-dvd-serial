# INDEX & MAPA DO PROJETO FIESTA ZETEC ROCAM 1.0

> **Data do Ponto de Retomada:** 02/11/2026 — 20:35  
> **Veículo:** Ford Fiesta 2010 Sedan 1.0 Flex Zetec Rocam (8V, 73 cv, câmbio IB5)  
> **Hardware:** LC_CANABLE_V2.1 (STM32G431) em modo SLCAN a 500 kbps (HS-CAN)  
> **Status Geral:** Cockpit Digital V2.0 Operacional + Sniffer V2.0 Ativo + Scanner UDS Pronto  
> **Diretriz de Integridade:** Calibração da ECU 100% original e intacta (Escopo Estritamente Read-Only)

---

## 📍 Onde Paramos Hoje (Resumo de Conquistas - 02/11/2026)

1. **Torque do Motor Diagnóstico & Solução:**
   - Identificado que o processo anterior `main.py` rodava em memória antes das alterações.
   - Descoberta metrológica: o **Byte 0 do frame 0x422** é a aceleração/demanda instantânea do acelerador (`0x00` a `0xF4` = 0 a 244 decimal). Foi calibrado para o torque real do motor Rocam 1.0 (8.0 Nm na lenta até 93.0 Nm no pico de aceleração).
   - O **Byte 6 do frame 0x422** foi mapeado como a carga/pressão do Ar-Condicionado (vai para 7 a 10 bar com A/C ligado, e 0 com A/C desligado).
   - Buffer serial em `can_adapter.py` corrigido: agora drena os dados sem descartar pacotes broadcast `0x422` e `0x430`.
2. **Upgrade do Sniffer Passivo (`sniff_passivo_fiesta.py`):**
   - Modo **Listen-Only (`L`)** estrito e seguro (sem emissão e sem ACK no barramento).
   - Teclas interativas **`[M]`** (grava marcador com milissegundos e prompt de descrição) e **`[C]`** (zera contadores para isolar testes de componentes).
   - Renderização fluida em ANSI sem flicker e duplo salvamento (`logs/sniff_passivo_*.txt` e `logs/sniff_bruto_*.csv`).
3. **Engenharia Reversa Pelican / OBDb:**
   - Análise completa do site `pelican.clutch.engineering` e download da base `obdb_fiesta_commands.json` (192 comandos e 203 sinais).
   - Criação do **Scanner UDS Ford Service 22** ([`testar_dids_fiesta.py`](file:///H:/Outros%20computadores/Meu%20computador/David-Pessoal/Projetos/Projeto%20Fiesta%20Zetec%20Rocam%201.0/testar_dids_fiesta.py) / [`testar_dids.bat`](file:///H:/Outros%20computadores/Meu%20computador/David-Pessoal/Projetos/Projeto%20Fiesta%20Zetec%20Rocam%201.0/testar_dids.bat)) com 28 DIDs prioritários mapeados.
4. **Organização Arquitetural do Projeto:**
   - Todos os scripts e executáveis centralizados na raiz.
   - Documentações, pesquisas da Pelican, logs e considerações organizados em subpastas limpas.

---

## 🎯 Roteiro Prático de Retomada (Passo a Passo para Amanhã)

Quando for para o carro amanhã, siga esta sequência direta:

### 1️⃣ Passo 1: Executar a Varredura de DIDs UDS
1. Plugue a CANable na USB do computador e conecte ao conector OBD-II do Fiesta.
2. Gire a chave para a **posição II (KOEO - ignição ligada sem dar partida)** ou **ligue o motor**.
3. Dê dois cliques em [`testar_dids.bat`](file:///H:/Outros%20computadores/Meu%20computador/David-Pessoal/Projetos/Projeto%20Fiesta%20Zetec%20Rocam%201.0/testar_dids.bat).
4. O script testará os 28 DIDs candidatos nos módulos **PCM 0x7E0**, **Painel 0x720** e **BCM 0x726**.
5. Ao final, confira os DIDs com resposta positiva `✅` salvos em `logs/scan_dids_*.txt` (alvo principal: **Tensão real da bateria `0x1172`**, **Temp. Cabeçote CHT `0x0334`** e **Hodômetro do Painel `0x404C`**).

### 2️⃣ Passo 2: Integrar os DIDs Descobertos ao Painel
- Adicionaremos os DIDs confirmados no ciclo de leitura do `can_adapter.py` e criaremos os novos cards no painel HTML (ex: Tensão Real da Bateria e CHT).

### 3️⃣ Passo 3: Testar o Painel Digital com o Torque Corrigido
1. Dê dois cliques em [`iniciar_painel.bat`](file:///H:/Outros%20computadores/Meu%20computador/David-Pessoal/Projetos/Projeto%20Fiesta%20Zetec%20Rocam%201.0/iniciar_painel.bat).
2. Com o motor ligado, acelere e comprove o **Card 9 (Torque Motor)** subindo dinamicamente de ~8 Nm até a faixa de 50 a 90 Nm.

---

## 🗂️ Mapa da Estrutura de Pastas e Scripts

```text
Projetos/Projeto Fiesta Zetec Rocam 1.0/
│
├── 🚀 EXECUTÁVEIS E SCRIPTS PRINCIPAIS (NA RAIZ):
│   ├── iniciar_painel.bat          # 1-clique: Inicia servidor FastAPI/WebSockets e abre o Cockpit no navegador
│   ├── main.py                     # Backend principal do Cockpit Digital
│   │
│   ├── testar_dids.bat             # 1-clique: Executa varredura de DIDs proprietários UDS Ford (Service 22)
│   ├── testar_dids_fiesta.py       # Scanner UDS com suporte a ISO-TP e decodificação automática
│   │
│   ├── sniff_passivo.bat           # 1-clique: Inicia sniffer passivo no barramento HS-CAN
│   ├── sniff_passivo_fiesta.py     # Sniffer Listen-Only ('L') com teclas [M] marcador e [C] zerar
│   │
│   ├── escanear_ecu.bat            # 1-clique: Escaneia inventário de PIDs OBD-II suportados (Modo 01 e 03)
│   ├── scanner_inventario_ecu.py   # Script de auditoria de PIDs OBD
│   │
│   ├── testar_bancada.bat          # 1-clique: Teste de bancada USB e loopback da CANable
│   └── test_bancada_canable.py     # Verificador de firmware e comunicação SLCAN
│
├── ⚙️ CONFIGURAÇÕES E DOCUMENTOS CENTRAIS:
│   ├── Relatorio_Desempenho_Consumo_Telemetria_HTML.html # Relatório executivo de esticadas de marcha, RPM e consumo térmico
│   ├── config.json                 # Configurações de porta COM, baudrate (500k) e modo
│   ├── requirements.txt            # Dependências Python (pyserial, fastapi, uvicorn, websockets)
│   ├── .gitignore                  # Arquivos ignorados pelo controle de versão
│   ├── AGENTS.md                   # Diretrizes técnicas, rigor metrológico e regras para agentes de IA
│   ├── Escopo do Projeto.txt       # Diário de bordo contínuo de progresso e sessões ao vivo
│   └── INDEX_PROJETO_FIESTA.md     # Este arquivo (índice mestre e ponto de retomada)
│
├── 📁 SUBPASTAS ORGANIZADAS:
│   ├── src/                        # Módulos Python internos (can_adapter, obd_manager, datalogger, server)
│   ├── static/                     # Interface Web do Cockpit (index.html, dashboard.css, app.js, gauge.js)
│   ├── logs/                       # Registros reais (viagens CSV, sniffer TXT/CSV, inventários JSON)
│   │   ├── inventario_ecu_fiesta.json # Resultado do escaneamento real da ECU KOEO
│   │   ├── viagem_fiesta_*.csv        # Datalogger de telemetria de viagens
│   │   ├── sniff_passivo_*.txt        # Logs legíveis de deltas e eventos com marcadores
│   │   └── sniff_bruto_*.csv          # Captura bruta de todos os frames para replay
│   │
│   ├── Documentacao/               # Manuais técnicos e documentações de pesquisa
│   │   ├── Manual_Pinagem_Chicote_OBD2_CANable.html # Manual visual de pinagem do conector OBD-II
│   │   ├── Proximos_Passos_Projeto_Fiesta_V2.txt    # Roteiro da arquitetura V2
│   │   └── Pesquisa_Pelican_OBDb/  # Base completa da Pelican / Open On-Board Diagnostics Database
│   │       ├── obdb_fiesta_commands.json   # 192 comandos e 203 sinais com fórmulas de decodificação
│   │       ├── pelican_fiesta.html         # Snapshot da documentação web do Fiesta
│   │       └── pelican_fiesta_parameters.html # Snapshot dos 334 parâmetros da Pelican
│   │
│   ├── Consideracoes_David/        # Relatórios técnicos do David e revisões detalhadas de Claude e GPT
│   │   ├── Consideracoes_Projeto_Fiesta_Rocam.txt
│   │   ├── Consideracoes_Tecnicas_Projeto_Fiesta_Zetec_Rocam.txt
│   │   ├── parte-2-Consideracoes_Parte2_Dados_ECU_Fiesta.txt
│   │   └── Considerações 2/        # Reviews detalhadas de Claude e GPT sobre o sniffer e CAN
│   │
│   ├── Integracao_Celular_WebUSB/  # Módulo de conexão direta CANable no celular Android via WebUSB
│   │   ├── Instrucoes_Integracao_Celular_WebUSB.md
│   │   └── Teste_WebUSB_CANable.html
│   │
│   ├── Android_App_Fiesta/         # Projeto Android Nativo (APK com usb-serial-for-android + Cockpit WebView)
│   │   └── app/src/main/           # MainActivity.java (CDC 16D0:117E) + assets (Cockpit & Terminal)
│   │
│   └── apk/                        # Repositório de instaladores Android compilados (Histórico Completo)
│       ├── Fiesta_Cockpit_USB.apk        # Ponteiro da versão mais recente (Latest Build)
│       ├── Fiesta_Cockpit_USB_v2.4.0.apk # Versão v2.4.0 (Scanner Completo de 53 PIDs/DIDs Ford EEC-VI, Sniffer CAN & Exportação de Relatório)
       ├── Fiesta_Cockpit_USB_v2.3.4.apk # Versão v2.3.4 (OpenStreetMap sem API Key, GPS Multi-Provider, UI Vertical/Horizontal & Logo Otimizada)
│       ├── Fiesta_Cockpit_USB_v2.3.3.apk # Versão v2.3.3 (Capa/Logo Oficial do APK & Correção Escopo Mapa Leaflet)
│       ├── Fiesta_Cockpit_USB_v2.3.2.apk # Versão v2.3.2 (Correção CartoDB {r} no Leaflet & Zero Mock Values sem ECU)
│       ├── Fiesta_Cockpit_USB_v2.3.1.apk # Versão v2.3.1 (Blindagem Android 14 FGS, Permissões & Leaflet Resize)
│       ├── Fiesta_Cockpit_USB_v2.3.0.apk # Versão v2.3.0 (Foreground Service, GPS Map, Cluster Compacto & 5 Temas)
│       └── Fiesta_Cockpit_USB_v2.2.0.apk # Versão v2.2.0 (Release nativa inicial com gauges e USB OTG)
```
