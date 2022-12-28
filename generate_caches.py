import json
from collections import defaultdict, OrderedDict
from pathlib import Path
from typing import Tuple, Set, Dict, Any, List

import requests
from nlp_extraction.utils.utils import just_sleep
from politiquices_api.config import static_data
from politiquices_api.sparql_queries import (
    get_all_parties_and_members_with_relationships,
    get_nr_relationships_as_subject,
    get_nr_relationships_as_target,
    get_persons_co_occurrences_counts,
    get_persons_wiki_id_name_image_url,
    get_total_nr_articles_for_each_person,
    get_wiki_id_affiliated_with_party,
)


def get_entities() -> Dict[str, Any]:
    """Get for each personality in the wikidata graph: name, image url, wikidata id, nr_articles"""

    all_wikidata_per = get_persons_wiki_id_name_image_url()
    per_articles = get_total_nr_articles_for_each_person()
    all_politiquices_per = defaultdict(dict)  # as of Python version 3.7, dictionaries are ordered
    for wiki_id, nr_articles in per_articles.items():
        all_politiquices_per[wiki_id]["nr_articles"] = nr_articles
        all_politiquices_per[wiki_id]["name"] = all_wikidata_per[wiki_id]["name"]
        # ToDo: rewrite image url here
        all_politiquices_per[wiki_id]["image_url"] = all_wikidata_per[wiki_id]["image_url"]

    return all_politiquices_per


def personalities_json_cache() -> Tuple[Set[str], Dict[str, Any]]:
    """
    Generates JSONs from SPARQL queries:
        'all_entities_info.json':  mapping from wiki_id -> {name, image_url, nr_articles}, sorted by nr_articles
        'persons.json':  a sorted list by name of tuples (person_name, wiki_id)

        'wiki_id_info.json' -> delete -> use all_entities_info.json
    """

    all_politiquices_per = get_entities()
    print(f"{len(all_politiquices_per)} personalities")
    with open(static_data + "all_entities_info.json", "w") as f_out:
        json.dump(all_politiquices_per, f_out, indent=4)

    # persons.json - cache for search box
    persons = [
        {"label": x[1]["name"], "value": x[0]}
        for x in sorted(all_politiquices_per.items(), key=lambda x: x[1]["name"])
    ]
    with open(static_data + "persons.json", "wt") as f_out:
        json.dump(persons, f_out, indent=True)

    return set([x["value"] for x in persons]), all_politiquices_per


def parties_json_cache(all_politiquices_persons):

    # rename parties names to include short-forms, nice to have in autocomplete
    parties_mapping = {
        "Bloco de Esquerda": "BE - Bloco de Esquerda",
        "Coliga\u00e7\u00e3o Democr\u00e1tica Unit\u00e1ria": "CDU - Coliga\u00e7\u00e3o Democr\u00e1tica Unit\u00e1ria (PCP-PEV)",
        "Juntos pelo Povo": "JPP - Juntos pelo Povo",
        "Partido Comunista Portugu\u00eas": "PCP - Partido Comunista Portugu\u00eas",
        "Partido Social Democrata": "PSD - Partido Social Democrata",
        "Partido Socialista": "PS - Partido Socialista",
        "Partido Socialista Revolucion\u00e1rio": "PSR - Partido Socialista Revolucion\u00e1rio",
        "Partido Democr\u00e1tico Republicano": "PDR - Partido Democr\u00e1tico Republicano",
        "Pessoas\u2013Animais\u2013Natureza": "PAN - Pessoas\u2013Animais\u2013Natureza",
        "Partido Comunista dos Trabalhadores Portugueses": "PCTP/MRPP - Partido Comunista dos Trabalhadores Portugueses",
        "RIR": "RIR - Reagir Incluir Reciclar",
        "Partido da Terra": "MPT - Partido da Terra",
    }

    # 'all_parties_info.json' - display in 'Partidos'
    parties_data = get_all_parties_and_members_with_relationships()
    sort_order = {"Portugal": 0, None: 3}
    parties_data.sort(key=lambda parties_data: sort_order.get(parties_data["country"], 2))
    print(f"{len(parties_data)} parties info (image + nr affiliated w/ relationships")
    with open(static_data + "all_parties_info.json", "w") as f_out:
        json.dump(parties_data, f_out, indent=4)

    # 'parties.json cache' - search box, filtering only for political parties from Portugal (Q45)
    parties = [
        {
            "name": parties_mapping.get(x["party_label"], x["party_label"]),
            "wiki_id": x["wiki_id"],
            "image_url": x["party_logo"],
        }
        for x in sorted(parties_data, key=lambda x: x["party_label"])
        # if x["country"] == "Portugal"
    ]
    with open(static_data + "parties.json", "w") as f_out:
        json.dump(parties, f_out, indent=4)

    # 'party_members.json' - shows members of each party, only those with at least 1 relationship
    party_members = defaultdict(list)
    for party in parties_data:
        # intersection between all wiki_id associated with a party and only those mention int rels
        wiki_ids = get_wiki_id_affiliated_with_party(party["wiki_id"])
        wiki_ids_in_politiquices = list(set(wiki_ids).intersection(all_politiquices_persons))
        party_members[party["wiki_id"]] = wiki_ids_in_politiquices
    with open(static_data + "party_members.json", "w") as f_out:
        json.dump(party_members, f_out, indent=4)


def entities_top_co_occurrences(wiki_id):
    raw_counts = get_persons_co_occurrences_counts()
    co_occurrences = []
    for x in raw_counts:
        co_occurrences.append(
            {
                "person_a": wiki_id[x["person_a"].split("/")[-1]],
                "person_b": wiki_id[x["person_b"].split("/")[-1]],
                "nr_occurrences": x["n_artigos"],
            }
        )
    with open(static_data + "top_co_occurrences.json", "w") as f_out:
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

    relationships = defaultdict(lambda: relationships_types())

    for entry in opposes_subj:
        relationships[entry[0]]["opposes"] += entry[1]

    for entry in supports_subj:
        relationships[entry[0]]["supports"] += entry[1]

    for entry in opposes_target:
        relationships[entry[0]]["is_opposed"] += entry[1]

    for entry in supports_target:
        relationships[entry[0]]["is_supported"] += entry[1]

    with open(static_data + "person_relationships_counts.json", "wt") as f_out:
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
                r = requests.get(url, allow_redirects=True, headers=headers)  # to get content after redirection
                if r.status_code == 200:
                    with open(f"{base_out}/{f_name}", "wb") as f_out:
                        f_out.write(r.content)
                else:
                    print("HTTP: ", r.status_code)
            except Exception as e:
                print(e, wiki_id)
            just_sleep(2)


def get_images():
    with open("json/all_entities_info.json") as f_in:
        wiki_id_info_all = json.load(f_in)
    save_images_from_url(wiki_id_info_all, base_out="images/personalities")

    with open("json/parties.json") as f_in:
        parties = json.load(f_in)
    transformed = {entry["wiki_id"]: {"image_url": entry["image_url"]} for entry in parties}
    save_images_from_url(transformed, base_out="images/parties")


def main():
    print("\nCaching and pre-computing static stuff from SPARQL engine :-)")

    # get all personalities cache
    all_politiquices_persons, wiki_id = personalities_json_cache()

    # parties cache
    parties_json_cache(all_politiquices_persons)

    # entities co-occurrences cache
    entities_top_co_occurrences(wiki_id)

    # unique number of relationships for each person
    persons_relationships_counts_by_type()

    # get images and resize them
    get_images()

    # ToDo: resize images automatically
    # mogrify -resize 250x250^ -gravity center -extent 250x250 *.*


if __name__ == "__main__":
    main()
