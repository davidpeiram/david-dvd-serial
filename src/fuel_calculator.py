"""
fuel_calculator.py - Cálculo de consumo de combustível instantâneo (km/L e L/h) - Versão 2.0
Utiliza o método Speed-Density calibrado para o motor Ford 1.0 8V Zetec Rocam Flex,
com compensação dinâmica de malha fechada via correções de mistura (STFT / LTFT) e fator K.
"""

from typing import Tuple, Optional


def calculate_fuel_consumption(
    rpm: int,
    map_kpa: int,
    iat_celsius: int,
    speed_kmh: int,
    stft_pct: float = 0.0,
    ltft_pct: float = 0.0,
    fuel_type: str = "flex_auto",
    calibration_k: float = 1.0,
) -> Tuple[float, Optional[float], str, str]:
    """
    Calcula consumo por Speed-Density com compensação de malha fechada (O2 trims) e fator K.

    Parâmetros:
      - rpm: Rotação atual do motor (RPM).
      - map_kpa: Pressão absoluta no coletor de admissão (kPa).
      - iat_celsius: Temperatura do ar de admissão (°C).
      - speed_kmh: Velocidade do veículo (km/h).
      - stft_pct: Correção de combustível a curto prazo (Short Term Fuel Trim %).
      - ltft_pct: Correção de combustível a longo prazo (Long Term Fuel Trim %).
      - fuel_type: "flex_auto", "gasoline" (E27) ou "ethanol" (E100).
      - calibration_k: Fator multiplicador de calibração volumétrica empírica pós-bomba.

    Retorna:
      (litros_por_hora, km_por_litro, valor_formatado, unidade)
    """
    if rpm < 350:
        return 0.0, None, "0.0", "L/h"

    # 1. Temperatura do ar de admissão em Kelvin (clamp para evitar divisão por zero/congelamento)
    iat_kelvin = max(240.0, float(iat_celsius) + 273.15)

    # 2. Eficiência volumétrica estimada do Zetec Rocam 1.0 8V
    # Na lenta (~850-1000 RPM) VE varia entre 0.68 e 0.72; em torque máximo (~4500 RPM) atinge ~0.86
    rpm_norm = min(1.0, float(rpm) / 4700.0)
    ve = 0.68 + (0.18 * rpm_norm)

    # 3. Cilindrada do motor (Zetec Rocam 1.0 = 0.999 L)
    displacement_l = 0.999

    # 4. Equação do gás ideal para fluxo mássico de ar (MAF em g/s)
    # MAF = (RPM * MAP / (2 * T)) * (Vd * VE * M_ar) / (R * 60)
    # Constantes: M_ar = 28.97 g/mol, R = 8.314 J/(mol*K)
    imap = (float(rpm) * float(map_kpa)) / (2.0 * iat_kelvin)
    maf_gps = (imap * displacement_l * ve * 28.97) / (8.314 * 60.0)

    # 5. Propriedades termoquímicas do combustível
    fuel_lower = (fuel_type or "flex_auto").lower()
    if fuel_lower == "ethanol":
        base_afr = 9.0
        fuel_density_g_per_l = 789.0
    elif fuel_lower == "gasoline":
        base_afr = 13.2
        fuel_density_g_per_l = 745.0
    else:
        # Padrão Brasileiro Flex: Gasolina C (E27) como base de referência
        base_afr = 13.2
        fuel_density_g_per_l = 750.0

    # 6. Compensação Dinâmica de Malha Fechada da Sonda Lambda (Trims STFT + LTFT)
    # Exemplo: STFT -14.1% e LTFT -13.3% -> total = -27.4% -> trim_mult = 0.726 (ECU injeta 27.4% menos combustível)
    total_trim = float(stft_pct) + float(ltft_pct)
    # Clamp de segurança física: autoridade típica de trim de injeção automotiva é de ±30%
    trim_mult = max(0.65, min(1.35, 1.0 + (total_trim / 100.0)))

    # 7. Taxa final de combustível em g/s e Litros/hora (com fator de calibração K)
    k_factor = max(0.5, min(2.0, float(calibration_k)))
    fuel_gps = (maf_gps / base_afr) * trim_mult * k_factor
    fuel_lph = max(0.0, (fuel_gps * 3600.0) / fuel_density_g_per_l)

    # 8. Formatação inteligente para o Cockpit
    if speed_kmh < 3:
        formatted = f"{fuel_lph:.1f}"
        return round(fuel_lph, 2), None, formatted, "L/h"
    else:
        kml = float(speed_kmh) / max(0.01, fuel_lph)
        kml_clamped = min(99.9, max(0.5, kml))
        formatted = f"{kml_clamped:.1f}"
        return round(fuel_lph, 2), round(kml_clamped, 1), formatted, "km/L"
