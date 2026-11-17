"""Original, attribution-free romantic copy for personalized menu print layouts."""
from __future__ import annotations

import hashlib

_COPY = {
    "ru": (
        ("Любовь живёт в заботе, которую мы дарим друг другу.", "Пусть каждый наш день будет поводом для нежности."),
        ("Уважение делает любовь глубже, а нежность — теплее.", "С тобой даже обычный ужин становится праздником."),
        ("Самое красивое признание — внимание каждый день.", "Я выбираю тебя в каждом новом рассвете."),
        ("Когда мы бережём друг друга, счастье становится домом.", "Пусть этот вечер останется нашим маленьким чудом."),
        ("Любить — значит замечать самое важное в мелочах.", "Для тебя — тепло, вкус и немного волшебства."),
    ),
    "uk": (
        ("Любов живе в турботі, яку ми даруємо одне одному.", "Нехай кожен наш день буде приводом для ніжності."),
        ("Повага робить любов глибшою, а ніжність — теплішою.", "З тобою навіть звичайна вечеря стає святом."),
        ("Найкраще зізнання — увага щодня.", "Я обираю тебе з кожним новим світанком."),
        ("Коли ми бережемо одне одного, щастя стає домом.", "Нехай цей вечір залишиться нашим маленьким дивом."),
        ("Любити — означає помічати найважливіше в дрібницях.", "Для тебе — тепло, смак і трохи чарів."),
    ),
    "en": (
        ("Love lives in the care we give each other.", "May every day offer a reason for tenderness."),
        ("Respect makes love deeper and tenderness warmer.", "With you, even an ordinary dinner feels special."),
        ("The loveliest declaration is daily attention.", "I choose you with every new sunrise."),
        ("When we cherish each other, happiness feels like home.", "May tonight become our little miracle."),
        ("To love is to notice what matters in small moments.", "For you: warmth, flavor, and a little magic."),
    ),
}


def romantic_copy(language: object, seed: str | int) -> tuple[str, str]:
    """Return a stable original quote and greeting without invented attribution."""
    lang = str(getattr(language, "value", language) or "ru").lower()
    entries = _COPY.get(lang, _COPY["ru"])
    digest = hashlib.sha256(f"{lang}:{seed}".encode()).digest()
    return entries[int.from_bytes(digest[:4], "big") % len(entries)]
