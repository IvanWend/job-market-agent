import re
from collections.abc import Iterable
from typing import Any, Literal

from bs4 import BeautifulSoup

# Defined here, not in schema.py, so the import stays one-way: schema imports
# normalize, never the reverse.
Seniority = Literal["intern", "junior", "mid", "senior", "staff+", "unknown"]
Employment = Literal["full-time", "part-time", "contract", "unknown"]
RemotePolicy = Literal["remote", "hybrid", "onsite", "unknown"]

# [^\S\n] is whitespace except newline — \xa0 included, which Habr and Remotive
# prose is full of.
_HORIZONTAL_WS = re.compile(r"[^\S\n]+")
_LINE_EDGES = re.compile(r"[^\S\n]*\n[^\S\n]*")
_BLANK_RUN = re.compile(r"\n{3,}")
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")

_BLOCK_TAGS = [
    "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6",
    "blockquote", "section", "article", "ul", "ol", "table",
]  # fmt: skip

HOURS_PER_MONTH = 173.33  # 2080/12
MONTHS_PER_YEAR = 12

_CURRENCY_CHARS = re.compile(r"[$€£₽₸₴¥₹]")
_MAGNITUDES = {"k": 1e3, "K": 1e3, "к": 1e3, "К": 1e3, "m": 1e6, "M": 1e6}

_PERIODS: dict[str, str] = {
    "year": "year", "yearly": "year", "yr": "year", "annual": "year",
    "annually": "year", "per year": "year", "/year": "year", "pa": "year",
    "month": "month", "monthly": "month", "mo": "month", "per month": "month",
    "/month": "month", "mth": "month",
    "hour": "hour", "hourly": "hour", "hr": "hour", "per hour": "hour", "/hour": "hour",
}  # fmt: skip

BLANK_STRINGS = frozenset({"", "null", "none", "n/a", "na", "nil", "-", "—", "–"})

_SENIORITY: dict[str, Seniority] = {
    "intern": "intern", "internship": "intern", "trainee": "intern",
    "стажер": "intern", "стажёр": "intern", "стажировка": "intern",
    "junior": "junior", "jr": "junior", "entry": "junior", "entry-level": "junior",
    "джуниор": "junior", "джун": "junior", "младший": "junior",
    "mid": "mid", "middle": "mid", "mid-level": "mid", "intermediate": "mid",
    "миддл": "mid", "мидл": "mid", "средний": "mid",
    "senior": "senior", "sr": "senior", "senior-level": "senior",
    "синьор": "senior", "сеньор": "senior", "старший": "senior",
    "staff": "staff+", "staff+": "staff+", "principal": "staff+", "architect": "staff+",
    "lead": "staff+", "tech lead": "staff+", "team lead": "staff+", "teamlead": "staff+",
    "head": "staff+", "тимлид": "staff+", "ведущий": "staff+", "руководитель": "staff+",
}  # fmt: skip

_EMPLOYMENT: dict[str, Employment] = {
    "full-time": "full-time", "fulltime": "full-time", "full": "full-time",
    "permanent": "full-time", "полная занятость": "full-time", "полный день": "full-time",
    "part-time": "part-time", "parttime": "part-time", "part": "part-time",
    "частичная занятость": "part-time", "неполный день": "part-time",
    "contract": "contract", "contractor": "contract", "freelance": "contract",
    "temporary": "contract", "temp": "contract", "b2b": "contract",
    "фриланс": "contract", "подряд": "contract", "проектная работа": "contract",
}  # fmt: skip

# Habr states 'rur', a legacy code that is not ISO 4217. Symbols arrive from
# prose, three-letter codes from the boards.
_CURRENCIES: dict[str, str] = {
    "rur": "RUB", "rub": "RUB", "руб": "RUB", "руб.": "RUB", "р.": "RUB", "₽": "RUB",
    "usd": "USD", "$": "USD", "us$": "USD", "$usd": "USD", "долл": "USD",
    "eur": "EUR", "€": "EUR", "gbp": "GBP", "£": "GBP",
    "kzt": "KZT", "₸": "KZT", "uah": "UAH", "₴": "UAH", "byn": "BYN",
    "inr": "INR", "₹": "INR", "jpy": "JPY", "cny": "CNY", "¥": "CNY",
}  # fmt: skip

_REMOTE: dict[str, RemotePolicy] = {
    "remote": "remote", "fully remote": "remote", "fully-remote": "remote",
    "100% remote": "remote", "100%-remote": "remote",
    "remote first": "remote", "remote-first": "remote",
    "wfh": "remote", "work from home": "remote", "work-from-home": "remote",
    "distributed": "remote", "anywhere": "remote", "worldwide": "remote",
    "удаленно": "remote", "удалённо": "remote",
    "удаленная работа": "remote", "удалённая работа": "remote",
    "hybrid": "hybrid", "partially remote": "hybrid", "partially-remote": "hybrid",
    "flexible": "hybrid", "гибрид": "hybrid", "гибридный": "hybrid",
    "onsite": "onsite", "on-site": "onsite", "on site": "onsite",
    "on-premise": "onsite", "on premise": "onsite",
    "in-office": "onsite", "in office": "onsite", "office": "onsite",
    "in-person": "onsite", "in person": "onsite", "local": "onsite",
    "офис": "onsite", "в офисе": "onsite",
}  # fmt: skip

# Seed, not a finished list. Grows from eval failures.
STACK_STOPLIST = frozenset({
    "open source", "opensource", "remote", "hybrid", "onsite", "full-time", "part-time",
    "contract", "internship", "entry-level", "junior", "senior", "lead", "non-tech",
    "engineer", "developer", "dev", "executive", "operations", "sales", "marketing",
    "crypto", "blockchain", "web3", "defi", "bitcoin", "ethereum",
    "united-states", "china", "europe", "worldwide", "usa", "uk", "team lead",
    "управление проектами", "управление рисками", "управление людьми",
    "управление разработкой", "планирование", "построение команды",
    "оптимизация бизнес-процессов", "информационная безопасность",
    "разработка программного обеспечения",
})  # fmt: skip

# Keys are post-fold, post-casefold.
STACK_ALIASES: dict[str, str] = {
    "postgresql": "postgres", "psql": "postgres", "postgre": "postgres",
    "k8s": "kubernetes", "golang": "go", "node": "nodejs", "node.js": "nodejs",
    "js": "javascript", "ts": "typescript", "py": "python",
    "c#": "csharp", "c++": "cpp", "objective-c": "objc",
    "amazon web services": "aws", "google cloud": "gcp",
    "google cloud platform": "gcp", "microsoft azure": "azure",
    "react.js": "react", "reactjs": "react", "vue.js": "vue", "vuejs": "vue",
    "next.js": "nextjs", "rest": "rest-api", "restful": "rest-api",
    "ci/cd": "ci-cd", "cicd": "ci-cd",
    "java spring framework": "spring", "spring boot": "spring",
    "oracle pl/sql": "plsql", "pl/sql": "plsql",
    "гост": "gost", "объектное хранилище s3": "s3", "1с": "1c",
}  # fmt: skip

# `1С` appears with a Cyrillic С in 33 corpus rows and a Latin C in 48.
_LOOKALIKES = str.maketrans("АВЕКМНОРСТУХаеорсух", "ABEKMHOPCTYXaeopcyx")


def html_to_text(html: str | None) -> str:
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    # Newlines per block tag, not get_text(separator=): a separator splits at
    # every string boundary, so inline markup breaks a sentence across lines and
    # any quote spanning it fails containment.
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n\n")
    for tag in soup.find_all("br"):
        tag.replace_with("\n")

    text = soup.get_text()
    text = _HORIZONTAL_WS.sub(" ", text)
    text = _LINE_EDGES.sub("\n", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip()


def blank_to_none(value: Any, extra: Iterable[str] = ()) -> Any:
    # Strings only — a numeric 0 is a real salary floor, not a blank.
    if not isinstance(value, str):
        return value

    stripped = value.strip()
    key = stripped.casefold()
    if key in BLANK_STRINGS:
        return None
    if any(key == item.casefold() for item in extra):
        return None
    return stripped


def to_number(value: float | str) -> float:
    if not isinstance(value, str):
        return float(value)

    # The LLM extracts verbatim, so "$180k" and "1.5M" arrive as written. Bare
    # float() rejects both, which would silently cost every HN salary.
    cleaned = _CURRENCY_CHARS.sub("", value).replace(",", "")
    cleaned = _HORIZONTAL_WS.sub("", cleaned).strip()
    multiplier = 1.0
    if cleaned and cleaned[-1] in _MAGNITUDES:
        multiplier = _MAGNITUDES[cleaned[-1]]
        cleaned = cleaned[:-1]
    return float(cleaned) * multiplier


def to_monthly(amount: float | str, period: str) -> int:
    unit = _PERIODS.get(str(period).strip().casefold())
    # Raise rather than default to monthly: a silent default produces a
    # plausible-looking number nothing downstream can catch.
    if unit is None:
        raise ValueError(f"unknown salary period: {period!r}")

    value = to_number(amount)
    if unit == "year":
        value /= MONTHS_PER_YEAR
    elif unit == "hour":
        value *= HOURS_PER_MONTH
    return round(value)


def fold_homoglyphs(text: str) -> str:
    folded = text.translate(_LOOKALIKES)
    # Only accept a fold that removes Cyrillic entirely; a partial fold of a
    # Russian word leaves mixed-script garbage.
    return folded if not _CYRILLIC.search(folded) else text


def alias(item: str | None) -> str | None:
    cleaned = blank_to_none(item)
    if cleaned is None:
        return None

    key = _HORIZONTAL_WS.sub(" ", fold_homoglyphs(cleaned)).strip().casefold()
    if key in STACK_STOPLIST:
        return None
    if key in STACK_ALIASES:
        return STACK_ALIASES[key]
    # Habr's Cyrillic skills are process/domain, not stack. Anything Cyrillic
    # worth keeping is mapped above.
    if _CYRILLIC.search(key):
        return None
    return key


def normalize_stack(items: Iterable[str | None]) -> list[str]:
    seen: dict[str, None] = {}
    for item in items:
        canonical = alias(item)
        if canonical is not None:
            seen.setdefault(canonical, None)
    return list(seen)


def seniority_enum(value: str | None) -> Seniority:
    cleaned = blank_to_none(value)
    if cleaned is None:
        return "unknown"

    key = _HORIZONTAL_WS.sub(" ", cleaned).strip().casefold().replace("_", "-")
    return _SENIORITY.get(key, "unknown")


def employment_enum(value: str | None) -> Employment:
    cleaned = blank_to_none(value)
    if cleaned is None:
        return "unknown"

    key = _HORIZONTAL_WS.sub(" ", cleaned).strip().casefold().replace("_", "-")
    return _EMPLOYMENT.get(key, "unknown")


def remote_policy_enum(value: str | bool | None) -> RemotePolicy:
    if isinstance(value, bool):
        return "remote" if value else "unknown"

    cleaned = blank_to_none(value)
    if cleaned is None:
        return "unknown"

    key = _HORIZONTAL_WS.sub(" ", cleaned).strip().casefold().replace("_", "-")
    return _REMOTE.get(key, "unknown")


def currency_enum(value: str | None) -> str | None:
    # Annotated because this is the one enum helper that returns a derived
    # string rather than a Literal, so blank_to_none's Any would leak out.
    cleaned: str | None = blank_to_none(value)
    if cleaned is None:
        return None

    key = cleaned.strip().casefold()
    if key in _CURRENCIES:
        return _CURRENCIES[key]
    # A bare three-letter ASCII code passes through as-is; anything else is not
    # a currency, and returning it would put junk in an ISO 4217 column.
    if len(key) == 3 and key.isascii() and key.isalpha():
        return key.upper()
    return None
