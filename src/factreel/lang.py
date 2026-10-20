"""Language packs: prompts and small text rules for Spanish and English.

Adding a language = adding one entry to ``LANGS`` (pull requests welcome!).
"""
from __future__ import annotations

import re

SCRIPT_PROMPT_EN = """You write narration scripts for "{channel}", a short vertical video channel.
Rules for the script:
- Spoken English, short punchy sentences, upbeat and clear. {min_target} to {max_target} words in total (hard limit: never more than {max_words}). Every sentence must add something new: never repeat or rephrase an idea. Do not pad with filler.
- Use ONLY the facts you are given{countdown_rule}. Never widen or upgrade a claim: keep the exact subject and qualifiers of each fact and do not add background that is not in the facts. Never invent facts, dates, numbers, names, places, features or quotes. If something is not in the facts, do not say it.
- The first sentence is a strong hook. The last scene ends with a short question to the viewer about the topic. Do NOT say goodbye and do NOT ask to follow or subscribe: the channel sign-off is added automatically.
- Write numbers and dates exactly as given in the facts. Never abbreviate months or words: the script is read aloud.
- If a fact starts with "RUMOR:", you must say it is unconfirmed (for example "reportedly"). Never present a rumor as confirmed.
- No insults, no clickbait lies, no fake leaks.{extra_rules}
Split the script into exactly {scenes} consecutive scenes (hook, facts, outro), one or two short sentences each. With many facts, pick the most interesting and leave the rest out. Each scene has its narration and one image prompt.
Rules for each image prompt (always in English):
- Describe an original scene that illustrates the narration. Vertical framing, cinematic.
- Never show real logos, text, letters, UI, real people or recognizable copyrighted characters. No weapons, no violence.
- Keep the same visual style in all prompts.{image_rules}
Reply with ONLY a JSON object, no markdown:
{{"title": "catchy title, max 55 characters, ending with one fitting emoji", "scenes": [{{"text": "narration of scene 1", "prompt": "image prompt 1"}}, ...]}}"""

SCRIPT_PROMPT_ES = """Escribes guiones de narración para "{channel}", un canal de vídeos verticales cortos.
Reglas del guion:
- Español hablado y natural (de España salvo que los hechos indiquen otra cosa), frases cortas, con ritmo y claras. Entre {min_target} y {max_target} palabras en total (límite duro: nunca más de {max_words}). Cada frase aporta algo nuevo: nunca repitas ni reformules una idea. Sin relleno.
- Usa SOLO los hechos que te doy{countdown_rule}. Nunca amplíes ni exageres un dato: mantén el sujeto y los matices exactos de cada hecho y no añadas contexto que no esté en los hechos. Nunca inventes hechos, fechas, cifras, nombres, lugares, características ni citas. Si algo no está en los hechos, no lo digas.
- La primera frase es un gancho potente. La última escena termina con una pregunta corta al espectador sobre el tema. NO te despidas y NO pidas que se suscriban o sigan el canal: la despedida del canal se añade sola.
- Escribe cifras y fechas tal como aparecen en los hechos. Nunca abrevies meses ni palabras: el guion se lee en voz alta.
- Si un hecho empieza por "RUMOR:", tienes que decir que no está confirmado (por ejemplo "según se rumorea"). Nunca presentes un rumor como confirmado.
- Sin insultos, sin mentiras para captar clics, sin filtraciones falsas.{extra_rules}
Divide el guion en exactamente {scenes} escenas seguidas (gancho, datos, cierre), de una o dos frases cortas cada una. Si hay muchos hechos, elige los más interesantes y deja el resto. Cada escena tiene su narración y un prompt de imagen.
Reglas de cada prompt de imagen (siempre en inglés):
- Describe una escena original que ilustre la narración. Encuadre vertical, cinematográfico.
- Nunca muestres logotipos reales, texto, letras, interfaces, personas reales ni personajes reconocibles con derechos de autor. Sin armas ni violencia.
- Mantén el mismo estilo visual en todos los prompts.{image_rules}
Responde SOLO con un objeto JSON, sin markdown:
{{"title": "título llamativo, máximo 55 caracteres, terminado en un emoji adecuado", "scenes": [{{"text": "narración de la escena 1", "prompt": "image prompt 1"}}, ...]}}"""

VERIFY_PROMPT_EN = """You are a strict fact checker. You get a list of verified facts and a narration script. List every claim in the script that is NOT directly supported by the facts{countdown_note}: widened claims, invented context, wrong subjects, extra numbers. Also list any sentence that only repeats an idea already stated. The channel sign-off, calls to action and rhetorical questions are fine.
Reply with ONLY JSON: {{"ok": true or false, "unsupported": ["quote of the unsupported claim", ...]}}"""

VERIFY_PROMPT_ES = """Eres un verificador de datos estricto. Recibes una lista de hechos verificados y un guion de narración. Enumera cada afirmación del guion que NO esté respaldada directamente por los hechos{countdown_note}: datos ampliados, contexto inventado, sujetos equivocados, cifras de más. Enumera también cualquier frase que solo repita una idea ya dicha. La despedida del canal, las llamadas a la acción y las preguntas retóricas están bien.
Responde SOLO con JSON: {{"ok": true o false, "unsupported": ["cita de la afirmación sin respaldo", ...]}}"""

MONTHS_EN = {"jan": "January", "feb": "February", "mar": "March", "apr": "April", "jun": "June", "jul": "July",
             "aug": "August", "sep": "September", "sept": "September", "oct": "October", "nov": "November",
             "dec": "December"}
MONTHS_ES = {"ene": "enero", "feb": "febrero", "mar": "marzo", "abr": "abril", "jun": "junio", "jul": "julio",
             "ago": "agosto", "sep": "septiembre", "sept": "septiembre", "oct": "octubre", "nov": "noviembre",
             "dic": "diciembre"}

LANGS: dict[str, dict] = {
    "en": {
        "script_prompt": SCRIPT_PROMPT_EN,
        "verify_prompt": VERIFY_PROMPT_EN,
        "months": MONTHS_EN,
        "month_regex": re.compile(r"\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?(?=\s+\d)", re.I),
        "cta_regex": re.compile(r"\s*[^.!?]*\b(follow|subscribe)\b[^.!?]*\b(channel|us|me)\b[^.!?]*[.!?]?", re.I),
        "countdown_rule": " plus the days-until number",
        "countdown_note": " or the days-until number",
        "countdown_sentence": "Only {days} days until {event}.",
        "countdown_hint": ("Days until {event}: {days}. You may use it, always inside a full sentence "
                           "(for example 'Only {days} days until {event}.'), never as a bare '{days} days.'"),
        "countdown_past": "{event} already happened; do not say there are days left.",
        "countdown_line": "⏳ {days} days until {event} ({date}).",
        "rumor_words": ("reportedly", "rumor", "rumour", "unconfirmed", "allegedly", "according to"),
        "rewrite": ("Rejected: {error}. Use only the verified facts, total {min_target} to {max_target} words across the "
                    "{scenes} scenes, no follow/subscribe line, without repeating any idea. Rewrite it fixing that and "
                    "reply with the complete JSON only."),
        "user_msg": ("Topic: {angle}\nVerified facts (the only things you may state):\n{facts}\n\n{countdown}\n\n"
                     "Titles already published (use a different angle and title):\n{recent}\n\nWrite today's script."),
        "default_voice": "en-US-AndrewNeural",
        "whisper_lang": "en",
    },
    "es": {
        "script_prompt": SCRIPT_PROMPT_ES,
        "verify_prompt": VERIFY_PROMPT_ES,
        "months": MONTHS_ES,
        "month_regex": re.compile(r"\b(ene|feb|mar|abr|jun|jul|ago|sept?|oct|nov|dic)\.?(?=\s+(de\s+)?\d)", re.I),
        "cta_regex": re.compile(r"\s*[^.!?¡¿]*\b(s[ií]gue(nos|me)?|suscr[ií]be(te)?)\b[^.!?]*[.!?]?", re.I),
        "countdown_rule": " más el número de días que faltan",
        "countdown_note": " o el número de días que faltan",
        "countdown_sentence": "Solo faltan {days} días para {event}.",
        "countdown_hint": ("Días que faltan para {event}: {days}. Puedes usarlo, siempre dentro de una frase completa "
                           "(por ejemplo 'Solo faltan {days} días para {event}.'), nunca como un '{days} días.' suelto."),
        "countdown_past": "{event} ya ha ocurrido; no digas que faltan días.",
        "countdown_line": "⏳ Faltan {days} días para {event} ({date}).",
        "rumor_words": ("rumor", "se rumorea", "según", "no confirmado", "sin confirmar", "supuestamente", "al parecer"),
        "rewrite": ("Rechazado: {error}. Usa solo los hechos verificados, entre {min_target} y {max_target} palabras en total "
                    "repartidas en las {scenes} escenas, sin pedir suscripciones y sin repetir ninguna idea. Reescríbelo "
                    "corrigiendo eso y responde solo con el JSON completo."),
        "user_msg": ("Tema: {angle}\nHechos verificados (lo único que puedes afirmar):\n{facts}\n\n{countdown}\n\n"
                     "Títulos ya publicados (usa otro enfoque y otro título):\n{recent}\n\nEscribe el guion de hoy."),
        "default_voice": "es-ES-AlvaroNeural",
        "whisper_lang": "es",
    },
}


def pack(language: str) -> dict:
    """Language pack for ``language`` (falls back to English)."""
    return LANGS.get((language or "en").lower()[:2], LANGS["en"])


def expand_months(text: str, language: str) -> str:
    """'Oct 2026' -> 'October 2026', 'nov. 19' -> 'noviembre 19'. Abbreviations sound wrong when read aloud."""
    p = pack(language)
    months = p["months"]

    def repl(m: re.Match) -> str:
        full = months[m.group(1).lower()]
        return full.capitalize() if m.group(1)[0].isupper() and language.startswith("en") else full

    return p["month_regex"].sub(repl, text)
