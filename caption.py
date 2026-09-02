"""
Lógica de generación de captions para @bici.venta.

Toma el mensaje libre que Aleksa manda por Telegram con los datos de una
bici y devuelve el caption completo, listo para copiar y pegar en Instagram,
siguiendo el formato real de la cuenta.

Soporta dos proveedores de IA intercambiables por variable de entorno
(AI_PROVIDER), pensado para poder comparar resultados sin tocar lo que ya
funciona en producción:

- "gemini" (default — el que ya usa el bot en producción): Google AI
  Studio, tier gratuito, modelo `gemini-3.6-flash`. Tarda ~20-30s.
- "groq": Groq Cloud (console.groq.com), también gratis, corre modelos
  abiertos (por defecto `openai/gpt-oss-120b`) en hardware propio (LPUs) y
  suele responder en 1-3 segundos en vez de 20-30. La contra: no es un
  modelo propietario tipo Gemini/GPT/Claude, así que conviene comparar la
  calidad del caption unos días antes de migrar el bot de verdad.

Para probar Groq sin tocar producción: conseguir una API key gratis en
console.groq.com/keys y, en las variables de entorno de Render, agregar
GROQ_API_KEY y AI_PROVIDER=groq. Sin esas dos variables, el bot sigue
usando Gemini exactamente como antes. Ver README.md para más detalle.
"""

import os
import time

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
AI_PROVIDER = os.environ.get("AI_PROVIDER", "gemini").strip().lower()

REINTENTOS_ANTE_ERROR_SERVIDOR = 2  # 1 intento + 1 reintento
ESPERA_ENTRE_REINTENTOS_SEG = 3


class IARateLimitError(RuntimeError):
    """El proveedor de IA devolvió un error de cuota/rate limit (429)."""


class IAIndisponibleError(RuntimeError):
    """El proveedor de IA falló repetidamente por un error de servidor
    (5xx), incluso después de reintentar."""


_gemini_client = None
_groq_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        from google import genai

        api_key = os.environ["GEMINI_API_KEY"]
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        from groq import Groq

        api_key = os.environ["GROQ_API_KEY"]
        _groq_client = Groq(api_key=api_key)
    return _groq_client


# Ejemplos reales tomados del feed de @bici.venta (agosto 2026), usados como
# few-shot para que el modelo calque el tono y el formato exacto.
EJEMPLOS = """\
--- EJEMPLO 1 (MTB Enduro) ---
Datos que dio el vendedor: Specialized Enduro Elite Carbon, 2018, talla M, carbono, \
aro 27.5" Alexrims, suspensión delantera RockShox Lyrik 170mm, suspensión trasera \
RockShox Monarch Plus R, frenos Shimano Saint, transmisión SRAM GX 12v, bielas \
Truvativ, dropper RockShox Reverb, timón Contact, asiento Specialized, pedales \
Shimano Saint, precio $1,900 dólares.

Caption esperado:
🚵‍♂️ SE VENDE 🚵‍♂️

• Marca: Specialized
• Modelo: Enduro Elite Carbon
• Año: 2018
• Talla: M
• Material: Carbono
• Aro: 27.5” Alexrims
• Suspensión delantera: RockShox Lyrik 170mm
• Suspensión trasera: RockShox Monarch Plus R
• Frenos: Shimano Saint
• Transmisión: SRAM GX 12v
• Bielas: Truvativ
• Dropper: RockShox Reverb
• Timón: Contact
• Asiento: Specialized
• Pedales: Shimano Saint

• Precio💵: $1,900 dólares

La Specialized Enduro Elite Carbon 2018 es una enduro enfocada en terrenos técnicos y \
descensos exigentes. Su cuadro de carbono, RockShox Lyrik de 170mm, Monarch Plus y \
componentes de alto rendimiento como los frenos Shimano Saint ofrecen una configuración \
sólida para quienes buscan una bicicleta agresiva y confiable para montaña.

En bici.venta tenemos la bicicleta ideal para ti, al mejor precio.

#specialized #enduro #endurobike #mtb #carbonbike

--- EJEMPLO 2 (MTB XC, con datos de condición/garantía) ---
Datos que dio el vendedor: Scott Spark RC Team, 2023, talla M, carbono, aros 29" \
carbono, suspensión delantera FOX 34 120mm, suspensión trasera Scott Nude 120mm, \
frenos Shimano XT hidráulicos, transmisión Shimano XT/XTR 12v, llantas tubeless \
ready, timón carbono, tiene BiciWrap, único dueño, garantía y factura de compra, \
mantenimiento al día, precio $3,750 dólares.

Caption esperado:
🚵‍♂️ SE VENDE 🚵‍♂️

• Marca: Scott
• Modelo: Spark RC Team
• Año: 2023
• Talla: M
• Material: Carbono
• Aros: 29” Carbono
• Suspensión delantera: FOX 34 120mm
• Suspensión trasera: Scott Nude 120mm
• Frenos: Shimano XT hidráulicos
• Transmisión: Shimano XT / XTR 12v
• Llantas: Tubeless Ready
• Timón: Carbono
• Extra: BiciWrap

• Precio💵: $3,750 dólares

La Scott Spark RC Team 2023 es una doble suspensión de XC de alto rendimiento, diseñada \
para competir y moverse rápido en terrenos técnicos. Su cuadro de carbono, suspensión \
FOX 34, transmisión XT/XTR y frenos XT ofrecen una excelente combinación de ligereza, \
eficiencia y control. Además, esta unidad ha tenido un único dueño, cuenta con garantía \
y factura de compra, y mantenimiento al día.

En bici.venta tenemos la bicicleta ideal para ti, al mejor precio.

#scott #sparkrc #xc #mtbperu #carbonbike

--- EJEMPLO 3 (MTB, datos mínimos → completar con specs de fábrica) ---
Datos que dio el vendedor: Trek Marlin 7, 2022, talla M, precio S/ 2,200.

(El vendedor NO detalló componentes, solo marca, modelo, año, talla y precio. \
Como es el caso de datos mínimos, se completan los specs con la configuración \
de fábrica real de la Trek Marlin 7 2022.)

Caption esperado:
🚵‍♂️ SE VENDE 🚵‍♂️

• Marca: Trek
• Modelo: Marlin 7
• Año: 2022
• Talla: M
• Material: Aluminio Alpha Silver
• Aro: 29”
• Suspensión delantera: RockShox Judy, 100mm
• Frenos: Shimano hidráulicos
• Transmisión: Shimano Deore 1x10
• Llantas: Bontrager Tubeless Ready
• Timón: Bontrager alloy

• Precio💵: S/ 2,200

La Trek Marlin 7 2022 es una MTB de cross country ideal para quien busca entrar \
al mundo del ciclismo de montaña con una base confiable. Su cuadro de aluminio \
Alpha Silver, suspensión RockShox Judy de 100mm, frenos hidráulicos Shimano y \
transmisión Deore 1x10 la hacen una opción sólida para trails y uso urbano \
exigente.

En bici.venta tenemos la bicicleta ideal para ti, al mejor precio.

#trek #marlin7 #mtb #mtbperu #xc
"""

SYSTEM_PROMPT = f"""Eres el redactor de captions de Instagram de @bici.venta, una \
cuenta peruana (13.1K seguidores) que hace de intermediaria en venta de bicicletas \
usadas y seminuevas. Cada post sigue SIEMPRE el mismo formato. Tu única tarea es \
tomar los datos que te pasa el dueño de la cuenta (en cualquier orden, en su propio \
formato, a veces abreviado) y devolver el caption completo, listo para copiar y \
pegar en Instagram. No agregues comentarios tuyos antes ni después del caption: tu \
respuesta completa ES el caption, nada más.

Sobre inventar specs: por defecto NO inventes specs que no te dieron — usa solo lo \
que el vendedor escribió. La ÚNICA excepción es el "caso de datos mínimos" descrito \
en el punto 2 más abajo (cuando el vendedor te da prácticamente solo marca, modelo, \
año y/o talla): ahí SÍ debes completar los specs de fábrica del modelo.

FORMATO EXACTO (respeta saltos de línea en blanco entre secciones):

1. Línea de encabezado con emoji repetido a cada lado + "SE VENDE", según la \
categoría de la bici:
   - MTB (enduro, downhill, XC, trail): 🚵‍♂️ SE VENDE 🚵‍♂️
   - Ruta / gravel: 🚴‍♂️ SE VENDE 🚴‍♂️
   - E-bike: ⚡ SE VENDE ⚡
   - Triatlón: 🏊‍♂️🚴‍♂️🏃‍♂️ SE VENDE 🏊‍♂️🚴‍♂️🏃‍♂️
   Si no es obvio, usa el emoji de MTB por defecto.

2. Línea en blanco, luego la lista de specs en viñetas con "•". Usa este orden \
cuando aplique: Marca, Modelo, Año, Talla, Material, Aro/Aros, Suspensión \
delantera, Suspensión trasera, Sistema de suspensión, Frenos, Transmisión, \
Bielas, Llantas, Dropper, Timón, Potencia, Asiento, Pedales, Extra, Condición, \
Ubicación. Cada línea con el formato "• Campo: valor".

   Hay dos casos posibles, según cuánto detalle te dio el vendedor:

   - CASO NORMAL (te dio una lista de specs de componentes, aunque sea \
parcial): usa SOLO los campos que efectivamente te dio. No agregues ni \
inventes specs que no mencionó.

   - CASO DATOS MÍNIMOS (te dio prácticamente solo marca, modelo, año y/o \
talla — SIN detallar componentes como suspensión, frenos, transmisión, \
material, aro, etc.): en este caso SÍ debes completar tú los campos de specs \
que apliquen a esa categoría de bici (Material, Aro/Aros, Suspensión, Frenos, \
Transmisión, Bielas, Llantas, Timón, etc.), usando la configuración de \
FÁBRICA (stock, tal como sale de fábrica) real de ESE modelo y año exactos, \
según tu conocimiento del catálogo de esa marca. Si el vendedor menciona algún \
upgrade o cambio puntual sobre esa bici (ej. "le cambiaron la suspensión a Fox \
34", "transmisión SRAM GX nueva", "le pusieron dropper"), usa ese dato para \
ese campo puntual en vez del de fábrica, y completa el resto igual con specs \
de fábrica. Si no estás 100% seguro de la configuración exacta de fábrica para \
ese año puntual, usa la configuración típica/más cercana de esa gama o \
versión del modelo en vez de dejar el campo vacío — nunca dejes specs vacíos \
ni escribas "no especificado". Este caso NO aplica si el vendedor ya te dio \
una lista de specs de componentes (aunque sea corta): ahí siempre manda lo \
que él te dio (caso normal de arriba).

3. Línea en blanco, luego "• Precio💵: " seguido del precio tal cual te lo dieron \
(si dicen dólares usa "$X dólares", si dicen soles usa "S/ X").

4. Línea en blanco, luego un párrafo de 3 a 5 oraciones en tono cercano y \
vendedor (no genérico ni robótico) que mencione el modelo, 2-4 componentes o \
características clave de las que aparecen en la lista de specs del punto 2 \
(ya sea porque el vendedor las dio o porque las completaste con specs de \
fábrica en el caso de datos mínimos), y para qué tipo de uso/terreno sirve. \
Si el vendedor mencionó condición, dueño único, garantía, factura o mantenimiento, \
inclúyelo naturalmente al final del párrafo. No inventes beneficios ni specs \
que no estén en la lista del punto 2.

5. Línea en blanco, luego siempre esta línea fija, exacta, sin cambios: \
"En bici.venta tenemos la bicicleta ideal para ti, al mejor precio."

6. Línea en blanco, luego 4 a 6 hashtags en minúsculas separados por espacio: \
marca, modelo (sin espacios), categoría (mtb/ruta/gravel/ebike/triatlon), y si \
aplica el material (ej. carbonbike) o "mtbperu"/"rutaperu". Sin numeral repetido \
ni texto extra.

Aquí tienes dos ejemplos reales ya publicados (para que calques el tono y \
formato) y un tercer ejemplo que ilustra el caso de datos mínimos explicado \
en el punto 2:

{EJEMPLOS}

Recuerda: responde ÚNICAMENTE con el caption final, sin explicaciones, sin \
comillas envolventes, sin markdown extra."""


def generar_caption(texto_usuario: str) -> str:
    """Genera el caption con el proveedor de IA configurado en AI_PROVIDER
    ("gemini" por default, o "groq")."""
    if AI_PROVIDER == "groq":
        return _generar_caption_groq(texto_usuario)
    if AI_PROVIDER == "gemini":
        return _generar_caption_gemini(texto_usuario)
    raise RuntimeError(
        f"AI_PROVIDER='{AI_PROVIDER}' no reconocido (usa 'gemini' o 'groq')"
    )


def _generar_caption_gemini(texto_usuario: str) -> str:
    """Llama a la API de Gemini para generar el caption a partir del mensaje
    libre que mandó el usuario por Telegram.

    Reintenta una vez si Gemini falla por un error transitorio del servidor
    (5xx) — el tier gratuito a veces devuelve un 503 puntual bajo carga.
    Si el error es 429 (cuota/rate limit) no tiene sentido reintentar: se
    avisa de una vez con un mensaje claro.
    """
    from google.genai import errors as genai_errors
    from google.genai import types

    client = _get_gemini_client()
    contents = f"Datos de la bici (tal cual los mandó el vendedor):\n\n{texto_usuario}"
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        # Modelos "thinking" (como gemini-3.x) gastan parte del presupuesto de
        # salida en razonamiento interno antes de escribir la respuesta visible,
        # así que dejamos bastante margen para que el caption final no se corte
        # a mitad de camino. (thinking_budget=0 no es válido para este modelo,
        # así que no lo tocamos y confiamos en el margen extra.)
        max_output_tokens=8192,
        temperature=0.7,
    )

    ultimo_error_servidor = None
    for intento in range(1, REINTENTOS_ANTE_ERROR_SERVIDOR + 1):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL, contents=contents, config=config,
            )
        except genai_errors.APIError as e:
            if e.code == 429:
                raise IARateLimitError(str(e)) from e
            if e.code and e.code >= 500:
                ultimo_error_servidor = e
                if intento < REINTENTOS_ANTE_ERROR_SERVIDOR:
                    time.sleep(ESPERA_ENTRE_REINTENTOS_SEG)
                    continue
                raise IAIndisponibleError(str(e)) from e
            raise
        else:
            texto = (response.text or "").strip()
            if not texto:
                raise RuntimeError(
                    "Gemini no devolvió texto (revisa response.candidates / safety blocks)"
                )
            return texto

    # No debería llegar acá, pero por las dudas:
    raise IAIndisponibleError(str(ultimo_error_servidor))


def _generar_caption_groq(texto_usuario: str) -> str:
    """Llama a la API de Groq (chat completions estilo OpenAI) para generar
    el caption. Misma política de reintentos que Gemini: 1 reintento ante
    5xx, sin reintentar ante 429 (cuota)."""
    from groq import APIStatusError

    client = _get_groq_client()
    mensajes = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"Datos de la bici (tal cual los mandó el vendedor):\n\n{texto_usuario}",
        },
    ]

    ultimo_error_servidor = None
    for intento in range(1, REINTENTOS_ANTE_ERROR_SERVIDOR + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=mensajes,
                temperature=0.7,
                max_completion_tokens=2048,
            )
        except APIStatusError as e:
            if e.status_code == 429:
                raise IARateLimitError(str(e)) from e
            if e.status_code >= 500:
                ultimo_error_servidor = e
                if intento < REINTENTOS_ANTE_ERROR_SERVIDOR:
                    time.sleep(ESPERA_ENTRE_REINTENTOS_SEG)
                    continue
                raise IAIndisponibleError(str(e)) from e
            raise
        else:
            texto = (response.choices[0].message.content or "").strip()
            if not texto:
                raise RuntimeError("Groq no devolvió texto")
            return texto

    raise IAIndisponibleError(str(ultimo_error_servidor))
