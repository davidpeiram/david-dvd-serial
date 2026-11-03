"""
main.py - Ponto de entrada do sistema de telemetria
Execute: python main.py
"""

import uvicorn
from src.server import app, config

if __name__ == "__main__":
    host = config.get("server_host", "0.0.0.0")
    port = config.get("server_port", 8000)
    print("=" * 60)
    print("  FORD FIESTA ZETEC ROCAM 1.0 - TELEMETRIA OBD-II")
    print(f"  Modo Ativo: {config.get('mode', 'simulation').upper()}")
    print(f"  Painel Web: http://localhost:{port}")
    print("=" * 60)
    uvicorn.run("src.server:app", host=host, port=port, log_level="info", reload=False)
