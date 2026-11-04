# AGENTS.md - Diretrizes Técnicas e Modus Operandi do Projeto Fiesta Rocam 1.0

Este documento estabelece o **modus operandi**, as diretrizes técnicas de engenharia e os padrões estritos de desenvolvimento para qualquer Agente de Inteligência Artificial que atue no **Projeto Fiesta Zetec Rocam 1.0**.

---

## 1. Identificação do Veículo e Arquitetura de Hardware

- **Veículo Alvo:** Ford Fiesta Sedan 1.0 8V Flex (Ano/Modelo 2010)
- **Motor & Transmissão:** Zetec Rocam 1.0L (73 cv / 9,3 kgfm) com Câmbio Manual Ford IB5
- **Unidade de Controle (ECU):** Ford EEC-VI (Black Oak)
- **Barramento de Comunicação:** High-Speed CAN (HS-CAN) a 500 kbps (11-bit standard ID)
- **Hardware de Conexão:** Módulo LC_CANABLE_V2.1 (MCU STM32G431) operando em modo *slcan* (porta serial virtual COM)
- **Chicote Físico OBD-II (SAE J1962):**
  - Pino 6: `CAN_H` $\rightarrow$ CANable `CAN_H`
  - Pino 14: `CAN_L` $\rightarrow$ CANable `CAN_L`
  - Pino 4/5: `GND` $\rightarrow$ CANable `GND`
  - Pino 16: `+12V Bateria` $\rightarrow$ **ISOLADO** (não conectado ao CANable para proteger a placa USB 5V de queima)

---

## 2. Princípio Fundamental de Rigor Metrológico (Modus Operandi)

> [!IMPORTANT]
> **REGRA DE OURO DA INSTRUMENTAÇÃO:**  
> **NUNCA** apresente uma grandeza estimada, simulada ou calculada como se fosse uma medição direta de sensor físico. Toda informação no sistema deve ser metrologicamente transparente.

O "diagnóstico cego" é inadmissível em engenharia. Exibir uma grandeza sintética (como forçar 14,2 V de tensão no painel se RPM > 450) pode mascarar falhas graves do veículo (ex: rompimento da correia de acessórios *Poly-V*, queima da ponte de diodos ou falha do regulador de voltagem do alternador), deixando o motorista sem alerta até o esgotamento total da bateria.

---

## 3. Classificação Obrigatória: `REAL` vs. `ESTIMADO`

Todo e qualquer parâmetro de telemetria, card de interface web (Cockpit), variável em backend, endpoint de API e coluna em logs CSV **DEVE** ser categorizado formalmente em uma das duas classes:

### 🟢 Categoria `REAL`
Aplicada **exclusivamente** a dados capturados diretamente de transdutores físicos instalados no veículo e transmitidos pela rede CAN / OBD-II:
- **RPM do Motor:** Sensor de Rotação Indutivo no Virabrequim (CKP) $\rightarrow$ PID `0x0C`
- **Velocidade do Veículo:** Sensor de Velocidade na Transmissão (VSS) $\rightarrow$ PID `0x0D`
- **Temperatura do Arrefecimento:** Sensor NTC de Temperatura da Água (ECT) $\rightarrow$ PID `0x05`
- **Pressão MAP do Coletor:** Sensor Piezorresistivo de Pressão Absoluta $\rightarrow$ PID `0x0B`
- **Posição da Borboleta (TPS):** Potenciômetro Duplo de Aceleração $\rightarrow$ PID `0x11`
- **Temperatura do Ar de Admissão (IAT):** Sensor NTC no Coletor $\rightarrow$ PID `0x0F`
- **Combustível Real do Tanque:** Boia Resistiva analógica transmitida pelo Painel de Instrumentos original $\rightarrow$ CAN ID `0x430` (Byte 0)
- **Ponto de Ignição:** Ângulo de centelha calculado e aplicado em tempo real pela ECU $\rightarrow$ PID `0x0E` (° APMS)
- **Correção da Sonda Lambda (STFT & LTFT):** Realimentação de malha fechada do sensor de O₂ $\rightarrow$ PIDs `0x06` e `0x07` (%)
- **Diagnóstico e Falhas (MIL & DTCs):** Status da lâmpada de anomalia e contagem de erros gravados $\rightarrow$ PID `0x01`
- **Distância Parcial da Viagem (Trip km):** Integração direta baseada no sensor de velocidade real VSS.

### 🟡 Categoria `ESTIMADO`
Aplicada a qualquer parâmetro obtido por modelos matemáticos, interpolação, aproximação física ou síntese algorítmica:
- **Marcha Engatada (N, 1, 2, 3, 4, 5):** Estimada a partir da razão matemática entre RPM e Velocidade pelas relações de engrenagens do câmbio Ford IB5 e pneus 175/65 R14.
- **Consumo Instantâneo (km/L ou L/h):** Estimado pelo método aerodinâmico/termodinâmico *Speed-Density* através de MAP, RPM, IAT, cilindrada de 999 cm³ e relação ar/combustível estequiométrica (AFR 13,2).
- **Autonomia Restante (DTE - Distance to Empty):** Estimada multiplicando os litros reais do tanque pela média recente de consumo (km/L).
- **Consumo Acumulado da Viagem (Litros gastos):** Integração temporal da taxa estimada de fluxo de combustível.
- **Custo Financeiro da Viagem (R$):** Projeção financeira do consumo estimado $\times$ preço de referência do combustível.
- **Tensão da Bateria / Alternador (V):** Estimada via software baseada no estado de rotação do motor, **enquanto não houver conversor A/D (ADC) físico conectado ao Pino 16 (+12V)**. Deve exibir obrigatoriamente a etiqueta `ESTIMADO` e o subtítulo `Aprox. por RPM • Sem ADC Físico`.

---

## 4. Padrão de Estilização Visual no Cockpit

Para garantir legibilidade instantânea pelo condutor em tablet ou TV Box:

1. **Tag `REAL`:**
   - Cor do texto: `#00e676` (Verde Esmeralda) ou `#00d2ff` (Ciano)
   - Fundo: `rgba(0, 230, 118, 0.12)`
   - Borda: `1px solid rgba(0, 230, 118, 0.35)`
   - Tipografia: Caixa alta, peso 800, tamanho compacto (`8.5px` a `10px`).

2. **Tag `ESTIMADO`:**
   - Cor do texto: `#ffb300` (Âmbar / Laranja suave)
   - Fundo: `rgba(255, 179, 0, 0.12)`
   - Borda: `1px solid rgba(255, 179, 0, 0.40)`
   - Tipografia: Caixa alta, peso 800, tamanho compacto (`8.5px` a `10px`).

---

## 5. Roteiro para Migração de Grandezas Estimadas para Reais

Quando for implementado hardware dedicado complementar (ex: microcontrolador auxiliar Arduino/ESP32 com divisor resistivo $30\text{ k}\Omega / 7,5\text{ k}\Omega$ conectado ao Pino 16 do OBD-II para leitura analógica direta de 0 a 16V):
1. O backend receberá o valor medido real via porta serial/ADC.
2. A tag do card correspondente no painel migrará imediatamente de `ESTIMADO` para `REAL`.
3. O log em `Escopo do Projeto.txt` registrará a validação de hardware.

---

## 6. Diário de Bordo Obrigatório

Toda alteração estrutural, novo PID decodificado, ajuste de calibração ou alteração na stack do projeto Fiesta DEVE ser registrada no arquivo:
- [Escopo do Projeto.txt](file:///H:/Outros%20computadores/Meu%20computador/David-Pessoal/Projetos/Projeto%20Fiesta%20Zetec%20Rocam%201.0/Escopo%20do%20Projeto.txt)

---

## 7. Diretrizes de Arquitetura e Qualidade de Software (Versão 2.0)

A partir da Versão 2.0, todo Agente deve respeitar as seguintes regras de robustez:
1. **Watchdog Temporal (Anti-Freeze):** Nunca acumular distância (`trip_km`) ou combustível queimado caso a idade do dado de velocidade (`speed`) ou rotação (`rpm`) exceda o TTL configurado (padrão 1,5s).
2. **Modelo de Consumo Multicombustível:** O cálculo de consumo deve sempre levar em conta as correções da Sonda Lambda (`STFT` e `LTFT`) para compensar misturas Flex reais e o fator `fuel_calibration_k_factor` do `config.json`.
3. **Histerese em Grandezas Estimadas:** Qualquer variável discreta derivada (como o número da Marcha) deve passar por filtro de histerese (mínimo de 3 leituras consistentes) para evitar cintilação visual na tela do cluster durante transientes e acionamento de embreagem.
4. **Segurança de Endpoints:** Nenhuma rota que manipula arquivos no disco (download ou gravação de logs) pode receber nomes sem sanitização de Path Traversal (`Path(name).name`).
5. **Configuração Centralizada:** Valores de calibração, capacidade de tanque, reserva, preço de combustível e IDs de barramento NÃO devem ser codificados de forma rígida (hardcoded) nos módulos de código. Devem ser sempre obtidos de `config.json`.


---

## 8. Diretriz de Integridade da ECU Original (Escopo Estritamente Read-Only)

> [!IMPORTANT]
> **COMPROMISSO DE ORIGINALIDADE DE FÁBRICA:**  
> A calibração de fábrica, as tabelas de injeção/ignição, o limitador de rotação e o firmware original da central eletrônica Ford EEC-VI devem permanecer **100% INTACTOS**. É expressamente proibido qualquer tentativa de reflash, reprogramação ou escrita permanente na memória Flash da ECU.

Todas as interações do projeto com o veículo operam exclusivamente em regime de **Leitura Passiva e Diagnóstico Não-Intrusivo (Read-Only)**:
1. **Sniffer Passivo:** Opera em modo Listen-Only estrito (`L`), sem transmissão de dados e sem emissão de bits de ACK no barramento físico.
2. **Consultas de Diagnóstico:** Utilizam exclusivamente serviços de consulta de dados padrão homologados:
   - SAE J1979 Modo 01 (Dados Dinâmicos de Sensores em Tempo Real);
   - SAE J1979 Modo 03 (Leitura de Códigos de Falha DTCs);
   - Ford UDS Serviço 0x22 (*ReadDataByIdentifier* - Leitura pontual de parâmetros como CHT, bateria e hodômetro).
3. **Proibição Estrita de Serviços de Gravação:** Bloqueado qualquer envio de rotinas de escrita ou reprogramação de memória (Serviços UDS 0x34 *RequestDownload*, 0x36 *TransferData*, 0x37 *RequestTransferExit* ou Modo 04 de limpeza sem autorização).


---

## 9. Política de Versionamento e Preservação de Releases de APKs (apk/)

- **Arquivamento Permanente de Releases:** Toda compilação e release do aplicativo nativo Android (`Android_App_Fiesta/`) deve obrigatoriamente gerar e preservar na pasta `apk/` o arquivo versionado nominal correspondente ao `versionName` do `build.gradle` (ex: `Fiesta_Cockpit_USB_v2.2.0.apk`, `Fiesta_Cockpit_USB_v2.3.0.apk`, `Fiesta_Cockpit_USB_v2.3.1.apk`), mantendo concomitantemente o arquivo `Fiesta_Cockpit_USB.apk` atualizado como ponteiro da versão mais recente (*latest*).
- **Proibição de Deleção de Versões Históricas:** Nunca delete ou sobrescreva versões anteriores na pasta `apk/`. O histórico completo de builds permite ao usuário realizar rollbacks imediatos em caso de regressão e efetuar testes cruzados de estabilidade entre smartphone e tablet.
- **Automação no CI/CD:** O pipeline do GitHub Actions (`.github/workflows/build_android_apk.yml`) extrai automaticamente a variável `versionName` e publica ambos os arquivos no repositório.
