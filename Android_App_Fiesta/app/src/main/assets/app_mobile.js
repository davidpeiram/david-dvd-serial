/**
 * app_mobile.js - Motor Nativo de Telemetria OBD-II / HS-CAN para Android (CANable V2.1)
 * Ford Fiesta Sedan 1.0 Zetec Rocam Flex (ECU Ford EEC-VI • 500 kbps)
 */

document.addEventListener('DOMContentLoaded', () => {
  // 1. Seletor de Temas com Persistência
  const themeSelect = document.getElementById('theme-switcher');
  const savedTheme = localStorage.getItem('html_manual_theme') || localStorage.getItem('html_estudos_theme') || 'dark';
  document.documentElement.setAttribute('data-theme', savedTheme);
  if (themeSelect) {
    themeSelect.value = savedTheme;
    themeSelect.addEventListener('change', (e) => {
      const val = e.target.value;
      document.documentElement.setAttribute('data-theme', val);
      localStorage.setItem('html_manual_theme', val);
      localStorage.setItem('html_estudos_theme', val);
    });
  }

  // 2. Mostradores Circulares (Canvas)
  const rpmGauge = new CircularGauge('gauge-rpm-canvas', {
    min: 0, max: 7000, redline: 6000, step: 1000, labelDivider: 1000, unit: 'RPM x1000',
  });
  const speedGauge = new CircularGauge('gauge-speed-canvas', {
    min: 0, max: 200, redline: 160, step: 20, labelDivider: 1, unit: 'km/h',
  });

  // 3. Referências de UI
  const elClock = document.getElementById('live-clock');
  const elAcBadge = document.getElementById('ac-badge');
  const elConnBadge = document.getElementById('conn-info-badge');
  const elMilBadge = document.getElementById('mil-badge');
  const elMilIcon = document.getElementById('mil-icon');
  const elMilText = document.getElementById('mil-text');
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
  const elTorqueVal = document.getElementById('val-torque');
  const elTorqueProgress = document.getElementById('progress-torque');
  const elTorqueSub = document.getElementById('val-torque-sub');

  // Relógio
  setInterval(() => {
    const now = new Date();
    if (elClock) elClock.textContent = now.toTimeString().slice(0, 8);
  }, 1000);

  // Tela Cheia
  let isFull = false;
  if (btnFullscreen) {
    btnFullscreen.addEventListener('click', () => {
      isFull = !isFull;
      if (window.AndroidUSB && window.AndroidUSB.toggleFullscreen) {
        window.AndroidUSB.toggleFullscreen(isFull);
      } else if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(() => {});
      } else {
        document.exitFullscreen().catch(() => {});
      }
      btnFullscreen.textContent = isFull ? '🗗 Normal' : '⛶ Cheia';
    });
  }

  // 4. Detector de Marchas Calibrado (Câmbio Ford IB5 1.0 Flex - Pneus 175/65 R14)
  const GEAR_RATIO_RANGES = [
    [1, 130.0, 240.0], // 1ª Marcha (centro ~175)
    [2, 80.0, 129.9],  // 2ª Marcha (centro ~101)
    [3, 55.0, 79.9],   // 3ª Marcha (centro ~65)
    [4, 41.5, 54.9],   // 4ª Marcha (centro ~47)
    [5, 24.0, 41.4],   // 5ª Marcha (centro ~37)
  ];
  const gearHistory = [];
  let currentStableGear = 'N';
  let outOfRangeCounter = 0;

  function detectGear(rpm, speed) {
    if (speed < 4 || rpm < 400) {
      gearHistory.length = 0;
      currentStableGear = 'N';
      outOfRangeCounter = 0;
      return 'N';
    }
    const ratio = rpm / speed;
    let candidate = 'N';
    for (const [g, minR, maxR] of GEAR_RATIO_RANGES) {
      if (ratio >= minR && ratio <= maxR) {
        candidate = String(g);
        break;
      }
    }
    if (candidate !== 'N') {
      outOfRangeCounter = 0;
      gearHistory.push(candidate);
      if (gearHistory.length > 4) gearHistory.shift();
      const matches = gearHistory.filter(x => x === candidate).length;
      if (matches >= 3) currentStableGear = candidate;
    } else {
      outOfRangeCounter++;
      if (outOfRangeCounter > 4) {
        currentStableGear = 'N';
        gearHistory.length = 0;
      }
    }
    return currentStableGear;
  }

  // 5. Cálculo de Consumo Speed-Density V2.0 (Com compensação STFT + LTFT)
  function calcSpeedDensity(rpm, mapKpa, iatC, speedKmh, stft, ltft) {
    if (rpm < 350) return { lph: 0.0, kml: null, str: '0.0', unit: 'L/h' };
    const iatK = Math.max(240.0, iatC + 273.15);
    const rpmNorm = Math.min(1.0, rpm / 4700.0);
    const ve = 0.68 + (0.18 * rpmNorm);
    const imap = (rpm * mapKpa) / (2.0 * iatK);
    const mafGps = (imap * 0.999 * ve * 28.97) / (8.314 * 60.0);
    const totalTrim = stft + ltft;
    const trimMult = Math.max(0.65, Math.min(1.35, 1.0 + (totalTrim / 100.0)));
    const fuelGps = (mafGps / 13.2) * trimMult;
    const lph = Math.max(0.0, (fuelGps * 3600.0) / 750.0);

    if (speedKmh < 3) {
      return { lph, kml: null, str: lph.toFixed(1), unit: 'L/h' };
    } else {
      const kml = Math.min(99.9, Math.max(0.5, speedKmh / Math.max(0.01, lph)));
      return { lph, kml, str: kml.toFixed(1), unit: 'km/L' };
    }
  }

  // 6. Estado Central de Telemetria
  const state = {
    usbConnected: false,
    ecuResponding: false,
    lastEcuRespMs: 0,
    lastRpmMs: 0,
    lastSpeedMs: 0,
    rpm: 0,
    speed: 0,
    gear: 'N',
    map: 38,
    throttle: 0.0,
    engineLoad: 0.0,
    timingAdvance: 3.0,
    coolantTemp: 0,
    intakeTemp: 30,
    stft: 0.0,
    ltft: 0.0,
    fuelLevel: 49.0,
    fuelLiters: 26.5,
    batteryVoltage: 12.5,
    engineTorqueNm: 0.0,
    acClutch: false,
    acPressureBar: 0.0,
    milOn: false,
    dtcCount: 0,
    dtcCodes: [],
    fuelRateLph: 0.0,
    fuelEcoStr: '--',
    fuelEcoUnit: 'km/L',
    tripKm: 0.0,
    totalFuelLiters: 0.0,
    sessionStartMs: Date.now(),
    lastCalcMs: Date.now(),
  };

  // 7. Terminal Modal & Log
  const modalTerminal = document.getElementById('modal-terminal');
  const termLog = document.getElementById('terminal-log');
  const btnOpenTerminal = document.getElementById('btn-open-terminal');
  const btnCloseTerminal = document.getElementById('btn-close-terminal');

  function appendTermLog(msg, cls = 'term-info') {
    if (!termLog) return;
    const div = document.createElement('div');
    div.className = `term-row ${cls}`;
    const t = new Date().toTimeString().slice(0, 8);
    div.textContent = `[${t}] ${msg}`;
    termLog.appendChild(div);
    if (termLog.children.length > 150) termLog.removeChild(termLog.firstChild);
    termLog.scrollTop = termLog.scrollHeight;
  }

  if (btnOpenTerminal) {
    btnOpenTerminal.addEventListener('click', () => {
      modalTerminal.classList.add('active');
    });
  }
  if (btnCloseTerminal) {
    btnCloseTerminal.addEventListener('click', () => {
      modalTerminal.classList.remove('active');
    });
  }

  function sendSlcan(cmd, logIt = false) {
    if (logIt) appendTermLog(`TX -> ${cmd}`, 'term-tx');
    if (window.AndroidUSB && window.AndroidUSB.sendCommand) {
      window.AndroidUSB.sendCommand(cmd);
    }
  }

  document.getElementById('btn-term-connect')?.addEventListener('click', () => {
    appendTermLog('Solicitando conexão USB ao Android...', 'term-info');
    if (window.AndroidUSB) window.AndroidUSB.connect();
  });
  document.getElementById('btn-term-ver')?.addEventListener('click', () => sendSlcan('V', true));
  document.getElementById('btn-term-init500')?.addEventListener('click', () => {
    sendSlcan('C', true);
    setTimeout(() => sendSlcan('S6', true), 40);
    setTimeout(() => sendSlcan('O', true), 80);
  });
  document.getElementById('btn-term-dtc')?.addEventListener('click', () => {
    sendSlcan('t7E0801030000000000', true);
  });
  document.getElementById('btn-term-clear')?.addEventListener('click', () => {
    if (termLog) termLog.innerHTML = '';
  });
  document.getElementById('btn-term-send')?.addEventListener('click', () => {
    const inp = document.getElementById('term-custom-input');
    if (inp && inp.value.trim()) {
      sendSlcan(inp.value.trim(), true);
      inp.value = '';
    }
  });

  if (elConnBadge) {
    elConnBadge.addEventListener('click', () => {
      if (window.AndroidUSB) window.AndroidUSB.connect();
    });
  }

  // 8. Recepção de Eventos Nativos do Android (Java -> JS)
  window.onNativeUsbStatus = (status, message) => {
    appendTermLog(`USB [${status}]: ${message}`, status === 'ERROR' ? 'term-err' : 'term-info');
    if (status === 'CONNECTED') {
      state.usbConnected = true;
      if (elConnBadge) elConnBadge.textContent = message || 'CANABLE 500K';
      if (elStatusDot) elStatusDot.className = 'status-dot waiting';
      if (elStatusText) elStatusText.textContent = 'AGUARDANDO ECU...';
    } else if (status === 'DISCONNECTED' || status === 'ERROR') {
      state.usbConnected = false;
      state.ecuResponding = false;
      if (elStatusDot) elStatusDot.className = 'status-dot offline';
      if (elStatusText) elStatusText.textContent = 'USB DESCONECTADO';
    }
  };

  window.onNativeSlcanFrame = (line) => {
    if (!line) return;
    if (modalTerminal && modalTerminal.classList.contains('active')) {
      appendTermLog(`RX <- ${line}`, 'term-rx');
    }

    if (!line.startsWith('t') || line.length < 5) return;
    const canId = parseInt(line.slice(1, 4), 16);
    const dlc = parseInt(line.slice(4, 5), 16);
    const hexData = line.slice(5, 5 + dlc * 2);
    if (hexData.length < dlc * 2) return;

    const bytes = [];
    for (let i = 0; i < hexData.length; i += 2) {
      bytes.push(parseInt(hexData.slice(i, i + 2), 16));
    }

    const now = Date.now();

    // 1. Broadcast 0x430: Nível Real da Boia do Tanque (Byte 0 / 2.55)
    if (canId === 0x430 && bytes.length >= 1) {
      state.fuelLevel = Math.round((bytes[0] / 2.55) * 10) / 10;
      state.fuelLiters = Math.round((state.fuelLevel / 100.0) * 54.0 * 10) / 10;
      return;
    }

    // 2. Broadcast 0x422: Torque Real do Motor (Byte 0) e Ar-Condicionado (Bytes 5 e 6)
    if (canId === 0x422 && bytes.length >= 1) {
      const b0 = bytes[0];
      state.engineTorqueNm = b0 > 0 ? Math.round((8.0 + 85.0 * (b0 / 255.0)) * 10) / 10 : (state.rpm > 400 ? 8.0 : 0.0);
      if (bytes.length >= 7) {
        state.acClutch = (bytes[5] === 0x48) || ((bytes[5] & 0x08) !== 0);
        state.acPressureBar = bytes[6];
      }
      return;
    }

    // 3. Resposta de Diagnóstico da ECU do Motor Ford EEC-VI (0x7E8)
    if (canId === 0x7E8 && bytes.length >= 3) {
      state.ecuResponding = true;
      state.lastEcuRespMs = now;

      const mode = bytes[1];
      const pid = bytes[2];

      // Resposta Modo 01 (0x41)
      if (mode === 0x41 && bytes.length >= 4) {
        const A = bytes[3];
        const B = bytes.length >= 5 ? bytes[4] : 0;

        switch (pid) {
          case 0x0C: // RPM
            state.rpm = Math.floor(((A * 256) + B) / 4);
            state.lastRpmMs = now;
            break;
          case 0x0D: // Speed km/h
            state.speed = A;
            state.lastSpeedMs = now;
            break;
          case 0x11: // TPS %
            state.throttle = Math.round((A * 100.0) / 255.0 * 10) / 10;
            break;
          case 0x04: // Engine Load %
            state.engineLoad = Math.round((A * 100.0) / 255.0 * 10) / 10;
            break;
          case 0x0B: // MAP kPa
            state.map = A;
            break;
          case 0x0E: // Timing Advance
            state.timingAdvance = Math.round(((A / 2.0) - 64.0) * 10) / 10;
            break;
          case 0x05: // Coolant Temp °C
            state.coolantTemp = A - 40;
            break;
          case 0x0F: // IAT °C
            state.intakeTemp = A - 40;
            break;
          case 0x06: // STFT %
            state.stft = Math.round(((A - 128) * 100.0 / 128.0) * 10) / 10;
            break;
          case 0x07: // LTFT %
            state.ltft = Math.round(((A - 128) * 100.0 / 128.0) * 10) / 10;
            break;
          case 0x01: // MIL & DTC Count
            state.milOn = (A & 0x80) !== 0;
            state.dtcCount = A & 0x7F;
            break;
        }
      }
    }
  };

  // 9. Scheduler de Requisições OBD-II (Prioridades 1, 2 e 3 em 0x7E0)
  const p1Pids = [0x0C, 0x0D, 0x11];
  const p2Pids = [0x04, 0x0B, 0x0E];
  const p3Pids = [0x05, 0x0F, 0x06, 0x07, 0x01];
  let pollStep = 0;
  let p2Idx = 0;
  let p3Idx = 0;

  setInterval(() => {
    if (!state.usbConnected) return;
    let pidToQuery;
    const mod = pollStep % 5;
    if (mod < 3) {
      pidToQuery = p1Pids[mod]; // RPM, Speed, TPS com máxima frequência
    } else if (mod === 3) {
      pidToQuery = p2Pids[p2Idx % p2Pids.length];
      p2Idx++;
    } else {
      pidToQuery = p3Pids[p3Idx % p3Pids.length];
      p3Idx++;
    }
    pollStep++;
    const pidHex = pidToQuery.toString(16).toUpperCase().padStart(2, '0');
    sendSlcan(`t7E080201${pidHex}00000000`, false);
  }, 42);

  // 10. Datalogger CSV (25 Colunas idênticas ao PC)
  let isLogging = false;
  let currentLogRows = [];
  let currentLogName = '';
  let logStartKm = 0;
  let logStartFuel = 0;
  let logStartMs = 0;
  let logMaxSpeed = 0;

  const CSV_HEADERS = [
    'timestamp', 'datetime', 'rpm', 'speed_kmh', 'gear', 'throttle_pct',
    'engine_load_pct', 'map_kpa', 'coolant_temp_c', 'intake_temp_c',
    'timing_advance_deg', 'stft_pct', 'ltft_pct', 'fuel_level_pct',
    'fuel_liters_tank', 'battery_voltage_v', 'fuel_rate_lph', 'fuel_economy_str',
    'trip_fuel_liters', 'trip_km', 'avg_kml', 'mil_on', 'dtc_count',
    'ecu_responding', 'engine_torque_nm'
  ];

  function formatDuration(sec) {
    const h = String(Math.floor(sec / 3600)).padStart(2, '0');
    const m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
    const s = String(Math.floor(sec % 60)).padStart(2, '0');
    return `${h}:${m}:${s}`;
  }

  // Loop de Integração Física, Watchdog e Renderização (10 Hz)
  setInterval(() => {
    const now = Date.now();
    const dtSec = Math.min(1.0, Math.max(0.001, (now - state.lastCalcMs) / 1000.0));
    state.lastCalcMs = now;

    const rpmStale = (now - state.lastRpmMs) > 1500;
    const speedStale = (now - state.lastSpeedMs) > 1500;
    state.ecuResponding = (now - state.lastEcuRespMs) <= 2000;

    const curRpm = rpmStale ? 0 : state.rpm;
    const curSpd = speedStale ? 0 : state.speed;

    state.gear = detectGear(curRpm, curSpd);
    state.batteryVoltage = curRpm > 450 ? 14.2 : 12.5;

    const sd = calcSpeedDensity(curRpm, state.map, state.intakeTemp, curSpd, state.stft, state.ltft);
    state.fuelRateLph = sd.lph;
    state.fuelEcoStr = sd.str;
    state.fuelEcoUnit = sd.unit;

    if (!speedStale && curSpd > 0) {
      state.tripKm += (curSpd / 3600.0) * dtSec;
    }
    if (!rpmStale && curRpm > 350) {
      state.totalFuelLiters += (state.fuelRateLph / 3600.0) * dtSec;
    }

    const avgKml = state.totalFuelLiters > 0.005
      ? Math.min(99.9, state.tripKm / state.totalFuelLiters)
      : 0.0;
    const tripCost = state.totalFuelLiters * 6.30;
    const refKml = avgKml > 3.0 ? avgKml : 11.5;
    const rangeKm = Math.round(state.fuelLiters * refKml);
    const tripTimeStr = formatDuration((now - state.sessionStartMs) / 1000.0);

    // Grava linha no Datalogger se ativo (10 Hz)
    if (isLogging) {
      if (curSpd > logMaxSpeed) logMaxSpeed = curSpd;
      const iso = new Date(now);
      const dtStr = iso.toISOString().replace('T', ' ').slice(0, 23);
      currentLogRows.push([
        (now / 1000.0).toFixed(3),
        dtStr,
        curRpm,
        curSpd,
        state.gear,
        state.throttle.toFixed(1),
        state.engineLoad.toFixed(1),
        state.map,
        state.coolantTemp,
        state.intakeTemp,
        state.timingAdvance.toFixed(1),
        state.stft.toFixed(1),
        state.ltft.toFixed(1),
        state.fuelLevel.toFixed(1),
        state.fuelLiters.toFixed(1),
        state.batteryVoltage.toFixed(2),
        state.fuelRateLph.toFixed(2),
        `${state.fuelEcoStr} ${state.fuelEcoUnit}`,
        state.totalFuelLiters.toFixed(4),
        state.tripKm.toFixed(3),
        avgKml.toFixed(2),
        state.milOn,
        state.dtcCount,
        state.ecuResponding,
        state.engineTorqueNm.toFixed(1)
      ].join(','));
    }

    // Atualiza UI
    if (elStatusDot && elStatusText) {
      if (state.ecuResponding) {
        elStatusDot.className = 'status-dot online';
        elStatusText.textContent = 'ECU ONLINE (500k)';
      } else if (state.usbConnected) {
        elStatusDot.className = 'status-dot waiting';
        elStatusText.textContent = 'AGUARDANDO ECU...';
      } else {
        elStatusDot.className = 'status-dot offline';
        elStatusText.textContent = 'DESCONECTADO';
      }
    }

    if (elAcBadge) {
      if (state.acClutch) {
        elAcBadge.textContent = `❄️ A/C ON (${state.acPressureBar} Bar)`;
        elAcBadge.style.background = 'rgba(0, 230, 118, 0.16)';
        elAcBadge.style.color = '#00e676';
        elAcBadge.style.borderColor = 'rgba(0, 230, 118, 0.4)';
      } else {
        elAcBadge.textContent = '❄️ A/C OFF';
        elAcBadge.style.background = 'rgba(148,163,184,0.12)';
        elAcBadge.style.color = '#94a3b8';
        elAcBadge.style.borderColor = 'rgba(148,163,184,0.25)';
      }
    }

    rpmGauge.setValue(curRpm);
    speedGauge.setValue(curSpd);
    if (elRpmVal) elRpmVal.textContent = curRpm.toLocaleString();
    if (elSpeedVal) elSpeedVal.textContent = curSpd;
    if (elGearVal) {
      elGearVal.textContent = state.gear;
      elGearVal.style.color = state.gear === 'N' ? '#829ab1' : '#00d2ff';
    }
    if (elConsumptionVal) elConsumptionVal.textContent = state.fuelEcoStr;
    if (elConsumptionUnit) elConsumptionUnit.textContent = state.fuelEcoUnit;
    if (elTripKm) elTripKm.textContent = `${state.tripKm.toFixed(1)} km`;
    if (elTripTime) elTripTime.textContent = tripTimeStr;
    if (elTripFuel) elTripFuel.textContent = `${state.totalFuelLiters.toFixed(2)} L`;
    if (elTripCost) elTripCost.textContent = `R$ ${tripCost.toFixed(2).replace('.', ',')}`;
    if (elTripAvg) elTripAvg.textContent = `${avgKml.toFixed(1)} km/L`;

    if (elCoolantVal) elCoolantVal.textContent = state.coolantTemp;
    if (elCoolantProgress) elCoolantProgress.style.width = `${Math.min(100, Math.max(0, ((state.coolantTemp - 40) / 80) * 100))}%`;

    if (elBatteryVal) elBatteryVal.textContent = state.batteryVoltage.toFixed(1);
    if (elBatteryProgress) elBatteryProgress.style.width = `${Math.min(100, Math.max(0, ((state.batteryVoltage - 10) / 5) * 100))}%`;

    if (elMapVal) elMapVal.textContent = state.map;
    if (elMapProgress) elMapProgress.style.width = `${Math.min(100, Math.max(0, (state.map / 105) * 100))}%`;

    if (elThrottleVal) elThrottleVal.textContent = state.throttle.toFixed(0);
    if (elThrottleProgress) elThrottleProgress.style.width = `${state.throttle}%`;

    const isReserve = state.fuelLiters <= 5.0;
    if (elFuelVal) {
      elFuelVal.textContent = state.fuelLevel.toFixed(0);
      elFuelVal.style.color = isReserve ? '#ff3366' : '#ffffff';
    }
    if (elFuelProgress) elFuelProgress.style.width = `${Math.min(100, Math.max(0, state.fuelLevel))}%`;
    if (elFuelSub) elFuelSub.textContent = `${state.fuelLiters.toFixed(1)} L / 54L • Auton: ~${rangeKm} km (Est.)`;

    if (elLoadVal) elLoadVal.textContent = state.engineLoad.toFixed(1);
    if (elLoadProgress) elLoadProgress.style.width = `${Math.min(100, Math.max(0, state.engineLoad))}%`;

    if (elTimingVal) elTimingVal.textContent = (state.timingAdvance >= 0 ? '+' : '') + state.timingAdvance.toFixed(1);
    if (elTimingProgress) elTimingProgress.style.width = `${Math.min(100, Math.max(0, ((state.timingAdvance + 10) / 55) * 100))}%`;

    if (elTrimSub) elTrimSub.textContent = `STFT: ${state.stft >= 0 ? '+' : ''}${state.stft.toFixed(1)}% • LTFT: ${state.ltft >= 0 ? '+' : ''}${state.ltft.toFixed(1)}%`;
    if (elTrimStatus) {
      if (Math.abs(state.stft) <= 5 && Math.abs(state.ltft) <= 5) {
        elTrimStatus.textContent = 'ESTEQUIOM.';
        elTrimStatus.style.color = '#00e676';
      } else if (state.stft < -8 || state.ltft < -8) {
        elTrimStatus.textContent = 'ENXUGANDO';
        elTrimStatus.style.color = '#00d2ff';
      } else {
        elTrimStatus.textContent = 'NORMAL';
        elTrimStatus.style.color = '#ffffff';
      }
    }
    if (elTrimProgress) elTrimProgress.style.width = `${Math.min(100, Math.max(0, ((state.stft + 25) / 50) * 100))}%`;

    if (elTorqueVal) elTorqueVal.textContent = state.engineTorqueNm.toFixed(0);
    if (elTorqueProgress) elTorqueProgress.style.width = `${Math.min(100, Math.max(0, (state.engineTorqueNm / 93.0) * 100))}%`;
    if (elTorqueSub) {
      const kgfm = (state.engineTorqueNm / 9.80665).toFixed(1);
      elTorqueSub.textContent = `${kgfm} kgfm • Máx 93 Nm (73 cv)`;
    }
  }, 100);

  // 11. Controles de Gravação e Exportação de Logs CSV no Android
  const btnToggleLog = document.getElementById('btn-toggle-log');
  const btnLogText = document.getElementById('btn-log-text');
  const btnResetTrip = document.getElementById('btn-reset-trip');
  const btnOpenLogs = document.getElementById('btn-open-logs');
  const modalSummary = document.getElementById('modal-summary');
  const modalLogsList = document.getElementById('modal-logs-list');

  let lastSavedCsvContent = '';
  let lastSavedCsvFilename = '';

  function getStoredLogs() {
    try {
      return JSON.parse(localStorage.getItem('fiesta_mobile_logs') || '[]');
    } catch (e) {
      return [];
    }
  }

  function saveStoredLog(name, csvContent, summaryText) {
    const list = getStoredLogs();
    list.unshift({
      filename: name,
      modified: new Date().toLocaleString('pt-BR'),
      size_kb: (csvContent.length / 1024).toFixed(1),
      summary: summaryText,
      content: csvContent
    });
    if (list.length > 8) list.pop();
    try {
      localStorage.setItem('fiesta_mobile_logs', JSON.stringify(list));
    } catch (e) {}
  }

  function exportCsvFile(filename, content) {
    if (window.AndroidUSB && window.AndroidUSB.saveAndShareCsv) {
      window.AndroidUSB.saveAndShareCsv(filename, content);
    } else {
      const blob = new Blob([content], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      a.click();
    }
  }

  if (btnToggleLog) {
    btnToggleLog.addEventListener('click', () => {
      if (!isLogging) {
        const now = new Date();
        const pad = n => String(n).padStart(2, '0');
        currentLogName = `viagem_fiesta_${now.getFullYear()}-${pad(now.getMonth()+1)}-${pad(now.getDate())}_${pad(now.getHours())}-${pad(now.getMinutes())}-${pad(now.getSeconds())}.csv`;
        currentLogRows = [CSV_HEADERS.join(',')];
        logStartKm = state.tripKm;
        logStartFuel = state.totalFuelLiters;
        logStartMs = Date.now();
        logMaxSpeed = 0;
        isLogging = true;
        btnToggleLog.classList.add('recording');
        if (btnLogText) btnLogText.textContent = 'PARAR LOG';
      } else {
        isLogging = false;
        btnToggleLog.classList.remove('recording');
        if (btnLogText) btnLogText.textContent = 'GRAVAR LOG';

        const dist = Math.max(0, state.tripKm - logStartKm);
        const fuel = Math.max(0, state.totalFuelLiters - logStartFuel);
        const cost = fuel * 6.30;
        const avg = fuel > 0.002 ? (dist / fuel) : 0.0;
        const durSec = Math.max(1, (Date.now() - logStartMs) / 1000.0);
        const avgSpd = (dist / (durSec / 3600.0));

        lastSavedCsvFilename = currentLogName;
        lastSavedCsvContent = currentLogRows.join('\n');
        saveStoredLog(lastSavedCsvFilename, lastSavedCsvContent, `${dist.toFixed(2)} km • ${currentLogRows.length - 1} amostras`);

        document.getElementById('summary-distance').textContent = `${dist.toFixed(2)} km`;
        document.getElementById('summary-fuel').textContent = `${fuel.toFixed(2)} L`;
        document.getElementById('summary-cost').textContent = `R$ ${cost.toFixed(2).replace('.', ',')}`;
        document.getElementById('summary-avg-kml').textContent = `${avg.toFixed(1)} km/L`;
        document.getElementById('summary-duration').textContent = formatDuration(durSec);
        document.getElementById('summary-speed').textContent = `${avgSpd.toFixed(1)} / ${logMaxSpeed} km/h`;

        if (modalSummary) modalSummary.classList.add('active');
      }
    });
  }

  document.getElementById('btn-download-current-log')?.addEventListener('click', () => {
    if (lastSavedCsvContent) {
      exportCsvFile(lastSavedCsvFilename, lastSavedCsvContent);
    }
  });

  document.getElementById('btn-close-summary')?.addEventListener('click', () => modalSummary?.classList.remove('active'));
  document.getElementById('btn-dismiss-summary')?.addEventListener('click', () => modalSummary?.classList.remove('active'));

  if (btnResetTrip) {
    btnResetTrip.addEventListener('click', () => {
      if (confirm('Deseja zerar o odômetro parcial e o combustível gasto da viagem?')) {
        state.tripKm = 0.0;
        state.totalFuelLiters = 0.0;
        state.sessionStartMs = Date.now();
      }
    });
  }

  if (btnOpenLogs) {
    btnOpenLogs.addEventListener('click', () => {
      const container = document.getElementById('logs-container');
      const list = getStoredLogs();
      if (container) {
        if (!list.length) {
          container.innerHTML = '<div style="color: #94a3b8; text-align: center; padding: 20px;">Nenhuma viagem gravada ainda.<br>Toque em <b>GRAVAR LOG</b> antes de sair com o carro!</div>';
        } else {
          container.innerHTML = list.map((item, idx) => `
            <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(0,0,0,0.35);border:1px solid rgba(255,255,255,0.1);border-radius:8px;padding:10px 12px;margin-bottom:8px;">
              <div>
                <div style="font-weight:700;font-size:12.5px;color:#f8fafc;">${item.filename}</div>
                <div style="font-size:11px;color:#94a3b8;margin-top:2px;">${item.modified} • ${item.size_kb} KB • ${item.summary}</div>
              </div>
              <button data-idx="${idx}" class="btn-export-item" style="background:linear-gradient(135deg,#2563eb,#00d2ff);color:#fff;border:none;padding:6px 12px;border-radius:6px;font-size:11.5px;font-weight:700;cursor:pointer;">📤 Exportar</button>
            </div>
          `).join('');
          container.querySelectorAll('.btn-export-item').forEach(btn => {
            btn.addEventListener('click', () => {
              const item = list[Number(btn.getAttribute('data-idx'))];
              if (item) exportCsvFile(item.filename, item.content);
            });
          });
        }
      }
      modalLogsList?.classList.add('active');
    });
  }

  document.getElementById('btn-close-logs-list')?.addEventListener('click', () => modalLogsList?.classList.remove('active'));
  document.getElementById('btn-dismiss-logs-list')?.addEventListener('click', () => modalLogsList?.classList.remove('active'));
});
