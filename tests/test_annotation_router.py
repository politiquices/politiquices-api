import asyncio
import json

import pytest

from src import annotation_router as ar


def _write_release(path, urls):
    path.write_text("\n".join(json.dumps({"url": url}) for url in urls), encoding="utf-8")


class TestFindLatestRelease:
    def test_picks_the_highest_version(self, tmp_path):
        for name in ("politiquices_data_v1.0.jsonl", "politiquices_data_v2.0.jsonl", "politiquices_data_v1.5.jsonl"):
            (tmp_path / name).write_text("")
        assert ar._find_latest_release(tmp_path).name == "politiquices_data_v2.0.jsonl"

    def test_double_digit_minor_version_sorts_numerically_not_lexicographically(self, tmp_path):
        for name in ("politiquices_data_v9.0.jsonl", "politiquices_data_v10.0.jsonl"):
            (tmp_path / name).write_text("")
        assert ar._find_latest_release(tmp_path).name == "politiquices_data_v10.0.jsonl"

    def test_no_release_files_returns_none(self, tmp_path):
        assert ar._find_latest_release(tmp_path) is None


class TestLoadReleaseAnnotatedIds:
    def test_seeds_annotated_ids_from_the_latest_release(self, tmp_path, monkeypatch):
        _write_release(tmp_path / "politiquices_data_v1.0.jsonl", ["https://a"])
        _write_release(tmp_path / "politiquices_data_v2.0.jsonl", ["https://b"])
        monkeypatch.setattr(ar, "DATA_RELEASES_DIR", tmp_path)
        ar._annotated_ids.clear()

        ar.load_release_annotated_ids()

        assert ar._record_id("https://b") in ar._annotated_ids
        assert ar._record_id("https://a") not in ar._annotated_ids

    def test_no_releases_dir_is_tolerated(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ar, "DATA_RELEASES_DIR", tmp_path / "does-not-exist")
        ar._annotated_ids.clear()
        ar.load_release_annotated_ids()  # must not raise
        assert ar._annotated_ids == set()


class TestSubmitAnnotationDedup:
    def test_record_only_present_in_the_release_is_rejected_as_already_annotated(self, tmp_path, monkeypatch):
        _write_release(tmp_path / "politiquices_data_v1.0.jsonl", ["https://already-in-release"])
        monkeypatch.setattr(ar, "DATA_RELEASES_DIR", tmp_path)
        monkeypatch.setattr(ar, "ANNOTATIONS_FILE", tmp_path / "annotations.jsonl")
        ar._annotated_ids.clear()
        ar.load_release_annotated_ids()

        payload = ar.AnnotationPayload(
            record_id=ar._record_id("https://already-in-release"),
            action="annotate",
            source="webapp",
            annotator="test",
            arquivo_url="https://already-in-release",
            rel_type="ent1_supports_ent2",
            ent1_id="Q1",
            ent1_str="A",
            ent2_id="Q2",
            ent2_str="B",
            original_rel_type="other",
            original_ent1_id="Q1",
            original_ent2_id="Q2",
        )
        with pytest.raises(Exception) as exc_info:
            asyncio.run(ar.submit_annotation(payload))
        assert exc_info.value.status_code == 409
