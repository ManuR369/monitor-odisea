"""
Monitor de nuevas fechas de La Odisea (IMAX Norcenter) en Showcase.
Extrae las fechas de la cartelera y avisa por Telegram cuando aparecen nuevas.

Uso:
    python monitor_odisea.py           # corre una sola vez (ideal para cron / GitHub Actions)
    python monitor_odisea.py --loop    # corre cada 5 minutos en loop (ideal para dejar en tu PC)

Requiere:
    pip install playwright requests
    playwright install chromium

Variables de entorno:
    TELEGRAM_BOT_TOKEN  -> token del bot (lo da @BotFather)
    TELEGRAM_CHAT_ID    -> tu chat id (lo da @userinfobot)
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

URL = (
    "https://entradas.todoshowcase.com/showcase/pelicula"
    "?filmid=5875&house_id=3250"
)

# En Railway definir STATE_DIR=/data (con un volumen montado ahi) para que
# el archivo de estado sobreviva a los redeploys. Local: usa la carpeta actual.
STATE_FILE = Path(os.environ.get("STATE_DIR", str(Path(__file__).parent))) / "fechas_conocidas.json"
CHECK_INTERVAL_SECONDS = 5 * 60

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Matchea fechas tipo "5/08", "13/08" (en la página vienen pegadas al nombre
# del día, ej "Mié 5/08Jue 6/08", así que buscamos solo el número).
# Los lookarounds excluyen fechas largas tipo "16/07/2026" de la descripción.
DATE_PATTERN = re.compile(r"(?<![\d/])(\d{1,2}/\d{2})(?![\d/])")


def sort_key(fecha: str):
    dia, mes = fecha.split("/")
    return (int(mes), int(dia))


def get_current_dates() -> set[str]:
    """Abre la página con un navegador headless y devuelve el set de fechas visibles."""
    debug_dir = Path(__file__).parent / "debug"
    debug_dir.mkdir(exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0.0.0 Safari/537.36"
            ),
            locale="es-AR",
            timezone_id="America/Argentina/Buenos_Aires",
            viewport={"width": 1366, "height": 900},
        )
        page = context.new_page()
        page.goto(URL, wait_until="domcontentloaded", timeout=60_000)

        # Intentar cerrar modales/popups tipo "ATENCION" que puedan tapar la página
        for selector in [
            "button:has-text('Aceptar')",
            "a:has-text('Aceptar')",
            ".modal button.close",
            ".modal .close",
            "button:has-text('×')",
        ]:
            try:
                el = page.locator(selector).first
                if el.is_visible(timeout=1_000):
                    el.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

        # Esperar a que aparezcan las fechas (hasta 25 segundos)
        try:
            page.wait_for_selector("text=/\\d{1,2}\\/\\d{2}/", timeout=25_000)
        except Exception:
            pass  # si no aparece nada, devolvemos lo que haya

        page.wait_for_timeout(3_000)  # margen extra para que termine de renderizar
        body_text = page.inner_text("body")

        # Debug: guardar captura y texto para diagnosticar (solo si DEBUG=1)
        if os.environ.get("DEBUG") == "1":
            try:
                page.screenshot(path=str(debug_dir / "pagina.png"), full_page=True)
                (debug_dir / "texto_pagina.txt").write_text(body_text, encoding="utf-8")
            except Exception:
                pass

        browser.close()

    dates = set(DATE_PATTERN.findall(body_text))
    if not dates:
        snippet = " | ".join(body_text.split())[:600]
        print(f"[DEBUG] La página cargó pero sin fechas. Primeros caracteres del texto: {snippet}")
    return dates


def load_known_dates() -> set[str]:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    return set()


def save_known_dates(dates: set[str]) -> None:
    STATE_FILE.write_text(
        json.dumps(sorted(dates), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[AVISO] Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID; no se envía mensaje.")
        print(message)
        return
    resp = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
        timeout=30,
    )
    resp.raise_for_status()


def check_once() -> None:
    current = get_current_dates()
    if not current:
        print("No se detectaron fechas en la página (¿cambió el sitio o falló la carga?).")
        return

    known = load_known_dates()
    new_dates = current - known

    if not known:
        # Primera corrida: solo guarda el estado inicial, no notifica
        save_known_dates(current)
        print(f"Estado inicial guardado ({len(current)} fechas): {sorted(current, key=sort_key)}")
        return

    if new_dates:
        msg = (
            "🎬 ¡Nuevas fechas de La Odisea en IMAX Norcenter!\n\n"
            + "\n".join(f"• {d}" for d in sorted(new_dates, key=sort_key))
            + f"\n\nEntradas: {URL}"
        )
        send_telegram(msg)
        save_known_dates(current)
        print(f"Nuevas fechas notificadas: {sorted(new_dates, key=sort_key)}")
    else:
        print(f"Sin novedades. Fechas actuales: {len(current)}")


def main() -> None:
    if "--loop" in sys.argv:
        print("Modo loop: chequeando cada 5 minutos. Ctrl+C para frenar.")
        while True:
            try:
                check_once()
            except Exception as e:
                print(f"[ERROR] {e}")
            time.sleep(CHECK_INTERVAL_SECONDS)
    else:
        check_once()


if __name__ == "__main__":
    main()
