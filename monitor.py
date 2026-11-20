import json
import os
from pathlib import Path
import requests

BOT_TOKEN = os.environ["BOT_TOKEN"]
CHAT_ID = os.environ["CHAT_ID"]
STATE_FILE = Path("notificados.json")

# Ligas vigiladas (todas en minúsculas)
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
                mensaje = (
                    f"🟨 ¡TARJETAS ABIERTAS EN PINNACLE / PS3838!\n"
                    f"🏆 Liga: {liga.get('name')}\n"
                    f"⚽ Partido: {nombres}\n"
                    f"👉 Ya puedes entrar a VOdds para ver la línea de salida."
                )
                enviar_telegram(mensaje)
                notificados.add(clave)
                nuevos = True

    if nuevos:
        guardar_notificados(notificados)


if __name__ == "__main__":
    revisar_pinnacle()
