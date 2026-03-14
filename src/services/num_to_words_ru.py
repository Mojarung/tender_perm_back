"""Convert a monetary amount to Russian words (roubles + kopecks)."""

_ONES_MASC = [
    "", "один", "два", "три", "четыре", "пять",
    "шесть", "семь", "восемь", "девять",
]
_ONES_FEM = [
    "", "одна", "две", "три", "четыре", "пять",
    "шесть", "семь", "восемь", "девять",
]
_TEENS = [
    "десять", "одиннадцать", "двенадцать", "тринадцать", "четырнадцать",
    "пятнадцать", "шестнадцать", "семнадцать", "восемнадцать", "девятнадцать",
]
_TENS = [
    "", "", "двадцать", "тридцать", "сорок", "пятьдесят",
    "шестьдесят", "семьдесят", "восемьдесят", "девяносто",
]
_HUNDREDS = [
    "", "сто", "двести", "триста", "четыреста", "пятьсот",
    "шестьсот", "семьсот", "восемьсот", "девятьсот",
]

# (singular, gen_singular, gen_plural, is_feminine)
_SCALES: list[tuple[str, str, str, bool]] = [
    ("", "", "", False),                        # ones
    ("тысяча", "тысячи", "тысяч", True),        # 10^3
    ("миллион", "миллиона", "миллионов", False), # 10^6
    ("миллиард", "миллиарда", "миллиардов", False),  # 10^9
]


def _plural_form(n: int, one: str, few: str, many: str) -> str:
    """Pick the correct Russian plural form for *n*."""
    mod100 = n % 100
    mod10 = n % 10
    if 11 <= mod100 <= 19:
        return many
    if mod10 == 1:
        return one
    if 2 <= mod10 <= 4:
        return few
    return many


def _triplet_to_words(n: int, feminine: bool) -> str:
    """Convert a number 0-999 to Russian words."""
    if n == 0:
        return ""
    parts: list[str] = []
    parts.append(_HUNDREDS[n // 100])
    remainder = n % 100
    if 10 <= remainder <= 19:
        parts.append(_TEENS[remainder - 10])
    else:
        parts.append(_TENS[remainder // 10])
        ones = remainder % 10
        parts.append((_ONES_FEM if feminine else _ONES_MASC)[ones])
    return " ".join(p for p in parts if p)


def number_to_words_ru(amount: float) -> str:
    """Return *amount* as Russian text: рубли + копейки.

    >>> number_to_words_ru(123456.78)
    'сто двадцать три тысячи четыреста пятьдесят шесть рублей 78 копеек'
    """
    roubles = int(amount)
    kopecks = round((amount - roubles) * 100)
    if kopecks >= 100:
        roubles += 1
        kopecks = 0

    if roubles == 0:
        words = "ноль"
    else:
        groups: list[str] = []
        remaining = roubles
        for i, (one, few, many, fem) in enumerate(_SCALES):
            chunk = remaining % 1000
            remaining //= 1000
            if chunk == 0:
                continue
            text = _triplet_to_words(chunk, fem)
            scale_word = _plural_form(chunk, one, few, many) if i > 0 else ""
            groups.append(f"{text} {scale_word}".strip())
            if remaining == 0:
                break
        words = " ".join(reversed(groups))

    rouble_word = _plural_form(roubles, "рубль", "рубля", "рублей")
    kopeck_word = _plural_form(kopecks, "копейка", "копейки", "копеек")

    return f"{words} {rouble_word} {kopecks:02d} {kopeck_word}"
