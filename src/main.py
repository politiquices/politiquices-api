import json
import logging
import os
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import List, Union

from fastapi import FastAPI, Path, Query, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware


from cache import all_entities_info, all_parties_info, persons, parties, stats as stats_cache
from chave import get_chave_article
from config import sparql_endpoint, start_year, end_year, NO_IMAGE, party_logo_url
from sparql import (
    get_person_info,
    get_person_relationships,
    get_person_relationships_by_year,
    get_person_relationships_for_year,
    get_personalities_by_assembly,
    get_personalities_by_education,
    get_personalities_by_government,
    get_personalities_by_occupation,
    get_personalities_by_party,
    get_personalities_by_public_office,
    get_relationship_between_parties,
    get_relationship_between_party_and_person,
    get_relationship_between_person_and_party,
    get_relationship_between_two_persons,
    get_timeline_personalities,
    get_all_persons_latest_party,
    get_top_relationships,
    get_wiki_id_affiliated_with_party,
)
from utils import get_info
from politiquices_mcp import server as mcp

rel_types = ["ent1_opposes_ent2", "ent1_supports_ent2", "ent2_opposes_ent1", "ent2_supports_ent1", "other"]

wiki_id_regex = r"^Q\d+$"
rel_type_regex = r"((" + "|".join(rel_types) + r"))"

topics = None
topic_distr = None
topic_token_distr = None
url2index = None

logger = logging.getLogger("uvicorn")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # The MCP endpoint's session manager owns a task group that must live as long as the app.
    async with mcp.mcp_server.session_manager.run():
        yield


app = FastAPI(lifespan=lifespan)
# MCP server for agents, at /mcp (see politiquices_mcp/server.py). Its route is exact-
# path, so where it sits among the routes below doesn't matter.
app.router.routes.extend(mcp.routes)

# The annotator routes read and write the annotation JSONL files, so they are dev-only:
# run_local.sh sets ENABLE_ANNOTATOR=1, the production container doesn't. Imported here
# rather than at the top because annotation_router loads the latest release on import.
if os.getenv("ENABLE_ANNOTATOR") == "1":
    from annotation_router import router as annotation_router
    from duplicate_router import router as duplicate_router

    app.include_router(annotation_router)
    app.include_router(duplicate_router)
    logger.info("Annotator routes enabled (ENABLE_ANNOTATOR=1)")

# see: https://fastapi.tiangolo.com/tutorial/cors/
origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
# /timeline/default ships ~1.9 MB uncompressed (29k raw relationships) — repetitive
# JSON (short wiki_ids, a handful of distinct strings), so it compresses hard. Nothing
# under 1 KB is worth the CPU to gzip; everything the API returns above that already
# benefits, not just this one route.
app.add_middleware(GZipMiddleware, minimum_size=1000)


logger.info(f"Testing SPARQL endpoint: {sparql_endpoint}")
logger.info(
    f"{len(persons)} persons, {stats_cache['nr_all_relationships']} relationships "
    f"({stats_cache['nr_all_articles']} articles), "
    f"{stats_cache['nr_all_relationships_sentiment']} tagged with sentiment"
)


# wiki_id -> most recent party, for the logo shown beside a face in the relations panel
# and the personalities list. Loaded once per process, like the default network below:
# one SPARQL query, ~0.3s, rather than one per person on every page.
_latest_party = get_all_persons_latest_party()
logger.info(f"{len(_latest_party)} persons with a party")


def _party_of(wiki_id: str) -> Union[dict, None]:
    party = _latest_party.get(wiki_id)
    if party is None:
        return None
    return {"wiki_id": party.wiki_id, "name": party.name, "image_url": party.image_url}


def _nr_relation_articles(info: dict) -> int:
    """nr_articles counts every article mentioning the person, 'other' included;
    this is just the ones with an actual support/opposition relation."""
    return info.get("nr_articles", 0) - info.get("nr_articles_by_type", {}).get("other", 0)


# Who counts as a seed person for Explorar's default view: every well-documented
# figure, so their combined ego networks read as one coherent whole-network picture.
# Mirrors RANDOM_MIN_ARTICLES (the "Aleatória" pool) on the frontend — no relation-
# frequency threshold here any more, since #45 moved that from a fetch-time filter to
# a client-side one (Explorar.jsx's WHOLE_NETWORK_MIN_FREQ), applied live to the raw
# relationships this cache returns.
DEFAULT_NETWORK_MIN_ARTICLES = 50


def _has_sentiment_articles(wiki_id: str) -> bool:
    return _nr_relation_articles(all_entities_info.get(wiki_id, {})) > 0


def local_image(wiki_id: str, org_url: str, ent_type: str) -> str:
    base_url = "/assets/images/"

    # Return the constant rather than passing org_url through: cached entries may
    # still carry the old '/assets/images/no_picture.jpg', which 404s.
    if not org_url or "no_picture" in org_url:
        return NO_IMAGE

    if ent_type == "person":
        # `make images` writes every portrait as <wiki_id>.jpg, so the URL no longer
        # depends on whichever extension Wikidata happened to use. Reading it from
        # the source URL is what produced .jpg/.png/.JPG/.JPEG/.tif side by side.
        return f"{base_url}personalities_small/{wiki_id}.jpg"

    return f"{base_url}{wiki_id}.{org_url.split('.')[-1]}"


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/article/chave/{doc_id}")
async def chave_article(doc_id: str = Path(pattern=r"^PUBLICO-\d{8}-\d+$")):
    article = get_chave_article(doc_id)
    if article is None:
        raise HTTPException(status_code=404, detail="article not found")
    return article


@app.get("/personality/{wiki_id}")
async def personality(wiki_id: str = Path(pattern=wiki_id_regex)):
    person = get_person_info(wiki_id)
    cached = all_entities_info.get(wiki_id, {})
    person.image_url = cached.get("image_url") or local_image(person.wiki_id, person.image_url, ent_type="person")
    for party in person.parties:
        party.image_url = party_logo_url(party.wiki_id)

    def year2index(input_year: int):
        return int(input_year) - start_year

    def index2year(index: int):
        return index + start_year

    per_relationships = get_person_relationships(wiki_id)
    values = [
        {"opposes": 0, "supports": 0, "opposed_by": 0, "supported_by": 0} for _ in range(end_year - start_year + 1)
    ]
    for k in ["opposes", "supports", "opposed_by", "supported_by"]:
        for r in per_relationships[k]:
            year = r["date"][0:4]
            if int(year) > end_year:
                continue
            values[year2index(year)][k] += 1

    # this is a bit tricky, rels.update returns "None", but also updates rels which we want to add to the list
    chart_data = [rels for idx, rels in enumerate(values) if not rels.update({"year": index2year(idx)})]
    person.relationships_charts = chart_data

    return person


@app.get("/personality/relationships/{wiki_id}")
async def personality_relationships(wiki_id: str = Path(pattern=wiki_id_regex)):
    return get_person_relationships(wiki_id)


@app.get("/personality/relationships/{wiki_id}/{year}")
async def personality_relationships_for_year(
    wiki_id: str = Path(pattern=wiki_id_regex),
    year: str = Path(pattern=r"^\d{4}$"),
):
    return get_person_relationships_for_year(wiki_id, year)


@app.get("/personality/relationships_by_year/{wiki_id}")
async def personality_relationships_by_year(wiki_id: str = Path(pattern=wiki_id_regex)):
    results = {}
    for rel_type in rel_types:
        results[rel_type] = get_person_relationships_by_year(wiki_id, rel_type)
    return results


@app.get("/personality/top_related_personalities/{wiki_id}")
async def personality_top_related_personalities(wiki_id: str = Path(pattern=wiki_id_regex)):
    related = get_top_relationships(wiki_id)
    for entries in related.values():
        for entry in entries:
            entry["party"] = _party_of(entry["wiki_id"])
    return related


@app.get("/relationships/{ent_1}/{rel_type}/{ent_2}/{start}/{end}")
async def relationships(
    ent_1: str = Path(pattern=wiki_id_regex),
    rel_type: str = Path(pattern=rel_type_regex),
    ent_2: str = Path(pattern=wiki_id_regex),
    start: str = Path(),
    end: str = Path(),
):
    return get_relationship_between_two_persons(ent_1, ent_2, rel_type, start, end)


@app.get("/parties/")
async def get_all_parties():
    return list(all_parties_info)


@app.get("/personalities/top/")
async def get_top_personalities(n: int = 50):
    portuguese = [
        {"wiki_id": k, "name": v["name"], "image_url": v["image_url"], "nr_articles": v["nr_articles"]}
        for k, v in all_entities_info.items()
        if any(c["wiki_id"] == "Q45" for c in v.get("countries", []))
        and (v["nr_articles"] - v["nr_articles_by_type"].get("other", 0)) > 0
    ]
    return sorted(portuguese, key=lambda x: x["nr_articles"], reverse=True)[:n]


@app.get("/personalities/{page_nr}")
async def get_personalities(
    page_nr: int = Path(..., title="Page Number"),
    portuguese_only: bool = False,
    international_only: bool = False,
    sort: str = "articles",
):
    personalities_per_page = 32
    personalities = [
        {
            "label": v["name"],
            "nr_articles": _nr_relation_articles(v),
            "local_image": v["image_url"],
            "wiki_id": k,
            "party": _party_of(k),
        }
        for k, v in all_entities_info.items()
        if (v["nr_articles"] - v["nr_articles_by_type"].get("other", 0)) > 0
        and (not portuguese_only or any(c["wiki_id"] == "Q45" for c in v.get("countries", [])))
        and (not international_only or not any(c["wiki_id"] == "Q45" for c in v.get("countries", [])))
    ]
    # all_entities_info is stored sorted by the *total* article count (cache-build
    # time, generate_caches.py), not the relation-only one used here since #14 — for
    # "articles" that drifted apart from what's actually displayed, so it's sorted
    # explicitly rather than trusted from dict order. "name" needs its own sort in
    # any case: nothing about this list is ever alphabetical otherwise.
    if sort == "name":
        personalities.sort(key=lambda p: p["label"])
    else:
        personalities.sort(key=lambda p: p["nr_articles"], reverse=True)
    start_index = (page_nr - 1) * personalities_per_page
    end_index = start_index + personalities_per_page
    return {"total": len(personalities), "items": personalities[start_index:end_index]}


@app.get("/persons/")
async def get_all_persons():
    return persons


@app.get("/persons_and_parties/")
async def persons_and_parties():
    return sorted(persons + parties, key=lambda x: x["label"])


def _build_timeline(wiki_ids: List[str], selected: bool, sentiment: bool, min_freq: int, start: str, end: str) -> dict:
    results = get_timeline_personalities(wiki_ids, selected, sentiment, start, end)

    built_nodes = set()
    nodes = []
    edges_agg = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    edges = []

    def build_node(key, result):
        if result[key] not in built_nodes:
            nodes.append({"id": result[key], "label": all_entities_info[result[key]]["name"], "image_url": all_entities_info[result[key]]["image_url"]})
            built_nodes.add(result[key])

    for x in results:
        build_node("ent1_id", x)
        build_node("ent2_id", x)
        rel_type = x["rel_type"]
        # Determine the actor (who is doing the action) and the target
        if rel_type in ("ent1_opposes_ent2", "ent1_supports_ent2"):
            actor, target = x["ent1_id"], x["ent2_id"]
        else:  # ent2_opposes_ent1, ent2_supports_ent1
            actor, target = x["ent2_id"], x["ent1_id"]
        sentiment = "opposes" if "opposes" in rel_type else "supports"
        # Use canonical ordering so A→B and B→A of same type merge into one edge
        canon_s, canon_t = (actor, target) if actor < target else (target, actor)
        edges_agg[canon_s][canon_t][sentiment] += 1

    for s, v in edges_agg.items():
        for t, rels in v.items():
            for rel_type, freq in rels.items():

                if freq < min_freq:
                    continue

                if rel_type == "opposes":
                    rel_text = "opõe-se"
                    color = "#FF0000"
                    highlight = "#780000"
                else:
                    rel_text = "apoia"
                    color = "#44861E"
                    highlight = "#1d4a03"

                edges.append(
                    {
                        "from": s,
                        "to": t,
                        "id": len(edges) + 1,
                        "color": {
                            "color": color,
                            "highlight": highlight,
                        },
                        "scaling": {"max": 7},
                        "title": rel_text,
                        "value": freq,
                    }
                )

    # remove nodes with edges < min_freq
    node_ids = set([e["from"] for e in edges] + [e["to"] for e in edges])
    nodes_filtered = [n for n in nodes if n["id"] in node_ids]

    # `news` used to carry every matching article so the page could list them below the
    # graph — no caller has read it since #38 moved article display to a per-edge
    # fetch, but it was still being built and serialised here on every request. For a
    # broad query (many seed persons) that's most of the response: a 168-person /
    # min_freq=20 request measured at ~16 MB with this filled in, all of it unread.
    print(f"nodes: {len(nodes)}, edges: {len(edges)}")
    return {"news": [], "nodes": nodes_filtered, "edges": edges}


@app.get("/timeline/")
async def timeline(
    q: Union[List[str], None] = Query(),
    selected: bool = Query(),
    sentiment: bool = Query(),
    min_freq: int = Query(default=10),
    start: str = Query(),
    end: str = Query()

):
    return _build_timeline(q, selected, sentiment, min_freq, start, end)


def _build_raw_relationships(wiki_ids: List[str], selected: bool, sentiment: bool, start: str, end: str) -> dict:
    """The same underlying data `_build_timeline` aggregates, but left raw: neither
    thresholded by min_freq nor canonicalised into one direction per pair (the old
    aggregation's `canon_s < canon_t` ordering silently merged "A supports B" with
    "B supports A" into a single edge under whichever id sorts first — harmless once
    counted down to a min_freq total, but wrong to build a client-side aggregator on).
    Every (actor, target, sign, year) survives here, so Explorar's threshold/period/
    sign controls can group and filter this once-fetched list live, in the browser,
    instead of re-querying SPARQL per slider move. `nodes` is a wiki_id lookup kept
    separate from `relationships` rather than repeated per row — the same person shows
    up in many relationships."""
    results = get_timeline_personalities(wiki_ids, selected, sentiment, start, end)

    relationships = []
    nodes = {}

    def add_node(wiki_id):
        if wiki_id not in nodes:
            info = all_entities_info.get(wiki_id, {})
            nodes[wiki_id] = {"name": info.get("name"), "image_url": info.get("image_url")}

    def add_relationship(actor, target, sign, x):
        add_node(actor)
        add_node(target)
        relationships.append({
            "from": actor,
            "to": target,
            "sign": sign,
            "year": int(x["date"][:4]),
            "score": x.get("score"),
        })

    for x in results:
        rel_type = x["rel_type"]
        if rel_type in ("ent1_opposes_ent2", "ent1_supports_ent2"):
            sign = "opõe-se" if "opposes" in rel_type else "apoia"
            add_relationship(x["ent1_id"], x["ent2_id"], sign, x)
        elif rel_type in ("ent2_opposes_ent1", "ent2_supports_ent1"):
            sign = "opõe-se" if "opposes" in rel_type else "apoia"
            add_relationship(x["ent2_id"], x["ent1_id"], sign, x)
        elif rel_type in ("mutual_agreement", "mutual_opposition"):
            # A single triple in the graph (see keep-mutual-relation-classes in project memory),
            # fanned out into both directions here: ent1 and ent2 are simultaneously actor and
            # target of the same relationship, so this draws as two arcs, same colour -- exactly
            # like two separate directional relationships would.
            sign = "opõe-se" if rel_type == "mutual_opposition" else "apoia"
            add_relationship(x["ent1_id"], x["ent2_id"], sign, x)
            add_relationship(x["ent2_id"], x["ent1_id"], sign, x)
        # else: "other" only reaches here when sentiment=False was requested -- there is no
        # direction to draw for it, so it's silently skipped rather than falling into an
        # unrelated bucket the way the old blanket `else` used to.

    print(f"raw relationships: {len(relationships)}, nodes: {len(nodes)}")
    return {"relationships": relationships, "nodes": nodes}


@app.get("/timeline/raw")
async def timeline_raw(
    q: Union[List[str], None] = Query(),
    selected: bool = Query(),
    sentiment: bool = Query(),
    start: str = Query(),
    end: str = Query(),
):
    return _build_raw_relationships(q, selected, sentiment, start, end)


@app.get("/timeline/default")
async def timeline_default():
    """Explorar's default view, precomputed at startup (see `_default_network_raw`
    below) — the SPARQL query behind it takes several seconds even for a single
    request; run once per process instead of once per page load."""
    return _default_network_raw


_default_network_seeds = [
    wiki_id for wiki_id, info in all_entities_info.items()
    if _nr_relation_articles(info) >= DEFAULT_NETWORK_MIN_ARTICLES
]
logger.info(f"Building the default network cache ({len(_default_network_seeds)} seed persons, raw)...")
_default_network_cache_start = time.time()
_default_network_raw = _build_raw_relationships(
    _default_network_seeds, selected=False, sentiment=True,
    start=str(start_year), end=str(end_year),
)
logger.info(
    f"Default network cache ready in {time.time() - _default_network_cache_start:.1f}s: "
    f"{len(_default_network_raw['relationships'])} relationships, {len(_default_network_raw['nodes'])} nodes"
)


@app.get("/queries")
async def queries(
    ent1: str = Query(pattern=wiki_id_regex),
    ent2: str = Query(pattern=wiki_id_regex),
    rel_type: str = Query(),
    start: str = Query(),
    end: str = Query(),
):
    # time interval for the query
    year_from = start
    year_to = end
    e1_type = get_info(ent1)
    e2_type = get_info(ent2)

    if e1_type == "person" and e2_type == "person":
        return get_relationship_between_two_persons(ent1, ent2, rel_type, year_from, year_to)

    if e1_type == "party" and e2_type == "person":
        return get_relationship_between_party_and_person(ent1, ent2, rel_type, year_from, year_to)

    if e1_type == "person" and e2_type == "party":
        return get_relationship_between_person_and_party(ent1, ent2, rel_type, year_from, year_to)

    if e1_type == "party" and e2_type == "party":
        # get the members for each party
        party_a = " ".join(["wd:" + x for x in get_wiki_id_affiliated_with_party(ent1)])
        party_b = " ".join(["wd:" + x for x in get_wiki_id_affiliated_with_party(ent2)])
        r = get_relationship_between_parties(party_a, party_b, rel_type, year_from, year_to)
        return r


def _with_entity_info(results: list) -> list:
    """The /personalities/<filter>/ routes: raw SPARQL bindings, one per person, with the
    cached portrait, the relation-article count and the most recent party attached, and
    the people with no sentiment articles left out."""
    for r in results:
        entry_wiki_id = r["ent1"]["value"].split("/")[-1]
        info = all_entities_info.get(entry_wiki_id, {})
        r["image_url"]["value"] = info.get("image_url", NO_IMAGE)
        r["nr_articles"] = _nr_relation_articles(info)
        r["party"] = _party_of(entry_wiki_id)
    return [r for r in results if _has_sentiment_articles(r["ent1"]["value"].split("/")[-1])]


@app.get("/personalities/educated_at/{wiki_id}")
async def personalities_educated_at(wiki_id: str = Path(pattern=wiki_id_regex)):
    results = get_personalities_by_education(wiki_id)
    return _with_entity_info(results)


@app.get("/personalities/occupation/{wiki_id}")
async def personalities_occupation(wiki_id: str = Path(pattern=wiki_id_regex)):
    results = get_personalities_by_occupation(wiki_id)
    return _with_entity_info(results)


@app.get("/personalities/public_office/{wiki_id}")
async def personalities_public_office(wiki_id: str = Path(pattern=wiki_id_regex)):
    results = get_personalities_by_public_office(wiki_id)
    return _with_entity_info(results)


@app.get("/personalities/government/{wiki_id}")
async def read_item(wiki_id: str = Path(pattern=wiki_id_regex)):
    results = get_personalities_by_government(wiki_id)
    return _with_entity_info(results)


@app.get("/personalities/assembly/{wiki_id}")
async def personalities_assembly(wiki_id: str = Path(pattern=wiki_id_regex)):
    results = get_personalities_by_assembly(wiki_id)
    return _with_entity_info(results)


@app.get("/personalities/party/{wiki_id}")
async def personalities_party(wiki_id: str = Path(pattern=wiki_id_regex)):
    results = get_personalities_by_party(wiki_id)
    return _with_entity_info(results)


@app.get("/stats")
async def stats():
    # Precomputed by generate_caches.py::stats_json_cache() alongside the
    # personalities/parties caches -- this data is static between data-pipeline runs,
    # so it's read from the cache instead of hitting SPARQL on every request.
    #
    # nr_persons matches /personalities exactly since both read the same curated
    # cache; a live "not other" SPARQL count here used to drift from it, still
    # including entities pruned from wiki_ttl via entities_config.json's remove list
    # (they keep a relationship in the graph, since create_rdf_graph.py writes it
    # independently of that curation).
    return {
        "nr_parties": len(all_parties_info),
        "nr_persons": len(persons),
        "nr_all_articles_sentiment": stats_cache["nr_all_articles_sentiment"],
        "nr_all_relationships_sentiment": stats_cache["nr_all_relationships_sentiment"],
    }


@app.get("/stats/yearly")
async def stats_yearly():
    return {"year_values": stats_cache["year_values"]}


@app.get("/stats/sources")
async def stats_sources():
    # Split out the same way /stats/yearly is: not on the metric cards' critical path,
    # so the Sobre page's sources section fetches and loads independently of them.
    return {
        "provenance": stats_cache["provenance"],
        "domains": stats_cache["domains"],
    }
