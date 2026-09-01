"""
Bot de Telegram que genera captions para las publicaciones de bicis de
@bici.venta. Recibe un mensaje con los datos de la bici y responde con el
caption completo, listo para copiar y pegar en Instagram.

Corre como un webhook (Flask) pensado para desplegarse en Render u otro
hosting similar. Ver README.md para la guía de despliegue paso a paso.
"""

import logging
import os

import requests
from flask import Flask, request

from caption import generar_caption

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("biciventa-caption-bot")

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
# Ruta secreta del webhook: evita que cualquiera en internet pueda mandarle
# updates falsos al bot adivinando la URL. Debe coincidir con la que se usa
# al registrar el webhook en Telegram (ver README).
WEBHOOK_SECRET = os.environ["WEBHOOK_SECRET"]
# Opcional: lista de IDs de usuario de Telegram separados por coma que pueden
# usar el bot. Si se deja vacío, cualquiera que le escriba al bot puede
# generar captions (y gastar tu cuota de la API de Gemini) — se recomienda
# configurarlo apenas sepas tu user id (ver README).
ALLOWED_USER_IDS = {
    uid.strip() for uid in os.environ.get("ALLOWED_USER_IDS", "").split(",") if uid.strip()
}

TELEGRAM_API = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

AYUDA = (
    "Mándame los datos de una bici en un solo mensaje (marca, modelo, año, "
    "talla, specs que tengas, precio, y cualquier extra como condición o "
    "garantía) y te devuelvo el caption listo para pegar en Instagram.\n\n"
    "No hace falta ningún formato especial, escríbelo como se lo dirías a "
    "alguien."
)


def enviar_mensaje(chat_id, texto):
    try:
        r = requests.post(
            f"{TELEGRAM_API}/sendMessage",
            json={"chat_id": chat_id, "text": texto},
            timeout=20,
        )
        r.raise_for_status()
    except requests.RequestException:
        log.exception("Fallo al enviar mensaje a Telegram (chat_id=%s)", chat_id)


@app.get("/")
def health():
    return "ok", 200


@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    update = request.get_json(silent=True) or {}
    message = update.get("message") or update.get("edited_message")
    if not message:
        return "ignored", 200

    chat_id = message["chat"]["id"]
    user_id = str(message.get("from", {}).get("id", ""))
    texto = (message.get("text") or "").strip()

    if ALLOWED_USER_IDS and user_id not in ALLOWED_USER_IDS:
        log.info("Usuario no autorizado intentó usar el bot: %s", user_id)
        enviar_mensaje(chat_id, "Este bot es privado, no está disponible para tu usuario.")
        return "ok", 200

    if not texto:
        enviar_mensaje(chat_id, "Mándame el texto con los datos de la bici (fotos no las proceso, solo texto).")
        return "ok", 200

    if texto in ("/start", "/help", "/ayuda"):
        enviar_mensaje(chat_id, AYUDA)
        return "ok", 200

    try:
        caption = generar_caption(texto)
    except Exception:
        log.exception("Fallo generando el caption")
        enviar_mensaje(chat_id, "Algo falló generando el caption. Intenta de nuevo en un momento.")
        return "ok", 200

    enviar_mensaje(chat_id, caption)
    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
