import json
import os
from pathlib import Path
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
STATE_FILE = Path("notificados.json")

LIGAS_OBJETIVO = [
    "spain - la liga",
    "spain - la liga 2",
    "spain - segunda",
    "england - premier league",
    "italy - serie a",
    "germany - bundesliga",
    "france - ligue 1",
    "uefa - champions league",
    "uefa - europa league",
    "uefa - conference league",
    "uefa - europa conference league",
    "brazil - serie a",
    "argentina - liga profesional",
    "argentina - primera",
]


def cargar_notificados() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))


def guardar_notificados(ids: set[str]) -> None:
    STATE_FILE.write_text(json.dumps(sorted(ids), indent=2), encoding="utf-8")


def enviar_telegram(mensaje: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": mensaje}, timeout=15).raise_for_status()


def american_a_decimal(cuota_raw) -> float | None:
    """
    Convierte cuota americana (ej. 150, -207) o decimal (ej. 2.02) a decimal.
    """
    if cuota_raw is None:
        return None
    try:
        val = float(cuota_raw)
    except (ValueError, TypeError):
        return None

    # Si ya viene en formato decimal típico (entre 1.01 y 25)
    if 1.01 <= val <= 25.0:
        return round(val, 3)

    # Conversión desde cuota americana
    if val >= 100:
        return round((val / 100.0) + 1.0, 3)
    if val <= -100:
        return round((100.0 / abs(val)) + 1.0, 3)

    return None


def formatear_decimal(valor: float) -> str:
    # Mantiene hasta 3 decimales sin ceros innecesarios al final (ej. 2,02 o 1,813)
    texto = f"{valor:.3f}".rstrip("0").rstrip(".")
    return texto.replace(".", ",")


def obtener_linea_principal(headers: dict, league_id: int, matchup_id: int | None) -> str:
    """
    Busca la línea principal Over/Under del mercado de tarjetas y devuelve algo limpio tipo:
    +5,0 a cuota 2,02 | -5,0 a cuota 1,813
    """
    if not matchup_id:
        return "Línea no disponible (revisa VOdds)"

    url_markets = f"https://guest.api.arcadia.pinnacle.com/0.1/leagues/{league_id}/markets/straight"
    try:
        m_resp = requests.get(url_markets, headers=headers, timeout=20)
        if m_resp.status_code != 200:
            return "Línea no disponible (revisa VOdds)"

        markets = m_resp.json()
        if not isinstance(markets, list):
            return "Línea no disponible (revisa VOdds)"

        # Agrupamos pares Over/Under por valor absoluto de puntos (ej. 5.0)
        pares_por_linea: dict[float, dict[str, tuple[float, float]]] = {}

        for m in markets:
            if m.get("matchupId") != matchup_id:
                continue
            for price in m.get("prices", []):
                lado = str(price.get("designation", "")).lower()
                if lado not in ("over", "under"):
                    continue

                puntos_raw = price.get("points")
                cuota_dec = american_a_decimal(price.get("price"))
                if puntos_raw is None or cuota_dec is None:
                    continue

                try:
                    puntos_val = abs(float(puntos_raw))
                except (ValueError, TypeError):
                    continue

                pares_por_linea.setdefault(puntos_val, {})[lado] = (puntos_val, cuota_dec)

        # Buscamos líneas que tengan tanto Over como Under
        completas = [
            (pts, lados["over"][1], lados["under"][1])
            for pts, lados in pares_por_linea.items()
            if "over" in lados and "under" in lados
        ]

        if not completas:
            return "Línea no disponible (revisa VOdds)"

        # Elegimos la línea más equilibrada (donde Over y Under estén más cerca de 2.00 / más parejos)
        completas.sort(key=lambda item: abs(item[1] - item[2]))
        pts_elegidos, cuota_over, cuota_under = completas[0]

        pts_str = f"{pts_elegidos:.1f}".replace(".", ",")
        over_str = formatear_decimal(cuota_over)
        under_str = formatear_decimal(cuota_under)

        return f"+{pts_str} a cuota {over_str} | -{pts_str} a cuota {under_str}"

    except Exception:
        return "Línea no disponible (revisa VOdds)"


def revisar_pinnacle() -> None:
    notificados = cargar_notificados()
    nuevos = False

    headers = {"User-Agent": "Mozilla/5.0"}
    url_ligas = "https://guest.api.arcadia.pinnacle.com/0.1/sports/29/leagues?all=false"
    resp = requests.get(url_ligas, headers=headers, timeout=20)
    resp.raise_for_status()

    for liga in resp.json():
        nombre_liga = liga.get("name", "").lower()
        if not any(obj in nombre_liga for obj in LIGAS_OBJETIVO):
            continue

        league_id = liga["id"]
        url_eventos = f"https://guest.api.arcadia.pinnacle.com/0.1/leagues/{league_id}/matchups"
        ev_resp = requests.get(url_eventos, headers=headers, timeout=20)
        if ev_resp.status_code != 200:
            continue

        for evento in ev_resp.json():
            parent_id = evento.get("parentId")
            unidades = str(evento.get("units", "")).lower()
            tipo_especial = str(evento.get("special", {}).get("description", "")).lower()

            if parent_id and ("booking" in unidades or "booking" in tipo_especial or "card" in tipo_especial):
                clave = f"{parent_id}_bookings"
                if clave in notificados:
                    continue

                partido = evento.get("parent", {}).get("participants", [])
                nombres = " vs ".join(p.get("name", "") for p in partido) or f"ID {parent_id}"
                special_matchup_id = evento.get("id")
                resumen_linea = obtener_linea_principal(headers, league_id, special_matchup_id)

                mensaje = (
                    f"🟨 ¡TARJETAS ABIERTAS EN PINNACLE / PS3838!\n"
                    f"🏆 Liga: {liga.get('name')}\n"
                    f"⚽ Partido: {nombres}\n"
                    f"📊 Línea: {resumen_linea}"
                )
                enviar_telegram(mensaje)
                notificados.add(clave)
                nuevos = True

    if nuevos:
        guardar_notificados(notificados)


if __name__ == "__main__":
    revisar_pinnacle()
