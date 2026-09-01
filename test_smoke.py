"""Smoke test local: valida el wiring de Flask/webhook sin llamar a las APIs
reales de Telegram ni de Gemini. No se sube a producción."""

import os
from unittest.mock import patch

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "fake-token")
os.environ.setdefault("WEBHOOK_SECRET", "sekret123")
os.environ.setdefault("GEMINI_API_KEY", "fake-key")

import app  # noqa: E402


def fake_generar_caption(texto):
    return "🚵‍♂️ SE VENDE 🚵‍♂️\n\n• Marca: Test\n\n• Precio💵: $1 dólar\n\n...\n\nEn bici.venta tenemos la bicicleta ideal para ti, al mejor precio.\n\n#test"


def build_update(text, user_id=111):
    return {
        "message": {
            "chat": {"id": 999},
            "from": {"id": user_id},
            "text": text,
        }
    }


def main():
    client = app.app.test_client()

    # health check
    r = client.get("/")
    assert r.status_code == 200, r.status_code
    print("OK health check")

    with patch("app.generar_caption", side_effect=fake_generar_caption), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None

        # /start
        r = client.post(f"/webhook/sekret123", json=build_update("/start"))
        assert r.status_code == 200
        sent_text = mock_post.call_args.kwargs["json"]["text"]
        assert "Mándame los datos" in sent_text
        print("OK /start responde con la ayuda")

        # mensaje normal -> genera caption
        mock_post.reset_mock()
        r = client.post(f"/webhook/sekret123", json=build_update("Trek Marlin 5, 2022, talla M, $650"))
        assert r.status_code == 200
        sent_text = mock_post.call_args.kwargs["json"]["text"]
        assert "SE VENDE" in sent_text
        print("OK mensaje normal genera y envía el caption")

        # wrong secret path -> 404
        r = client.post("/webhook/otro-secreto", json=build_update("hola"))
        assert r.status_code == 404
        print("OK secreto incorrecto devuelve 404")

    # ALLOWED_USER_IDS bloquea usuarios no autorizados
    app.ALLOWED_USER_IDS = {"1"}
    with patch("app.generar_caption", side_effect=fake_generar_caption), \
         patch("app.requests.post") as mock_post:
        mock_post.return_value.raise_for_status = lambda: None
        r = client.post(f"/webhook/sekret123", json=build_update("hola", user_id=999))
        assert r.status_code == 200
        sent_text = mock_post.call_args.kwargs["json"]["text"]
        assert "privado" in sent_text
        print("OK usuario no autorizado es bloqueado")

    print("\nTodos los smoke tests pasaron.")


if __name__ == "__main__":
    main()
