"""
Monitor de entradas de Dune en el IMAX Theatre (Norcenter) de Showcase.

Cada CHECK_INTERVAL segundos pide la boleteria de Showcase (2 pedidos HTTP,
sin navegador), elige el cine IMAX y se fija si en la lista de peliculas hay
alguna que diga "dune" o "duna". Si aparece una nueva, avisa por Telegram.

Uso:
    python monitor_dune.py             # chequea una sola vez
    python monitor_dune.py --loop      # chequea cada 30 s para siempre
    python monitor_dune.py --loop 300  # chequea cada 30 s durante 300 s

Variables de entorno:
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    CHECK_INTERVAL  -> segundos entre chequeos (default 30)
"""

import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path

import requests

URL = "https://entradas.todoshowcase.com/showcase/boleteria.aspx"
# Matchea "Dune", "Duna", "DUNE: Parte Tres", "Dunas", con o sin tildes
KEYWORD = re.compile(r"\bdun(a|e)s?\b", re.IGNORECASE)
STATE_FILE = Path(__file__).parent / "dune_avisadas.json"
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "30"))
ALERTA_FALLOS = 40  # ~20 min de errores seguidos -> aviso por Telegram

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def send_telegram(text: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[AVISO] Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID:\n" + text)
        return
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=20,
    ).raise_for_status()


def options(html: str, select_id: str) -> dict[str, str]:
    """Devuelve {value: texto} de las opciones de un <select>."""
    m = re.search(rf'id="{select_id}".*?</select>', html, re.S)
    if not m:
        return {}
    return {
        v: t.strip()
        for v, t in re.findall(r'<option[^>]*value="([^"]*)"[^>]*>([^<]*)', m.group(0))
        if v
    }


def imax_movies() -> dict[str, str]:
    """Peliculas con funciones en el IMAX Theatre (Norcenter): {id: titulo}."""
    s = requests.Session()
    s.headers["User-Agent"] = "Mozilla/5.0"
    html = s.get(URL, timeout=20).text

    cines = options(html, "ctl00_Contenido_lstCinemaFull")
    imax = next((v for v, t in cines.items() if "imax" in t.lower()), None)
    if not imax:
        raise RuntimeError(f"No encontre el cine IMAX en la lista: {cines}")

    form = dict(re.findall(r'<input[^>]+type="hidden"[^>]+name="([^"]+)"[^>]*value="([^"]*)"', html))
    form["__EVENTTARGET"] = "ctl00$Contenido$lstCinemaFull"
    form["ctl00$Contenido$lstCinemaFull"] = imax
    html = s.post(URL, data=form, timeout=20).text

    movies = options(html, "ctl00_Contenido_lstMovies")
    if not movies:
        raise RuntimeError("La lista de peliculas del IMAX vino vacia")
    return movies


def es_dune(titulo: str) -> bool:
    sin_tildes = unicodedata.normalize("NFKD", titulo).encode("ascii", "ignore").decode()
    return bool(KEYWORD.search(sin_tildes))


def load_state() -> set[str]:
    return set(json.loads(STATE_FILE.read_text())) if STATE_FILE.exists() else set()


def check_once() -> bool:
    """Devuelve True si encontro una Dune nueva (y aviso)."""
    movies = imax_movies()
    avisadas = load_state()
    nuevas = {i: t for i, t in movies.items() if es_dune(t) and i not in avisadas}
    if not nuevas:
        print(f"Sin Dune. IMAX: {', '.join(movies.values())}")
        return False

    for movie_id, titulo in nuevas.items():
        send_telegram(
            f"🎬🚨 ¡SALIERON ENTRADAS DE {titulo.upper()} EN IMAX NORCENTER!\n\n"
            f"Comprá ya: https://entradas.todoshowcase.com/showcase/pelicula.aspx?filmid={movie_id}\n"
            f"o en {URL} → IMAX Theatre (Norcenter)"
        )
        print(f"AVISADO: {titulo} ({movie_id})")
    STATE_FILE.write_text(json.dumps(sorted(avisadas | set(nuevas)), indent=2))
    return True


def main() -> None:
    if "--loop" not in sys.argv:
        check_once()
        return

    args = sys.argv[sys.argv.index("--loop") + 1:]
    fin = time.time() + int(args[0]) if args else float("inf")
    fallos = 0
    while time.time() < fin:
        try:
            if check_once():
                return  # salimos para que GitHub Actions guarde el estado
            fallos = 0
        except Exception as e:
            fallos += 1
            print(f"[ERROR {fallos}] {type(e).__name__}: {e}")
            if fallos == ALERTA_FALLOS:
                try:
                    send_telegram(f"⚠️ El monitor de Dune lleva ~20 min sin poder leer Showcase.\nÚltimo error: {e}")
                except Exception:
                    pass
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
