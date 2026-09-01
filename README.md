# Bot de Telegram: captions para @bici.venta

Le mandas al bot los datos de una bici en un solo mensaje (como se te ocurra
escribirlos) y te responde con el caption completo, en el mismo formato que
usan tus posts reales — encabezado con emoji según categoría, viñetas de
specs, precio, párrafo de venta, línea fija y hashtags.

Corre 24/7 en Render (plan gratuito), como un webhook. No necesitas tu compu
prendida.

## Antes de empezar: lo que necesitas crear tú

Estas cuentas y claves no las puedo crear yo por ti — son tuyas y quedan bajo
tu control.

### 1. Crear el bot en Telegram (~2 min)

1. Abre Telegram y busca **@BotFather**.
2. Mándale `/newbot`.
3. Te va a pedir un nombre (el que se muestra, ej. "BiciVenta Captions") y
   un username que termine en `bot` (ej. `biciventa_captions_bot`).
4. Te devuelve un **token** con este formato: `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`.
   Guárdalo, es tu `TELEGRAM_BOT_TOKEN`.

### 2. (Recomendado) Averiguar tu user id de Telegram

Para que el bot sea privado y solo tú puedas usarlo (y gastar tu API key):

1. Busca **@userinfobot** en Telegram y mándale cualquier mensaje.
2. Te responde con tu **Id** (un número). Ese es tu `ALLOWED_USER_IDS`.

### 3. Conseguir una API key de Gemini (Google AI Studio)

1. Entra a [aistudio.google.com](https://aistudio.google.com) con tu cuenta
   de Google y acepta los términos si te los pide.
2. Ve a **Get API key** → **Create API key**.
3. Copia la key. Es tu `GEMINI_API_KEY`.
4. No hace falta cargar tarjeta ni saldo: el modelo por defecto (Gemini
   Flash) tiene un **tier gratuito** que debería alcanzar sin costo para el
   volumen de captions de la cuenta. Si más adelante lo usas muchísimo y
   quieres más margen, puedes activar facturación desde el mismo panel.

## Desplegar en Render (gratis)

1. Sube esta carpeta a un repositorio de GitHub (puede ser privado).
2. Entra a [render.com](https://render.com) y crea una cuenta (puedes
   registrarte con tu cuenta de GitHub).
3. **New +** → **Web Service** → conecta el repositorio que acabas de subir.
4. Configuración del servicio:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Free
5. En la sección **Environment**, agrega estas variables (los valores que
   sacaste arriba):
   - `TELEGRAM_BOT_TOKEN`
   - `WEBHOOK_SECRET` → invéntate un string largo y aleatorio (por ejemplo,
     corre `python3 -c "import secrets; print(secrets.token_urlsafe(24))"`
     en tu compu y usa lo que te salga)
   - `GEMINI_API_KEY`
   - `ALLOWED_USER_IDS` → tu user id del paso 2 (opcional pero recomendado)
6. Dale a **Create Web Service** y espera a que termine el deploy (2-3 min).
   Render te da una URL tipo `https://biciventa-captions.onrender.com`.

### Nota sobre el plan gratuito de Render

El plan free "se duerme" tras ~15 min sin tráfico. Cuando le mandes un
mensaje al bot después de un rato sin usarlo, la primera respuesta puede
tardar 30-50 segundos mientras Render lo despierta — es normal, no está
roto. Los mensajes siguientes responden al toque.

## Conectar el webhook (un solo comando, una sola vez)

Con tu token y la URL de Render, corre esto una vez (en tu compu, terminal,
o hasta desde el navegador reemplazando los valores en esta URL):

```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=https://<TU-APP>.onrender.com/webhook/<WEBHOOK_SECRET>"
```

Reemplaza `<TELEGRAM_BOT_TOKEN>`, `<TU-APP>` y `<WEBHOOK_SECRET>` por tus
valores reales. Debería responder algo como:

```json
{"ok":true,"result":true,"description":"Webhook was set"}
```

## Probarlo

Abre Telegram, busca tu bot por el username que le pusiste, y mándale
`/start` para ver las instrucciones. Luego mándale algo como:

```
Trek Marlin 5, 2022, talla M, aro 29, frenos hidráulicos Shimano,
transmisión Shimano Deore 10v, suspensión RockShox judy 100mm,
condición usada en buen estado, precio $650 dólares, ubicación Miraflores
```

Y te debería devolver el caption completo, listo para copiar y pegar en el
post de Instagram (junto con las fotos que subas tú directamente ahí).

## Cómo funciona por dentro

- `app.py` — servidor Flask que recibe los mensajes de Telegram vía webhook
  y responde.
- `caption.py` — arma el prompt con el formato exacto de @bici.venta
  (incluye 2 ejemplos reales tomados del feed) y llama a la API de Gemini
  para generar el caption.
- El bot NO toca Instagram para nada — solo te da el texto. Publicar el post
  (con las fotos) lo sigues haciendo tú a mano, como siempre.
- No guarda historial ni base de datos: cada mensaje se procesa solo, sin
  memoria de mensajes anteriores.

## Ajustar el estilo más adelante

Si algún caption sale con el emoji de categoría equivocado, el orden de
specs distinto al que quieres, o el párrafo de venta no te convence, edita
el `SYSTEM_PROMPT` en `caption.py` — ahí están todas las reglas de formato
en texto plano, y los dos ejemplos que usa como referencia. Puedes agregar
más ejemplos reales tuyos para afinar el tono.

## Costos

- Render free: $0/mes (con el "sleep" descrito arriba). Si más adelante
  quieres que responda sin demora en frío, el plan pago arranca en unos
  pocos dólares/mes.
- Gemini: $0 mientras te mantengas dentro del tier gratuito de Flash (debería
  cubrir de sobra el volumen de posts de la cuenta). Puedes revisar tu uso en
  aistudio.google.com → Usage, y los límites/tiers vigentes en
  ai.google.dev/gemini-api/docs/pricing.
