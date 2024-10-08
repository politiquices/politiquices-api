import sys
from collections import defaultdict
from functools import lru_cache
from typing import List

from SPARQLWrapper import SPARQLWrapper, JSON
from cache import all_entities_info
from config import NO_IMAGE, politiquices_endpoint, PS_LOGO, wikidata_endpoint, LANG
from data_models import Element, Person, PoliticalParty
from utils import make_https, _process_rel_type

from sparql_prefixes import PREFIXES


# Statistics
def get_nr_articles_per_year():
    query = """
        SELECT ?year (COUNT(?arquivo_doc) AS ?nr_articles)
        WHERE {
          ?x politiquices:url ?arquivo_doc .
          ?arquivo_doc dc:date ?date .
        }
        GROUP BY (YEAR(?date) AS ?year)
        ORDER BY ?year
        """
    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    nr_articles = {}
    for x in result["results"]["bindings"]:
        nr_articles[int(x["year"]["value"])] = int(x["nr_articles"]["value"])
    return nr_articles


def get_total_nr_of_articles():
    query = """
        SELECT (COUNT(?x) as ?nr_articles) WHERE {
            ?x politiquices:url ?y .
        }
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    all_articles = results["results"]["bindings"][0]["nr_articles"]["value"]

    query = """
        SELECT (COUNT(?rel) as ?nr_articles) WHERE {
            VALUES ?rel_values {'ent1_opposes_ent2' 'ent2_opposes_ent1'
                                'ent1_supports_ent2' 'ent2_supports_ent1'} .
            ?rel politiquices:type ?rel_values .
            ?rel politiquices:url ?url .
        }
    """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    no_other_articles = results["results"]["bindings"][0]["nr_articles"]["value"]

    return all_articles, no_other_articles


def get_nr_of_persons() -> int:
    """
    persons only with 'ent1_other_ent2' and 'ent2_other_ent1' relationships are not considered
    """
    query = """
        SELECT (COUNT(DISTINCT ?person) as ?nr_persons) {
            ?person wdt:P31 wd:Q5;
            {?rel politiquices:ent1 ?person} UNION {?rel politiquices:ent2 ?person} .
            ?rel politiquices:type ?rel_type FILTER(!REGEX(?rel_type,"other") ) .
        }
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    return results["results"]["bindings"][0]["nr_persons"]["value"]


def get_total_articles_by_year_by_relationship_type():
    query = """
        SELECT ?year ?rel_type (COUNT(?rel_type) AS ?nr_articles)
        WHERE {
            ?x politiquices:url ?arquivo_doc .
            ?x politiquices:type ?rel_type .
            ?arquivo_doc dc:date ?date .
        }
        GROUP BY (YEAR(?date) AS ?year) ?rel_type
        ORDER BY ?year
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")

    def rels_values():
        return {
            "ent1_opposes_ent2": 0,
            "ent2_opposes_ent1": 0,
            "ent1_supports_ent2": 0,
            "ent2_supports_ent1": 0,
            "ent1_other_ent2": 0,
            "ent2_other_ent1": 0,
        }

    values = defaultdict(rels_values)
    for x in results["results"]["bindings"]:
        values[x["year"]["value"]][x["rel_type"]["value"]] = x["nr_articles"]["value"]

    return values


def get_persons_articles_freq():
    query = """
        SELECT DISTINCT ?person (COUNT (?url) as ?n_artigos)
        WHERE {
            VALUES ?rel_values {'ent1_opposes_ent2' 'ent2_opposes_ent1'
                                'ent1_supports_ent2' 'ent2_supports_ent1'} .

            ?rel politiquices:type ?rel_values .
            { ?rel politiquices:ent1 ?person .} UNION { ?rel politiquices:ent2 ?person . }
            ?rel politiquices:url ?url .
            ?rel politiquices:type ?rel_type .
        }
        GROUP BY ?person
        HAVING (?n_artigos > 0)
        ORDER BY DESC(?n_artigos)
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    top_freq = []
    for x in results["results"]["bindings"]:
        try:
            top_freq.append(
                {
                    "person": all_entities_info[x["person"]["value"].split("/")[-1]]["name"],
                    "freq": x["n_artigos"]["value"],
                }
            )
        except KeyError:
            print("KeyError: ", x["person"]["value"].split("/")[-1])

    return top_freq


# Political Parties
def get_wiki_id_affiliated_with_party(political_party: str):
    query = f"""
        SELECT DISTINCT ?wiki_id {{
            ?wiki_id wdt:P102 wd:{political_party}; .
        }}
    """
    results = query_sparql(PREFIXES + "\n" + query, "wikidata")
    return [x["wiki_id"]["value"].split("/")[-1] for x in results["results"]["bindings"]]


# Personality Information
def get_person_info(wiki_id):
    query = f"""
        SELECT ?name ?image_url ?political_party_logo ?political_party ?political_party_label
        WHERE {{
            wd:{wiki_id} rdfs:label ?name
            FILTER(LANG(?name)="{LANG}") .
            OPTIONAL {{ wd:{wiki_id} wdt:P18 ?image_url. }}
            OPTIONAL {{
                wd:{wiki_id} p:P102 ?political_partyStmnt.
                ?political_partyStmnt ps:P102 ?political_party.
                ?political_party rdfs:label ?political_party_label
                    FILTER(LANG(?political_party_label)="{LANG}").
                OPTIONAL {{ ?political_party wdt:P154 ?political_party_logo. }}
            }}
        }}
    """
    results = query_sparql(PREFIXES + "\n" + query, "wikidata")

    name = None
    image_url = None
    parties = []
    for e in results["results"]["bindings"]:
        if not name:
            name = e["name"]["value"]
        if not image_url:
            image_url = e["image_url"]["value"] if "image_url" in e else NO_IMAGE
        if "political_party" in e:
            party_image_url = NO_IMAGE

            # add 'PS' logo since it's not on Wikidata
            if e["political_party"]["value"] == "http://www.wikidata.org/entity/Q847263":
                party_image_url = PS_LOGO

            party = PoliticalParty(
                wiki_id=e["political_party"]["value"].split("/")[-1],
                name=e["political_party_label"]["value"],
                image_url=make_https(e["political_party_logo"]["value"])
                if "political_party_logo" in e
                and e["political_party"]["value"] != "http://www.wikidata.org/entity/Q847263"
                else party_image_url,
            )
            if party not in parties:
                parties.append(party)

    results = get_person_detailed_info(wiki_id)

    return Person(
        wiki_id=wiki_id,
        name=name,
        image_url=image_url,
        parties=parties,
        positions=results["position"],
        education=results["education"],
        occupations=results["occupation"],
        governments=results["government"],
        assemblies=results["assembly"],
    )


def get_person_detailed_info(wiki_id):
    occupation_query = f"""
        SELECT DISTINCT ?occupation ?occupation_label
        WHERE {{
          wd:{wiki_id} p:P106 ?occupationStmnt .
          ?occupationStmnt ps:P106 ?occupation .
          ?occupation rdfs:label ?occupation_label FILTER(LANG(?occupation_label) = "{LANG}").
        }}
        """

    education_query = f"""
        SELECT DISTINCT ?educatedAt ?educatedAt_label
        WHERE {{
            wd:{wiki_id} p:P69 ?educatedAtStmnt .
            ?educatedAtStmnt ps:P69 ?educatedAt .
            ?educatedAt rdfs:label ?educatedAt_label FILTER(LANG(?educatedAt_label) = "{LANG}").
            }}
        """

    positions_query = f"""
        SELECT DISTINCT ?position ?position_label
        WHERE {{
            wd:{wiki_id} p:P39 ?positionStmnt .
            ?positionStmnt ps:P39 ?position .
             ?position rdfs:label ?position_label FILTER(LANG(?position_label) = "{LANG}").
        }}
        """

    governments_query = f"""
        SELECT DISTINCT ?government ?government_label
        WHERE {{
            wd:{wiki_id} p:P39 ?positionStmnt .
            ?positionStmnt pq:P5054 ?government .
            ?government rdfs:label ?government_label . FILTER(LANG(?government_label) = "{LANG}") .
        }}"""

    assemblies_query = f"""
        SELECT DISTINCT ?parliamentary_term ?parliamentary_term_label
        WHERE {{
            wd:{wiki_id} p:P39 ?positionStmnt .
            ?positionStmnt pq:P2937 ?parliamentary_term.
            ?parliamentary_term rdfs:label ?parliamentary_term_label . FILTER(LANG(?parliamentary_term_label) = "{LANG}").
        }}"""

    results = query_sparql(PREFIXES + "\n" + occupation_query, "wikidata")
    occupations = []
    for x in results["results"]["bindings"]:
        if x["occupation_label"]["value"] == "político":
            continue
        occupations.append(Element(x["occupation"]["value"], x["occupation_label"]["value"]))

    results = query_sparql(PREFIXES + "\n" + education_query, "wikidata")
    education = [
        Element(x["educatedAt"]["value"], x["educatedAt_label"]["value"]) for x in results["results"]["bindings"]
    ]

    results = query_sparql(PREFIXES + "\n" + positions_query, "wikidata")
    positions = [Element(x["position"]["value"], x["position_label"]["value"]) for x in results["results"]["bindings"]]

    results = query_sparql(PREFIXES + "\n" + governments_query, "wikidata")
    governments = [
        Element(x["government"]["value"], x["government_label"]["value"]) for x in results["results"]["bindings"]
    ]

    results = query_sparql(PREFIXES + "\n" + assemblies_query, "wikidata")

    assemblies = [
        Element(x["parliamentary_term"]["value"], x["parliamentary_term_label"]["value"])
        for x in results["results"]["bindings"]
    ]

    return {
        "education": education,
        "occupation": occupations,
        "position": positions,
        "government": governments,
        "assembly": assemblies,
    }


# Person relationships
def get_person_relationships(wiki_id):
    # pylint: disable=too-many-branches, too-many-statements
    query = f"""
        SELECT DISTINCT ?arquivo_doc ?date ?creator ?publisher ?title ?description ?rel_type ?ent1 ?ent1_str ?ent2 ?ent2_str
        WHERE {{
         {{ ?rel politiquices:ent1 wd:{wiki_id} }} UNION {{?rel politiquices:ent2 wd:{wiki_id} }}

            ?rel politiquices:type ?rel_type.

             ?rel politiquices:ent1 ?ent1 ;
                  politiquices:ent2 ?ent2 ;
                  politiquices:ent1_str ?ent1_str ;
                  politiquices:ent2_str ?ent2_str ;
                  politiquices:url ?arquivo_doc .

              ?arquivo_doc dc:title ?title ;
                           dc:description ?description;
                           dc:creator ?creator;
                           dc:publisher ?publisher;
                           dc:date  ?date .
        }}
        ORDER BY ASC(?date)
        """

    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    relations = defaultdict(list)

    # ToDo: refactor to a function
    for e in results["results"]["bindings"]:
        ent1_wiki = e["ent1"]["value"].split("/")[-1].strip()
        ent2_wiki = e["ent2"]["value"].split("/")[-1].strip()

        if e["rel_type"]["value"] == "ent1_supports_ent2":
            if wiki_id == ent1_wiki:
                rel_type = "supports"
                other_ent_url = ent2_wiki
                other_ent_name = e["ent2_str"]["value"].split("/")[-1]
                focus_ent = e["ent1_str"]["value"].split("/")[-1]

            elif wiki_id == ent2_wiki:
                rel_type = "supported_by"
                other_ent_url = ent1_wiki
                other_ent_name = e["ent1_str"]["value"].split("/")[-1]
                focus_ent = e["ent2_str"]["value"].split("/")[-1]

        elif e["rel_type"]["value"] == "ent1_opposes_ent2":
            if wiki_id == ent1_wiki:
                rel_type = "opposes"
                other_ent_url = ent2_wiki
                other_ent_name = e["ent2_str"]["value"].split("/")[-1]
                focus_ent = e["ent1_str"]["value"].split("/")[-1]

            elif wiki_id == ent2_wiki:
                rel_type = "opposed_by"
                other_ent_url = ent1_wiki
                other_ent_name = e["ent1_str"]["value"].split("/")[-1]
                focus_ent = e["ent2_str"]["value"].split("/")[-1]

        elif e["rel_type"]["value"] == "ent2_supports_ent1":
            if wiki_id == ent2_wiki:
                rel_type = "supports"
                other_ent_url = ent1_wiki
                other_ent_name = e["ent1_str"]["value"].split("/")[-1]
                focus_ent = e["ent2_str"]["value"].split("/")[-1]

            elif wiki_id == ent1_wiki:
                rel_type = "supported_by"
                other_ent_url = ent2_wiki
                other_ent_name = e["ent2_str"]["value"].split("/")[-1]
                focus_ent = e["ent1_str"]["value"].split("/")[-1]

        elif e["rel_type"]["value"] == "ent2_opposes_ent1":
            if wiki_id == ent2_wiki:
                rel_type = "opposes"
                other_ent_url = ent1_wiki
                other_ent_name = e["ent1_str"]["value"].split("/")[-1]
                focus_ent = e["ent2_str"]["value"].split("/")[-1]

            elif wiki_id == ent1_wiki:
                rel_type = "opposed_by"
                other_ent_url = ent2_wiki
                other_ent_name = e["ent2_str"]["value"].split("/")[-1]
                focus_ent = e["ent1_str"]["value"].split("/")[-1]

        elif e["rel_type"]["value"] == "other":
            if wiki_id == ent1_wiki:
                rel_type = "other"
                other_ent_url = ent2_wiki
                other_ent_name = e["ent2_str"]["value"].split("/")[-1]
                focus_ent = e["ent1_str"]["value"].split("/")[-1]

            elif wiki_id == ent2_wiki:
                rel_type = "other_by"
                other_ent_url = ent1_wiki
                other_ent_name = e["ent1_str"]["value"].split("/")[-1]
                focus_ent = e["ent2_str"]["value"].split("/")[-1]

        elif e["rel_type"]["value"] == "mutual_agreement":
            print("mutual_agreement")
            if wiki_id == ent1_wiki:
                rel_type = "mutual_agreement"
                other_ent_url = ent2_wiki
                other_ent_name = e["ent2_str"]["value"].split("/")[-1]
                focus_ent = e["ent1_str"]["value"].split("/")[-1]

        elif e["rel_type"]["value"] == "mutual_opposition":
            print("mutual_opposition")
            if wiki_id == ent1_wiki:
                rel_type = "mutual_agreement"
                other_ent_url = ent2_wiki
                other_ent_name = e["ent2_str"]["value"].split("/")[-1]
                focus_ent = e["ent1_str"]["value"].split("/")[-1]

        else:
            print("unknown rel_type:", e)
            # raise Exception(e["rel_type"]["value"] + " not known")

        try:
            relations[rel_type].append(
                {
                    "arquivo_doc": e["arquivo_doc"]["value"],
                    "title": e["title"]["value"],
                    "domain": e["creator"]["value"],
                    "original_url": e["publisher"]["value"],
                    "paragraph": e["description"]["value"],
                    "date": e["date"]["value"].split("T")[0],
                    "ent1_id": wiki_id,
                    "ent1_img": all_entities_info[wiki_id]["image_url"],
                    "ent1_str": focus_ent,
                    "ent2_id": other_ent_url,
                    "ent2_img": all_entities_info[other_ent_url]["image_url"],
                    "ent2_str": other_ent_name,
                    "rel_type": rel_type,
                }
            )
        except KeyError as error:
            print("KeyError:", error)
            continue

    all_relationships = []
    sentiment_only = []
    for rel_type in relations.keys():  # pylint: disable=consider-using-dict-items
        all_relationships.extend(relations[rel_type])
        if rel_type in {"opposes", "supports"}:
            sentiment_only.extend(relations[rel_type])

    relations["all"] = sorted(all_relationships, key=lambda x: x["date"], reverse=True)
    relations["sentiment"] = sorted(sentiment_only, key=lambda x: x["date"], reverse=True)

    return relations


def get_top_relationships(wiki_id, top_n=3):
    # get all the relationships where the person acts as subject, i.e: opposes and supports
    query = f"""
        SELECT ?rel_type ?ent2
        WHERE {{
          {{
            ?rel politiquices:ent1 wd:{wiki_id};
                 politiquices:ent2 ?ent2;
                 politiquices:type ?rel_type.
                 FILTER(REGEX((?rel_type), "^ent1_opposes|ent1_supports"))
          }}
          UNION
          {{
            ?rel politiquices:ent2 wd:{wiki_id};
                 politiquices:ent1 ?ent2;
                 politiquices:type ?rel_type.
                 FILTER(REGEX((?rel_type), "^ent2_opposes|ent2_supports"))
          }}
        }}
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    person_as_subject = defaultdict(lambda: defaultdict(int))
    for x in results["results"]["bindings"]:
        other_person = x["ent2"]["value"].split("/")[-1]
        if "opposes" in x["rel_type"]["value"]:
            person_as_subject["who_person_opposes"][other_person] += 1
        if "supports" in x["rel_type"]["value"]:
            person_as_subject["who_person_supports"][other_person] += 1

    # get all the relationships where the person acts as target, i.e.: is opposed/supported by
    query = f"""
        SELECT ?rel_type ?ent2
        WHERE {{
          {{
            ?rel politiquices:ent1 wd:{wiki_id};
                 politiquices:ent2 ?ent2;
                 politiquices:type ?rel_type.
                 FILTER(REGEX((?rel_type), "^ent2_opposes|ent2_supports"))
          }}
          UNION
          {{
            ?rel politiquices:ent2 wd:{wiki_id};
                 politiquices:ent1 ?ent2;
                 politiquices:type ?rel_type.
                 FILTER(REGEX((?rel_type), "^ent1_opposes|ent1_supports"))
          }}
        }}
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    person_as_target = defaultdict(lambda: defaultdict(int))
    for x in results["results"]["bindings"]:
        other_person = x["ent2"]["value"].split("/")[-1]
        if "opposes" in x["rel_type"]["value"]:
            person_as_target["who_opposes_person"][other_person] += 1
        if "supports" in x["rel_type"]["value"]:
            person_as_target["who_supports_person"][other_person] += 1

    total = sum(person_as_subject["who_person_opposes"].values())
    who_person_opposes = [
        {
            "wiki_id": k,
            "name": all_entities_info[k]["name"],
            "image_url": all_entities_info[k]["image_url"],
            "freq": v,
            "relative": str(round(v / total * 100, 2)) + "%",
        }
        for k, v in person_as_subject["who_person_opposes"].items()
    ]

    total = sum(person_as_subject["who_person_supports"].values())
    who_person_supports = [
        {
            "wiki_id": k,
            "name": all_entities_info[k]["name"],
            "image_url": all_entities_info[k]["image_url"],
            "freq": v,
            "relative": str(round(v / total * 100, 2)) + "%",
        }
        for k, v in person_as_subject["who_person_supports"].items()
    ]

    total = sum(person_as_target["who_opposes_person"].values())
    who_opposes_person = [
        {
            "wiki_id": k,
            "name": all_entities_info[k]["name"],
            "image_url": all_entities_info[k]["image_url"],
            "freq": v,
            "relative": str(round(v / total * 100, 2)) + "%",
        }
        for k, v in person_as_target["who_opposes_person"].items()
    ]

    total = sum(person_as_target["who_supports_person"].values())
    who_supports_person = [
        {
            "wiki_id": k,
            "name": all_entities_info[k]["name"],
            "image_url": all_entities_info[k]["image_url"],
            "freq": v,
            "relative": str(round(v / total * 100, 2)) + "%",
        }
        for k, v in person_as_target["who_supports_person"].items()
    ]

    # see PEP448: https://peps.python.org/pep-0448/
    return {
        "who_person_opposes": who_person_opposes[0:top_n],
        "who_person_supports": who_person_supports[0:top_n],
        "who_opposes_person": who_opposes_person[0:top_n],
        "who_supports_person": who_supports_person[0:top_n],
    }


def get_person_relationships_by_year(wiki_id, rel_type, ent="ent1"):
    query = f"""
        SELECT DISTINCT ?year (COUNT(?arquivo_doc) as ?nr_articles)
        WHERE {{

              ?rel politiquices:{ent} wd:{wiki_id} .
              ?rel politiquices:type ?rel_type .

              FILTER (?rel_type = "{rel_type}")

              ?rel politiquices:ent1 ?ent1 ;
                   politiquices:ent2 ?ent2 ;
                   politiquices:ent1_str ?ent1_str ;
                   politiquices:ent2_str ?ent2_str ;
                   politiquices:url ?arquivo_doc .

              ?arquivo_doc dc:title ?title ;
                           dc:date  ?date .
        }}
    GROUP BY (YEAR(?date) AS ?year)
    ORDER BY ?year
    """
    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    # dicts are insertion ordered
    year_articles = {}
    for x in result["results"]["bindings"]:
        year = x["year"]["value"]
        year_articles[str(year)] = int(x["nr_articles"]["value"])

    return year_articles


# relationship queries
@lru_cache(maxsize=50)
def get_relationship_between_two_persons(wiki_id_one, wiki_id_two, rel_type, start_year, end_year):

    rel_type, rel_type_inverted = _process_rel_type(rel_type)

    query = f"""
        SELECT DISTINCT ?arquivo_doc ?creator ?publisher ?date ?title ?description ?rel_type ?ent1 ?ent1_str ?ent2 ?ent2_str
        WHERE {{
            {{
              ?rel politiquices:ent1 wd:{wiki_id_one};
                   politiquices:ent2 wd:{wiki_id_two};
                   politiquices:url ?arquivo_doc;
                   politiquices:ent1 ?ent1;
                   politiquices:ent2 ?ent2;
                   politiquices:ent1_str ?ent1_str;
                   politiquices:ent2_str ?ent2_str;
                   politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type}')

              ?arquivo_doc dc:title ?title ;
                           dc:description ?description;
                           dc:creator ?creator;
                           dc:publisher ?publisher;
                           dc:date ?date . FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
           }}
           UNION
           {{
              ?rel politiquices:ent2 wd:{wiki_id_one};
                   politiquices:ent1 wd:{wiki_id_two};
                   politiquices:url ?arquivo_doc;
                   politiquices:ent1 ?ent1;
                   politiquices:ent2 ?ent2;
                   politiquices:ent1_str ?ent1_str;
                   politiquices:ent2_str ?ent2_str;
                   politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type_inverted}')

              ?arquivo_doc dc:title ?title;
                           dc:description ?description;              
                           dc:creator ?creator;
                           dc:publisher ?publisher;
                           dc:date ?date . FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})

           }}
        }}
        ORDER BY ASC(?date)
        """

    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    results = []
    for x in result["results"]["bindings"]:
        results.append(
            {
                "arquivo_doc": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "domain": x["creator"]["value"],
                "original_url": x["publisher"]["value"],
                "paragraph": x["description"]["value"],
                "rel_type": x["rel_type"]["value"],
                "ent1_id": wiki_id_one,
                "ent1_str": x["ent1_str"]["value"],
                "ent2_id": wiki_id_two,
                "ent2_str": x["ent2_str"]["value"],
                "ent1_img": all_entities_info[wiki_id_one]["image_url"],
                "ent2_img": all_entities_info[wiki_id_two]["image_url"],
            }
        )

    return results


@lru_cache(maxsize=50)
def get_relationship_between_party_and_person(party, person, rel_type, start_year, end_year):
    rel_type, rel_type_inverted = _process_rel_type(rel_type)

    query = f"""
        SELECT DISTINCT ?ent1 ?ent1_str ?ent2 ?ent2_str ?rel_type ?arquivo_doc ?date ?title ?description ?creator ?publisher
        WHERE {{
            {{
                ?rel politiquices:ent1 ?ent1;
                     politiquices:ent2 ?ent2 . FILTER(?ent2=wd:{person})
                ?rel politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;
                     politiquices:url ?arquivo_doc;
                     politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type}')
                ?arquivo_doc dc:title ?title;
                             dc:description ?description; 
                             dc:creator ?creator;
                             dc:publisher ?publisher;
                             dc:date ?date. FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
             }}
                UNION
            {{
                ?rel politiquices:ent2 ?ent1;
                     politiquices:ent1 ?ent2 . FILTER(?ent2=wd:{person})
                ?rel politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;
                     politiquices:url ?arquivo_doc;
                     politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type_inverted}')

                ?arquivo_doc dc:title ?title;
                             dc:description ?description;                
                             dc:creator ?creator;
                             dc:publisher ?publisher;
                             dc:date ?date. FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})

             }}

            SERVICE <{wikidata_endpoint}> {{
                ?ent1 wdt:P102 wd:{party};
                      rdfs:label ?personLabel.
                FILTER(LANG(?personLabel) = "{LANG}")
            }}
        }}
        ORDER BY DESC(?date)
        """

    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    results = []
    for x in result["results"]["bindings"]:
        results.append(
            {
                "arquivo_doc": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "domain": x["creator"]["value"],
                "original_url": x["publisher"]["value"],
                "paragraph": x["description"]["value"],
                "rel_type": x["rel_type"]["value"],
                "ent1_id": x["ent1"]["value"].split("/")[-1],
                "ent1_str": x["ent1_str"]["value"],
                "ent2_id": x["ent2"]["value"].split("/")[-1],
                "ent2_str": x["ent2_str"]["value"],
                "ent1_img": all_entities_info[x["ent1"]["value"].split("/")[-1]]["image_url"],
                "ent2_img": all_entities_info[x["ent2"]["value"].split("/")[-1]]["image_url"],
            }
        )

    return results


@lru_cache(maxsize=50)
def get_relationship_between_person_and_party(person, party, relation, start_year, end_year):
    rel_type, rel_type_inverted = _process_rel_type(relation)

    query = f"""
        SELECT DISTINCT ?ent1 ?ent2 ?ent2_str ?ent1_str ?rel_type ?arquivo_doc ?date ?title ?description ?creator ?publisher
        WHERE {{
            {{
                ?rel politiquices:ent2 ?ent2;
                     politiquices:ent1 ?ent1 . FILTER(?ent1=wd:{person})
                ?rel politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;
                     politiquices:url ?arquivo_doc;
                     politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type}')
                ?arquivo_doc dc:title ?title;
                             dc:description ?description;
                             dc:creator ?creator;
                             dc:publisher ?publisher;
                             dc:date ?date; FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
            }}
              UNION
            {{
                ?rel politiquices:ent1 ?ent2;
                     politiquices:ent2 ?ent1 . FILTER(?ent1=wd:{person})
                ?rel politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;
                     politiquices:url ?arquivo_doc;
                     politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type_inverted}')
                ?arquivo_doc dc:title ?title;
                             dc:description ?description;
                             dc:creator ?creator;
                             dc:publisher ?publisher;
                             dc:date ?date; FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
            }}

            SERVICE <{wikidata_endpoint}> {{
                ?ent2 wdt:P102 wd:{party};
                      rdfs:label ?personLabel. FILTER(LANG(?personLabel) = "{LANG}")
            }}
        }}
        ORDER BY DESC(?date)
        """

    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    results = []
    for x in result["results"]["bindings"]:
        results.append(
            {
                "arquivo_doc": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "domain": x["creator"]["value"],
                "original_url": x["publisher"]["value"],
                "paragraph": x["description"]["value"],
                "rel_type": x["rel_type"]["value"],
                "ent1_id": x["ent1"]["value"].split("/")[-1],
                "ent1_str": x["ent1_str"]["value"],
                "ent2_id": x["ent2"]["value"].split("/")[-1],
                "ent2_str": x["ent2_str"]["value"],
                "ent1_img": all_entities_info[x["ent1"]["value"].split("/")[-1]]["image_url"],
                "ent2_img": all_entities_info[x["ent2"]["value"].split("/")[-1]]["image_url"],
            }
        )

    return results


@lru_cache(maxsize=50)
def get_relationship_between_parties(per_party_a, per_party_b, relation, start_year, end_year):
    rel_type, rel_type_inverted = _process_rel_type(relation)

    query = f"""
    SELECT DISTINCT ?person_party_a ?ent1_str ?person_party_b ?ent2_str ?arquivo_doc ?date ?title ?description ?rel_type
    WHERE {{
      {{
        VALUES ?person_party_a {{ {per_party_a} }}
        VALUES ?person_party_b {{ {per_party_b} }}
      }}

      {{ ?rel politiquices:ent1 ?person_party_a;
              politiquices:ent2 ?person_party_b;
              politiquices:ent1_str ?ent1_str;
              politiquices:ent2_str ?ent2_str;
              {{
                SELECT ?rel ?rel_type ?arquivo_doc ?title ?description ?date
                WHERE {{
                     ?rel politiquices:url ?arquivo_doc;
                          politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type}')

                      ?arquivo_doc dc:title ?title;
                                   dc:description ?description;                      
                                   dc:date ?date;
                                   FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
                }}
             }}
      }}

      UNION

      {{ ?rel politiquices:ent1 ?person_party_b;
              politiquices:ent2 ?person_party_a;
              politiquices:ent1_str ?ent1_str;
              politiquices:ent2_str ?ent2_str;
              {{
                SELECT ?rel ?rel_type ?arquivo_doc ?title ?description ?date
                WHERE {{
                      ?rel politiquices:url ?arquivo_doc;
                           politiquices:type ?rel_type. FILTER REGEX(?rel_type, '{rel_type_inverted}')

                      ?arquivo_doc dc:title ?title;
                                   dc:description ?description;                      
                                   dc:date ?date;
                                   FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
                }}
              }}
      }}
    }}
    """

    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    relationships = []
    for x in result["results"]["bindings"]:
        relationships.append(
            {
                "arquivo_doc": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "paragraph": x["description"]["value"],
                "rel_type": x["rel_type"]["value"],
                "ent1_id": x["person_party_a"]["value"].split("/")[-1],
                "ent1_str": x["ent1_str"]["value"],
                "ent2_id": x["person_party_b"]["value"].split("/")[-1],
                "ent2_str": x["ent2_str"]["value"],
                "ent1_img": all_entities_info[x["person_party_a"]["value"].split("/")[-1]]["image_url"],
                "ent2_img": all_entities_info[x["person_party_b"]["value"].split("/")[-1]]["image_url"],
            }
        )

    return relationships


def get_timeline_personalities(wiki_ids: List[str], only_among_selected: bool, only_sentiment: bool, start_year: str, end_year: str):
    values = " ".join(["wd:" + wiki_id for wiki_id in wiki_ids])

    query = f"""
        PREFIX politiquices: <http://www.politiquices.pt/>
        PREFIX      rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX        dc: <http://purl.org/dc/elements/1.1/>
        PREFIX       ns1: <http://xmlns.com/foaf/0.1/>
        PREFIX       ns2: <http://www.w3.org/2004/02/skos/core#>
        PREFIX        wd: <http://www.wikidata.org/entity/>
        PREFIX       wdt: <http://www.wikidata.org/prop/direct/>

        SELECT DISTINCT ?arquivo_doc ?creator ?date ?publisher ?title ?description ?rel_type ?ent1 ?ent1_str ?ent2 ?ent2_str
        WHERE {{
                VALUES ?person_one {{{values}}}
                VALUES ?person_two {{{values}}}
                {{
                    {{ ?rel politiquices:ent1 ?person_one .}} UNION {{ ?rel politiquices:ent2 ?person_two .}}
                       ?rel politiquices:ent1 ?ent1;
                            politiquices:ent2 ?ent2;
                            politiquices:ent1_str ?ent1_str;
                            politiquices:ent2_str ?ent2_str;
                            politiquices:url ?arquivo_doc;
                            politiquices:type ?rel_type.

                  ?arquivo_doc dc:title ?title ;
                           dc:description ?description;
                           dc:creator ?creator;
                           dc:publisher ?publisher;
                           dc:date ?date . FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})

            }}
        }}
        ORDER BY DESC(?date)
        """
    result = query_sparql(PREFIXES + "\n" + query, "politiquices")

    if only_among_selected and len(wiki_ids) > 1:
        # only consider triples where both 'ent1' and 'ent2' are part of wiki_ids
        new_bindings = []
        for r in result["results"]["bindings"]:
            ent1 = r["ent1"]["value"].split("/")[-1]
            ent2 = r["ent2"]["value"].split("/")[-1]
            if len({ent1, ent2}.intersection(set(wiki_ids))) != 2:
                continue
            new_bindings.append(r)
        result["results"]["bindings"] = new_bindings

    if only_sentiment:
        new_bindings = []
        for r in result["results"]["bindings"]:
            if r["rel_type"]["value"] == "other":
                continue
            new_bindings.append(r)
        result["results"]["bindings"] = new_bindings

    news = []
    for e in result["results"]["bindings"]:
        try:
            news.append(
                {
                    "arquivo_doc": e["arquivo_doc"]["value"],
                    "title": e["title"]["value"],
                    "domain": e["creator"]["value"],
                    "original_url": e["publisher"]["value"],
                    "paragraph": e["description"]["value"],
                    "date": e["date"]["value"].split("T")[0],
                    "ent1_id": e["ent1"]["value"].split("/")[-1],
                    "ent1_img": all_entities_info[e["ent1"]["value"].split("/")[-1]]["image_url"],
                    "ent1_str": e["ent1_str"]["value"],
                    "ent2_id": e["ent2"]["value"].split("/")[-1],
                    "ent2_img": all_entities_info[e["ent2"]["value"].split("/")[-1]]["image_url"],
                    "ent2_str": e["ent2_str"]["value"],
                    "rel_type": e["rel_type"]["value"],
                }
            )
        except KeyError:
            print("KeyError", e)

    return news


def get_personalities_by_education(institution_wiki_id: str):
    query = f"""
    SELECT ?ent1 ?ent1_name
    (GROUP_CONCAT(DISTINCT ?image_url;separator=",") as ?images_url)
    WHERE {{
        ?ent1 wdt:P31 wd:Q5;
              rdfs:label ?ent1_name;
              p:P69 ?educatedAtStmnt.
        ?educatedAtStmnt ps:P69 wd:{institution_wiki_id} .
        OPTIONAL {{ ?ent1 wdt:P18 ?image_url. }}
        FILTER(LANG(?ent1_name) = "{LANG}")
      }}
    GROUP BY ?ent1 ?ent1_name
    ORDER BY ASC(?ent1_name)
    """
    result = query_sparql(PREFIXES + "\n" + query, "wikidata")

    for r in result["results"]["bindings"]:
        if "images_url" not in r:
            r["image_url"] = {}
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = NO_IMAGE
        else:
            if images := r["images_url"]["value"].split(","):
                r["image_url"] = r.pop("images_url")
                r["image_url"]["value"] = images[0]
            else:
                r["image_url"] = r.pop("images_url")

    return result["results"]["bindings"]


def get_personalities_by_occupation(occupation_wiki_id: str):
    query = f"""
    SELECT ?ent1 ?ent1_name
    (GROUP_CONCAT(DISTINCT ?image_url;separator=",") as ?images_url)
    WHERE {{
        ?ent1 wdt:P31 wd:Q5;
              rdfs:label ?ent1_name;
              p:P106 ?occupationStmnt .
        ?occupationStmnt ps:P106 wd:{occupation_wiki_id} .
        OPTIONAL {{ ?ent1 wdt:P18 ?image_url. }}
        FILTER(LANG(?ent1_name) = "{LANG}")
    }}
    GROUP BY ?ent1 ?ent1_name
    ORDER BY ASC(?ent1_name)
    """
    result = query_sparql(PREFIXES + "\n" + query, "wikidata")

    for r in result["results"]["bindings"]:
        if "images_url" not in r:
            r["image_url"] = {}
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = NO_IMAGE
        else:
            if images := r["images_url"]["value"].split(","):
                r["image_url"] = r.pop("images_url")
                r["image_url"]["value"] = images[0]
            else:
                r["image_url"] = r.pop("images_url")

    return result["results"]["bindings"]


def get_personalities_by_public_office(public_office: str):
    query = f"""
    SELECT ?ent1 ?ent1_name
    (GROUP_CONCAT(DISTINCT ?image_url;separator=",") as ?images_url)
    WHERE {{
        ?ent1 wdt:P31 wd:Q5;
              rdfs:label ?ent1_name;
              p:P39 ?positionStmnt .
        ?positionStmnt ps:P39 wd:{public_office} .
        OPTIONAL {{ ?ent1 wdt:P18 ?image_url. }}
        FILTER(LANG(?ent1_name) = "{LANG}")
    }}
    GROUP BY ?ent1 ?ent1_name
    ORDER BY ASC(?ent1_name)
    """
    result = query_sparql(PREFIXES + "\n" + query, "wikidata")

    for r in result["results"]["bindings"]:
        if "images_url" not in r:
            r["image_url"] = {}
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = NO_IMAGE
        else:
            if images := r["images_url"]["value"].split(","):
                r["image_url"] = r.pop("images_url")
                r["image_url"]["value"] = images[0]
            else:
                r["image_url"] = r.pop("images_url")

    return result["results"]["bindings"]


def get_personalities_by_assembly(parliamentary_term: str):
    # get all other members in politiquices of part of the same assembly/parliament
    # example of an assembly/parliament in Wikidata: https://www.wikidata.org/wiki/Q71014092
    query = f"""
    SELECT DISTINCT ?ent1 ?ent1_name
    (GROUP_CONCAT(DISTINCT ?image_url;separator=",") as ?images_url)
    WHERE {{
        ?ent1 wdt:P31 wd:Q5;
              wdt:P27 wd:Q45;
              p:P39 ?officeStmnt;
              rdfs:label ?ent1_name . FILTER(LANG(?ent1_name) = "{LANG}")
        ?officeStmnt pq:P2937 wd:{parliamentary_term}.
        OPTIONAL {{ ?ent1 wdt:P18 ?image_url. }}
    }}
    GROUP BY ?ent1 ?ent1_name
    ORDER BY ASC(?ent1_name)
    """

    result = query_sparql(PREFIXES + "\n" + query, "wikidata")

    for r in result["results"]["bindings"]:
        if "images_url" not in r:
            r["image_url"] = {}
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = NO_IMAGE
        else:
            if images := r["images_url"]["value"].split(","):
                r["image_url"] = r.pop("images_url")
                r["image_url"]["value"] = images[0]
            else:
                r["image_url"] = r.pop("images_url")

    return result["results"]["bindings"]


def get_personalities_by_government(legislature: str):
    # get all other members of a government in politiquices part of the same government
    # example of a government in WikiData: https://www.wikidata.org/wiki/Q71014092
    query = f"""
    SELECT DISTINCT ?ent1 ?ent1_name
    (GROUP_CONCAT(DISTINCT ?image_url;separator=",") as ?images_url)
    WHERE {{
        ?ent1 wdt:P31 wd:Q5;
                wdt:P27 wd:Q45;
                p:P39 ?officeStmnt;
                rdfs:label ?ent1_name . FILTER(LANG(?ent1_name) = "{LANG}")
        ?officeStmnt pq:P5054 wd:{legislature}.
        OPTIONAL {{ ?ent1 wdt:P18 ?image_url. }}
    }}
    GROUP BY ?ent1 ?ent1_name
    ORDER BY ASC(?ent1_name)
    """
    result = query_sparql(PREFIXES + "\n" + query, "wikidata")

    for r in result["results"]["bindings"]:
        if "images_url" not in r:
            r["image_url"] = {}
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = NO_IMAGE
        else:
            if images := r["images_url"]["value"].split(","):
                r["image_url"] = r.pop("images_url")
                r["image_url"]["value"] = images[0]
            else:
                r["image_url"] = r.pop("images_url")

    return result["results"]["bindings"]


def get_personalities_by_party(political_party: str):
    query = f"""
    SELECT DISTINCT ?ent1 ?ent1_name
    (GROUP_CONCAT(DISTINCT ?image_url;separator=",") as ?images_url)
    WHERE {{
        ?ent1 wdt:P31 wd:Q5;
              wdt:P102 wd:{political_party};
              rdfs:label ?ent1_name . FILTER(LANG(?ent1_name) = "{LANG}")
        OPTIONAL {{ ?ent1 wdt:P18 ?image_url. }}
    }}
    GROUP BY ?ent1 ?ent1_name
    ORDER BY ASC(?ent1_name)
    """

    result = query_sparql(PREFIXES + "\n" + query, "wikidata")

    for r in result["results"]["bindings"]:
        if "images_url" not in r:
            r["image_url"] = {}
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = NO_IMAGE
        else:
            if images := r["images_url"]["value"].split(","):
                r["image_url"] = r.pop("images_url")
                r["image_url"]["value"] = images[0]
            else:
                r["image_url"] = r.pop("images_url")

    return result["results"]["bindings"]


def get_relationships_aggregate_by_party(wiki_id: str):
    # ToDo: ongoing
    """
    Shows which parties related more with a certain person through support, opposition relationships.
    """

    query = f"""
        SELECT ?rel_type ?ent2 ?noticia ?d
        WHERE {{
            {{
            ?rel politiquices:ent1 {{wd:wiki_id}};
                 politiquices:ent2 ?ent2;
                 politiquices:type ?rel_type;
                 politiquices:url ?noticia.
            ?noticia dc:date ?d
            FILTER(REGEX((?rel_type), "^ent1_opposes|ent1_supports"))
            }}
            UNION
            {{
            ?rel politiquices:ent2 {{wd:wiki_id}};
                 politiquices:ent1 ?ent2;
                 politiquices:type ?rel_type;
                 politiquices:url ?noticia .
            ?noticia dc:date ?d
            FILTER(REGEX((?rel_type), "^ent2_opposes|ent2_supports"))
              }}
        }}
        """


def query_sparql(query, endpoint):
    if endpoint == "wikidata":
        endpoint_url = wikidata_endpoint
    else:
        endpoint_url = politiquices_endpoint
    user_agent = f"Python/{sys.version_info[0]}.{sys.version_info[1]}"
    sparql = SPARQLWrapper(endpoint_url, agent=user_agent)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results
