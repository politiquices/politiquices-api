"""Turn what sparql.py returns (shaped for the web app) into compact records for an agent.

Pure functions, no SPARQL and no caches: everything they need is passed in, so they
can be tested without Jena. Two rules hold throughout:

- an agent never sees the raw ent1_*_ent2 encoding, only a stance read as
  "subject <stance> object" (or, for one person's relationships, from that person's
  point of view);
- every relationship says whether a human annotated it, because most are classifier
  predictions and the classifier gets some of them wrong.
"""
from typing import Iterable, Optional

# get_person_relationships() buckets, already from the queried person's point of view
# (see sparql._classify_person_relationship). "all" and "sentiment" are aggregates of
# the others and are never read here, or every relationship would come out twice.
PERSON_STANCES = ("supports", "opposes", "supported_by", "opposed_by", "mutual_agreement", "mutual_opposition")
OTHER_STANCES = ("other", "other_by")


def wiki_id_of(uri: str) -> str:
    """'http://www.wikidata.org/entity/Q610788' -> 'Q610788'; a bare id passes through."""
    return uri.rsplit("/", 1)[-1]


def _articles(rel: dict, include_paragraph: bool) -> list:
    articles = []
    for a in rel["articles"]:
        article = {"title": a["title"], "url": a["arquivo_doc"], "source": a["domain"], "date": a["date"][:10]}
        if include_paragraph:
            article["paragraph"] = a["paragraph"]
        articles.append(article)
    return articles


def _is_annotated(rel: dict, annotated_urls: Optional[set]) -> Optional[bool]:
    """True/False when we know which articles were human-annotated, None when we don't
    (no annotation source loaded) -- never a guess."""
    if annotated_urls is None:
        return None
    return any(a["arquivo_doc"] in annotated_urls for a in rel["articles"])


def person_relationships(
    buckets: dict,
    stances: Iterable[str],
    annotated_urls: Optional[set],
    include_paragraph: bool = False,
    names: Optional[dict] = None,
) -> list:
    """get_person_relationships() output -> one record per relationship, newest first.

    ent2_str is the name as the headline wrote it ("Centeno"); `names` (wiki_id ->
    canonical name) replaces it with the full name when known."""
    names = names or {}
    records = []
    for stance in stances:
        for rel in buckets.get(stance, []):
            records.append(
                {
                    "stance": stance,
                    "other": {"wiki_id": rel["ent2_id"], "name": names.get(rel["ent2_id"], rel["ent2_str"])},
                    "date": rel["date"][:10],
                    "annotated": _is_annotated(rel, annotated_urls),
                    "articles": _articles(rel, include_paragraph),
                }
            )
    records.sort(key=lambda r: r["date"], reverse=True)
    return records


def year_relationships_to_buckets(relationships: list) -> dict:
    """get_person_relationships_for_year() returns a flat list with rel_type already in
    the person's point of view; group it the way get_person_relationships() does."""
    buckets = {}
    for rel in relationships:
        buckets.setdefault(rel["rel_type"], []).append(rel)
    return buckets


# get_relationship_between_*() rel_type, with ent1 = the first side asked for and
# ent2 = the second, -> (stance, subject_is_ent1)
_BETWEEN = {
    "ent1_supports_ent2": ("supports", True),
    "ent1_opposes_ent2": ("opposes", True),
    "ent2_supports_ent1": ("supports", False),
    "ent2_opposes_ent1": ("opposes", False),
    "mutual_agreement": ("mutual_agreement", True),
    "mutual_opposition": ("mutual_opposition", True),
}


def between_relationships(
    relationships: list,
    annotated_urls: Optional[set],
    include_paragraph: bool = False,
) -> list:
    """get_relationship_between_*() output -> 'subject <stance> object' records, newest
    first. For a party side, ent1/ent2 is the party member who took part."""
    records = []
    for rel in relationships:
        mapped = _BETWEEN.get(rel["rel_type"])
        if mapped is None:  # "other": no stance to report
            continue
        stance, subject_is_ent1 = mapped
        ent1 = {"wiki_id": rel["ent1_id"], "name": rel["ent1_str"]}
        ent2 = {"wiki_id": rel["ent2_id"], "name": rel["ent2_str"]}
        subject, obj = (ent1, ent2) if subject_is_ent1 else (ent2, ent1)
        records.append(
            {
                "subject": subject,
                "stance": stance,
                "object": obj,
                "date": rel["date"][:10],
                "annotated": _is_annotated(rel, annotated_urls),
                "articles": _articles(rel, include_paragraph),
            }
        )
    records.sort(key=lambda r: r["date"], reverse=True)
    return records


def top_related(records: list) -> list:
    """person_relationships() records -> one row per counterpart, with how many
    relationships of each stance they share and how many of those a human annotated,
    most relationships first. Lets an agent rank "who criticised X most" without
    reading every record."""
    rows = {}
    for r in records:
        row = rows.setdefault(
            r["other"]["wiki_id"],
            {"other": r["other"], "total": 0, "annotated": 0, "stances": {}, "first_date": r["date"],
             "last_date": r["date"]},
        )
        row["total"] += 1
        row["annotated"] += 1 if r["annotated"] else 0
        row["stances"][r["stance"]] = row["stances"].get(r["stance"], 0) + 1
        row["first_date"] = min(row["first_date"], r["date"])
        row["last_date"] = max(row["last_date"], r["date"])
    return sorted(rows.values(), key=lambda row: (-row["total"], row["other"]["name"]))


def within(date: str, start: Optional[str], end: Optional[str]) -> bool:
    """Is a YYYY-MM-DD date inside [start, end]? Bounds may be YYYY, YYYY-MM or
    YYYY-MM-DD, and are inclusive at their own precision: end="2023" keeps all of 2023.
    Comparing the date cut to each bound's length does exactly that."""
    if start and date[: len(start)] < start:
        return False
    if end and date[: len(end)] > end:
        return False
    return True


def personality(person, nr_relation_articles: int, offices: list) -> dict:
    """sparql.get_person_info()'s Person dataclass plus sparql.get_person_offices() ->
    plain dict with bare Q-ids, so the agent can pass any of them straight to
    find_personalities. `offices` replaces the web app's undated positions."""

    def elements(items):
        return [{"wiki_id": wiki_id_of(e.wiki_id), "label": e.label} for e in items or []]

    return {
        "wiki_id": person.wiki_id,
        "name": person.name,
        "nr_relation_articles": nr_relation_articles,
        "parties": [
            {"wiki_id": p.wiki_id, "name": p.name, "start_year": p.start_year, "end_year": p.end_year,
             "current": p.current}
            for p in person.parties or []
        ],
        "offices": offices,
        "governments": elements(person.governments),
        "assemblies": elements(person.assemblies),
        "education": elements(person.education),
        "occupations": elements(person.occupations),
    }


def personalities(bindings: list, nr_relation_articles: dict, party_of: dict) -> list:
    """get_personalities_by_*() bindings -> people who have at least one support or
    opposition article, most-covered first. nr_relation_articles maps wiki_id to that
    count; party_of maps wiki_id to the person's latest party ({wiki_id, name})."""
    people = []
    for b in bindings:
        wiki_id = wiki_id_of(b["ent1"]["value"])
        count = nr_relation_articles.get(wiki_id, 0)
        if count <= 0:
            continue
        people.append(
            {"wiki_id": wiki_id, "name": b["ent1_name"]["value"], "party": party_of.get(wiki_id),
             "nr_relation_articles": count}
        )
    people.sort(key=lambda p: p["nr_relation_articles"], reverse=True)
    return people


def page(records: list, limit: int, offset: int) -> dict:
    return {"total": len(records), "offset": offset, "items": records[offset: offset + limit]}
