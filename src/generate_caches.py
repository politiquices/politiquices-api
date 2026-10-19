import json
from collections import defaultdict
from pathlib import Path
from random import randint
from time import sleep
from typing import Dict, Any

import requests
from requests import RequestException

from config import STATIC_DATA, NO_IMAGE, start_year, end_year
from sparql import (
    get_total_nr_of_articles,
    get_nr_articles_per_year,
    get_articles_by_source,
)
from sparql_queries_cache import (
    get_all_parties_and_members_with_relationships,
    get_persons_wiki_id_name_image_url,
    get_total_nr_articles_for_each_person,
    get_all_parties_images,
    get_all_persons_images,
)
from utils import get_chart_labels_min_max


def just_sleep(lower_bound=1, upper_bound=3, verbose=False):
    sec = randint(lower_bound, upper_bound)
    if verbose:
        print(f"sleeping for {sec} seconds")
    sleep(sec)


def get_entities() -> Dict[str, Any]:
    """Get for each personality in the wikidata graph: name, image url, wikidata id, nr_articles per rel_type"""

    all_wikidata_per = get_persons_wiki_id_name_image_url()
    per_articles = get_total_nr_articles_for_each_person()
    all_politiquices_per = defaultdict(dict)
    for wiki_id in all_wikidata_per.keys():  # pylint: disable=consider-using-dict-items, consider-iterating-dictionary
        rel_counts = per_articles.get(wiki_id, {})

        def nr_relationships(rel_type):
            return rel_counts.get(rel_type, {}).get("nr_relationships", 0)

        def nr_source_articles(rel_type):
            return rel_counts.get(rel_type, {}).get("nr_source_articles", 0)

        rel_types = (
            "ent1_supports_ent2", "ent2_supports_ent1", "ent1_opposes_ent2", "ent2_opposes_ent1",
            "other", "mutual_agreement", "mutual_opposition",
        )
        # `nr_articles` keeps meaning "relationships" here, unchanged from before this
        # personality/sort thresholds already trust it -- `nr_source_articles` is the
        # new, genuinely article-counting sibling, since a relationship can now be
        # backed by several near-duplicate source articles.
        all_politiquices_per[wiki_id]["nr_articles"] = sum(nr_relationships(rt) for rt in rel_types)
        all_politiquices_per[wiki_id]["nr_articles_by_type"] = {rt: nr_relationships(rt) for rt in rel_types}
        all_politiquices_per[wiki_id]["nr_source_articles"] = sum(nr_source_articles(rt) for rt in rel_types)
        all_politiquices_per[wiki_id]["nr_source_articles_by_type"] = {rt: nr_source_articles(rt) for rt in rel_types}
        all_politiquices_per[wiki_id]["name"] = all_wikidata_per[wiki_id]["name"]
        all_politiquices_per[wiki_id]["countries"] = all_wikidata_per[wiki_id]["countries"]
        original_url = all_wikidata_per[wiki_id]["image_url"]
        if original_url.startswith("http"):
            # every portrait is normalised to <wiki_id>.jpg by `make images`
            f_name = f"{wiki_id}.jpg"
            all_politiquices_per[wiki_id]["image_url"] = f"/assets/images/personalities_small/{f_name}"
        else:
            all_politiquices_per[wiki_id]["image_url"] = NO_IMAGE

    return {
        entry[0]: entry[1]
        for entry in sorted(all_politiquices_per.items(), key=lambda x: x[1]["nr_articles"], reverse=True)
    }


def personalities_json_cache() -> Dict[str, Any]:
    """
    Generates JSONs from SPARQL queries:
        'all_entities_info.json':  mapping from wiki_id -> {name, image_url, nr_articles}, sorted by nr_articles
        'persons.json':  a sorted list by name of tuples (person_name, wiki_id)
    """

    all_politiquices_per = get_entities()
    print(f"{len(all_politiquices_per)} personalities")
    with open(STATIC_DATA + "all_entities_info.json", "wt", encoding="utf8") as f_out:
        json.dump(all_politiquices_per, f_out, indent=4)

    # persons.json - person names sorted alphabetically
    persons = [
        {"label": x[1]["name"], "value": x[0]}
        for x in sorted(all_politiquices_per.items(), key=lambda x: x[1]["name"])
        if (x[1]["nr_articles"] - x[1]["nr_articles_by_type"]["other"]) > 0
    ]
    with open(STATIC_DATA + "persons.json", "wt", encoding="utf8") as f_out:
        json.dump(persons, f_out, indent=True)

    return all_politiquices_per


def parties_json_cache():
    # rename parties names to include short-forms, nice to have in autocomplete
    parties_mapping = {
        "Bloco de Esquerda": "BE - Bloco de Esquerda",
        "Coliga\u00e7\u00e3o Democr\u00e1tica Unit\u00e1ria": "CDU - Coliga\u00e7\u00e3o Democr\u00e1tica "
        "Unit\u00e1ria (PCP-PEV)",
        "Juntos pelo Povo": "JPP - Juntos pelo Povo",
        "Partido Comunista Portugu\u00eas": "PCP - Partido Comunista Portugu\u00eas",
        "Partido Social Democrata": "PSD - Partido Social Democrata",
        "Partido Socialista": "PS - Partido Socialista",
        "Partido Socialista Revolucion\u00e1rio": "PSR - Partido Socialista Revolucion\u00e1rio",
        "Partido Democr\u00e1tico Republicano": "PDR - Partido Democr\u00e1tico Republicano",
        "Pessoas\u2013Animais\u2013Natureza": "PAN - Pessoas\u2013Animais\u2013Natureza",
        "Partido Comunista dos Trabalhadores Portugueses": "PCTP/MRPP - Partido Comunista dos Trabalhadores "
        "Portugueses",
        "RIR": "RIR - Reagir Incluir Reciclar",
        "Partido da Terra": "MPT - Partido da Terra",
    }

    # 'all_parties_info.json'
    parties_data = get_all_parties_and_members_with_relationships()
    print(f"{len(parties_data)} parties")
    with open(STATIC_DATA + "all_parties_info.json", "wt", encoding="utf8") as f_out:
        json.dump(parties_data, f_out)

    # 'parties.json cache' - search box, filtering only for political parties from Portugal (Q45)
    parties = [
        {"label": parties_mapping.get(x["party_label"], x["party_label"]), "value": x["wiki_id"]}
        for x in sorted(parties_data, key=lambda x: x["party_label"])
        if "Portugal" in x["countries"]
    ]
    with open(STATIC_DATA + "parties.json", "wt", encoding="utf8") as f_out:
        json.dump(parties, f_out)

    return {x["wiki_id"] for x in parties_data}


def stats_json_cache():
    """
    Generates 'stats.json': the /stats, /stats/yearly and /stats/sources metric-card
    totals, per-year unique-article counts, and article-provenance/source-domain
    breakdown used by the Sobre page. These are as static as the personalities/parties
    caches -- they only change when the data pipeline runs again -- so they're
    precomputed here instead of hitting SPARQL on every request.
    """
    totals = get_total_nr_of_articles()

    all_years = get_chart_labels_min_max(min_date=start_year, max_date=end_year)
    articles_per_year = get_nr_articles_per_year()
    year_values = [
        {"year": year, "nr_articles": articles_per_year.get(int(year), 0)}
        for year in all_years
    ]
    sources = get_articles_by_source()

    stats = {
        "nr_all_articles": totals["articles"],
        "nr_all_relationships": totals["relationships"],
        "nr_all_articles_sentiment": totals["articles_sentiment"],
        "nr_all_relationships_sentiment": totals["relationships_sentiment"],
        "year_values": year_values,
        "provenance": sources["provenance"],
        "domains": sources["domains"],
    }
    with open(STATIC_DATA + "stats.json", "wt", encoding="utf8") as f_out:
        json.dump(stats, f_out, indent=4)

    return stats


def save_images_from_url(wiki_id_info: Dict[str, Any], base_out: str, max_retries: int = 5):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/39.0.2171.95 Safari/537.36"
    }
    valid = {k: v for k, v in wiki_id_info.items() if v["image_url"].startswith("http")}
    already = sum(
        1 for wiki_id, info in valid.items()
        if Path(f"{base_out}/{wiki_id}.{info['image_url'].split('.')[-1]}").exists()
    )
    print(f"  {already} already downloaded, {len(valid) - already} to download (of {len(valid)})")

    for wiki_id, info in wiki_id_info.items():
        if not info["image_url"].startswith("http"):
            continue
        url = info["image_url"]
        extension = url.split(".")[-1]
        f_name = f"{wiki_id}.{extension}"
        path = Path(f"{base_out}/{f_name}")
        if path.exists():
            continue

        print(f"{wiki_id}...downloading", end="", flush=True)
        for attempt in range(1, max_retries + 1):
            try:
                # to get content after redirection
                r = requests.get(url, allow_redirects=True, headers=headers, timeout=10)
                if r.status_code == 200:
                    Path(base_out).mkdir(parents=True, exist_ok=True)
                    with open(f"{base_out}/{f_name}", "wb") as f_out:
                        f_out.write(r.content)
                    print(" OK")
                    just_sleep(60, 70, verbose=True)
                    break
                elif r.status_code == 429:
                    retry_after = r.headers.get("Retry-After")
                    wait = int(retry_after) if retry_after and retry_after.isdigit() else 60 * attempt
                    server_hint = f"server suggests {retry_after}s" if retry_after else "no Retry-After header"
                    print(f"  HTTP 429 (attempt {attempt}/{max_retries}), {server_hint}, waiting {wait}s")
                    sleep(wait)
                else:
                    print(f"  HTTP {r.status_code}, skipping")
                    break
            except RequestException as e:
                print(f"  error: {e}, attempt {attempt}/{max_retries}")
                if attempt < max_retries:
                    just_sleep(10, 30, verbose=True)
        else:
            print(f"  gave up after {max_retries} attempts")


def get_images(party_wiki_ids: set):
    """Download images for all personalities and parties in the Wikidata sub-graph"""
    print("\nPersonalities")
    transformed = get_all_persons_images()
    save_images_from_url(transformed, base_out="assets/images/personalities")

    print("\nParties")
    transformed = get_all_parties_images(party_wiki_ids)
    save_images_from_url(transformed, base_out="assets/images/parties")


def main():
    print("Caching and pre-computing static information")
    personalities_json_cache()
    party_wiki_ids = parties_json_cache()
    stats_json_cache()
    get_images(party_wiki_ids)

    generated_files = [
        STATIC_DATA + "all_entities_info.json",
        STATIC_DATA + "persons.json",
        STATIC_DATA + "all_parties_info.json",
        STATIC_DATA + "parties.json",
        STATIC_DATA + "stats.json",
    ]
    print("\nGenerated files:")
    for path in generated_files:
        print(f"  {path}")


if __name__ == "__main__":
    main()
