import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from cache import all_entities_info
from sparql import get_all_relationships_paginated, get_relationship_by_url, get_total_relationships_count

router = APIRouter(prefix="/annotator", tags=["annotator"])

ANNOTATIONS_FILE = Path(os.getenv("ANNOTATIONS_FILE", "./annotations.jsonl"))
_annotated_ids: Set[str] = set()


def load_existing_annotations() -> None:
    if not ANNOTATIONS_FILE.exists():
        return
    with open(ANNOTATIONS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if "record_id" in record:
                    _annotated_ids.add(record["record_id"])
            except json.JSONDecodeError:
                pass


# Load on module import so IDs are ready before any request arrives
load_existing_annotations()


def _record_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def _compute_entropy(scores: dict) -> float:
    entropy = 0.0
    for p in scores.values():
        if p > 0:
            entropy -= p * math.log2(p)
    return round(entropy, 4)


def _normalize_sparql_record(e: dict) -> dict:
    ent1_id = e["ent1"]["value"].split("/")[-1]
    ent2_id = e["ent2"]["value"].split("/")[-1]
    arquivo_url = e["arquivo_doc"]["value"]
    return {
        "record_id": _record_id(arquivo_url),
        "source": "sparql",
        "arquivo_url": arquivo_url,
        "original_url": e.get("publisher", {}).get("value", ""),
        "date": e.get("date", {}).get("value", "")[:10],
        "title": e.get("title", {}).get("value", ""),
        "paragraph_text": e.get("description", {}).get("value", ""),
        "domain": e.get("creator", {}).get("value", ""),
        "rel_type": e.get("rel_type", {}).get("value", "other"),
        "ent1_id": ent1_id,
        "ent1_str": e.get("ent1_str", {}).get("value", ""),
        "ent1_img": all_entities_info.get(ent1_id, {}).get("image_url", ""),
        "ent2_id": ent2_id,
        "ent2_str": e.get("ent2_str", {}).get("value", ""),
        "ent2_img": all_entities_info.get(ent2_id, {}).get("image_url", ""),
        "predicted_scores": None,
        "uncertainty_score": None,
    }


def _normalize_jsonl_record(record: dict) -> dict:
    entities = record.get("entities", [])
    ent1 = entities[0] if len(entities) > 0 else {}
    ent2 = entities[1] if len(entities) > 1 else {}

    ent1_wikidata = ent1.get("wikidata", "")
    ent2_wikidata = ent2.get("wikidata", "")
    # wikidata field can be a plain URI string or {"wiki_id": "...", "label": "...", "aliases": [...]}
    if isinstance(ent1_wikidata, dict):
        ent1_wikidata = ent1_wikidata.get("wiki_id", "")
    if isinstance(ent2_wikidata, dict):
        ent2_wikidata = ent2_wikidata.get("wiki_id", "")
    ent1_id = ent1_wikidata.split("/")[-1] if ent1_wikidata else ""
    ent2_id = ent2_wikidata.split("/")[-1] if ent2_wikidata else ""

    arquivo_url = record.get("arquivo_url", "")
    predicted_scores = record.get("predicted_scores") or {}
    entropy = _compute_entropy(predicted_scores) if predicted_scores else 0.0

    return {
        "record_id": _record_id(arquivo_url),
        "source": "jsonl",
        "arquivo_url": arquivo_url,
        "original_url": record.get("original_url", ""),
        "date": (record.get("publication_date") or record.get("crawled_date", ""))[:10],
        "title": record.get("title", ""),
        "paragraph_text": record.get("paragraph_text", ""),
        "domain": record.get("domain", ""),
        "rel_type": record.get("predicted_relationship", "other"),
        "ent1_id": ent1_id,
        "ent1_str": ent1.get("name", ""),
        "ent1_img": all_entities_info.get(ent1_id, {}).get("image_url", ""),
        "ent2_id": ent2_id,
        "ent2_str": ent2.get("name", ""),
        "ent2_img": all_entities_info.get(ent2_id, {}).get("image_url", ""),
        "predicted_scores": predicted_scores,
        "uncertainty_score": entropy,
    }


@router.get("/articles")
async def get_articles(
    source: str = Query(..., regex="^(sparql|jsonl)$"),
    jsonl_path: Optional[str] = Query(None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    sort_by: str = Query(default="default", regex="^(default|uncertainty)$"),
):
    if source == "sparql":
        total = get_total_relationships_count()
        bindings = get_all_relationships_paginated(offset=offset, limit=limit)
        items = [_normalize_sparql_record(e) for e in bindings]
        return {"total": total, "offset": offset, "items": items}

    if not jsonl_path:
        raise HTTPException(status_code=400, detail="jsonl_path required when source=jsonl")
    path = Path(jsonl_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {jsonl_path}")

    with open(path, encoding="utf-8") as f:
        all_records = [
            r for line in f
            if line.strip()
            for r in [json.loads(line)]
            if any(v > 0 for v in (r.get("predicted_scores") or {}).values())
            and _record_id(r.get("arquivo_url", "")) not in _annotated_ids
        ]

    total = len(all_records)

    if sort_by == "uncertainty":
        for r in all_records:
            scores = r.get("predicted_scores") or {}
            r["_entropy"] = _compute_entropy(scores) if scores else 0.0
        all_records.sort(key=lambda r: r["_entropy"], reverse=True)

    page_records = all_records[offset: offset + limit]
    items = [_normalize_jsonl_record(r) for r in page_records]
    return {"total": total, "offset": offset, "items": items}


@router.get("/article")
async def get_article(
    url: str = Query(...),
    source: str = Query(..., regex="^(sparql|jsonl)$"),
    jsonl_path: Optional[str] = Query(None),
):
    if source == "sparql":
        bindings = get_relationship_by_url(url)
        if not bindings:
            raise HTTPException(status_code=404, detail="Article not found in SPARQL endpoint")
        return _normalize_sparql_record(bindings[0])

    if not jsonl_path:
        raise HTTPException(status_code=400, detail="jsonl_path required when source=jsonl")
    path = Path(jsonl_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {jsonl_path}")
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("arquivo_url") == url:
                return _normalize_jsonl_record(record)
    raise HTTPException(status_code=404, detail="Article not found in JSONL file")


@router.get("/entities")
async def search_entities(
    q: str = Query(..., min_length=2),
    limit: int = Query(default=10, ge=1, le=50),
):
    q_lower = q.lower()
    matches = [
        {
            "wiki_id": wiki_id,
            "name": info["name"],
            "image_url": info.get("image_url", ""),
            "nr_articles": info.get("nr_articles", 0),
        }
        for wiki_id, info in all_entities_info.items()
        if q_lower in info.get("name", "").lower()
    ]
    matches.sort(key=lambda x: x["nr_articles"], reverse=True)
    return {"results": matches[:limit]}


class AnnotationPayload(BaseModel):
    record_id: str
    action: str
    source: str
    annotator: str
    arquivo_url: str
    original_url: str = ""
    date: str = ""
    title: str = ""
    paragraph_text: str = ""
    domain: str = ""
    rel_type: str
    ent1_id: str
    ent1_str: str
    ent2_id: str
    ent2_str: str
    original_rel_type: str
    original_ent1_id: str
    original_ent2_id: str
    predicted_scores: Optional[dict] = None


@router.post("/annotations")
async def submit_annotation(payload: AnnotationPayload):
    if payload.record_id in _annotated_ids:
        raise HTTPException(status_code=409, detail="Record already annotated")

    record = payload.dict()
    record["annotated_at"] = datetime.now(timezone.utc).isoformat()

    with open(ANNOTATIONS_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    _annotated_ids.add(payload.record_id)
    return {"status": "ok", "record_id": payload.record_id}


@router.get("/stats")
async def get_stats():
    if not ANNOTATIONS_FILE.exists():
        return {"total_annotated": 0, "total_skipped": 0, "by_rel_type": {}}

    total_annotated = 0
    total_skipped = 0
    by_rel_type: dict = {}

    with open(ANNOTATIONS_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if record.get("action") == "skip":
                    total_skipped += 1
                else:
                    total_annotated += 1
                    rel = record.get("rel_type", "other")
                    by_rel_type[rel] = by_rel_type.get(rel, 0) + 1
            except json.JSONDecodeError:
                pass

    return {"total_annotated": total_annotated, "total_skipped": total_skipped, "by_rel_type": by_rel_type}
