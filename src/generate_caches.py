import json
from collections import defaultdict
from pathlib import Path
from typing import Dict, Any

import requests
from utils import just_sleep

from config import STATIC_DATA
from sparql import (
    get_all_parties_and_members_with_relationships,
    get_nr_relationships_as_subject,
    get_nr_relationships_as_target,
    get_persons_co_occurrences_counts,
    get_persons_wiki_id_name_image_url,
    get_total_nr_articles_for_each_person,
    get_all_parties_images,
    get_all_persons_images,
)


def get_entities() -> Dict[str, Any]:
    """Get for each personality in the wikidata graph: name, image url, wikidata id, nr_articles"""

    all_wikidata_per = get_persons_wiki_id_name_image_url()
    per_articles = get_total_nr_articles_for_each_person()
    all_politiquices_per = defaultdict(dict)
    for wiki_id in all_wikidata_per.keys():
        all_politiquices_per[wiki_id]["nr_articles"] = per_articles.get(wiki_id, 0)
        all_politiquices_per[wiki_id]["name"] = all_wikidata_per[wiki_id]["name"]
        f_name = f"{wiki_id}.{all_wikidata_per[wiki_id]['image_url'].split('.')[-1]}"
        all_politiquices_per[wiki_id]["image_url"] = f"/assets/images/personalities_small/{f_name}"

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
        if x[1]["nr_articles"] > 0
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
        if x["country"] == "Portugal"
    ]
    with open(STATIC_DATA + "parties.json", "wt", encoding="utf8") as f_out:
        json.dump(parties, f_out)


def entities_top_co_occurrences(all_politiquices_per):
    raw_counts = get_persons_co_occurrences_counts()
    co_occurrences = []
    for x in raw_counts:
        co_occurrences.append(
            {
                "person_a": all_politiquices_per[x["person_a"].split("/")[-1]],
                "person_b": all_politiquices_per[x["person_b"].split("/")[-1]],
                "nr_occurrences": x["n_artigos"],
            }
        )
    with open(STATIC_DATA + "top_co_occurrences.json", "wt", encoding="utf8") as f_out:
        json.dump(co_occurrences, f_out, indent=4)
    print(f"{len(co_occurrences)} entity co-occurrences")


def persons_relationships_counts_by_type():
    opposes_subj = get_nr_relationships_as_subject("opposes")
    supports_subj = get_nr_relationships_as_subject("supports")
    opposes_target = get_nr_relationships_as_target("opposes")
    supports_target = get_nr_relationships_as_target("supports")

    def relationships_types():
        return {
            "opposes": 0,
            "supports": 0,
            "is_opposed": 0,
            "is_supported": 0,
        }

    relationships = defaultdict(relationships_types)

    for entry in opposes_subj:
        relationships[entry[0]]["opposes"] += entry[1]

    for entry in supports_subj:
        relationships[entry[0]]["supports"] += entry[1]

    for entry in opposes_target:
        relationships[entry[0]]["is_opposed"] += entry[1]

    for entry in supports_target:
        relationships[entry[0]]["is_supported"] += entry[1]

    with open(STATIC_DATA + "person_relationships_counts.json", "wt", encoding="utf8") as f_out:
        json.dump(relationships, f_out, indent=True)


def save_images_from_url(wiki_id_info: Dict[str, Any], base_out: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/39.0.2171.95 Safari/537.36"
    }
    for wiki_id, info in wiki_id_info.items():
        if not info["image_url"].startswith("http"):
            continue
        url = info["image_url"]
        print(wiki_id, end="...")
        extension = url.split(".")[-1]
        f_name = f"{wiki_id}.{extension}"
        path = Path(f"{base_out}/{f_name}")
        if path.exists():
            print("skipping")
        else:
            print("downloading")
            try:
                # to get content after redirection
                r = requests.get(url, allow_redirects=True, headers=headers, timeout=10)
                if r.status_code == 200:
                    with open(f"{base_out}/{f_name}", "wb") as f_out:
                        f_out.write(r.content)
                else:
                    print("HTTP: ", r.status_code)
            except Exception as e:
                print(e, wiki_id)
            just_sleep(2)


def get_images():
    """Download images for all personalities and parties in the Wikidata sub-graph"""
    print("\nPersonalities")
    transformed = get_all_persons_images()
    save_images_from_url(transformed, base_out="assets/images/personalities")

    print("\nParties")
    transformed = get_all_parties_images()
    save_images_from_url(transformed, base_out="assets/images/parties")


def main():
    print("\nCaching and pre-computing static information")
    all_politiquices_per = personalities_json_cache()
    parties_json_cache()
    entities_top_co_occurrences(all_politiquices_per)
    persons_relationships_counts_by_type()
    get_images()


if __name__ == "__main__":
    main()
