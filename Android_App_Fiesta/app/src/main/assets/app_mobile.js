/**
 * app_mobile.js - Motor Nativo de Telemetria OBD-II / HS-CAN para Android (CANable V2.1)
 * Ford Fiesta Sedan 1.0 Zetec Rocam Flex (ECU Ford EEC-VI • 500 kbps)
 * Versão v2.3.2 - Cluster Digital Compacto, Correção Mapa GPS e Rigor Metrológico
 */

// Funções Globais Disponíveis no Escopo de Janela
let leafletMap = null;
let gpsMarker = null;
let gpsPolyline = null;
let isMapInitialized = false;

window.switchAppTab = function(tabName) {
  const tabCockpit = document.getElementById('tab-cockpit');
  const tabMap = document.getElementById('tab-map');
  const btnCockpit = document.getElementById('tab-btn-cockpit');
  const btnMap = document.getElementById('tab-btn-map');

  if (tabName === 'map') {
    if (tabCockpit) tabCockpit.classList.remove('active');
    if (tabMap) tabMap.classList.add('active');
    if (btnCockpit) btnCockpit.classList.remove('active');
    if (btnMap) btnMap.classList.add('active');

    const LeafletObj = window.L || window.leaflet;
    if (!isMapInitialized && LeafletObj) {
      initLeafletMap();
    }
    setTimeout(() => {
      if (leafletMap) leafletMap.invalidateSize();
    }, 150);
  } else {
    if (tabMap) tabMap.classList.remove('active');
    if (tabCockpit) tabCockpit.classList.add('active');
    if (btnMap) btnMap.classList.remove('active');
    if (btnCockpit) btnCockpit.classList.add('active');
  }
};

window.changeTheme = function(themeName) {
  document.documentElement.setAttribute('data-theme', themeName);
  try {
    localStorage.setItem('fiesta_cockpit_theme', themeName);
    localStorage.setItem('html_manual_theme', themeName);
    localStorage.setItem('html_estudos_theme', themeName);
  } catch (e) {}
  const sel = document.getElementById('theme-switcher');
  if (sel) sel.value = themeName;
};

window.toggleGpsTracking = function() {
  const btn = document.getElementById('btn-toggle-gps');
  let active = false;
  if (window.AndroidUSB && window.AndroidUSB.isGpsActive) {
    active = window.AndroidUSB.isGpsActive();
  }

  if (active) {
    if (window.AndroidUSB && window.AndroidUSB.stopGps) {
      window.AndroidUSB.stopGps();
    }
    if (btn) {
      btn.textContent = '📍 GPS OFF';
      btn.classList.remove('active');
      btn.style.borderColor = 'var(--border-color)';
      btn.style.color = 'var(--text-secondary)';
    }
  } else {
    if (window.AndroidUSB && window.AndroidUSB.startGps) {
      window.AndroidUSB.startGps();
    }
    if (btn) {
      btn.textContent = '📍 GPS ON';
      btn.classList.add('active');
      btn.style.borderColor = 'var(--accent-cyan)';
      btn.style.color = 'var(--accent-cyan)';
    }
  }
};

function initLeafletMap() {
  const container = document.getElementById('leaflet-map');
  const LeafletObj = window.L || window.leaflet;
  if (!container || !LeafletObj || leafletMap) return;

  try {
    // Coordenadas iniciais: última posição conhecida do GPS ou Região RJ / Niterói (-22.9068, -43.1729)
    const initialPos = (state.gpsLat != null && state.gpsLon != null)
      ? [state.gpsLat, state.gpsLon]
      : [-22.9068, -43.1729];

    leafletMap = LeafletObj.map('leaflet-map', {
      zoomControl: true,
      attributionControl: false
    }).setView(initialPos, 16);

    // Tiles CartoDB Dark Matter (Estilo Cockpit Noturno) - sem token {r} para evitar exceção no Leaflet
    const tileLayer = LeafletObj.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png', {
      maxZoom: 19,
      subdomains: 'abcd'
    });
    tileLayer.addTo(leafletMap);

    // Linha de Trajetória
    gpsPolyline = LeafletObj.polyline([], {
      color: '#00d2ff',
      weight: 4,
      opacity: 0.85
    }).addTo(leafletMap);

    // Marcador do Veículo
    const vehicleIcon = LeafletObj.divIcon({
      className: 'vehicle-map-pin',
      html: '<div style="width:16px;height:16px;background:#00e676;border:2.5px solid #ffffff;border-radius:50%;box-shadow:0 0 10px #00e676;"></div>',
      iconSize: [16, 16],
      iconAnchor: [8, 8]
    });
    gpsMarker = LeafletObj.marker(initialPos, { icon: vehicleIcon }).addTo(leafletMap);

    if (state.gpsLat != null && state.gpsLon != null) {
      gpsPolyline.addLatLng(initialPos);
    }

    isMapInitialized = true;
    console.log('Mapa Leaflet inicializado com sucesso.');
    setTimeout(() => {
      if (leafletMap) leafletMap.invalidateSize();
    }, 200);
  } catch (err) {
    console.error('Erro ao inicializar mapa Leaflet:', err);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  // 1. Inicialização de Tema
  const savedTheme = localStorage.getItem('fiesta_cockpit_theme') ||
                     localStorage.getItem('html_manual_theme') ||
                     localStorage.getItem('html_estudos_theme') || 'dark';
  window.changeTheme(savedTheme);

  // 2. Elementos de Interface
  const elClock = document.getElementById('live-clock');
  const elConnBadge = document.getElementById('conn-info-badge');
  const elMilBadge = document.getElementById('mil-badge');
  const elMilIcon = document.getElementById('mil-icon');
  const elMilText = document.getElementById('mil-text');
  const elStatusDot = document.getElementById('status-dot');
  const elStatusText = document.getElementById('status-text');
  const btnFullscreen = document.getElementById('btn-fullscreen');

  const elTachoBarFill = document.getElementById('tacho-bar-fill');
  const elRpmVal = document.getElementById('val-rpm');
  const elSpeedVal = document.getElementById('val-speed');
  const elGearVal = document.getElementById('val-gear');
  const elConsumptionVal = document.getElementById('val-consumption');
  const elConsumptionUnit = document.getElementById('unit-consumption');
  const elTripKm = document.getElementById('val-trip-km');
  const elTripTime = document.getElementById('val-trip-time');
  const elTripFuel = document.getElementById('val-trip-fuel');
  const elTripAvg = document.getElementById('val-trip-avg');

  const elCoolantVal = document.getElementById('val-coolant');
  const elCoolantProgress = document.getElementById('progress-coolant');
  const elTorqueVal = document.getElementById('val-torque');
  const elTorqueProgress = document.getElementById('progress-torque');
  const elTorqueSub = document.getElementById('val-torque-sub');
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
  const elBatteryVal = document.getElementById('val-battery');
  const elBatteryProgress = document.getElementById('progress-battery');

  // Elementos do HUD do Mapa GPS
  const elHudGpsSpeed = document.getElementById('hud-gps-speed');
  const elHudEcuSpeed = document.getElementById('hud-ecu-speed');
  const elHudGpsAlt = document.getElementById('hud-gps-alt');
  const elHudGpsAcc = document.getElementById('hud-gps-acc');
  const elHudGpsCoords = document.getElementById('hud-gps-coords');

  // Relógio Top Bar
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
      btnFullscreen.textContent = isFull ? '🗗' : '⛶';
    });
  }

  // 3. Detector de Marchas Calibrado (Câmbio Ford IB5 1.0 Flex - Pneus 175/65 R14)
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

  // 4. Cálculo de Consumo Speed-Density V2.0 (Com compensação STFT + LTFT)
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

  // 5. Estado Central de Telemetria
  const state = {
    usbConnected: false,
    ecuResponding: false,
    hasReceivedFuelFrame: false,
    hasReceivedTorqueFrame: false,
    lastEcuRespMs: 0,
    lastRpmMs: 0,
    lastSpeedMs: 0,
    rpm: 0,
    speed: 0,
    gear: 'N',
    map: null,
    throttle: null,
    engineLoad: null,
    timingAdvance: null,
    coolantTemp: null,
    intakeTemp: null,
    stft: null,
    ltft: null,
    fuelLevel: null,
    fuelLiters: null,
    batteryVoltage: null,
    engineTorqueNm: 0.0,
    milOn: false,
    dtcCount: 0,
    fuelRateLph: 0.0,
    fuelEcoStr: '--',
    fuelEcoUnit: 'km/L',
    tripKm: 0.0,
    totalFuelLiters: 0.0,
    sessionStartMs: Date.now(),
    lastCalcMs: Date.now(),
    gpsLat: null,
    gpsLon: null,
    gpsSpeed: 0.0,
    gpsAlt: 0.0,
    gpsBearing: 0.0,
    gpsAcc: 999.0,
    firstGpsFix: false
  };

  // 6. Terminal SLCAN & Métodos de Depuração
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
    if (termLog.children.length > 120) termLog.removeChild(termLog.firstChild);
    termLog.scrollTop = termLog.scrollHeight;
  }

  window.termSend = function(cmd) {
    appendTermLog(`TX -> ${cmd}`, 'term-tx');
    if (window.AndroidUSB && window.AndroidUSB.sendCommand) {
      window.AndroidUSB.sendCommand(cmd);
    }
  };

  window.clearTermLog = function() {
    if (termLog) termLog.innerHTML = '';
  };

  function sendSlcan(cmd, logIt = false) {
    if (logIt) appendTermLog(`TX -> ${cmd}`, 'term-tx');
    if (window.AndroidUSB && window.AndroidUSB.sendCommand) {
      window.AndroidUSB.sendCommand(cmd);
    }
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

  if (elConnBadge) {
    elConnBadge.addEventListener('click', () => {
      if (window.AndroidUSB) window.AndroidUSB.connect();
    });
  }

  // 7. Recepção de Eventos Nativos do Android (Java -> JS)
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

  // Callback de Status de GPS Nativo
  window.onNativeGpsStatusChanged = (active) => {
    state.gpsActive = Boolean(active);
    const btn = document.getElementById('btn-toggle-gps');
    if (btn) {
      btn.textContent = active ? '📍 GPS ON' : '📍 GPS OFF';
      if (active) {
        btn.classList.add('active');
        btn.style.borderColor = 'var(--accent-cyan)';
        btn.style.color = 'var(--accent-cyan)';
      } else {
        btn.classList.remove('active');
        btn.style.borderColor = 'var(--border-color)';
        btn.style.color = 'var(--text-secondary)';
      }
    }
  };

  // Redimensionamento Dinâmico do Mapa (Rotação de Tela Celular / Tablet)
  window.addEventListener('resize', () => {
    if (leafletMap) {
      leafletMap.invalidateSize();
    }
  });

  // Callback de GPS Nativo
  window.onNativeGpsUpdate = (lat, lon, speedKmh, alt, bearing, acc) => {
    state.gpsLat = lat;
    state.gpsLon = lon;
    state.gpsSpeed = speedKmh;
    state.gpsAlt = alt;
    state.gpsBearing = bearing;
    state.gpsAcc = acc;

    if (elHudGpsSpeed) elHudGpsSpeed.textContent = `${speedKmh.toFixed(1)} km/h`;
    if (elHudGpsCoords) elHudGpsCoords.textContent = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    if (elHudGpsAlt) elHudGpsAlt.textContent = `${alt.toFixed(0)} m`;
    if (elHudGpsAcc) elHudGpsAcc.textContent = `±${acc.toFixed(0)} m`;

    const tabMap = document.getElementById('tab-map');
    const isMapVisible = tabMap && tabMap.classList.contains('active');

    const LeafletObj = window.L || window.leaflet;
    if (!isMapInitialized && LeafletObj && isMapVisible) {
      initLeafletMap();
    }

    if (leafletMap && gpsMarker && gpsPolyline) {
      const pos = [lat, lon];
      gpsMarker.setLatLng(pos);
      gpsPolyline.addLatLng(pos);
      if (!state.firstGpsFix) {
        state.firstGpsFix = true;
        leafletMap.setView(pos, 16);
      } else {
        leafletMap.panTo(pos, { animate: true });
      }
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
      state.hasReceivedFuelFrame = true;
      state.fuelLevel = Math.round((bytes[0] / 2.55) * 10) / 10;
      state.fuelLiters = Math.round((state.fuelLevel / 100.0) * 54.0 * 10) / 10;
      return;
    }

    // 2. Broadcast 0x422: Demanda do Pedal e Torque Real do Motor
    if (canId === 0x422 && bytes.length >= 1) {
      state.hasReceivedTorqueFrame = true;
      const b0 = bytes[0];
      state.engineTorqueNm = b0 > 0 ? Math.round((8.0 + 85.0 * (b0 / 255.0)) * 10) / 10 : (state.rpm > 400 ? 8.0 : 0.0);
      return;
    }

    // 3. Resposta de Diagnóstico da ECU Ford EEC-VI (0x7E8)
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

  // 8. Scheduler de Requisições OBD-II (Prioridades 1, 2 e 3 em 0x7E0)
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
      pidToQuery = p1Pids[mod]; // RPM, Speed, TPS com alta taxa (15+ Hz)
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

  // 9. Datalogger CSV (27 Colunas com GPS Lat/Lon)
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
    'ecu_responding', 'engine_torque_nm', 'gps_lat', 'gps_lon'
  ];

  function formatDuration(sec) {
    const h = String(Math.floor(sec / 3600)).padStart(2, '0');
    const m = String(Math.floor((sec % 3600) / 60)).padStart(2, '0');
    const s = String(Math.floor(sec % 60)).padStart(2, '0');
    return `${h}:${m}:${s}`;
  }

  // 10. Loop de Integração Física, Watchdog e Renderização (10 Hz)
  setInterval(() => {
    const now = Date.now();
    const dtSec = Math.min(1.0, Math.max(0.001, (now - state.lastCalcMs) / 1000.0));
    state.lastCalcMs = now;

    const rpmStale = (now - state.lastRpmMs) > 1500;
    const speedStale = (now - state.lastSpeedMs) > 1500;
    state.ecuResponding = (now - state.lastEcuRespMs) <= 2000;
    const isEcuActive = state.ecuResponding;

    const curRpm = (isEcuActive && !rpmStale) ? state.rpm : 0;
    const curSpd = (isEcuActive && !speedStale) ? state.speed : 0;

    state.gear = isEcuActive ? detectGear(curRpm, curSpd) : 'N';
    state.batteryVoltage = isEcuActive ? (curRpm > 450 ? 14.2 : 12.5) : null;

    if (isEcuActive && state.map != null && curRpm > 350) {
      const iat = state.intakeTemp != null ? state.intakeTemp : 30;
      const st = state.stft != null ? state.stft : 0.0;
      const lt = state.ltft != null ? state.ltft : 0.0;
      const sd = calcSpeedDensity(curRpm, state.map, iat, curSpd, st, lt);
      state.fuelRateLph = sd.lph;
      state.fuelEcoStr = sd.str;
      state.fuelEcoUnit = sd.unit;
    } else {
      state.fuelRateLph = 0.0;
      state.fuelEcoStr = '--';
      state.fuelEcoUnit = 'km/L';
    }

    if (isEcuActive && !speedStale && curSpd > 0) {
      state.tripKm += (curSpd / 3600.0) * dtSec;
    }
    if (isEcuActive && !rpmStale && curRpm > 350) {
      state.totalFuelLiters += (state.fuelRateLph / 3600.0) * dtSec;
    }

    const avgKml = state.totalFuelLiters > 0.005
      ? Math.min(99.9, state.tripKm / state.totalFuelLiters)
      : 0.0;
    const tripTimeStr = formatDuration((now - state.sessionStartMs) / 1000.0);

    // Grava linha no Datalogger se ativo (10 Hz) com proteção de nulos
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
        state.throttle != null ? state.throttle.toFixed(1) : '0.0',
        state.engineLoad != null ? state.engineLoad.toFixed(1) : '',
        state.map != null ? state.map : '',
        state.coolantTemp != null ? state.coolantTemp : '',
        state.intakeTemp != null ? state.intakeTemp : '',
        state.timingAdvance != null ? state.timingAdvance.toFixed(1) : '',
        state.stft != null ? state.stft.toFixed(1) : '',
        state.ltft != null ? state.ltft.toFixed(1) : '',
        state.fuelLevel != null ? state.fuelLevel.toFixed(1) : '',
        state.fuelLiters != null ? state.fuelLiters.toFixed(1) : '',
        state.batteryVoltage != null ? state.batteryVoltage.toFixed(2) : '',
        state.fuelRateLph.toFixed(2),
        `${state.fuelEcoStr} ${state.fuelEcoUnit}`,
        state.totalFuelLiters.toFixed(4),
        state.tripKm.toFixed(3),
        avgKml.toFixed(2),
        state.milOn,
        state.dtcCount,
        state.ecuResponding,
        state.engineTorqueNm.toFixed(1),
        state.gpsLat != null ? state.gpsLat.toFixed(6) : '',
        state.gpsLon != null ? state.gpsLon.toFixed(6) : ''
      ].join(','));
    }

    // Atualiza Status de Conexão
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

    // Atualiza MIL
    if (elMilBadge && elMilIcon && elMilText) {
      if (isEcuActive && (state.milOn || state.dtcCount > 0)) {
        elMilBadge.className = 'mil-badge mil-alert';
        elMilIcon.textContent = '⚠️';
        elMilText.textContent = `DTC: ${state.dtcCount}`;
      } else {
        elMilBadge.className = 'mil-badge mil-ok';
        elMilIcon.textContent = '✅';
        elMilText.textContent = 'OK';
      }
    }

    // Atualiza Barra Fita Superior de Shift Light / RPM
    if (elTachoBarFill) {
      const pct = (isEcuActive && curRpm > 0) ? Math.min(100, Math.max(0, (curRpm / 6000.0) * 100)) : 0;
      elTachoBarFill.style.width = `${pct}%`;
      if (curRpm >= 5500) {
        elTachoBarFill.style.background = 'linear-gradient(90deg, #ffb300, #ff1744)';
      } else if (curRpm >= 4000) {
        elTachoBarFill.style.background = 'linear-gradient(90deg, #00d2ff, #ffb300)';
      } else {
        elTachoBarFill.style.background = 'linear-gradient(90deg, #00d2ff, #00e676)';
      }
    }

    // Velocidade, RPM e Marcha Digitais
    if (elRpmVal) elRpmVal.textContent = isEcuActive ? curRpm.toLocaleString() : '0';
    if (elSpeedVal) elSpeedVal.textContent = isEcuActive ? curSpd : '0';
    if (elGearVal) {
      elGearVal.textContent = state.gear;
      elGearVal.style.color = state.gear === 'N' ? '#829ab1' : '#00d2ff';
    }
    if (elConsumptionVal) elConsumptionVal.textContent = isEcuActive ? state.fuelEcoStr : '--';
    if (elConsumptionUnit) elConsumptionUnit.textContent = state.fuelEcoUnit;
    if (elTripKm) elTripKm.textContent = `${state.tripKm.toFixed(1)} km`;
    if (elTripTime) elTripTime.textContent = tripTimeStr;
    if (elTripFuel) elTripFuel.textContent = `${state.totalFuelLiters.toFixed(2)} L`;
    if (elTripAvg) elTripAvg.textContent = `${avgKml.toFixed(1)} km/L`;

    // Atualiza Velocidade ECU no HUD do Mapa
    if (elHudEcuSpeed) elHudEcuSpeed.textContent = isEcuActive ? `${curSpd} km/h` : '-- km/h';

    // Sensores Grid 3x3
    // Card 1: Temp ECT
    if (elCoolantVal) {
      elCoolantVal.textContent = (isEcuActive && state.coolantTemp != null) ? state.coolantTemp : '--';
    }
    if (elCoolantProgress) {
      elCoolantProgress.style.width = (isEcuActive && state.coolantTemp != null)
        ? `${Math.min(100, Math.max(0, ((state.coolantTemp - 40) / 80) * 100))}%`
        : '0%';
    }

    // Card 2: Torque Motor (ESTIMADO)
    const showTorque = (isEcuActive || state.hasReceivedTorqueFrame) && curRpm > 400;
    if (elTorqueVal) elTorqueVal.textContent = showTorque ? state.engineTorqueNm.toFixed(0) : '0';
    if (elTorqueProgress) {
      elTorqueProgress.style.width = showTorque
        ? `${Math.min(100, Math.max(0, (state.engineTorqueNm / 93.0) * 100))}%`
        : '0%';
    }
    if (elTorqueSub) {
      const kgfm = (state.engineTorqueNm / 9.80665).toFixed(1);
      elTorqueSub.textContent = showTorque ? `${kgfm} kgfm • Máx: 93 Nm` : '0.0 kgfm • Máx: 93 Nm';
    }

    // Card 3: MAP
    if (elMapVal) {
      elMapVal.textContent = (isEcuActive && state.map != null) ? state.map : '--';
    }
    if (elMapProgress) {
      elMapProgress.style.width = (isEcuActive && state.map != null)
        ? `${Math.min(100, Math.max(0, (state.map / 105) * 100))}%`
        : '0%';
    }

    // Card 4: Demanda / Pedal TPS
    if (elThrottleVal) {
      elThrottleVal.textContent = (isEcuActive && state.throttle != null) ? state.throttle.toFixed(0) : '0';
    }
    if (elThrottleProgress) {
      elThrottleProgress.style.width = (isEcuActive && state.throttle != null) ? `${state.throttle}%` : '0%';
    }

    // Card 5: Combustível Real (Boia CAN 0x430)
    const showFuel = state.hasReceivedFuelFrame && state.fuelLevel != null;
    if (elFuelVal) {
      if (showFuel) {
        const isReserve = (state.fuelLiters != null && state.fuelLiters <= 5.0);
        elFuelVal.textContent = state.fuelLevel.toFixed(0);
        elFuelVal.style.color = isReserve ? '#ff3366' : 'var(--text-primary)';
      } else {
        elFuelVal.textContent = '--';
        elFuelVal.style.color = 'var(--text-primary)';
      }
    }
    if (elFuelProgress) {
      elFuelProgress.style.width = showFuel ? `${Math.min(100, Math.max(0, state.fuelLevel))}%` : '0%';
    }
    if (elFuelSub) {
      if (showFuel) {
        const refKml = avgKml > 3.0 ? avgKml : 11.5;
        const rangeKm = Math.round(state.fuelLiters * refKml);
        elFuelSub.textContent = `${state.fuelLiters.toFixed(1)} L / 54L • Auton: ~${rangeKm} km`;
      } else {
        elFuelSub.textContent = '-- L / 54L • Auton: -- km';
      }
    }

    // Card 6: Carga do Motor
    if (elLoadVal) {
      elLoadVal.textContent = (isEcuActive && state.engineLoad != null) ? state.engineLoad.toFixed(1) : '--';
    }
    if (elLoadProgress) {
      elLoadProgress.style.width = (isEcuActive && state.engineLoad != null)
        ? `${Math.min(100, Math.max(0, state.engineLoad))}%`
        : '0%';
    }

    // Card 7: Ponto de Ignição
    if (elTimingVal) {
      elTimingVal.textContent = (isEcuActive && state.timingAdvance != null)
        ? ((state.timingAdvance >= 0 ? '+' : '') + state.timingAdvance.toFixed(1))
        : '--';
    }
    if (elTimingProgress) {
      elTimingProgress.style.width = (isEcuActive && state.timingAdvance != null)
        ? `${Math.min(100, Math.max(0, ((state.timingAdvance + 10) / 55) * 100))}%`
        : '0%';
    }

    // Card 8: Sonda Lambda
    if (isEcuActive && state.stft != null) {
      const lt = state.ltft != null ? state.ltft : 0.0;
      if (elTrimSub) {
        elTrimSub.textContent = `STFT: ${state.stft >= 0 ? '+' : ''}${state.stft.toFixed(1)}% • LTFT: ${lt >= 0 ? '+' : ''}${lt.toFixed(1)}%`;
      }
      if (elTrimStatus) {
        if (Math.abs(state.stft) <= 5 && Math.abs(lt) <= 5) {
          elTrimStatus.textContent = 'ESTEQUIOM.';
          elTrimStatus.style.color = '#00e676';
        } else if (state.stft < -8 || lt < -8) {
          elTrimStatus.textContent = 'ENXUGANDO';
          elTrimStatus.style.color = '#00d2ff';
        } else {
          elTrimStatus.textContent = 'NORMAL';
          elTrimStatus.style.color = 'var(--text-primary)';
        }
      }
      if (elTrimProgress) {
        elTrimProgress.style.width = `${Math.min(100, Math.max(0, ((state.stft + 25) / 50) * 100))}%`;
      }
    } else {
      if (elTrimStatus) {
        elTrimStatus.textContent = '--';
        elTrimStatus.style.color = 'var(--text-secondary)';
      }
      if (elTrimSub) {
        elTrimSub.textContent = 'STFT: --% • LTFT: --%';
      }
      if (elTrimProgress) {
        elTrimProgress.style.width = '0%';
      }
    }

    // Card 9: Tensão Bateria (ESTIMADO)
    if (elBatteryVal) {
      elBatteryVal.textContent = (isEcuActive && state.batteryVoltage != null)
        ? state.batteryVoltage.toFixed(1)
        : '--';
    }
    if (elBatteryProgress) {
      elBatteryProgress.style.width = (isEcuActive && state.batteryVoltage != null)
        ? `${Math.min(100, Math.max(0, ((state.batteryVoltage - 10) / 5) * 100))}%`
        : '0%';
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
        if (btnLogText) btnLogText.textContent = '■ PARAR LOG';
      } else {
        isLogging = false;
        btnToggleLog.classList.remove('recording');
        if (btnLogText) btnLogText.textContent = '● GRAVAR LOG';

        const dist = Math.max(0, state.tripKm - logStartKm);
        const fuel = Math.max(0, state.totalFuelLiters - logStartFuel);
        const avg = fuel > 0.002 ? (dist / fuel) : 0.0;
        const durSec = Math.max(1, (Date.now() - logStartMs) / 1000.0);
        const avgSpd = (dist / (durSec / 3600.0));

        lastSavedCsvFilename = currentLogName;
        lastSavedCsvContent = currentLogRows.join('\n');
        saveStoredLog(lastSavedCsvFilename, lastSavedCsvContent, `${dist.toFixed(2)} km • ${currentLogRows.length - 1} amostras`);

        const sumDist = document.getElementById('summary-distance');
        const sumFuel = document.getElementById('summary-fuel');
        const sumAvg = document.getElementById('summary-avg-kml');
        const sumDur = document.getElementById('summary-duration');
        const sumSpd = document.getElementById('summary-speed');

        if (sumDist) sumDist.textContent = `${dist.toFixed(2)} km`;
        if (sumFuel) sumFuel.textContent = `${fuel.toFixed(2)} L`;
        if (sumAvg) sumAvg.textContent = `${avg.toFixed(1)} km/L`;
        if (sumDur) sumDur.textContent = formatDuration(durSec);
        if (sumSpd) sumSpd.textContent = `${avgSpd.toFixed(1)} / ${logMaxSpeed} km/h`;

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
          container.innerHTML = '<div style="color: var(--text-secondary); text-align: center; padding: 20px;">Nenhuma viagem gravada ainda.<br>Toque em <b>GRAVAR LOG</b> antes de sair com o carro!</div>';
        } else {
          container.innerHTML = list.map((item, idx) => `
            <div style="display:flex;justify-content:space-between;align-items:center;background:rgba(0,0,0,0.35);border:1px solid var(--border-color);border-radius:8px;padding:8px 10px;margin-bottom:8px;">
              <div>
                <div style="font-weight:700;font-size:12px;color:var(--text-primary);">${item.filename}</div>
                <div style="font-size:10.5px;color:var(--text-secondary);margin-top:2px;">${item.modified} • ${item.size_kb} KB • ${item.summary}</div>
              </div>
              <button data-idx="${idx}" class="btn-export-item" style="background:var(--accent-cyan);color:#000;border:none;padding:5px 10px;border-radius:6px;font-size:11px;font-weight:700;cursor:pointer;">📤 Exportar</button>
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
