"""Small clean-ups for model output."""
import re

# Models often ignore "don't refer to the passage"; strip those references instead of dropping the item.
_TRAILING = re.compile(
    r"[,\s]*\b(as\s+)?(described|mentioned|stated|discussed|explained|presented|defined|outlined)\s+"
    r"(in|by)\s+(the|this)\s+(passage|text|chapter|section|author|book|excerpt)\b",
    re.IGNORECASE,
)
_LEADING = re.compile(
    r"\b(according to|based on|in|from)\s+(the|this)\s+(passage|text|chapter|section|excerpt)[,:]?\s+",
    re.IGNORECASE,
)
_ACCORDING_END = re.compile(
    r"(?<=\w)[,\s]+(according to|based on)\s+(the|this)\s+(passage|text|chapter|section|excerpt|author)(?=\s*[?.!]|\s*$)",
    re.IGNORECASE,
)


def strip_passage_references(text: str) -> str:
    out = _TRAILING.sub("", text)
    out = _ACCORDING_END.sub("", out)
    out = _LEADING.sub("", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([?.!,])", r"\1", out)
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    if text.rstrip().endswith("?") and not out.endswith("?"):
        out = out.rstrip(".") + "?"
    return out or text
