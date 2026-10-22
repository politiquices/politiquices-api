from types import SimpleNamespace

from politiquices_mcp import adapters
from politiquices_mcp.search import Entity, EntityIndex, normalize


def _rel(ent1_id, ent2_id, rel_type, date, urls, ent1_str="A", ent2_str="B"):
    return {
        "ent1_id": ent1_id, "ent1_str": ent1_str, "ent2_id": ent2_id, "ent2_str": ent2_str,
        "rel_type": rel_type, "date": date,
        "articles": [
            {"arquivo_doc": u, "title": f"title {u}", "domain": "publico.pt", "original_url": u,
             "paragraph": "para", "date": date}
            for u in urls
        ],
    }


class TestBetweenRelationships:
    def test_reads_every_rel_type_as_subject_stance_object(self):
        rels = [
            _rel("Q1", "Q2", "ent1_supports_ent2", "2020-01-01", ["u1"]),
            _rel("Q1", "Q2", "ent2_opposes_ent1", "2021-01-01", ["u2"]),
            _rel("Q1", "Q2", "mutual_opposition", "2022-01-01", ["u3"]),
        ]
        out = adapters.between_relationships(rels, annotated_urls=set())
        got = [(r["subject"]["wiki_id"], r["stance"], r["object"]["wiki_id"]) for r in out]
        assert got == [("Q1", "mutual_opposition", "Q2"), ("Q2", "opposes", "Q1"), ("Q1", "supports", "Q2")]

    def test_other_is_dropped(self):
        assert adapters.between_relationships([_rel("Q1", "Q2", "other", "2020-01-01", ["u"])], set()) == []

    def test_annotated_when_any_article_is_in_the_release(self):
        rel = _rel("Q1", "Q2", "ent1_supports_ent2", "2020-01-01", ["dup", "annotated"])
        assert adapters.between_relationships([rel], {"annotated"})[0]["annotated"] is True
        assert adapters.between_relationships([rel], {"elsewhere"})[0]["annotated"] is False

    def test_annotated_is_null_without_an_annotation_source(self):
        rel = _rel("Q1", "Q2", "ent1_supports_ent2", "2020-01-01", ["u"])
        assert adapters.between_relationships([rel], None)[0]["annotated"] is None

    def test_paragraph_only_on_request(self):
        rel = _rel("Q1", "Q2", "ent1_supports_ent2", "2020-01-01T00:00:00", ["u"])
        assert "paragraph" not in adapters.between_relationships([rel], set())[0]["articles"][0]
        out = adapters.between_relationships([rel], set(), include_paragraph=True)[0]
        assert out["articles"][0]["paragraph"] == "para"
        assert out["date"] == "2020-01-01"


class TestPersonRelationships:
    def test_reads_the_requested_buckets_only_newest_first(self):
        buckets = {
            "supports": [_rel("Q1", "Q2", "supports", "2019-05-01", ["a"])],
            "opposed_by": [_rel("Q1", "Q3", "opposed_by", "2021-05-01", ["b"])],
            "other": [_rel("Q1", "Q4", "other", "2022-05-01", ["c"])],
            # aggregates of the buckets above: reading them would duplicate records
            "all": [_rel("Q1", "Q2", "supports", "2019-05-01", ["a"])],
            "sentiment": [_rel("Q1", "Q2", "supports", "2019-05-01", ["a"])],
        }
        out = adapters.person_relationships(buckets, adapters.PERSON_STANCES, set())
        assert [(r["stance"], r["other"]["wiki_id"]) for r in out] == [("opposed_by", "Q3"), ("supports", "Q2")]

    def test_canonical_name_replaces_the_headline_mention(self):
        buckets = {"supports": [_rel("Q1", "Q2", "supports", "2019-05-01", ["a"], ent2_str="Centeno")]}
        out = adapters.person_relationships(buckets, ["supports"], set(), names={"Q2": "Mário Centeno"})
        assert out[0]["other"]["name"] == "Mário Centeno"
        unnamed = adapters.person_relationships(buckets, ["supports"], set())
        assert unnamed[0]["other"]["name"] == "Centeno"

    def test_top_related_counts_per_counterpart_most_first(self):
        buckets = {
            "opposed_by": [_rel("Q1", "Q2", "opposed_by", "2019-05-01", ["a"]),
                           _rel("Q1", "Q2", "opposed_by", "2019-07-01", ["b"]),
                           _rel("Q1", "Q3", "opposed_by", "2019-06-01", ["c"])],
            "supported_by": [_rel("Q1", "Q2", "supported_by", "2019-01-01", ["d"])],
        }
        records = adapters.person_relationships(buckets, adapters.PERSON_STANCES, {"b"}, names={"Q2": "B", "Q3": "C"})
        rows = adapters.top_related(records)
        assert rows[0] == {"other": {"wiki_id": "Q2", "name": "B"}, "total": 3, "annotated": 1,
                           "stances": {"opposed_by": 2, "supported_by": 1},
                           "first_date": "2019-01-01", "last_date": "2019-07-01"}
        assert [r["other"]["wiki_id"] for r in rows] == ["Q2", "Q3"]

    def test_year_list_groups_into_the_same_buckets(self):
        flat = [_rel("Q1", "Q2", "supports", "2019-05-01", ["a"]), _rel("Q1", "Q3", "opposes", "2019-06-01", ["b"])]
        buckets = adapters.year_relationships_to_buckets(flat)
        assert sorted(buckets) == ["opposes", "supports"]


class TestPersonalitiesAndProfile:
    def test_drops_people_without_relation_articles_and_ranks_by_coverage(self):
        bindings = [
            {"ent1": {"value": "http://www.wikidata.org/entity/Q1"}, "ent1_name": {"value": "Few"}},
            {"ent1": {"value": "http://www.wikidata.org/entity/Q2"}, "ent1_name": {"value": "Many"}},
            {"ent1": {"value": "http://www.wikidata.org/entity/Q3"}, "ent1_name": {"value": "None"}},
        ]
        out = adapters.personalities(bindings, {"Q1": 2, "Q2": 50, "Q3": 0}, {"Q2": {"wiki_id": "Q9", "name": "P"}})
        assert [(p["wiki_id"], p["party"]) for p in out] == [("Q2", {"wiki_id": "Q9", "name": "P"}), ("Q1", None)]

    def test_profile_ids_are_bare_q_ids(self):
        element = SimpleNamespace(wiki_id="http://www.wikidata.org/entity/Q21224349", label="XXI Governo")
        person = SimpleNamespace(wiki_id="Q1", name="X", parties=[], positions=[], governments=[element],
                                 assemblies=None, education=None, occupations=None)
        offices = [{"wiki_id": "Q2", "label": "Ministro", "start": "2019-10-26", "end": "2023-01-04",
                    "government": None, "term": None}]
        profile = adapters.personality(person, 3, offices)
        assert profile["governments"] == [{"wiki_id": "Q21224349", "label": "XXI Governo"}]
        assert profile["offices"] == offices and "positions" not in profile

    def test_within_is_inclusive_at_each_bounds_precision(self):
        assert adapters.within("2023-01-04", "2023-01-04", None)
        assert not adapters.within("2023-01-03", "2023-01-04", None)
        assert adapters.within("2023-12-31", None, "2023")
        assert not adapters.within("2024-01-01", None, "2023")
        assert adapters.within("2022-12-15", "2022-12", "2022-12")
        assert not adapters.within("2022-11-30", "2022-12", "2022-12")
        assert adapters.within("1999-05-05", None, None)

    def test_page(self):
        assert adapters.page(list(range(5)), limit=2, offset=3) == {"total": 5, "offset": 3, "items": [3, 4]}


class TestSearch:
    index = EntityIndex([
        Entity("Q610788", "António Costa", "person", 4533),
        Entity("Q10261183", "José Inácio da Costa Martins", "person", 1, ["Costa Martins"]),
        Entity("Q200941", "António Vitorino", "person", 88, ["Vitorino"]),
        Entity("Q847263", "PS - Partido Socialista", "party"),
    ])

    def test_normalize_strips_accents_case_and_spacing(self):
        assert normalize("  António   COSTA ") == "antonio costa"

    def test_whole_word_match_ranks_by_coverage_over_an_alias_prefix(self):
        assert [r["wiki_id"] for r in self.index.search("Costa")][:2] == ["Q610788", "Q10261183"]

    def test_accent_insensitive_exact_match_comes_first(self):
        assert self.index.search("antonio costa")[0]["wiki_id"] == "Q610788"

    def test_alias_match_is_reported(self):
        result = self.index.search("Vitorino")[0]
        assert result["wiki_id"] == "Q200941" and result["matched_alias"] == "Vitorino"

    def test_kind_filter_and_no_coverage_count_for_parties(self):
        results = self.index.search("socialista", kind="party")
        assert results == [{"wiki_id": "Q847263", "name": "PS - Partido Socialista", "kind": "party"}]
        assert self.index.search("socialista", kind="person") == []

    def test_blank_query_matches_nothing(self):
        assert self.index.search("   ") == []
