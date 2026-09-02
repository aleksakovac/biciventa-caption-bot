"""
Bot de Telegram que genera captions para las publicaciones de bicis de
@bici.venta. Recibe un mensaje con los datos de la bici y responde con el
caption completo, listo para copiar y pegar en Instagram.

Corre como un webhook (Flask) pensado para desplegarse en Render u otro
hosting similar. Ver README.md para la guía de despliegue paso a paso.
"""

import logging
import os
import threading
import time
from collections import deque

import requests
from flask import Flask, request

from caption import IAIndisponibleError, IARateLimitError, IARespuestaVaciaError, generar_caption

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

# Límite real de la API de Telegram para sendMessage. Si algún caption
# saliera más largo (no debería, pero por las dudas), lo partimos en varios
# mensajes en vez de que Telegram lo rechace con un 400 silencioso.
LIMITE_TELEGRAM = 4096

# Últimos update_id ya procesados, para no reprocesar un mismo mensaje si
# Telegram reenvía el update (pasa si el webhook no respondió rápido, algo
# que ya no debería ocurrir ahora que la generación corre en segundo plano,
# pero esto queda como segunda capa de protección). En memoria nomás: se
# resetea con cada redeploy/restart, y para un bot de un solo usuario eso
# es más que suficiente.
_UPDATE_IDS_RECIENTES = deque(maxlen=500)

# Referencia al último hilo en segundo plano lanzado por el webhook. Solo la
# usan los tests, para esperar a que termine antes de revisar qué se mandó.
_ultimo_hilo_para_tests = None


def _update_ya_procesado(update_id):
    if update_id is None:
        return False
    if update_id in _UPDATE_IDS_RECIENTES:
        return True
    _UPDATE_IDS_RECIENTES.append(update_id)
    return False


def enviar_mensaje(chat_id, texto):
    """Manda un mensaje de texto a Telegram. Si supera el límite de 4096
    caracteres de sendMessage, lo parte en varios mensajes seguidos."""
    partes = [texto[i:i + LIMITE_TELEGRAM] for i in range(0, len(texto), LIMITE_TELEGRAM)] or [""]
    for parte in partes:
        try:
            r = requests.post(
                f"{TELEGRAM_API}/sendMessage",
                json={"chat_id": chat_id, "text": parte},
                timeout=20,
            )
            r.raise_for_status()
        except requests.RequestException:
            log.exception("Fallo al enviar mensaje a Telegram (chat_id=%s)", chat_id)
            return


@app.get("/")
def health():
    return "ok", 200


def _generar_y_responder(chat_id, texto):
    """Corre en un hilo aparte: avisa que está generando, llama a Gemini
    (que puede tardar 20-30s) y manda el resultado. Vive fuera del ciclo
    request/response de Flask a propósito — ver nota en webhook()."""
    enviar_mensaje(chat_id, "🕐 Generando tu caption, dame unos segundos...")

    t0 = time.monotonic()
    try:
        caption = generar_caption(texto)
    except IARateLimitError:
        log.warning("Rate limit del proveedor de IA alcanzado (chat_id=%s)", chat_id)
        enviar_mensaje(
            chat_id,
            "Se llegó al límite de uso gratuito de la IA por ahora. Espera unos minutos y vuelve a intentar.",
        )
        return
    except IAIndisponibleError:
        log.warning("Proveedor de IA no disponible tras reintentos (chat_id=%s)", chat_id)
        enviar_mensaje(chat_id, "La IA está temporalmente saturada. Intenta de nuevo en un minuto.")
        return
    except IARespuestaVaciaError as e:
        log.warning("La IA no devolvió texto tras reintentar (chat_id=%s): %s", chat_id, e)
        enviar_mensaje(
            chat_id,
            "El caption no se pudo generar completo (probablemente por lo complejo del pedido). "
            "Intenta de nuevo — si vuelve a pasar, prueba mandando también las specs que conozcas "
            "en vez de solo marca/modelo/talla/año.",
        )
        return
    except Exception:
        log.exception("Fallo generando el caption (chat_id=%s)", chat_id)
        enviar_mensaje(chat_id, "Algo falló generando el caption. Intenta de nuevo en un momento.")
        return

    log.info("Caption generado en %.1fs (chat_id=%s)", time.monotonic() - t0, chat_id)
    enviar_mensaje(chat_id, caption)


@app.post(f"/webhook/{WEBHOOK_SECRET}")
def webhook():
    global _ultimo_hilo_para_tests

    update = request.get_json(silent=True) or {}

    # Telegram reintenta el mismo update si no recibe la respuesta a tiempo.
    # Como generar un caption tarda bastante, ignoramos updates repetidos en
    # vez de arriesgarnos a generar y mandar el mismo caption dos veces.
    if _update_ya_procesado(update.get("update_id")):
        log.info("Update duplicado ignorado: %s", update.get("update_id"))
        return "ok", 200

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

    # Si el mensaje viene con el username del bot pegado (ej. "/start@biciventa_captions_bot",
    # como a veces manda Telegram), lo ignoramos para reconocer el comando igual.
    primera_palabra = texto.split(maxsplit=1)[0].lower().split("@")[0]
    if primera_palabra in ("/start", "/help", "/ayuda"):
        enviar_mensaje(chat_id, AYUDA)
        return "ok", 200

    # La generación (Gemini, 20-30s, hasta 50s con Render dormido) corre en
    # un hilo aparte para que Flask responda "ok" a Telegram de inmediato.
    # Si no hiciéramos esto, el request quedaría colgado esperando a Gemini
    # y Telegram, al no recibir respuesta a tiempo, reintentaría el mismo
    # update — generando (y mandando) el caption duplicado.
    hilo = threading.Thread(target=_generar_y_responder, args=(chat_id, texto), daemon=True)
    hilo.start()
    _ultimo_hilo_para_tests = hilo

    return "ok", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
