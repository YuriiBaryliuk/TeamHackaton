"""Parse the common subset of OpenStreetMap `opening_hours` into our format.

Supported (covers most Polish pharmacies and toilets):
    24/7
    Mo-Fr 08:00-20:00; Sa 08:00-15:00; Su off
    Mo-Fr 08:00-20:00, Sa 08:00-16:00          (comma between day rules)
    06:00-22:00                                 (no days = every day)
    Mo,We,Fr 09:00-12:00,13:00-17:00            (several intervals: we keep first start .. last end)
    PH off                                      (public holidays: ignored)

Anything else (months, sunrise, comments, "+" ...) returns None: the caller then stores
{"unknown": true}, and the place is never counted as "open now". Better honest than wrong.
"""
import re

OSM_DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
OUR_DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
DAY = r"(?:Mo|Tu|We|Th|Fr|Sa|Su)"
DAYS_RE = re.compile(rf"{DAY}(?:-{DAY})?(?:,{DAY}(?:-{DAY})?)*")
TIME = r"\d{1,2}:\d{2}"
TIMES_RE = re.compile(rf"{TIME}\s*-\s*{TIME}(?:\s*,\s*{TIME}\s*-\s*{TIME})*")
# Rules are separated by ";" or by a comma that comes right after a time and before a day
# ("Mo-Fr 08:00-20:00, Sa 09:00-14:00"); commas inside a day list ("Mo,We,Fr") are not splits.
RULE_SPLIT = re.compile(r";\s*|(?<=\d),\s*(?=(?:Mo|Tu|We|Th|Fr|Sa|Su|PH|SH)\b)")


def _hhmm(text: str) -> str:
    h, m = text.split(":")
    return f"{int(h):02d}:{m}"


def _days(selector: str) -> list[str] | None:
    if not DAYS_RE.fullmatch(selector):
        return None
    out = []
    for part in selector.split(","):
        a, _, b = part.partition("-")
        i, j = OSM_DAYS.index(a), OSM_DAYS.index(b or a)
        span = range(i, j + 1) if i <= j else [*range(i, 7), *range(0, j + 1)]  # Fr-Mo wraps
        out += [OUR_DAYS[k] for k in span]
    return out


def parse_osm_hours(text: str | None) -> dict | None:
    if not text or not text.strip():
        return None
    text = text.strip()
    if text == "24/7":
        return {"always": True}

    hours: dict = {}
    for rule in RULE_SPLIT.split(text):
        rule = rule.strip()
        if not rule:
            continue
        if rule.startswith(("PH", "SH")):
            continue  # holiday rules: we do not model holidays
        m = re.fullmatch(rf"(?:({DAY}[A-Za-z,\-]*)\s+)?(.+)", rule)
        selector, times = m.group(1), m.group(2).strip()
        days = _days(selector) if selector else OUR_DAYS
        if days is None:
            return None
        if times in ("off", "closed"):
            for d in days:
                hours.pop(d, None)
            continue
        if not TIMES_RE.fullmatch(times):
            return None
        stamps = [_hhmm(t) for t in re.findall(TIME, times)]
        span = [stamps[0], stamps[-1]]
        if span == ["00:00", "24:00"] and days == OUR_DAYS:
            return {"always": True}
        for d in days:
            hours[d] = span  # a later rule overrides an earlier one, as in OSM
    return hours
