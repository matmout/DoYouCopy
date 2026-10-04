"""Text post-processing: user replacements and spoken punctuation commands.

Pure functions on strings, applied after decoding: no effect on timestamps.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from functools import lru_cache

log = logging.getLogger(__name__)

NBSP = " "

# Symbol kinds produced by the voice commands.
PUNCT = "punct"  # attaches to the previous word: , . ? ! ; : …
BREAK = "break"  # line or paragraph break
OPEN = "open"  # opening quote / parenthesis: no space after
CLOSE = "close"  # closing quote / parenthesis: no space before

# Only unambiguous phrases: a lone "point" (fr) or "period" (en, except at the very end)
# is far too common in ordinary speech to be read as punctuation.
_APOS = "['’]"
VOICE_COMMANDS: dict[str, list[tuple[str, str, str]]] = {
    "fr": [
        (r"points? de suspension", PUNCT, "…"),
        (rf"point{_APOS}?\s?d{_APOS}\s?interrogation", PUNCT, "?"),
        (rf"point{_APOS}?\s?d{_APOS}\s?exclamation", PUNCT, "!"),
        (r"point[- ]virgule", PUNCT, ";"),
        (r"point final", PUNCT, "."),
        (r"deux[- ]points", PUNCT, ":"),
        (r"virgule", PUNCT, ","),
        (r"nouveau paragraphe", BREAK, "\n\n"),
        (r"(?:retour )?[àa] la ligne", BREAK, "\n"),
        (r"ouvre[zr]? les guillemets", OPEN, "«"),
        (r"ferme[zr]? les guillemets", CLOSE, "»"),
        (r"ouvre[zr]? la parenth[èe]se", OPEN, "("),
        (r"ferme[zr]? la parenth[èe]se", CLOSE, ")"),
    ],
    "en": [
        (r"question mark", PUNCT, "?"),
        (r"exclamation (?:mark|point)", PUNCT, "!"),
        (r"semi-?colon", PUNCT, ";"),
        (r"full stop", PUNCT, "."),
        (r"period(?=[\s.!?]*$)", PUNCT, "."),
        (r"colon", PUNCT, ":"),
        (r"comma", PUNCT, ","),
        (r"ellipsis", PUNCT, "…"),
        (r"new paragraph", BREAK, "\n\n"),
        (r"new line", BREAK, "\n"),
        (r"open quote", OPEN, "“"),
        (r"(?:close|end) quote", CLOSE, "”"),
        (r"open paren(?:thesis)?", OPEN, "("),
        (r"close paren(?:thesis)?", CLOSE, ")"),
    ],
}

# Whisper often wraps a spoken command in its own punctuation ("Bonjour, virgule, ça va").
_NOISE = r"[\s,.;:!?…]*"
_MARK = "\x01"
_MARK_RE = re.compile(f"{_MARK}(\\d+){_MARK}")
_SENTENCE_END = (".", "?", "!", "…")


def apply_replacements(text: str, rules: Sequence[Sequence[str]]) -> str:
    """Rules are (heard, written) pairs: whole words, case-insensitive.
    A pattern written /like this/ is a regular expression (\\1 allowed in the replacement)."""
    for pattern, template, is_regex in _compile_rules(tuple(tuple(r) for r in rules)):
        if is_regex:
            text = pattern.sub(template, text)
        else:
            text = pattern.sub(lambda _m, t=template: t, text)
    return text


@lru_cache(maxsize=16)
def _compile_rules(rules: tuple[tuple[str, ...], ...]) -> list[tuple[re.Pattern, str, bool]]:
    compiled = []
    for rule in rules:
        if len(rule) < 2 or not rule[0].strip():
            continue
        heard, written = rule[0].strip(), rule[1]
        if len(heard) > 2 and heard.startswith("/") and heard.endswith("/"):
            try:
                compiled.append((re.compile(heard[1:-1], re.IGNORECASE), written, True))
            except re.error as exc:
                log.warning("Invalid replacement pattern %r: %s", heard, exc)
            continue
        pattern = re.compile(rf"(?<!\w){re.escape(heard)}(?!\w)", re.IGNORECASE)
        compiled.append((pattern, written, False))
    return compiled


def apply_voice_commands(text: str, language: str | None) -> str:
    commands = VOICE_COMMANDS.get((language or "")[:2])
    if not commands:
        return text
    symbols: list[tuple[str, str]] = []
    for phrase, kind, symbol in commands:
        regex = re.compile(rf"{_NOISE}(?<!\w){phrase}(?!\w){_NOISE}", re.IGNORECASE)

        def mark(_m, kind=kind, symbol=symbol) -> str:
            symbols.append((kind, symbol))
            return f" {_MARK}{len(symbols) - 1}{_MARK} "

        text = regex.sub(mark, text)
    if not symbols:
        return text
    return _assemble(text, symbols, french=language.startswith("fr"))


def _assemble(text: str, symbols: list[tuple[str, str]], french: bool) -> str:
    out = ""
    glue = True  # no space before the next word
    for i, piece in enumerate(_MARK_RE.split(text)):
        if i % 2 == 0:
            words = " ".join(piece.split())
            if words:
                out += words if glue or not out or out.endswith("\n") else " " + words
                glue = False
            continue
        kind, symbol = symbols[int(piece)]
        if kind == PUNCT:
            out = out.rstrip(" " + NBSP)
            if french and symbol in "?!;:":
                out += NBSP
            out += symbol
            glue = False
        elif kind == BREAK:
            out = out.rstrip(" " + NBSP) + symbol
            glue = True
        elif kind == OPEN:
            if out and not out.endswith(("\n", " ")):
                out += " "
            out += symbol + (NBSP if french and symbol == "«" else "")
            glue = True
        else:  # CLOSE
            out = out.rstrip(" " + NBSP) + (NBSP if french and symbol == "»" else "") + symbol
            glue = False
    lines = [line.strip(" ") for line in out.split("\n")]
    return _capitalize("\n".join(lines).strip())


def _capitalize(text: str) -> str:
    """Upper-cases the first letter of the text, of each line and after a sentence end."""
    chars = list(text)
    upper_next = True
    for i, c in enumerate(chars):
        if c.isalpha():
            if upper_next:
                chars[i] = c.upper()
            upper_next = False
        elif c in _SENTENCE_END or c == "\n":
            upper_next = True
        elif c.isdigit():
            upper_next = False
    return "".join(chars)


def postprocess(
    text: str,
    language: str | None,
    replacements: Sequence[Sequence[str]] = (),
    voice_commands: bool = False,
) -> str:
    if voice_commands:
        text = apply_voice_commands(text, language)
    return apply_replacements(text, replacements)
