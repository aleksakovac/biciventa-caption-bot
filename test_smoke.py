"""Smoke test local: valida el wiring de Flask/webhook sin llamar a las APIs
reales de Telegram ni de Gemini. No se sube a producción."""

import os
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "fake-token")
os.environ.setdefault("WEBHOOK_SECRET", "sekret123")
os.environ.setdefault("GEMINI_API_KEY", "fake-key")

import app  # noqa: E402
from caption import IAIndisponibleError, IARateLimitError, IARespuestaVaciaError  # noqa: E402


def fake_generar_caption(texto):
    return "🚵‍♂️ SE VENDE 🚵‍♂️\n\n• Marca: Test\n\n• Precio💵: $1 dólar\n\n...\n\nEn bici.venta tenemos la bicicleta ideal para ti, al mejor precio.\n\n#test"


def build_update(text, user_id=111, update_id=None):
    update = {
        "message": {
            "chat": {"id": 999},
            "from": {"id": user_id},
            "text": text,
        }
    }
    if update_id is not None:
        update["update_id"] = update_id
    return update


def esperar_hilo_en_segundo_plano():
    """La generación corre en threading.Thread; hay que esperarla antes de
    revisar qué se le mandó a Telegram en el test."""
    if app._ultimo_hilo_para_tests is not None:
        app._ultimo_hilo_para_tests.join(timeout=5)
        assert not app._ultimo_hilo_para_tests.is_alive(), "el hilo no terminó a tiempo"


def main():
    client = app.app.test_client()

    # health check
    r = client.get("/")
    assert r.status_code == 200, r.status_code
    print("OK health check")

    with patch("app.generar_caption", side_effect=fake_generar_caption), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None

        # /start (no dispara hilo en segundo plano)
        r = client.post(f"/webhook/sekret123", json=build_update("/start"))
        assert r.status_code == 200
        sent_text = mock_post.call_args.kwargs["json"]["text"]
        assert "Mándame los datos" in sent_text
        print("OK /start responde con la ayuda")

        # /start@biciventa_captions_bot también cuenta como comando
        mock_post.reset_mock()
        r = client.post(f"/webhook/sekret123", json=build_update("/start@biciventa_captions_bot"))
        assert r.status_code == 200
        sent_text = mock_post.call_args.kwargs["json"]["text"]
        assert "Mándame los datos" in sent_text
        print("OK /start@bot también responde con la ayuda")

        # mensaje normal -> responde rápido y en segundo plano avisa que está
        # generando y luego manda el caption
        mock_post.reset_mock()
        r = client.post(f"/webhook/sekret123", json=build_update("Trek Marlin 5, 2022, talla M, $650", update_id=1))
        assert r.status_code == 200
        esperar_hilo_en_segundo_plano()
        assert mock_post.call_count == 2, "debería mandar el aviso de 'generando' y luego el caption"
        aviso = mock_post.call_args_list[0].kwargs["json"]["text"]
        caption_enviado = mock_post.call_args_list[1].kwargs["json"]["text"]
        assert "Generando" in aviso
        assert "SE VENDE" in caption_enviado
        print("OK mensaje normal avisa que está generando y luego envía el caption (en segundo plano)")

        # el mismo update_id repetido (Telegram reintentando el webhook) se ignora
        mock_post.reset_mock()
        r = client.post(f"/webhook/sekret123", json=build_update("Trek Marlin 5, 2022, talla M, $650", update_id=1))
        assert r.status_code == 200
        assert mock_post.call_count == 0, "un update_id repetido no debería procesarse de nuevo"
        print("OK update_id duplicado se ignora (no reprocesa ni reenvía)")

        # wrong secret path -> 404
        r = client.post("/webhook/otro-secreto", json=build_update("hola"))
        assert r.status_code == 404
        print("OK secreto incorrecto devuelve 404")

    # caption más largo que el límite de Telegram (4096) se parte en varios mensajes
    with patch("app.generar_caption", return_value="x" * 5000), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        r = client.post(f"/webhook/sekret123", json=build_update("bici con specs larguísimas", update_id=2))
        assert r.status_code == 200
        esperar_hilo_en_segundo_plano()
        textos_enviados = [c.kwargs["json"]["text"] for c in mock_post.call_args_list]
        # 1 aviso de "generando" + 2 partes del caption de 5000 caracteres
        assert len(textos_enviados) == 3
        assert len(textos_enviados[1]) == 4096
        assert len(textos_enviados[2]) == 5000 - 4096
        print("OK caption más largo que 4096 caracteres se parte en varios mensajes")

    # Gemini sin cuota (429) -> mensaje claro, sin reintentar infinito
    with patch("app.generar_caption", side_effect=IARateLimitError("429")), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        r = client.post(f"/webhook/sekret123", json=build_update("Trek Marlin 5, 2022, $650", update_id=3))
        assert r.status_code == 200
        esperar_hilo_en_segundo_plano()
        ultimo_mensaje = mock_post.call_args_list[-1].kwargs["json"]["text"]
        assert "límite de uso gratuito" in ultimo_mensaje
        print("OK rate limit de Gemini avisa con mensaje específico")

    # Gemini caído tras reintentos (5xx) -> mensaje claro
    with patch("app.generar_caption", side_effect=IAIndisponibleError("503")), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        r = client.post(f"/webhook/sekret123", json=build_update("Trek Marlin 5, 2022, $650", update_id=4))
        assert r.status_code == 200
        esperar_hilo_en_segundo_plano()
        ultimo_mensaje = mock_post.call_args_list[-1].kwargs["json"]["text"]
        assert "temporalmente saturada" in ultimo_mensaje
        print("OK Gemini caído tras reintentos avisa con mensaje específico")

    # Gemini devuelve respuesta vacía tras reintentar (ej. se quedó sin
    # presupuesto de "thinking") -> mensaje específico, no el genérico
    with patch("app.generar_caption", side_effect=IARespuestaVaciaError("finish_reason=MAX_TOKENS")), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        r = client.post(f"/webhook/sekret123", json=build_update("Trek Marlin 5, 2022, talla M", update_id=6))
        assert r.status_code == 200
        esperar_hilo_en_segundo_plano()
        ultimo_mensaje = mock_post.call_args_list[-1].kwargs["json"]["text"]
        assert "no se pudo generar completo" in ultimo_mensaje
        print("OK respuesta vacía de la IA avisa con mensaje específico (no el genérico)")

    # ALLOWED_USER_IDS bloquea usuarios no autorizados
    app.ALLOWED_USER_IDS = {"1"}
    with patch("app.generar_caption", side_effect=fake_generar_caption), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        r = client.post(f"/webhook/sekret123", json=build_update("hola", user_id=999, update_id=5))
        assert r.status_code == 200
        sent_text = mock_post.call_args.kwargs["json"]["text"]
        assert "privado" in sent_text
        print("OK usuario no autorizado es bloqueado")

    print("\nTodos los smoke tests pasaron.")


if __name__ == "__main__":
    main()
