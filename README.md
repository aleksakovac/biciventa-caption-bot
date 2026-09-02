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
  (incluye 2 ejemplos reales tomados del feed + 1 ejemplo del caso de datos
  mínimos) y llama a la API de Gemini para generar el caption.
- El bot NO toca Instagram para nada — solo te da el texto. Publicar el post
  (con las fotos) lo sigues haciendo tú a mano, como siempre.
- No guarda historial ni base de datos: cada mensaje se procesa solo, sin
  memoria de mensajes anteriores.
- Apenas le mandas los datos de una bici, el bot responde de una con un
  aviso ("🕐 Generando tu caption, dame unos segundos...") y después manda
  el caption — así no parece colgado mientras Gemini genera (20-30s
  normalmente, hasta 50s si Render venía dormido).
- Si Gemini falla por un error puntual del servidor (5xx), el bot reintenta
  una vez automáticamente antes de avisarte. Si el error es por límite de
  cuota (429), no reintenta — te avisa de una vez que esperes un momento.
- La generación corre en segundo plano: el webhook le responde "ok" a
  Telegram de inmediato y el aviso + el caption se mandan aparte. Esto evita
  que Telegram, al no recibir respuesta rápido, reintente el mismo mensaje
  y termine generando (y mandando) el caption duplicado. Como refuerzo, el
  bot también recuerda los últimos `update_id` procesados e ignora repetidos.
- Si un caption saliera más largo que el límite de Telegram (4096
  caracteres), se manda partido en varios mensajes en vez de fallar.
- Si le mandas SOLO marca, modelo, año y/o talla (sin detallar componentes
  como suspensión, frenos, transmisión, etc.), el bot completa los specs
  faltantes con la configuración de fábrica (stock) real de ese modelo y
  año. Si mencionas algún upgrade puntual (ej. "le cambiaron la suspensión a
  Fox 34"), ese dato manda sobre el de fábrica solo en ese campo — el resto
  se sigue completando con specs de fábrica. Si en cambio le das una lista de
  specs (aunque sea corta), el bot usa solo esos datos y no completa nada más
  (comportamiento de siempre).

## Probar Groq en vez de Gemini (opcional, sin arriesgar lo que ya funciona)

El bot soporta un segundo proveedor de IA: **Groq**. Hace exactamente lo
mismo (mismo prompt, mismo formato), pero corre en hardware especializado
para inferencia rápida y suele responder en **1-3 segundos** en vez de los
20-30s de Gemini — la contra es que usa un modelo abierto (no propietario
como Gemini), así que conviene comparar la calidad del caption antes de
dejarlo como el proveedor de siempre.

Es 100% opcional y no toca nada de lo que ya anda: mientras no configures
`AI_PROVIDER=groq`, el bot sigue usando Gemini exactamente igual que hasta
ahora.

1. Crea una cuenta gratis en [console.groq.com](https://console.groq.com)
   (no pide tarjeta) y saca una API key en **API Keys → Create API Key**.
2. En las variables de **Environment** de Render, agrega:
   - `GROQ_API_KEY` → la key que sacaste.
   - `AI_PROVIDER` → `groq`.
3. Guarda los cambios — Render redeploya solo con las nuevas variables.
4. Mándale al bot los mismos datos de bici que le mandarías siempre y
   compará el caption contra los que te da Gemini.

Para volver a Gemini en cualquier momento: borra `AI_PROVIDER` (o ponlo en
`gemini`) en las variables de Render. No hace falta tocar código ni volver
a desplegar nada distinto.

Por defecto usa el modelo `openai/gpt-oss-120b` de Groq (el insignia
gratuito). Si querés probar otro modelo del catálogo de Groq, se puede
fijar con la variable opcional `GROQ_MODEL` (ver `console.groq.com/docs/models`
para la lista vigente).

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
- Groq (si lo activas): $0 en el tier gratuito, con un límite de ~1.000
  mensajes/día en los modelos recomendados — muy por encima del volumen de
  la cuenta. Límites vigentes en console.groq.com/docs/rate-limits.
