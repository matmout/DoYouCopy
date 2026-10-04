import pytest

from mywhisper.core.textproc import NBSP, apply_replacements, apply_voice_commands, postprocess


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("j'utilise rock m tous les jours", "j'utilise ROCm tous les jours"),
        ("ROCK M et Rock M", "ROCm et ROCm"),
        ("rock mélodique", "rock mélodique"),  # whole words only
    ],
)
def test_plain_replacement(text, expected):
    assert apply_replacements(text, [["rock m", "ROCm"]]) == expected


def test_regex_replacement_with_group():
    rules = [[r"/(\d+) pour ?cent/", r"\1 %"]]
    assert apply_replacements("une hausse de 12 pour cent", rules) == "une hausse de 12 %"


def test_invalid_regex_and_empty_rules_are_ignored():
    assert apply_replacements("texte", [["/(/", "x"], ["", "y"], ["seul"]]) == "texte"


def test_replacement_text_is_literal():
    assert apply_replacements("chemin", [["chemin", r"C:\temp"]]) == r"C:\temp"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Bonjour virgule comment ça va point d'interrogation", f"Bonjour, comment ça va{NBSP}?"),
        ("Bonjour, virgule, comment ça va ? Point d'interrogation.", f"Bonjour, comment ça va{NBSP}?"),
        ("c'est fini point final à la ligne merci", "C'est fini.\nMerci"),
        ("titre nouveau paragraphe texte", "Titre\n\nTexte"),
        ("il a dit ouvrez les guillemets oui fermez les guillemets", f"Il a dit «{NBSP}oui{NBSP}»"),
        ("voici la liste deux-points pommes point-virgule poires", f"Voici la liste{NBSP}: pommes{NBSP}; poires"),
        ("attention point d’exclamation", f"Attention{NBSP}!"),
        ("un exemple ouvrez la parenthèse court fermez la parenthèse", "Un exemple (court)"),
        ("et puis points de suspension", "Et puis…"),
    ],
)
def test_french_voice_commands(text, expected):
    assert apply_voice_commands(text, "fr") == expected


def test_lone_point_is_never_a_command():
    text = "C'est un point important, à ce point."
    assert apply_voice_commands(text, "fr") == text


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("hello comma how are you question mark", "Hello, how are you?"),
        ("first line new line second line period", "First line\nSecond line."),
        ("a period of time", "a period of time"),
        ("she said open quote yes close quote", "She said “yes”"),
    ],
)
def test_english_voice_commands(text, expected):
    assert apply_voice_commands(text, "en") == expected


def test_unknown_language_is_untouched():
    assert apply_voice_commands("hola coma", "es") == "hola coma"
    assert apply_voice_commands("virgule", None) == "virgule"


def test_postprocess_chains_commands_then_replacements():
    out = postprocess("merci rock m virgule à demain", "fr", [["rock m", "ROCm"]], voice_commands=True)
    assert out == "Merci ROCm, à demain"
    assert postprocess("merci virgule", "fr", voice_commands=False) == "merci virgule"
