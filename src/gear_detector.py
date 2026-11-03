"""
gear_detector.py - Detecção estimada de marcha por razão RPM / Velocidade - Versão 2.1
Específico para o câmbio Ford IB5 do Fiesta Sedan 1.0 Zetec Rocam Flex (Pneus 175/65 R14).
Relações reais do câmbio IB5 1.0L Flex: 1ª 4.08, 2ª 2.29, 3ª 1.52, 4ª 1.11, 5ª 0.88 | Diferencial 4.56.
Inclui filtro de histerese temporal para evitar oscilações ao acionar a embreagem ou durante trocas.
"""

from collections import deque
from typing import List, Tuple, Optional

# Faixas calibradas de razão (RPM / km/h) para cada marcha no câmbio IB5 do Fiesta 1.0 Flex:
# 1ª Marcha: teórica 169.3 | centro empírico ~175 | faixa 130.0 a 240.0
# 2ª Marcha: teórica 95.0-102.0 | centro empírico ~101 | faixa 80.0 a 129.9
# 3ª Marcha: teórica 63.1-65.0 | centro empírico ~65 | faixa 55.0 a 79.9
# 4ª Marcha: teórica 46.1-47.0 | centro empírico ~47 | faixa 41.5 a 54.9
# 5ª Marcha: teórica 36.5-37.0 | centro empírico ~37 | faixa 24.0 a 41.4
GEAR_RATIO_RANGES: List[Tuple[int, float, float]] = [
    (1, 130.0, 240.0),  # 1ª Marcha
    (2, 80.0, 129.9),   # 2ª Marcha
    (3, 55.0, 79.9),    # 3ª Marcha
    (4, 41.5, 54.9),    # 4ª Marcha
    (5, 24.0, 41.4),    # 5ª Marcha
]


class GearDetector:
    """
    Detector com filtro de histerese temporal e amortecimento de transição.
    Evita que o número da marcha fique piscando ou oscilando quando o motorista
    pisa na embreagem entre as trocas de marcha.
    """

    def __init__(
        self,
        history_len: int = 4,
        min_consecutive_matches: int = 3,
        ratio_ranges: Optional[List[Tuple[int, float, float]]] = None,
    ):
        self.history = deque(maxlen=history_len)
        self.min_matches = min_consecutive_matches
        self.ratio_ranges = ratio_ranges or GEAR_RATIO_RANGES
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

        for gear, min_ratio, max_ratio in self.ratio_ranges:
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
