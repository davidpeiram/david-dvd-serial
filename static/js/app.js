/**
 * app.js - Painel Digital de Instrumentos do Ford Fiesta Zetec Rocam
 * Aplicação Final para Conector Físico OBD-II (LC_CANable_V2.1)
 */

document.addEventListener('DOMContentLoaded', () => {
  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
  // 1. Mostradores Circulares de Alta Performance (Canvas)
  const rpmGauge = new CircularGauge('gauge-rpm-canvas', {
    min: 0,
    max: 7000,
    redline: 6000,
    step: 1000,
    labelDivider: 1000,
    unit: 'RPM x1000',
  });

  const speedGauge = new CircularGauge('gauge-speed-canvas', {
    min: 0,
    max: 200,
    redline: 160,
    step: 20,
    labelDivider: 1,
    unit: 'km/h',
  });

  // 2. Elementos da Interface
  const elClock = document.getElementById('live-clock');
  const elConnBadge = document.getElementById('conn-info-badge');
  const elMilBadge = document.getElementById('mil-badge');
  const elMilIcon = document.getElementById('mil-icon');
  const elMilText = document.getElementById('mil-text');
  const elTorqueVal = document.getElementById('val-torque');
  const elTorqueProgress = document.getElementById('progress-torque');
  const elTorqueSub = document.getElementById('val-torque-sub');
  const elStatusDot = document.getElementById('status-dot');
  const elStatusText = document.getElementById('status-text');
  const btnFullscreen = document.getElementById('btn-fullscreen');

  const elRpmVal = document.getElementById('val-rpm');
  const elSpeedVal = document.getElementById('val-speed');
  const elGearVal = document.getElementById('val-gear');

  const elConsumptionVal = document.getElementById('val-consumption');
  const elConsumptionUnit = document.getElementById('unit-consumption');
  const elTripKm = document.getElementById('val-trip-km');
  const elTripTime = document.getElementById('val-trip-time');
  const elTripFuel = document.getElementById('val-trip-fuel');
  const elTripCost = document.getElementById('val-trip-cost');
  const elTripAvg = document.getElementById('val-trip-avg');

  const btnToggleLog = document.getElementById('btn-toggle-log');
  const btnLogText = document.getElementById('btn-log-text');
  const btnResetTrip = document.getElementById('btn-reset-trip');
  const btnOpenLogs = document.getElementById('btn-open-logs');

  const modalSummary = document.getElementById('modal-summary');
  const btnCloseSummary = document.getElementById('btn-close-summary');
  const btnDismissSummary = document.getElementById('btn-dismiss-summary');
  const btnDownloadCurrentLog = document.getElementById('btn-download-current-log');

  const modalLogsList = document.getElementById('modal-logs-list');
  const btnCloseLogsList = document.getElementById('btn-close-logs-list');
  const btnDismissLogsList = document.getElementById('btn-dismiss-logs-list');
  const logsContainer = document.getElementById('logs-container');

  const summaryDistance = document.getElementById('summary-distance');
  const summaryFuel = document.getElementById('summary-fuel');
  const summaryCost = document.getElementById('summary-cost');
  const summaryAvgKml = document.getElementById('summary-avg-kml');
  const summaryDuration = document.getElementById('summary-duration');
  const summarySpeed = document.getElementById('summary-speed');

  let isLoggingActive = false;
  let lastLogFileName = '';

  const elCoolantVal = document.getElementById('val-coolant');
  const elCoolantProgress = document.getElementById('progress-coolant');
  const elBatteryVal = document.getElementById('val-battery');
  const elBatteryProgress = document.getElementById('progress-battery');
  const elMapVal = document.getElementById('val-map');
  const elMapProgress = document.getElementById('progress-map');
  const elThrottleVal = document.getElementById('val-throttle');
  const elThrottleProgress = document.getElementById('progress-throttle');
  
  const elFuelVal = document.getElementById('val-fuel');
  const elFuelProgress = document.getElementById('progress-fuel');
  const elFuelSub = document.getElementById('val-fuel-sub');
  
  const elLoadVal = document.getElementById('val-load');
  const elLoadProgress = document.getElementById('progress-load');
  
  const elTimingVal = document.getElementById('val-timing');
  const elTimingProgress = document.getElementById('progress-timing');
  
  const elTrimStatus = document.getElementById('val-trim-status');
  const elTrimProgress = document.getElementById('progress-trim');
  const elTrimSub = document.getElementById('val-trim-sub');

  // 3. Relógio Digital Automotivo
  function updateClock() {
    const now = new Date();
    const h = String(now.getHours()).padStart(2, '0');
    const m = String(now.getMinutes()).padStart(2, '0');
    const s = String(now.getSeconds()).padStart(2, '0');
    if (elClock) elClock.textContent = `${h}:${m}:${s}`;
  }
  setInterval(updateClock, 1000);
  updateClock();

  // 4. Badge de Conexão com Reconexão Manual ao Clicar
  if (elConnBadge) {
    elConnBadge.style.cursor = 'pointer';
    elConnBadge.title = 'Clique para forçar reconexão à porta COM do CANable';
    elConnBadge.addEventListener('click', async () => {
      elConnBadge.textContent = 'PROCURANDO COM...';
      try {
        const res = await fetch('/api/reconnect', { method: 'POST' });
        const data = await res.json();
        console.log('[Reconnect]', data);
      } catch (err) {
        console.error('[Reconnect Error]', err);
      }
    });
  }

  // 5. Wake Lock API (Evita que a tela do tablet ou TV Box apague enquanto o carro estiver rodando)
  async function requestWakeLock() {
    if ('wakeLock' in navigator) {
      try {
        await navigator.wakeLock.request('screen');
        console.log('[Display] Wake Lock ativado: tela permanecerá acesa.');
      } catch (err) {
        console.warn('[Display] Wake Lock não pôde ser ativado:', err);
      }
    }
  }
  requestWakeLock();
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') requestWakeLock();
  });

  // 5. Botão Tela Cheia (Fullscreen)
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
        btnFullscreen.textContent = '🗗 Sair Cheia';
      } else {
        document.exitFullscreen().catch(() => {});
        btnFullscreen.textContent = '⛶ Tela Cheia';
      }
    });
  }

  // 6. Conexão WebSocket com o Servidor de Telemetria
  let ws = null;
  let reconnectTimer = null;

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[WebSocket] Conectado ao leitor OBD-II.');
      elStatusDot.classList.add('online');
      elStatusText.textContent = 'ONLINE / ECU CONECTADA';
      if (reconnectTimer) {
        clearInterval(reconnectTimer);
        reconnectTimer = null;
      }
    };

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        updateTelemetryUI(data);
      } catch (e) {
        console.error('[WebSocket] Erro ao decodificar JSON:', e);
      }
    };

    ws.onclose = () => {
      elStatusDot.classList.remove('online');
      elStatusText.textContent = 'BUSCANDO ECU...';
      if (!reconnectTimer) {
        reconnectTimer = setTimeout(connectWebSocket, 1500);
      }
    };

    ws.onerror = (err) => {
      console.error('[WebSocket] Erro:', err);
      ws.close();
    };
  }

  // 7. Atualização dos Sensores na Tela
  function updateTelemetryUI(data) {
    // Info da Conexão e Estado Discriminado (V2.0)
    if (elConnBadge && data.connection_info) {
      elConnBadge.textContent = data.connection_info;
    }

    const connState = data.connection_state || (data.connected ? 'ECU_CONNECTED' : 'DISCONNECTED');
    if (elStatusDot && elStatusText) {
      if (connState === 'ECU_CONNECTED') {
        elStatusDot.className = 'status-dot online';
        elStatusText.textContent = 'ECU ONLINE (500k)';
      } else if (connState === 'WAITING_ECU') {
        elStatusDot.className = 'status-dot waiting';
        elStatusText.textContent = 'AGUARDANDO ECU...';
      } else if (connState === 'DEMO') {
        elStatusDot.className = 'status-dot demo';
        elStatusText.textContent = 'DEMO BANCADA';
      } else {
        elStatusDot.className = 'status-dot offline';
        elStatusText.textContent = 'DESCONECTADO';
      }
    }

    // Mostradores Principais com Watchdog de Frescor (Stale Data)
    const rpm = data.rpm || 0;
    const speed = data.speed || 0;
    rpmGauge.setValue(rpm);
    speedGauge.setValue(speed);

    elRpmVal.textContent = rpm.toLocaleString();
    elSpeedVal.textContent = speed;

    if (data.rpm_stale) {
      elRpmVal.classList.add('stale-indicator');
    } else {
      elRpmVal.classList.remove('stale-indicator');
    }

    if (data.speed_stale) {
      elSpeedVal.classList.add('stale-indicator');
    } else {
      elSpeedVal.classList.remove('stale-indicator');
    }

    // Marcha Estimada (Câmbio Ford IB5)
    if (elGearVal) {
      elGearVal.textContent = data.gear || 'N';
      elGearVal.style.color = (data.gear === 'N') ? '#829ab1' : '#00d2ff';
    }

    // Consumo Instantâneo
    if (elConsumptionVal && elConsumptionUnit) {
      elConsumptionVal.textContent = data.fuel_economy_str || '--';
      elConsumptionUnit.textContent = data.fuel_economy_unit || 'km/L';
    }

    // Trip Computer e Combustível Gasto da Viagem
    if (elTripKm && data.trip_km !== undefined) {
      elTripKm.textContent = `${data.trip_km.toFixed(1)} km`;
    }
    if (elTripTime && data.trip_time_str) {
      elTripTime.textContent = data.trip_time_str;
    }
    if (elTripFuel && data.total_fuel_liters !== undefined) {
      elTripFuel.textContent = `${data.total_fuel_liters.toFixed(2)} L`;
    }
    if (elTripCost && data.trip_cost_brl !== undefined) {
      elTripCost.textContent = `R$ ${data.trip_cost_brl.toFixed(2).replace('.', ',')}`;
    }
    if (elTripAvg && data.avg_fuel_kml !== undefined) {
      elTripAvg.textContent = `${data.avg_fuel_kml.toFixed(1)} km/L`;
    }

    // Status de Gravação do Datalogger
    if (data.logging_active !== undefined) {
      isLoggingActive = data.logging_active;
      if (btnToggleLog && btnLogText) {
        if (isLoggingActive) {
          btnToggleLog.classList.add('recording');
          btnLogText.textContent = 'PARAR LOG';
        } else {
          btnToggleLog.classList.remove('recording');
          btnLogText.textContent = 'GRAVAR LOG';
        }
      }
    }

    // Temperatura do Líquido de Arrefecimento
    const coolant = data.coolant_temp || 0;
    elCoolantVal.textContent = coolant;
    elCoolantProgress.style.width = `${Math.min(100, Math.max(0, ((coolant - 40) / 80) * 100))}%`;

    elCoolantVal.classList.remove('temp-ok', 'temp-warm', 'temp-crit');
    if (coolant < 98) {
      elCoolantVal.classList.add('temp-ok');
      elCoolantProgress.style.background = 'linear-gradient(90deg, #3a7bd5, #00e676)';
    } else if (coolant < 105) {
      elCoolantVal.classList.add('temp-warm');
      elCoolantProgress.style.background = 'linear-gradient(90deg, #ff9900, #ff5500)';
    } else {
      elCoolantVal.classList.add('temp-crit');
      elCoolantProgress.style.background = 'linear-gradient(90deg, #ff3366, #ff0033)';
    }

    // Status da Injeção (Luz MIL e Falhas DTC com código alfanumérico Modo 03)
    if (elMilBadge && elMilIcon && elMilText) {
      if (data.mil_on || (data.dtc_count && data.dtc_count > 0)) {
        elMilBadge.className = 'mil-badge mil-alert';
        elMilIcon.textContent = '⚠️';
        const codes = data.dtc_codes_str || (data.dtc_codes && data.dtc_codes.join(', '));
        if (codes) {
          elMilText.textContent = `FALHA (${codes})`;
        } else {
          elMilText.textContent = `FALHA (${data.dtc_count || 1} DTC)`;
        }
      } else {
        elMilBadge.className = 'mil-badge mil-ok';
        elMilIcon.textContent = '✅';
        elMilText.textContent = 'INJEÇÃO OK';
      }
    }

    // Tensão da Bateria (Alternador)
    const battery = data.battery_voltage || 0;
    elBatteryVal.textContent = battery.toFixed(1);
    elBatteryProgress.style.width = `${Math.min(100, Math.max(0, ((battery - 10) / 5) * 100))}%`;
    elBatteryVal.style.color = (battery >= 13.5 && battery <= 14.8) ? '#00e676' : ((battery < 12.5) ? '#ff9900' : '#ffffff');

    // MAP
    const mapVal = data.map || 0;
    elMapVal.textContent = mapVal;
    elMapProgress.style.width = `${Math.min(100, Math.max(0, (mapVal / 105) * 100))}%`;

    // Torque Real do Motor (Engenharia Reversa Ford ID 0x422 Byte 6 em Nm)
    const torque = Number(data.engine_torque_nm) || 0;
    if (elTorqueVal) {
      elTorqueVal.textContent = torque.toFixed(0);
      if (torque > 75) {
        elTorqueVal.style.color = '#ff3366';
      } else if (torque > 40) {
        elTorqueVal.style.color = '#00d2ff';
      } else {
        elTorqueVal.style.color = '#00e676';
      }
    }
    if (elTorqueProgress) {
      // Escala 0 a 95 Nm (Torque máx do Fiesta 1.0 Rocam é 93 Nm / 9.5 kgfm)
      const pct = Math.min(100, Math.max(0, (torque / 93.0) * 100));
      elTorqueProgress.style.width = `${pct}%`;
      elTorqueProgress.style.background = (torque > 75)
        ? 'linear-gradient(90deg, #ff9900, #ff3366)'
        : 'linear-gradient(90deg, #00d2ff, #00e676)';
    }
    if (elTorqueSub) {
      const kgfm = (torque / 9.80665).toFixed(1);
      elTorqueSub.textContent = `${kgfm} kgfm • Máx 93 Nm (73 cv)`;
    }

    // Borboleta (TPS)
    const throttle = data.throttle || 0;
    elThrottleVal.textContent = throttle.toFixed(0);
    elThrottleProgress.style.width = `${throttle}%`;

    // Combustível Real da Boia (ID 0x430) e Autonomia
    const fuel = data.fuel_level !== undefined ? data.fuel_level : 49.0;
    const liters = data.fuel_liters !== undefined ? data.fuel_liters : 26.5;
    const range = data.range_km !== undefined ? data.range_km : 305;
    const isReserve = data.fuel_reserve || (liters <= 5.0);

    if (elFuelVal) {
      elFuelVal.textContent = fuel.toFixed(0);
      elFuelVal.style.color = isReserve ? '#ff3366' : '#ffffff';
    }
    if (elFuelProgress) {
      elFuelProgress.style.width = `${Math.min(100, Math.max(0, fuel))}%`;
      elFuelProgress.style.background = isReserve
        ? 'linear-gradient(90deg, #ff3366, #ff0033)'
        : 'linear-gradient(90deg, #00d2ff, #00e676)';
    }
    if (elFuelSub) {
      if (isReserve) {
        elFuelSub.innerHTML = `<span style="color: #ff3366; font-weight: 800;">⚠️ RESERVA</span> • ${liters.toFixed(1)} L / 54L • Auton: ~${range} km (Est.)`;
      } else {
        elFuelSub.textContent = `${liters.toFixed(1)} L / 54L • Auton: ~${range} km (Est.)`;
      }
    }

    // Carga do Motor (Engine Load)
    const load = data.engine_load || 0;
    if (elLoadVal) elLoadVal.textContent = load.toFixed(1);
    if (elLoadProgress) elLoadProgress.style.width = `${Math.min(100, Math.max(0, load))}%`;

    // Ponto de Ignição (Timing Advance)
    const timing = data.timing_advance !== undefined ? data.timing_advance : 0.0;
    if (elTimingVal) elTimingVal.textContent = (timing >= 0 ? '+' : '') + timing.toFixed(1);
    if (elTimingProgress) elTimingProgress.style.width = `${Math.min(100, Math.max(0, ((timing + 10) / 55) * 100))}%`;

    // Sonda Lambda e Ajustes de Mistura (STFT / LTFT)
    const stft = data.stft !== undefined ? data.stft : 0.0;
    const ltft = data.ltft !== undefined ? data.ltft : 0.0;
    if (elTrimSub) {
      elTrimSub.textContent = `STFT: ${stft > 0 ? '+' : ''}${stft.toFixed(1)}% • LTFT: ${ltft > 0 ? '+' : ''}${ltft.toFixed(1)}%`;
    }
    if (elTrimStatus) {
      if (Math.abs(stft) <= 5.0 && Math.abs(ltft) <= 5.0) {
        elTrimStatus.textContent = 'ESTEQUIOM.';
        elTrimStatus.style.color = '#00e676';
      } else if (stft < -8.0 || ltft < -8.0) {
        elTrimStatus.textContent = 'ENXUGANDO';
        elTrimStatus.style.color = '#00d2ff';
      } else if (stft > 8.0 || ltft > 8.0) {
        elTrimStatus.textContent = 'ENRIQUECENDO';
        elTrimStatus.style.color = '#ff9900';
      } else {
        elTrimStatus.textContent = 'NORMAL';
        elTrimStatus.style.color = '#ffffff';
      }
    }
    if (elTrimProgress) {
      elTrimProgress.style.width = `${Math.min(100, Math.max(0, ((stft + 25) / 50) * 100))}%`;
    }
  }

  // 8. Controles de Gravação de Log de Viagem (Datalogger)
  if (btnToggleLog) {
    btnToggleLog.addEventListener('click', async () => {
      if (!isLoggingActive) {
        try {
          const res = await fetch('/api/trip/start?prefix=viagem_fiesta', { method: 'POST' });
          const json = await res.json();
          if (json.status === 'started' || json.status === 'already_running') {
            lastLogFileName = json.filename;
            isLoggingActive = true;
            btnToggleLog.classList.add('recording');
            if (btnLogText) btnLogText.textContent = 'PARAR LOG';
          }
        } catch (err) {
          console.error('[Start Log Error]', err);
        }
      } else {
        try {
          const res = await fetch('/api/trip/stop', { method: 'POST' });
          const summary = await res.json();
          isLoggingActive = false;
          btnToggleLog.classList.remove('recording');
          if (btnLogText) btnLogText.textContent = 'GRAVAR LOG';

          if (summary.status === 'stopped') {
            lastLogFileName = summary.filename;
            if (summaryDistance) summaryDistance.textContent = `${summary.distance_km} km`;
            if (summaryFuel) summaryFuel.textContent = `${summary.fuel_spent_liters.toFixed(2)} L`;
            if (summaryCost) summaryCost.textContent = `R$ ${summary.estimated_cost_brl.toFixed(2).replace('.', ',')}`;
            if (summaryAvgKml) summaryAvgKml.textContent = `${summary.avg_consumption_kml} km/L`;
            if (summaryDuration) summaryDuration.textContent = summary.duration_str;
            if (summarySpeed) summarySpeed.textContent = `${summary.avg_speed_kmh} / ${summary.max_speed_kmh} km/h`;

            if (modalSummary) modalSummary.classList.add('active');
          }
        } catch (err) {
          console.error('[Stop Log Error]', err);
        }
      }
    });
  }

  // Zerar Viagem (Reset Trip)
  if (btnResetTrip) {
    btnResetTrip.addEventListener('click', async () => {
      if (confirm('Deseja zerar o odômetro e o combustível gasto para iniciar uma nova viagem?')) {
        try {
          await fetch('/api/trip/reset', { method: 'POST' });
          if (elTripKm) elTripKm.textContent = '0.0 km';
          if (elTripTime) elTripTime.textContent = '00:00:00';
          if (elTripFuel) elTripFuel.textContent = '0.00 L';
          if (elTripCost) elTripCost.textContent = 'R$ 0,00';
          if (elTripAvg) elTripAvg.textContent = '0.0 km/L';
        } catch (err) {
          console.error('[Reset Trip Error]', err);
        }
      }
    });
  }

  // Baixar log do modal de resumo
  if (btnDownloadCurrentLog) {
    btnDownloadCurrentLog.addEventListener('click', () => {
      if (lastLogFileName) {
        window.open(`/api/logs/download/${lastLogFileName}`, '_blank');
      }
    });
  }

  // Fechar modal de resumo
  if (btnCloseSummary) btnCloseSummary.addEventListener('click', () => modalSummary.classList.remove('active'));
  if (btnDismissSummary) btnDismissSummary.addEventListener('click', () => modalSummary.classList.remove('active'));

  // Abrir lista de logs gravados
  if (btnOpenLogs) {
    btnOpenLogs.addEventListener('click', async () => {
      try {
        const res = await fetch('/api/logs');
        const files = await res.json();
        if (logsContainer) {
          if (!files || files.length === 0) {
            logsContainer.innerHTML = '<div style="color: #94a3b8; text-align: center; padding: 24px;">Nenhum arquivo de log gravado ainda.<br><br>Clique em <b>GRAVAR LOG</b> no painel antes de sair de casa!</div>';
          } else {
            logsContainer.innerHTML = files.map(f => `
              <div style="display: flex; justify-content: space-between; align-items: center; background: rgba(0,0,0,0.35); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px; padding: 10px 14px; margin-bottom: 8px;">
                <div>
                  <div style="font-weight: 700; font-size: 13px; color: #f0f4f8;">${escapeHtml(f.filename)}</div>
                  <div style="font-size: 11px; color: #94a3b8; margin-top: 2px;">${escapeHtml(f.modified)} • ${escapeHtml(f.size_kb)} KB</div>
                </div>
                <a href="/api/logs/download/${encodeURIComponent(f.filename)}" download style="background: linear-gradient(135deg, #2563eb, #00d2ff); color: #fff; text-decoration: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; font-weight: 700;">Baixar CSV</a>
              </div>
            `).join('');
          }
        }
        if (modalLogsList) modalLogsList.classList.add('active');
      } catch (err) {
        console.error('[List Logs Error]', err);
      }
    });
  }

  if (btnCloseLogsList) btnCloseLogsList.addEventListener('click', () => modalLogsList.classList.remove('active'));
  if (btnDismissLogsList) btnDismissLogsList.addEventListener('click', () => modalLogsList.classList.remove('active'));

  connectWebSocket();
});
