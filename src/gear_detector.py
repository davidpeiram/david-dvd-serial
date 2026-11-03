"""
gear_detector.py - Detecção estimada de marcha por razão RPM / Velocidade - Versão 2.0
Específico para o câmbio Ford IB5 do Fiesta Sedan 1.0 Zetec Rocam Flex (Pneus 175/65 R14).
Inclui filtro de histerese temporal para evitar oscilações ao acionar a embreagem ou durante trocas.
"""

from collections import deque
from typing import List, Tuple

# Faixas nominais de razão (RPM / km/h) para cada marcha no câmbio IB5 1.0 (relação 4.56 final):
# 1ª: 3.58 * 4.56 -> razão ~155
# 2ª: 1.93 * 4.56 -> razão ~84
# 3ª: 1.28 * 4.56 -> razão ~55
# 4ª: 0.95 * 4.56 -> razão ~41
# 5ª: 0.76 * 4.56 -> razão ~33
GEAR_RATIO_RANGES: List[Tuple[int, float, float]] = [
    (1, 120.0, 220.0),  # 1ª Marcha
    (2, 68.0, 119.0),   # 2ª Marcha
    (3, 46.0, 67.0),    # 3ª Marcha
    (4, 35.0, 45.0),    # 4ª Marcha
    (5, 24.0, 34.0),    # 5ª Marcha
]


class GearDetector:
    """
    Detector com filtro de histerese temporal e amortecimento de transição.
    Evita que o número da marcha fique piscando ou oscilando quando o motorista
    pisa na embreagem entre as trocas de marcha.
    """

    def __init__(self, history_len: int = 4, min_consecutive_matches: int = 3):
        self.history = deque(maxlen=history_len)
        self.min_matches = min_consecutive_matches
        self.current_stable_gear = "N"
        self._out_of_range_counter = 0

    def update(self, rpm: int, speed: int) -> str:
        """
        Recebe a telemetria atual e retorna a marcha filtrada ('N', '1', '2', '3', '4', '5').
        """
        # Carro parado ou motor desligado -> Neutro imediato
        if speed < 4 or rpm < 400:
            self.history.clear()
            self.current_stable_gear = "N"
            self._out_of_range_counter = 0
            return "N"

        ratio = float(rpm) / float(speed)
        raw_candidate = "N"

        for gear, min_ratio, max_ratio in GEAR_RATIO_RANGES:
            if min_ratio <= ratio <= max_ratio:
                raw_candidate = str(gear)
                break

        if raw_candidate != "N":
            self._out_of_range_counter = 0
            self.history.append(raw_candidate)
            # Se atingiu o limiar de concordância consecutiva, confirma a nova marcha
            if self.history.count(raw_candidate) >= self.min_matches:
                self.current_stable_gear = raw_candidate
        else:
            # Embreagem acionada ou corte de marcha
            self._out_of_range_counter += 1
            # Mantém a marcha estável por até 4 ciclos (~160ms) para amortecer a troca
            if self._out_of_range_counter > 4:
                self.current_stable_gear = "N"
                self.history.clear()

        return self.current_stable_gear

    def reset(self) -> None:
        self.history.clear()
        self.current_stable_gear = "N"
        self._out_of_range_counter = 0


# Instância global padrão para uso direto
_default_detector = GearDetector()


def estimate_gear(rpm: int, speed: int) -> str:
    """Função compatível com a API original, utilizando o filtro de histerese."""
    return _default_detector.update(rpm, speed)
