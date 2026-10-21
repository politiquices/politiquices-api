"""Read-only MCP server for politiquices.pt, served by the API itself at /mcp.

Five tools, shaped for an agent rather than mirroring the web app's endpoints:
search_entities -> get_personality / get_relationships / get_relationship_between /
find_personalities. No LLM runs here; the agent connecting to it brings its own.

main.py adds `routes` to the FastAPI app and runs `mcp_server.session_manager` in the
app's lifespan. The tools are plain `def`s on purpose: the SDK runs sync tools on a
worker thread, so a slow SPARQL query doesn't block the event loop the site shares.
"""
import json
import logging
import os
import re
from functools import cache, lru_cache
from pathlib import Path
from typing import Annotated, Literal, Optional

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations
from pydantic import Field

import sparql
from cache import all_entities_info, parties, persons
from config import start_year, end_year
from politiquices_mcp import adapters
from politiquices_mcp.search import Entity, EntityIndex
from utils import get_info

logger = logging.getLogger("uvicorn")

ENTITIES_KB = Path(os.getenv("ENTITIES_KB", "../sparql/entities_kb.jsonl"))
ALIAS_OVERRIDES = Path(os.getenv("ALIAS_OVERRIDES", "../sparql/alias_overrides.json"))
# Same lookup as annotation_router.DATA_RELEASES_DIR, duplicated rather than imported:
# importing annotation_router loads its own state, and it's dev-only.
DATA_RELEASES_DIR = Path(os.getenv("DATA_RELEASES_DIR", "../data-releases"))
ALLOWED_HOSTS = os.getenv("MCP_ALLOWED_HOSTS", "api.politiquices.pt,127.0.0.1:*,localhost:*").split(",")

WikiId = Annotated[str, Field(pattern=r"^Q\d+$", description="A Wikidata id such as Q610788, from search_entities")]
Limit = Annotated[int, Field(ge=1, le=100)]
Offset = Annotated[int, Field(ge=0)]
Year = Annotated[int, Field(ge=start_year, le=end_year)]
Stance = Literal["supports", "opposes", "supported_by", "opposed_by", "mutual_agreement", "mutual_opposition"]
READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)
# Every tool returns its own compact JSON string: left to the SDK, a dict goes out as
# indent=2 text, which costs the agent a third more tokens on large result pages.
TOOL = {"annotations": READ_ONLY, "structured_output": False}

INSTRUCTIONS = f"""\
politiquices.pt: support and opposition between Portuguese political figures, extracted
from news headlines ({start_year}-{end_year}, mostly arquivo.pt and publico.pt).

Every person and party is identified by a Wikidata id (Q...). Start with search_entities
to turn a name into an id; names are ambiguous, so check the candidates (or ask the user)
before going on.

Stances read from the subject's side: "A supports B", "A opposes B";
supported_by/opposed_by are the same relationships seen from B. A relationship is one
headline (sometimes several near-duplicate articles about the same event).

Most relationships are predicted by a classifier, not checked by a person. Each one
carries `annotated`: true when a human labelled it, false when it is a prediction, null
when that is unknown. Predictions are often wrong, and the classifier over-predicts
"supports" -- read the headline before stating a relationship as fact, and always cite
the article url.
"""


def _nr_relation_articles(wiki_id: str) -> int:
    """Articles with a support/opposition relation; same count the web app shows."""
    info = all_entities_info.get(wiki_id, {})
    return info.get("nr_articles", 0) - info.get("nr_articles_by_type", {}).get("other", 0)


def _kind(wiki_id: str) -> Optional[str]:
    """"person", "party", or None for an id politiquices.pt doesn't know."""
    try:
        return get_info(wiki_id)
    except ValueError:
        return None


def _require(wiki_id: str, *kinds: str) -> str:
    """ToolError, not ValueError: the SDK only passes a ToolError's message on to the
    agent, and this one tells it what to do next."""
    kind = _kind(wiki_id)
    if kind not in kinds:
        raise ToolError(f"{wiki_id} is not a {' or '.join(kinds)} in politiquices.pt; use search_entities first")
    return kind


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _load_aliases() -> dict:
    aliases = {}
    if ENTITIES_KB.exists():
        with open(ENTITIES_KB, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    aliases[adapters.wiki_id_of(entry["wiki_id"])] = list(entry.get("aliases", []))
    else:
        logger.warning(f"MCP: {ENTITIES_KB} not found, search_entities will match names only")
    if ALIAS_OVERRIDES.exists():
        with open(ALIAS_OVERRIDES, encoding="utf-8") as f:
            for wiki_id, extra in json.load(f).items():
                aliases.setdefault(wiki_id, []).extend(extra)
    return aliases


def _build_index() -> EntityIndex:
    aliases = _load_aliases()
    entities = [
        Entity(p["value"], p["label"], "person", _nr_relation_articles(p["value"]), aliases.get(p["value"], []))
        for p in persons
    ]
    entities += [Entity(p["value"], p["label"], "party", None, aliases.get(p["value"], [])) for p in parties]
    return EntityIndex(entities)


def _find_latest_release(releases_dir: Path) -> Optional[Path]:
    versioned = sorted(
        releases_dir.glob("politiquices_data_v*.jsonl"),
        key=lambda p: [int(n) for n in re.search(r"v(\d+)\.(\d+)", p.name).groups()],
    )
    return versioned[-1] if versioned else None


def _load_annotated_urls() -> Optional[set]:
    """Article urls a human annotated, from the latest data release. None (not an empty
    set) when there is no release to read, so `annotated` says "unknown" instead of
    claiming every relationship is a prediction."""
    release = _find_latest_release(DATA_RELEASES_DIR) if DATA_RELEASES_DIR.is_dir() else None
    if release is None:
        logger.warning(f"MCP: no data release under {DATA_RELEASES_DIR}, `annotated` will be null")
        return None
    with open(release, encoding="utf-8") as f:
        urls = {json.loads(line)["url"] for line in f if line.strip()}
    logger.info(f"MCP: {len(urls)} annotated urls from {release.name}")
    return urls


index = _build_index()
annotated_urls = _load_annotated_urls()
names = {wiki_id: info["name"] for wiki_id, info in all_entities_info.items() if info.get("name")}


@cache
def _latest_party() -> dict:
    """wiki_id -> {wiki_id, name} of the person's most recent party. One SPARQL query,
    run on first use rather than at import (main.py already runs the same query once at
    startup for the web app)."""
    return {k: {"wiki_id": v.wiki_id, "name": v.name} for k, v in sparql.get_all_persons_latest_party().items()}


# get_person_relationships() has no cache of its own and a well-covered person has
# thousands of relationships; paging through them shouldn't re-run the query each time.
_person_relationships = lru_cache(maxsize=64)(sparql.get_person_relationships)

mcp_server = MCPServer(name="politiquices", title="politiquices.pt", instructions=INSTRUCTIONS)


@mcp_server.tool(**TOOL)
def search_entities(
    name: Annotated[str, Field(min_length=2, description="A name or part of one, accents optional")],
    kind: Optional[Literal["person", "party"]] = None,
    limit: Limit = 10,
) -> str:
    """Find persons or parties by name and return their Wikidata ids.

    Matching ignores accents and case and also covers known aliases. Results are
    ordered by how well they match, then by how much coverage the person has
    (nr_relation_articles). Several people often share a surname: pick by the full
    name, by coverage, or by checking get_personality, and ask the user when unsure."""
    return _json({"results": index.search(name, kind=kind, limit=limit)})


@mcp_server.tool(**TOOL)
def get_personality(wiki_id: WikiId) -> str:
    """Profile of a person: parties (with years when known), public offices,
    governments, parliamentary terms, education and occupations.

    The ids of governments, terms, offices, parties and schools here can be passed to
    find_personalities, e.g. to list everyone in the same government."""
    _require(wiki_id, "person")
    return _json(adapters.personality(sparql.get_person_info(wiki_id), _nr_relation_articles(wiki_id)))


@mcp_server.tool(**TOOL)
def get_relationships(
    wiki_id: WikiId,
    stance: Optional[Stance] = None,
    year: Optional[Year] = None,
    include_other: Annotated[bool, Field(description="Also return headlines with no support/opposition")] = False,
    include_paragraph: Annotated[bool, Field(description="Add each article's first paragraph (larger)")] = False,
    limit: Limit = 20,
    offset: Offset = 0,
) -> str:
    """Everyone this person supported or opposed, and everyone who supported or opposed
    them, newest first, one record per headline.

    Stances are from this person's side: "supports"/"opposes" = this person towards
    `other`; "supported_by"/"opposed_by" = `other` towards this person. Use stance and
    year to narrow down; page with offset."""
    _require(wiki_id, "person")
    if year is None:
        buckets = _person_relationships(wiki_id)
    else:
        buckets = adapters.year_relationships_to_buckets(sparql.get_person_relationships_for_year(wiki_id, str(year)))
    stances = [stance] if stance else list(adapters.PERSON_STANCES) + (list(adapters.OTHER_STANCES) if include_other else [])
    records = adapters.person_relationships(buckets, stances, annotated_urls, include_paragraph, names)
    return _json(adapters.page(records, limit, offset))


@mcp_server.tool(**TOOL)
def get_relationship_between(
    a: WikiId,
    b: WikiId,
    start_year: Year = start_year,
    end_year: Year = end_year,
    include_paragraph: Annotated[bool, Field(description="Add each article's first paragraph (larger)")] = False,
    limit: Limit = 20,
    offset: Offset = 0,
) -> str:
    """Support and opposition between two entities, as "subject <stance> object"
    records, newest first. Each side can be a person or a party; for a party, the
    subject/object is the party member involved.

    Use it for questions like "how did A and B get along over the years" or "has A ever
    supported B". Party vs party compares every member of both and can take a few
    seconds."""
    kind_a, kind_b = _require(a, "person", "party"), _require(b, "person", "party")
    if start_year > end_year:
        raise ToolError("start_year must not be after end_year")
    start, end = str(start_year), str(end_year)
    # Same dispatch as main.py's /queries. "all_sentiment" is what the web app sends,
    # and the only value every branch handles (see utils._process_rel_type).
    if kind_a == "person" and kind_b == "person":
        rels = sparql.get_relationship_between_two_persons(a, b, "all_sentiment", start, end)
    elif kind_a == "party" and kind_b == "person":
        rels = sparql.get_relationship_between_party_and_person(a, b, "all_sentiment", start, end)
    elif kind_a == "person" and kind_b == "party":
        rels = sparql.get_relationship_between_person_and_party(a, b, "all_sentiment", start, end)
    else:
        members_a = " ".join("wd:" + x for x in sparql.get_wiki_id_affiliated_with_party(a))
        members_b = " ".join("wd:" + x for x in sparql.get_wiki_id_affiliated_with_party(b))
        rels = sparql.get_relationship_between_parties(members_a, members_b, "all_sentiment", start, end)
    records = adapters.between_relationships(rels, annotated_urls, include_paragraph)
    return _json(adapters.page(records, limit, offset))


_FILTERS = {
    "party": sparql.get_personalities_by_party,
    "government": sparql.get_personalities_by_government,
    "assembly": sparql.get_personalities_by_assembly,
    "public_office": sparql.get_personalities_by_public_office,
    "education": sparql.get_personalities_by_education,
    "occupation": sparql.get_personalities_by_occupation,
}


@mcp_server.tool(**TOOL)
def find_personalities(
    filter: Literal["party", "government", "assembly", "public_office", "education", "occupation"],
    wiki_id: WikiId,
    limit: Limit = 50,
    offset: Offset = 0,
) -> str:
    """People in a party, government, parliamentary term ("assembly"), public office,
    school ("education") or occupation, most-covered first. Only people with at least
    one support/opposition article are listed. Membership is "ever", not "currently":
    a party lists everyone who was once a member (`party` shows their latest one).

    wiki_id is the group's id: a party id from search_entities, or a government, term,
    office, school or occupation id from get_personality."""
    bindings = _FILTERS[filter](wiki_id)
    nr = {adapters.wiki_id_of(b["ent1"]["value"]): _nr_relation_articles(adapters.wiki_id_of(b["ent1"]["value"]))
          for b in bindings}
    return _json(adapters.page(adapters.personalities(bindings, nr, _latest_party()), limit, offset))


http_app = mcp_server.streamable_http_app(
    streamable_http_path="/mcp",
    # Stateless + plain JSON: every call stands alone (all tools are read-only), and no
    # SSE stream has to survive Apache's proxy and gzip.
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(allowed_hosts=ALLOWED_HOSTS),
)
routes = http_app.routes
