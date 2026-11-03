"""
server.py - Servidor Web & WebSocket do Painel Digital para Ford Fiesta Rocam - Versão 2.0
Inclui proteção contra Path Traversal, sanitização de prefixos, reconexão segura e sincronia de config.
"""

import re
import json
import asyncio
from pathlib import Path
import serial.tools.list_ports
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .can_adapter import CANableSLCANAdapter, SimulatedFallbackAdapter
from .obd_manager import OBDManager
from .datalogger import TripDatalogger

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
STATIC_DIR = BASE_DIR / "static"


def load_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[Server] Erro ao ler config.json: {e}")
    return {
        "version": "2.0",
        "mode": "real",
        "fallback_to_simulation_if_unavailable": True,
        "serial_port": "AUTO",
        "baudrate": 115200,
        "can_bitrate": 500000,
        "can_target_ecu_id": "0x7E0",
        "can_response_ecu_id": "0x7E8",
        "server_host": "0.0.0.0",
        "server_port": 8000,
        "telemetry_interval_ms": 40,
        "fuel_tank_capacity_liters": 54.0,
        "fuel_reserve_liters": 5.0,
        "fuel_price_per_liter": 6.30,
        "fuel_type": "flex_auto",
        "fuel_calibration_k_factor": 1.0,
        "gear_ratio_ranges": [
            {"gear": 1, "min": 130.0, "max": 240.0},
            {"gear": 2, "min": 80.0, "max": 129.9},
            {"gear": 3, "min": 55.0, "max": 79.9},
            {"gear": 4, "min": 41.5, "max": 54.9},
            {"gear": 5, "min": 24.0, "max": 41.4},
        ],
    }


config = load_config()

# Seleção do Adaptador CAN
adapter = None
if config.get("mode") == "real":
    canable = CANableSLCANAdapter(
        port=config.get("serial_port", "AUTO"),
        baudrate=config.get("baudrate", 115200),
        can_bitrate=config.get("can_bitrate", 500000),
    )
    if canable.open():
        print(f"[*] CANable conectado com sucesso na porta {canable.actual_port}!")
        adapter = canable
    elif config.get("fallback_to_simulation_if_unavailable", True):
        print("[!] Hardware CANable não detectado no momento. Iniciando modo Demonstração de Bancada...")
        adapter = SimulatedFallbackAdapter()
    else:
        adapter = canable
else:
    print("[*] Iniciando em Modo Demonstração...")
    adapter = SimulatedFallbackAdapter()

datalogger = TripDatalogger()
obd_manager = OBDManager(
    adapter=adapter,
    datalogger=datalogger,
    config=config,
)

app = FastAPI(title="Ford Fiesta Rocam OBD-II Digital Cluster V2.0")

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
def startup_event():
    obd_manager.start()


@app.on_event("shutdown")
def shutdown_event():
    obd_manager.stop()


@app.get("/")
def get_dashboard():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {"message": "static/index.html não encontrado"}


@app.get("/api/telemetry")
def get_telemetry():
    return obd_manager.get_snapshot()


@app.get("/api/config")
def get_server_config():
    return config


@app.get("/api/ports")
def get_ports():
    ports = serial.tools.list_ports.comports()
    return [{"device": p.device, "description": p.description, "hwid": p.hwid} for p in ports]


@app.post("/api/reconnect")
def post_reconnect():
    global adapter
    canable = CANableSLCANAdapter(
        port=config.get("serial_port", "AUTO"),
        baudrate=config.get("baudrate", 115200),
        can_bitrate=config.get("can_bitrate", 500000),
    )
    if canable.open():
        adapter = canable
        obd_manager.reconnect(canable)
        return {"status": "ok", "message": f"Conectado em {canable.actual_port}"}
    else:
        if config.get("fallback_to_simulation_if_unavailable", True):
            adapter = SimulatedFallbackAdapter()
            obd_manager.reconnect(adapter)
            return {"status": "fallback", "message": "Nenhum hardware detectado. Modo Demonstração ativo."}
        return {"status": "error", "message": "Falha ao abrir porta serial do CANable"}


@app.post("/api/trip/start")
def post_start_trip(reset_first: bool = False, prefix: str = "viagem"):
    # Sanitização contra Path Traversal e injeção de caracteres em prefixos
    safe_prefix = re.sub(r"[^a-zA-Z0-9_\-]", "", prefix)[:32] or "viagem"
    if reset_first:
        obd_manager.reset_trip()
    snap = obd_manager.get_snapshot()
    res = datalogger.start_logging(
        session_prefix=safe_prefix,
        initial_km=snap.get("trip_km", 0.0),
        initial_fuel=snap.get("total_fuel_liters", 0.0),
    )
    return res


@app.post("/api/trip/stop")
def post_stop_trip():
    snap = obd_manager.get_snapshot()
    res = datalogger.stop_logging(
        final_km=snap.get("trip_km", 0.0),
        final_fuel=snap.get("total_fuel_liters", 0.0),
        fuel_price_per_liter=config.get("fuel_price_per_liter", 6.30),
    )
    return res


@app.post("/api/trip/reset")
def post_reset_trip():
    obd_manager.reset_trip()
    return {"status": "ok", "message": "Viagem zerada"}


@app.get("/api/trip/status")
def get_trip_status():
    status = datalogger.get_status()
    snap = obd_manager.get_snapshot()
    status["trip_km"] = snap.get("trip_km", 0.0)
    status["total_fuel_liters"] = snap.get("total_fuel_liters", 0.0)
    status["trip_cost_brl"] = snap.get("trip_cost_brl", 0.0)
    status["avg_fuel_kml"] = snap.get("avg_fuel_kml", 0.0)
    return status


@app.get("/api/logs")
def get_logs():
    return datalogger.list_logs()


@app.get("/api/logs/download/{filename}")
def download_log(filename: str):
    # Proteção estrita contra Path Traversal
    safe_name = Path(filename).name
    file_path = (datalogger.logs_dir / safe_name).resolve()
    logs_dir_resolved = datalogger.logs_dir.resolve()

    if (
        file_path.is_file()
        and file_path.parent == logs_dir_resolved
        and file_path.suffix.lower() == ".csv"
    ):
        return FileResponse(file_path, filename=safe_name, media_type="text/csv")
    return {"error": "Arquivo não encontrado ou acesso inválido"}


@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    await websocket.accept()
    interval = config.get("telemetry_interval_ms", 40) / 1000.0
    try:
        while True:
            data = obd_manager.get_snapshot()
            await websocket.send_text(json.dumps(data))
            await asyncio.sleep(interval)
    except (WebSocketDisconnect, ConnectionResetError, ConnectionAbortedError):
        pass
    except Exception as e:
        print(f"[WebSocket] Conexão encerrada: {e}")
