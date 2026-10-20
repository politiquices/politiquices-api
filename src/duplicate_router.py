import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Set

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from annotation_router import _normalize_jsonl_record

router = APIRouter(prefix="/annotator/duplicates", tags=["duplicates"])

# kept alongside the rest of the annotation tooling and its output
# (nlp_extraction/annotations/jsonl/), not scattered between the API and nlp_extraction repos.
# duplicate_annotations.jsonl only ever holds same_relationship: true judgments -- it gets
# deleted by nlp_extraction/annotations/release/build_release.py once its pairs are folded into a
# release's duplicate_group_id tags. duplicate_annotations_negative.jsonl is never deleted: a
# negative judgment has no equivalent representation in a release, so this file is the sole
# permanent record of "these two are confirmed different".
PAIR_ANNOTATIONS_FILE = Path(
    os.getenv("PAIR_ANNOTATIONS_FILE", "../nlp_extraction/annotations/jsonl/duplicate_annotations.jsonl")
)
PAIR_ANNOTATIONS_NEGATIVE_FILE = Path(
    os.getenv(
        "PAIR_ANNOTATIONS_NEGATIVE_FILE",
        "../nlp_extraction/annotations/jsonl/duplicate_annotations_negative.jsonl",
    )
)
_judged_pairs: Set[str] = set()


def _load_pair_ids(path: Path) -> Set[str]:
    ids: Set[str] = set()
    if not path.exists():
        return ids
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                if "pair_id" in record:
                    ids.add(record["pair_id"])
            except json.JSONDecodeError:
                pass
    return ids


def load_existing_pairs() -> None:
    # Both files must be read: a pair judged same_relationship: false only ever lives in
    # PAIR_ANNOTATIONS_NEGATIVE_FILE (never derivable from a release, unlike the positive side --
    # see build_release.py's duplicate_group_id tagging), so skipping it would let a
    # resubmission of an already-rejected pair silently succeed instead of 409ing.
    _judged_pairs.update(_load_pair_ids(PAIR_ANNOTATIONS_FILE))
    _judged_pairs.update(_load_pair_ids(PAIR_ANNOTATIONS_NEGATIVE_FILE))


# Load on module import so pair ids are ready before any request arrives
load_existing_pairs()


def _pair_id(record_id_a: str, record_id_b: str) -> str:
    a, b = sorted([record_id_a, record_id_b])
    return hashlib.sha256(f"{a}|{b}".encode()).hexdigest()


@router.get("/search")
async def search_articles(
    jsonl_path: str = Query(...),
    q: Optional[str] = Query(None, min_length=2),
    domain: Optional[str] = Query(None, min_length=2),
    date_from: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    date_to: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    exclude_record_id: Optional[str] = Query(None),
    limit: int = Query(default=20, ge=1, le=50),
):
    if not any([q, domain, date_from, date_to]):
        raise HTTPException(status_code=400, detail="At least one of q, domain, date_from, date_to is required")

    path = Path(jsonl_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {jsonl_path}")

    q_lower = q.lower() if q else None
    domain_lower = domain.lower() if domain else None

    matches = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = _normalize_jsonl_record(json.loads(line))

            if exclude_record_id and record["record_id"] == exclude_record_id:
                continue
            if q_lower and q_lower not in record["title"].lower():
                continue
            if domain_lower and domain_lower not in record["domain"].lower():
                continue
            if date_from and (not record["date"] or record["date"] < date_from):
                continue
            if date_to and (not record["date"] or record["date"] > date_to):
                continue

            matches.append(record)

    matches.sort(key=lambda r: r["date"], reverse=True)
    total_matches = len(matches)
    return {"results": matches[:limit], "total_matches": total_matches}


class DuplicatePairPayload(BaseModel):
    a_record_id: str
    a_source: str = "jsonl"
    a_arquivo_url: str
    a_original_url: str = ""
    a_date: str = ""
    a_title: str = ""
    a_domain: str = ""
    a_rel_type: str = ""
    a_ent1_id: str = ""
    a_ent1_str: str = ""
    a_ent2_id: str = ""
    a_ent2_str: str = ""
    b_record_id: str
    b_source: str = "jsonl"
    b_arquivo_url: str
    b_original_url: str = ""
    b_date: str = ""
    b_title: str = ""
    b_domain: str = ""
    b_rel_type: str = ""
    b_ent1_id: str = ""
    b_ent1_str: str = ""
    b_ent2_id: str = ""
    b_ent2_str: str = ""
    same_relationship: bool
    annotator: str
    note: Optional[str] = None


@router.post("")
async def submit_duplicate_pair(payload: DuplicatePairPayload):
    if payload.a_record_id == payload.b_record_id:
        raise HTTPException(status_code=400, detail="Cannot pair an article with itself")

    pair_id = _pair_id(payload.a_record_id, payload.b_record_id)
    if pair_id in _judged_pairs:
        raise HTTPException(status_code=409, detail="Pair already judged")

    record = payload.model_dump()
    record["pair_id"] = pair_id
    record["annotated_at"] = datetime.now(timezone.utc).isoformat()

    target_file = PAIR_ANNOTATIONS_FILE if payload.same_relationship else PAIR_ANNOTATIONS_NEGATIVE_FILE
    with open(target_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    _judged_pairs.add(pair_id)
    return {"status": "ok", "pair_id": pair_id}


@router.get("/stats")
async def get_duplicate_stats():
    total_judged = 0
    same_count = 0
    different_count = 0

    for path in (PAIR_ANNOTATIONS_FILE, PAIR_ANNOTATIONS_NEGATIVE_FILE):
        if not path.exists():
            continue
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total_judged += 1
                if record.get("same_relationship"):
                    same_count += 1
                else:
                    different_count += 1

    return {"total_judged": total_judged, "same_count": same_count, "different_count": different_count}
