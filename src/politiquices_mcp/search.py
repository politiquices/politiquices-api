"""Name -> wiki_id lookup for persons and parties.

Portuguese names carry accents and appear in many forms ("Costa", "António Costa",
"Antonio Luis Santos da Costa"), so matching is accent- and case-insensitive and
also runs over the aliases from sparql/entities_kb.jsonl and alias_overrides.json.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional

# match quality, best first. Whole words beat a prefix: "Costa" should rank António
# Costa (by coverage) alongside "Costa Martins", not behind every name starting "Costa".
EXACT, ALL_TOKENS, PREFIX, SUBSTRING = 4, 3, 2, 1


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped).strip().lower()


@dataclass
class Entity:
    wiki_id: str
    name: str
    kind: str  # "person" | "party"
    nr_relation_articles: Optional[int] = None  # persons only
    aliases: List[str] = field(default_factory=list)
    _forms: List[str] = field(default_factory=list, repr=False)

    def __post_init__(self):
        self._forms = [normalize(f) for f in [self.name, *self.aliases]]


def _match(query: str, form: str) -> int:
    if form == query:
        return EXACT
    tokens = form.split()
    if all(q in tokens for q in query.split()):
        return ALL_TOKENS
    if form.startswith(query):
        return PREFIX
    if query in form:
        return SUBSTRING
    return 0


class EntityIndex:
    def __init__(self, entities: List[Entity]):
        self.entities = entities

    def search(self, name: str, kind: Optional[str] = None, limit: int = 10) -> List[dict]:
        query = normalize(name)
        if not query:
            return []
        scored = []
        for e in self.entities:
            if kind and e.kind != kind:
                continue
            best, matched = 0, None
            for form, original in zip(e._forms, [e.name, *e.aliases]):
                score = _match(query, form)
                if score > best:
                    best, matched = score, original
            if best:
                scored.append((best, e.nr_relation_articles or 0, e, matched))
        scored.sort(key=lambda s: (s[0], s[1]), reverse=True)
        results = []
        for _, _, e, matched in scored[:limit]:
            result = {"wiki_id": e.wiki_id, "name": e.name, "kind": e.kind}
            if e.nr_relation_articles is not None:
                result["nr_relation_articles"] = e.nr_relation_articles
            if matched != e.name:
                result["matched_alias"] = matched
            results.append(result)
        return results
