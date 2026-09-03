import asyncio
import json

import pytest

from src import duplicate_router as dr


@pytest.fixture(autouse=True)
def _isolate_pair_files(tmp_path, monkeypatch):
    """Every test gets its own empty pair files and a cleared _judged_pairs set, so none of
    this reads or writes the real nlp_extraction/annotations/jsonl/ files and no test leaks
    state into the next one (both files are module-level singletons populated once at import).
    """
    monkeypatch.setattr(dr, "PAIR_ANNOTATIONS_FILE", tmp_path / "duplicate_annotations.jsonl")
    monkeypatch.setattr(dr, "PAIR_ANNOTATIONS_NEGATIVE_FILE", tmp_path / "duplicate_annotations_negative.jsonl")
    dr._judged_pairs.clear()
    yield


def _payload(a_url, b_url, same_relationship, a_record_id="a", b_record_id="b"):
    return dr.DuplicatePairPayload(
        a_record_id=a_record_id,
        a_arquivo_url=a_url,
        b_record_id=b_record_id,
        b_arquivo_url=b_url,
        same_relationship=same_relationship,
        annotator="test",
    )


class TestSubmitDuplicatePair:
    def test_same_relationship_true_is_written_to_the_positive_file(self):
        result = asyncio.run(dr.submit_duplicate_pair(_payload("https://a", "https://b", True)))
        assert dr.PAIR_ANNOTATIONS_FILE.exists()
        assert not dr.PAIR_ANNOTATIONS_NEGATIVE_FILE.exists()
        written = json.loads(dr.PAIR_ANNOTATIONS_FILE.read_text().strip())
        assert written["same_relationship"] is True
        assert written["pair_id"] == result["pair_id"]

    def test_same_relationship_false_is_written_to_the_negative_file(self):
        result = asyncio.run(dr.submit_duplicate_pair(_payload("https://a", "https://b", False)))
        assert dr.PAIR_ANNOTATIONS_NEGATIVE_FILE.exists()
        assert not dr.PAIR_ANNOTATIONS_FILE.exists()
        written = json.loads(dr.PAIR_ANNOTATIONS_NEGATIVE_FILE.read_text().strip())
        assert written["same_relationship"] is False
        assert written["pair_id"] == result["pair_id"]

    def test_resubmitting_a_positive_pair_is_rejected(self):
        payload = _payload("https://a", "https://b", True)
        asyncio.run(dr.submit_duplicate_pair(payload))
        with pytest.raises(Exception) as exc_info:
            asyncio.run(dr.submit_duplicate_pair(payload))
        assert exc_info.value.status_code == 409

    def test_resubmitting_a_negative_pair_is_rejected(self):
        payload = _payload("https://a", "https://b", False)
        asyncio.run(dr.submit_duplicate_pair(payload))
        with pytest.raises(Exception) as exc_info:
            asyncio.run(dr.submit_duplicate_pair(payload))
        assert exc_info.value.status_code == 409

    def test_pairing_a_record_with_itself_is_rejected(self):
        payload = _payload("https://a", "https://a", True, a_record_id="x", b_record_id="x")
        with pytest.raises(Exception) as exc_info:
            asyncio.run(dr.submit_duplicate_pair(payload))
        assert exc_info.value.status_code == 400


class TestLoadExistingPairs:
    def test_seeds_judged_pairs_from_both_files(self):
        dr.PAIR_ANNOTATIONS_FILE.write_text(json.dumps({"pair_id": "p1"}) + "\n")
        dr.PAIR_ANNOTATIONS_NEGATIVE_FILE.write_text(json.dumps({"pair_id": "p2"}) + "\n")
        dr.load_existing_pairs()
        assert dr._judged_pairs == {"p1", "p2"}

    def test_missing_files_are_tolerated(self):
        dr.load_existing_pairs()
        assert dr._judged_pairs == set()


class TestGetDuplicateStats:
    def test_sums_both_files(self):
        asyncio.run(dr.submit_duplicate_pair(_payload("https://a", "https://b", True, "a", "b")))
        asyncio.run(dr.submit_duplicate_pair(_payload("https://c", "https://d", False, "c", "d")))
        stats = asyncio.run(dr.get_duplicate_stats())
        assert stats == {"total_judged": 2, "same_count": 1, "different_count": 1}

    def test_no_files_yet_reports_zero(self):
        stats = asyncio.run(dr.get_duplicate_stats())
        assert stats == {"total_judged": 0, "same_count": 0, "different_count": 0}
