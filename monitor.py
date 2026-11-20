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


def obtener_resumen_linea(headers: dict, league_id: int, matchup_id: int | None) -> str:
    """
    Intenta localizar línea y cuotas en los mercados de la liga para el matchup_id indicado.
    Si no encuentra datos o cambia la estructura, devuelve un texto alternativo seguro.
    """
    if not matchup_id:
        return "Línea no disponible en el feed (revisa VOdds)"

    url_markets = f"https://guest.api.arcadia.pinnacle.com/0.1/leagues/{league_id}/markets/straight"
    try:
        m_resp = requests.get(url_markets, headers=headers, timeout=20)
        if m_resp.status_code != 200:
            return "Línea no disponible aún (revisa VOdds)"

        markets = m_resp.json()
        if not isinstance(markets, list):
            return "Línea no disponible aún (revisa VOdds)"

        coincidencias = []
        for m in markets:
            if m.get("matchupId") != matchup_id:
                continue
            for price in m.get("prices", []):
                lado = str(price.get("designation", "")).capitalize()
                puntos = price.get("points")
                cuota = price.get("price")
                if puntos is not None and cuota is not None:
                    signo = "+" if lado.lower() == "over" and float(puntos) > 0 else ""
                    puntos_str = f"{signo}{str(puntos).replace('.', ',')}"
                    cuota_str = str(cuota).replace(".", ",")
                    etiqueta = f"{lado} {puntos_str}" if lado else puntos_str
                    coincidencias.append(f"{etiqueta} a cuota {cuota_str}")

        if coincidencias:
            return " | ".join(coincidencias)

    except Exception:
        pass

    return "Línea no disponible aún (revisa VOdds)"


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
                resumen_linea = obtener_resumen_linea(headers, league_id, special_matchup_id)

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
