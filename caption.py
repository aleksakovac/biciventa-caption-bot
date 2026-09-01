"""
Lógica de generación de captions para @bici.venta.

Toma el mensaje libre que Aleksa manda por Telegram con los datos de una
bici y devuelve el caption completo, listo para copiar y pegar en Instagram,
siguiendo el formato real de la cuenta.
"""

import os
from google import genai
from google.genai import types

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

_client = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = os.environ["GEMINI_API_KEY"]
        _client = genai.Client(api_key=api_key)
    return _client


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
"""

SYSTEM_PROMPT = f"""Eres el redactor de captions de Instagram de @bici.venta, una \
cuenta peruana (13.1K seguidores) que hace de intermediaria en venta de bicicletas \
usadas y seminuevas. Cada post sigue SIEMPRE el mismo formato. Tu única tarea es \
tomar los datos que te pasa el dueño de la cuenta (en cualquier orden, en su propio \
formato, a veces abreviado) y devolver el caption completo, listo para copiar y \
pegar en Instagram. No inventes specs que no te dieron. No agregues comentarios \
tuyos antes ni después del caption: tu respuesta completa ES el caption, nada más.

FORMATO EXACTO (respeta saltos de línea en blanco entre secciones):

1. Línea de encabezado con emoji repetido a cada lado + "SE VENDE", según la \
categoría de la bici:
   - MTB (enduro, downhill, XC, trail): 🚵‍♂️ SE VENDE 🚵‍♂️
   - Ruta / gravel: 🚴‍♂️ SE VENDE 🚴‍♂️
   - E-bike: ⚡ SE VENDE ⚡
   - Triatlón: 🏊‍♂️🚴‍♂️🏃‍♂️ SE VENDE 🏊‍♂️🚴‍♂️🏃‍♂️
   Si no es obvio, usa el emoji de MTB por defecto.

2. Línea en blanco, luego la lista de specs en viñetas con "•", SOLO con los \
campos que el vendedor te dio (nunca inventes ni completes specs faltantes). \
Usa este orden cuando aplique: Marca, Modelo, Año, Talla, Material, Aro/Aros, \
Suspensión delantera, Suspensión trasera, Sistema de suspensión, Frenos, \
Transmisión, Bielas, Llantas, Dropper, Timón, Potencia, Asiento, Pedales, \
Extra, Condición, Ubicación. Cada línea con el formato "• Campo: valor".

3. Línea en blanco, luego "• Precio💵: " seguido del precio tal cual te lo dieron \
(si dicen dólares usa "$X dólares", si dicen soles usa "S/ X").

4. Línea en blanco, luego un párrafo de 3 a 5 oraciones en tono cercano y \
vendedor (no genérico ni robótico) que mencione el modelo, 2-4 componentes o \
características clave que sí te dieron, y para qué tipo de uso/terreno sirve. \
Si el vendedor mencionó condición, dueño único, garantía, factura o mantenimiento, \
inclúyelo naturalmente al final del párrafo. No inventes specs ni beneficios que \
no te dieron.

5. Línea en blanco, luego siempre esta línea fija, exacta, sin cambios: \
"En bici.venta tenemos la bicicleta ideal para ti, al mejor precio."

6. Línea en blanco, luego 4 a 6 hashtags en minúsculas separados por espacio: \
marca, modelo (sin espacios), categoría (mtb/ruta/gravel/ebike/triatlon), y si \
aplica el material (ej. carbonbike) o "mtbperu"/"rutaperu". Sin numeral repetido \
ni texto extra.

Aquí tienes dos ejemplos reales ya publicados, para que calques el tono y formato:

{EJEMPLOS}

Recuerda: responde ÚNICAMENTE con el caption final, sin explicaciones, sin \
comillas envolventes, sin markdown extra."""


def generar_caption(texto_usuario: str) -> str:
    """Llama a la API de Gemini para generar el caption a partir del mensaje
    libre que mandó el usuario por Telegram."""
    client = _get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=f"Datos de la bici (tal cual los mandó el vendedor):\n\n{texto_usuario}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            # Modelos "thinking" (como gemini-3.x) gastan parte del presupuesto de
            # salida en razonamiento interno antes de escribir la respuesta visible,
            # así que dejamos bastante margen para que el caption final no se corte
            # a mitad de camino. (thinking_budget=0 no es válido para este modelo,
            # así que no lo tocamos y confiamos en el margen extra.)
            max_output_tokens=8192,
            temperature=0.7,
        ),
    )
    texto = (response.text or "").strip()
    if not texto:
        raise RuntimeError("Gemini no devolvió texto (revisa response.candidates / safety blocks)")
    return texto
