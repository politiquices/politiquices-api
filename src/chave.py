from typing import Dict, Optional, Tuple

from cache import chave_publico

CHAVE_URL_PREFIX = "https://www.linguateca.pt/CHAVE?"

# Matches nlp_extraction/data_sources/chave/generate_input.py::PARAGRAPH_WORD_THRESHOLD: the
# CHAVE/CETEMPúblico corpus bundles several unrelated short wire briefs under one SGML "doc" (and
# therefore one linguateca.pt/CHAVE?<doc_id> URL) with no blank line between them -- a line with
# this many words or more is trusted as a paragraph, the line right before it as that brief's
# title. Reused here, unmodified, so a doc's boundary between two bundled briefs is drawn exactly
# where generate_input.py already drew it when it picked the single title/paragraph pair that
# ended up in the data release.
PARAGRAPH_WORD_THRESHOLD = 15

# A Público byline sits on its own line directly above the body, e.g. "Jerónimo Pimentel" or
# "Carlos Camponez e Margarida Portugal" -- every word capitalised bar a handful of lowercase
# Portuguese name particles. A real (if short) title almost always has at least one ordinary
# lowercase word ("Redobradas cautelas", "Mitterrand já escolheu a campa"), which this rejects.
# Sampled 400 random docs against this rule: 69 matches, the overwhelming majority recognisable
# Público reporter names (Pedro Fernandes, Paulo Moura, Ana Gerschenfeld, ...); a handful of
# false positives (a dateline like "Em Sarajevo", a section label) are an acceptable miss for a
# cosmetic byline vs. always crediting the article to whichever line happened to precede the
# paragraph, title or not.
_NAME_PARTICLES = {"de", "da", "do", "dos", "das", "e"}
_TRAILING_PUNCT = (".", "»", ":", ",", ";")


def _looks_like_byline(line: str) -> bool:
    if line.endswith(_TRAILING_PUNCT):
        return False
    words = line.split()
    if not 2 <= len(words) <= 5:
        return False
    return all(w.lower() in _NAME_PARTICLES or w[:1].isupper() for w in words)


def extract_full_article(doc_text: str) -> Optional[Tuple[str, Optional[str], str]]:
    """The (title, author, body) of the first article in a CHAVE doc's raw text, with every one
    of its own paragraphs kept -- not just the first, which is all generate_input.py ever
    captured.

    A "paragraph" is any line with PARAGRAPH_WORD_THRESHOLD words or more. The line right before
    the first one is normally the title, except when it looks like a byline (see
    _looks_like_byline) and there is a further line above it to use as the title instead -- e.g.
    "...acusações de Cavaco" / "«Vai valer tudo...»" / "Jerónimo Pimentel" / <paragraph> yields
    title="«Vai valer tudo...»", author="Jerónimo Pimentel", not the reporter's name as the
    headline. Once inside the article, lines keep being appended for as long as they too look
    like paragraphs -- the first short line marks the start of the next bundled brief (or the end
    of the doc), so it isn't included. Returns None if no line in the doc ever clears the
    threshold.
    """
    lines = [line.strip() for line in doc_text.split("\n") if line.strip()]
    start = None
    for i, line in enumerate(lines):
        if len(line.split()) >= PARAGRAPH_WORD_THRESHOLD:
            start = i
            break
    if start is None or start == 0:
        return None

    author = None
    title = lines[start - 1]
    if start >= 2 and _looks_like_byline(title):
        author = title
        title = lines[start - 2]

    paragraphs = [lines[start]]
    for line in lines[start + 1 :]:
        if len(line.split()) < PARAGRAPH_WORD_THRESHOLD:
            break
        paragraphs.append(line)
    return title, author, "\n\n".join(paragraphs)


def _build_index() -> Dict[str, Dict[str, Optional[str]]]:
    # api/json/CHAVE-Publico_94_95.jsonl keys each entry by its bare doc id ("id") rather than
    # the full linguateca.pt/CHAVE?<doc_id> URL used everywhere else in the pipeline, and its
    # date field is "date" rather than "publish_date" -- a different shape from the
    # nlp_extraction/data_sources/full_text_cache/ copy of this same corpus.
    index = {}
    for entry in chave_publico:
        parsed = extract_full_article(entry.get("text") or "")
        if parsed is None:
            continue
        title, author, text = parsed
        index[CHAVE_URL_PREFIX + entry["id"]] = {
            "title": title,
            "author": author,
            "date": entry["date"],
            "text": text,
        }
    return index


_INDEX = _build_index()


def get_chave_article(doc_id: str) -> Optional[Dict[str, str]]:
    return _INDEX.get(CHAVE_URL_PREFIX + doc_id)
