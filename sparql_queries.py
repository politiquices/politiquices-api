import sys
from collections import defaultdict
from functools import lru_cache
from typing import List, Dict, Any

from SPARQLWrapper import SPARQLWrapper, JSON
from politiquices_api.config import (
    live_wikidata,
    no_image,
    politiquices_endpoint,
    ps_logo,
    wikidata_endpoint,
)
from politiquices_api.data_models import Element, Person, PoliticalParty
from politiquices_api.utils import make_https, invert_relationship

LANG = 'en'

POLITIQUICES_PREFIXES = """
    PREFIX politiquices: <http://www.politiquices.pt/>
    PREFIX      rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX        dc: <http://purl.org/dc/elements/1.1/>
    PREFIX 		 ns1: <http://xmlns.com/foaf/0.1/>
    PREFIX		 ns2: <http://www.w3.org/2004/02/skos/core#>
    """

WIKIDATA_PREFIXES = """
    PREFIX        wd: <http://www.wikidata.org/entity/>
    PREFIX       wds: <http://www.wikidata.org/entity/statement/>
    PREFIX       wdv: <http://www.wikidata.org/value/>
    PREFIX       wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX         p: <http://www.wikidata.org/prop/>
    PREFIX        ps: <http://www.wikidata.org/prop/statement/>
    PREFIX        pq: <http://www.wikidata.org/prop/qualifier/>
    PREFIX      rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    """

PREFIXES = POLITIQUICES_PREFIXES + WIKIDATA_PREFIXES


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
    nr_articles = dict()
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


def get_persons_co_occurrences_counts():
    query = """
        SELECT DISTINCT ?person_a ?person_b (COUNT (?url) as ?n_artigos) {
            VALUES ?rel_values {'ent1_opposes_ent2' 'ent2_opposes_ent1' 
                                'ent1_supports_ent2' 'ent2_supports_ent1'} .

            ?rel politiquices:type ?rel_values .
            {
                ?rel politiquices:ent1 ?person_a .
                ?rel politiquices:ent2 ?person_b .
            }
            UNION {
                ?rel politiquices:ent2 ?person_a .
                ?rel politiquices:ent1 ?person_b .
            }
            ?rel politiquices:url ?url .
            ?rel politiquices:type ?rel_type .
        }
        GROUP BY ?person_a ?person_b
        ORDER BY DESC(?n_artigos)
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    co_occurrences = []
    seen = set()
    for x in results["results"]["bindings"]:
        person_a = x["person_a"]["value"]
        person_b = x["person_b"]["value"]
        artigos = x["n_artigos"]["value"]
        if person_a + " " + person_b in seen:
            continue
        co_occurrences.append({"person_a": person_a, "person_b": person_b, "n_artigos": artigos})
        seen.add(person_a + " " + person_b)
        seen.add(person_b + " " + person_a)

    return co_occurrences


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
    top_freq = [
        {"person": x["person"]["value"], "freq": x["n_artigos"]["value"]} for x in results["results"]["bindings"]
    ]
    return top_freq


def get_persons_wiki_id_name_image_url() -> Dict[str, Any]:
    # wd:Q5 -> all human beings
    # wd:Q15904441 -> Dailai Lama, he's not a human being, it's a position/spiritual leader
    query = f"""
        SELECT ?wiki_id ?label ?image_url {{
            VALUES ?valid_instances {{wd:Q5 wd:Q15904441}}
            ?wiki_id wdt:P31 ?valid_instances.
            ?wiki_id rdfs:label ?label . FILTER(LANG(?label) = "{LANG}")  
            OPTIONAL {{ ?wiki_id wdt:P18 ?image_url. }}
        }}
        """
    result = query_sparql(PREFIXES + "\n" + query, "wikidata")
    results = dict()
    for e in result["results"]["bindings"]:
        wiki_id = e["wiki_id"]["value"].split("/")[-1]
        results[wiki_id] = {
            "wiki_id": wiki_id,
            "name": e["label"]["value"],
            "image_url": make_https(e["image_url"]["value"]) if "image_url" in e else no_image,
        }

    return results


def get_all_parties_and_members_with_relationships():
    """Get a list of all the parties and the count of members"""

    query = f"""
        SELECT DISTINCT ?political_party ?party_label ?party_logo ?country_label (COUNT(?person) as ?nr_personalities)
        WHERE {{
            ?person p:P102 ?political_partyStmnt.
            ?political_partyStmnt ps:P102 ?political_party.
            ?political_party rdfs:label ?party_label . FILTER(LANG(?party_label) = "en")  
            OPTIONAL {{ ?political_party wdt:P154 ?party_logo. }}
            OPTIONAL {{ 
                ?political_party wdt:P17 ?party_country. 
                ?party_country rdfs:label ?country_label . FILTER(LANG(?country_label) = "en")
            }}
            SERVICE <http://0.0.0.0:3030/politiquices/query> {{
                SELECT ?person WHERE {{ ?person wdt:P31 wd:Q5 . }}     
            }}
        }}
        GROUP BY ?political_party ?party_label ?party_logo ?country_label 
        ORDER BY DESC(?nr_personalities)
        """
    results = query_sparql(PREFIXES + "\n" + query, "wikidata")

    political_parties = []
    for x in results["results"]["bindings"]:
        party_logo = x["party_logo"]["value"] if "party_logo" in x else no_image
        if x["political_party"]["value"].split("/")[-1] == "Q847263":
            party_logo = ps_logo
        country = x["country_label"]["value"] if x.get("country_label") else None
        political_parties.append(
            {
                "wiki_id": x["political_party"]["value"].split("/")[-1],
                "party_label": x["party_label"]["value"],
                "party_logo": make_https(party_logo),
                "country": country,
                "nr_personalities": x["nr_personalities"]["value"],
            }
        )

    return political_parties


def get_total_nr_articles_for_each_person() -> Dict[str, int]:
    query = """
        SELECT ?person (COUNT(*) as ?count)
        WHERE {
          VALUES ?rel_values {'ent1_opposes_ent2' 'ent2_opposes_ent1' 
                              'ent1_supports_ent2' 'ent2_supports_ent1' 'other'}
            ?person wdt:P31 wd:Q5 ;
            {?rel politiquices:ent1 ?person} UNION {?rel politiquices:ent2 ?person} .
            ?rel politiquices:type ?rel_values .
          }
        GROUP BY ?person
        ORDER BY DESC (?count)
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    return {e["person"]["value"].split("/")[-1]: int(e["count"]["value"]) for e in results["results"]["bindings"]}


def get_nr_relationships_as_subject(relationship: str):
    query = f"""
        SELECT DISTINCT ?person_a (COUNT(?url) as ?nr_articles) {{
          {{ ?rel politiquices:ent1 ?person_a .
            ?rel politiquices:type 'ent1_{relationship}_ent2'.
          }}  
          UNION 
          {{ ?rel politiquices:ent2 ?person_a .
            ?rel politiquices:type 'ent2_{relationship}_ent1'.
          }}
          ?rel politiquices:url ?url .
        }}
        GROUP BY ?person_a
        ORDER BY DESC(?nr_articles)
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    return [
        (x["person_a"]["value"].split("/")[-1], int(x["nr_articles"]["value"])) for x in results["results"]["bindings"]
    ]


def get_nr_relationships_as_target(relationship: str):
    query = f"""
        SELECT DISTINCT ?person_a (COUNT(?url) as ?nr_articles) {{
          {{ ?rel politiquices:ent2 ?person_a .
            ?rel politiquices:type 'ent1_{relationship}_ent2'.
          }}  
          UNION 
          {{ ?rel politiquices:ent1 ?person_a .
            ?rel politiquices:type 'ent2_{relationship}_ent1'.
          }}
          ?rel politiquices:url ?url .
        }}
        GROUP BY ?person_a
        ORDER BY DESC(?nr_articles)
        """
    results = query_sparql(PREFIXES + "\n" + query, "politiquices")
    return [
        (x["person_a"]["value"].split("/")[-1], int(x["nr_articles"]["value"])) for x in results["results"]["bindings"]
    ]


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
            image_url = e["image_url"]["value"] if "image_url" in e else no_image
        if "political_party" in e:
            party_image_url = no_image

            # add 'PS' logo since it's not on Wikidata
            if e["political_party"]["value"] == "http://www.wikidata.org/entity/Q847263":
                party_image_url = ps_logo

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
            ?positionStmnt pq:P5054 ?government. 
            ?government rdfs:label ?government_label . FILTER(LANG(?government_label) = "{LANG}").
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
    query = f"""
        SELECT DISTINCT ?arquivo_doc ?date ?title ?rel_type ?score ?ent1 ?ent1_str ?ent2 ?ent2_str
        WHERE {{
         {{ ?rel politiquices:ent1 wd:{wiki_id} }} UNION {{?rel politiquices:ent2 wd:{wiki_id} }}        

            ?rel politiquices:type ?rel_type;
                 politiquices:score ?score.

             ?rel politiquices:ent1 ?ent1 ;
                  politiquices:ent2 ?ent2 ;
                  politiquices:ent1_str ?ent1_str ;
                  politiquices:ent2_str ?ent2_str ;
                  politiquices:url ?arquivo_doc .

              ?arquivo_doc dc:title ?title ;
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

        else:
            print(e)
            continue
            # ToDo: re-activate this Exception
            # raise Exception(e["rel_type"]["value"] + " not known")

        relations[rel_type].append(
            {
                "url": e["arquivo_doc"]["value"],
                "title": e["title"]["value"],
                "score": str(e["score"]["value"])[0:5],
                "date": e["date"]["value"].split("T")[0],
                "focus_ent": focus_ent,
                "other_ent_url": "entity?q=" + other_ent_url,
                "other_ent_name": other_ent_name,
                "rel_type": rel_type,
            }
        )

    return relations


def get_top_relationships(wiki_id):
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

    return person_as_subject, person_as_target


def get_person_relationships_by_year(wiki_id, rel_type, ent="ent1"):
    query = f"""
        SELECT DISTINCT ?year (COUNT(?arquivo_doc) as ?nr_articles)
        WHERE {{

              ?rel politiquices:{ent} wd:{wiki_id} .
              ?rel politiquices:type ?rel_type ;
                   politiquices:score ?score.

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
    year_articles = dict()
    for x in result["results"]["bindings"]:
        year = x["year"]["value"]
        year_articles[str(year)] = int(x["nr_articles"]["value"])

    return year_articles


# Get relationships for 'Entity vs. Entity'
def get_all_relationships_between_two_entities(wiki_id_one, wiki_id_two):
    query = f"""
        SELECT DISTINCT ?arquivo_doc ?date ?title ?rel_type ?score ?ent1 ?ent1_str ?ent2 ?ent2_str
        WHERE {{               
          {{
              ?rel politiquices:ent1 wd:{wiki_id_one};
                   politiquices:ent2 wd:{wiki_id_two};
                   politiquices:ent1 ?ent1;
                   politiquices:ent2 ?ent2;
                   politiquices:ent1_str ?ent1_str;
                   politiquices:ent2_str ?ent2_str;
                   politiquices:score ?score;
                   politiquices:url ?arquivo_doc; 
                   politiquices:type ?rel_type. FILTER(!REGEX(?rel_type,"other"))

              ?arquivo_doc dc:title ?title;
                           dc:date  ?date .
          }} UNION {{
              ?rel politiquices:ent2 wd:{wiki_id_one};
                   politiquices:ent1 wd:{wiki_id_two};       
                   politiquices:ent2 ?ent2;
                   politiquices:ent1 ?ent1;
                   politiquices:ent2_str ?ent2_str;
                   politiquices:ent1_str ?ent1_str;
                   politiquices:score ?score;
                   politiquices:url ?arquivo_doc;   
                   politiquices:type ?rel_type FILTER(!REGEX(?rel_type,"other"))

              ?arquivo_doc dc:title ?title;
                           dc:date  ?date .
             }}
        }}
        ORDER BY ASC(?date)
        """

    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    relationships = []
    for x in result["results"]["bindings"]:
        relationships.append(
            {
                "url": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "rel_type": x["rel_type"]["value"],
                "score": x["score"]["value"][0:5],
                "ent1_wiki": x["ent1"]["value"].split("/")[-1],
                "ent1_str": x["ent1_str"]["value"],
                "ent2_wiki": x["ent2"]["value"].split("/")[-1],
                "ent2_str": x["ent2_str"]["value"],
            }
        )

    return relationships


# Relationship Queries
@lru_cache(maxsize=50)
def get_relationship_between_two_persons(wiki_id_one, wiki_id_two, rel_type, start_year, end_year):
    rel_type_inverted = invert_relationship(rel_type)

    query = f"""
        SELECT DISTINCT ?arquivo_doc ?date ?title ?rel_type ?score ?ent1 ?ent1_str ?ent2 ?ent2_str
        WHERE {{ 
            {{          
              ?rel politiquices:ent1 wd:{wiki_id_one};
                   politiquices:ent2 wd:{wiki_id_two};                                             
                   politiquices:score ?score;
                   politiquices:url ?arquivo_doc;
                   politiquices:ent1 ?ent1;
                   politiquices:ent2 ?ent2;
                   politiquices:ent1_str ?ent1_str;
                   politiquices:ent2_str ?ent2_str;
                   politiquices:type ?rel_type. FILTER((?rel_type)='{rel_type}')
              ?arquivo_doc dc:title ?title ;
                           dc:date ?date . FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
           }}
           UNION
           {{          
              ?rel politiquices:ent2 wd:{wiki_id_one};
                   politiquices:ent1 wd:{wiki_id_two};
                   politiquices:score ?score;
                   politiquices:url ?arquivo_doc;
                   politiquices:ent1 ?ent1;
                   politiquices:ent2 ?ent2;
                   politiquices:ent1_str ?ent1_str;
                   politiquices:ent2_str ?ent2_str;
                   politiquices:type ?rel_type. FILTER((?rel_type)='{rel_type_inverted}')

              ?arquivo_doc dc:title ?title ;
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
                "url": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "score": x["score"]["value"][0:5],
                "rel_type": x["rel_type"]["value"],
                "ent1_wiki": wiki_id_one,
                "ent1_str": x["ent1_str"]["value"],
                "ent2_wiki": x["ent2"]["value"],
                "ent2_str": x["ent2_str"]["value"],
            }
        )

    return results


@lru_cache(maxsize=50)
def get_relationship_between_party_and_person(party, person, rel_type, start_year, end_year):
    rel_type_inverted = invert_relationship(rel_type)

    query = f"""
        SELECT DISTINCT ?ent1 ?ent1_str ?ent2 ?ent2_str ?rel_type ?arquivo_doc ?date ?title ?score
        WHERE {{
            {{
                ?rel politiquices:ent1 ?ent1;
                     politiquices:ent2 ?ent2 . FILTER(?ent2=wd:{person})
                ?rel politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;                 
                     politiquices:score ?score;
                     politiquices:url ?arquivo_doc;
                     politiquices:type ?rel_type. FILTER((?rel_type)='{rel_type}')

                ?arquivo_doc dc:title ?title;
                             dc:date ?date. FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
             }}
                UNION
            {{
                ?rel politiquices:ent2 ?ent1;
                     politiquices:ent1 ?ent2 . FILTER(?ent2=wd:{person})
                ?rel politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;                 
                     politiquices:score ?score;
                     politiquices:url ?arquivo_doc;
                     politiquices:type ?rel_type. FILTER((?rel_type)='{rel_type_inverted}')

                ?arquivo_doc dc:title ?title;
                             dc:date ?date. FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
             }}

            SERVICE <{wikidata_endpoint}> {{
                ?ent1 wdt:P102 wd:{party};
                      rdfs:label ?personLabel.
                FILTER(LANG(?personLabel) = "{LANG}")                
            }}
        }}
        ORDER BY DESC(?date) ASC(?score)
        """

    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    results = []
    for x in result["results"]["bindings"]:

        if x["rel_type"]["value"].startswith("ent1"):
            ent1_wiki = x["ent1"]["value"]
            ent2_wiki = person
        elif x["rel_type"]["value"].startswith("ent2"):
            ent2_wiki = x["ent1"]["value"]
            ent1_wiki = person

        results.append(
            {
                "url": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "rel_type": x["rel_type"]["value"],
                "score": x["score"]["value"][0:5],
                "ent1_wiki": ent1_wiki,
                "ent1_str": x["ent1_str"]["value"],
                "ent2_wiki": ent2_wiki,
                "ent2_str": x["ent2_str"]["value"],
            }
        )

    return results


@lru_cache(maxsize=50)
def get_relationship_between_person_and_party(person, party, relation, start_year, end_year):
    inverted_relationship = invert_relationship(relation)

    query = f"""
        SELECT DISTINCT ?ent2 ?ent2_str ?ent1_str ?rel_type ?arquivo_doc ?date ?title ?score
        WHERE {{
            {{
                ?rel politiquices:ent1 wd:{person};
                     politiquices:ent2 ?ent2;
                     politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;
                     politiquices:score ?score;
                     politiquices:url ?arquivo_doc .
                ?rel politiquices:type ?rel_type. FILTER((?rel_type)='{relation}')

                ?arquivo_doc dc:title ?title;
                             dc:date ?date; FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
            }}
              UNION
            {{
                ?rel politiquices:ent1 ?ent2;
                     politiquices:ent2 wd:{person};
                     politiquices:ent1_str ?ent1_str;
                     politiquices:ent2_str ?ent2_str;
                     politiquices:score ?score;
                     politiquices:url ?arquivo_doc .
                ?rel politiquices:type ?rel_type. FILTER((?rel_type)='{inverted_relationship}')

                ?arquivo_doc dc:title ?title;
                             dc:date ?date; FILTER(YEAR(?date)>={start_year} && YEAR(?date)<={end_year})
            }}

            SERVICE <{wikidata_endpoint}> {{
                ?ent2 wdt:P102 wd:{party};
                      rdfs:label ?personLabel. FILTER(LANG(?personLabel) = "{LANG}")                
            }}
        }}
        ORDER BY DESC(?date) ASC(?score)
        """

    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    results = []
    for x in result["results"]["bindings"]:

        if x["rel_type"]["value"].startswith("ent1"):
            ent2_wiki = x["ent2"]["value"]
            ent1_wiki = person
        elif x["rel_type"]["value"].startswith("ent2"):
            ent1_wiki = x["ent2"]["value"]
            ent2_wiki = person

        results.append(
            {
                "url": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "rel_type": relation,
                "score": x["score"]["value"][0:5],
                "ent1_wiki": ent1_wiki,
                "ent1_str": x["ent1_str"]["value"],
                "ent2_wiki": ent2_wiki,
                "ent2_str": x["ent2_str"]["value"],
            }
        )

    return results


@lru_cache(maxsize=50)
def get_relationship_between_parties(per_party_a, per_party_b, rel_type, start_year, end_year):
    inverted_rel_type = invert_relationship(rel_type)

    query = f"""
    SELECT DISTINCT ?person_party_a ?ent1_str ?person_party_b ?ent2_str ?arquivo_doc ?date ?title 
                    ?score ?rel_type
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
                SELECT ?rel ?rel_type ?arquivo_doc ?title ?date ?score
                WHERE {{
                     ?rel politiquices:score ?score;
                          politiquices:url ?arquivo_doc;
                          politiquices:type ?rel_type. FILTER((?rel_type)='{rel_type}')

                      ?arquivo_doc dc:title ?title;
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
                SELECT ?rel ?rel_type ?arquivo_doc ?title ?date ?score
                WHERE {{
                      ?rel politiquices:score ?score;
                           politiquices:url ?arquivo_doc;
                           politiquices:type ?rel_type. FILTER((?rel_type)='{inverted_rel_type}')

                      ?arquivo_doc dc:title ?title;
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
                "url": x["arquivo_doc"]["value"],
                "date": x["date"]["value"],
                "title": x["title"]["value"],
                "rel_type": x["rel_type"]["value"],
                "score": x["score"]["value"][0:5],
                "ent1_wiki": x["person_party_a"]["value"],
                "ent1_str": x["ent1_str"]["value"],
                "ent2_wiki": x["person_party_b"]["value"],
                "ent2_str": x["ent2_str"]["value"],
            }
        )

    return relationships


# Other
def get_entities_without_image():
    query = f"""
        SELECT DISTINCT ?item ?label ?image_url {{
            ?item wdt:P31 wd:Q5.
                SERVICE <{live_wikidata}> {{
                ?item rdfs:label ?label .
                FILTER(LANG(?label) = "{LANG}")
                FILTER NOT EXISTS {{ ?item wdt:P18 ?image_url. }}
          }}
          }}
        ORDER BY ?label
        """
    result = query_sparql(PREFIXES + "\n" + query, "politiquices")
    entities = []
    for x in result["results"]["bindings"]:
        entities.append({"wikidata_id": x["item"]["value"].split("/")[-1], "label": x["label"]["value"]})

    return entities


# new website


def get_timeline_personalities(wiki_ids: List[str], only_among_selected: bool, only_sentiment: bool):
    values = " ".join(["wd:" + wiki_id for wiki_id in wiki_ids])

    date_start = None
    date_ent = None

    query = f"""
        PREFIX politiquices: <http://www.politiquices.pt/>
        PREFIX      rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX        dc: <http://purl.org/dc/elements/1.1/>
        PREFIX 		 ns1: <http://xmlns.com/foaf/0.1/>
        PREFIX		 ns2: <http://www.w3.org/2004/02/skos/core#>
        PREFIX        wd: <http://www.wikidata.org/entity/>
        PREFIX	     wdt: <http://www.wikidata.org/prop/direct/>


        SELECT DISTINCT ?arquivo_doc ?date ?title ?rel_type ?ent1 ?ent1_str ?ent2 ?ent2_str 
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

                   ?arquivo_doc dc:title ?title;
                                dc:date  ?date .
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

    return result["results"]["bindings"]


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
            r["image_url"] = dict()
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = no_image
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
            r["image_url"] = dict()
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = no_image
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
            r["image_url"] = dict()
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = no_image
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
            r["image_url"] = dict()
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = no_image
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
            r["image_url"] = dict()
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = no_image
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
            r["image_url"] = dict()
            r["image_url"]["type"] = "uri"
            r["image_url"]["value"] = no_image
        else:
            if images := r["images_url"]["value"].split(","):
                r["image_url"] = r.pop("images_url")
                r["image_url"]["value"] = images[0]
            else:
                r["image_url"] = r.pop("images_url")

    return result["results"]["bindings"]


def get_all_parties_images():
    query = """
        SELECT ?party ?logo
        WHERE {
            ?party wdt:P31 wd:Q7278 .
            OPTIONAL { ?party wdt:P154 ?logo. }
        }"""

    results = query_sparql(PREFIXES + "\n" + query, "wikidata")
    transformed = {
        r['party']['value'].split("/")[-1]: {"image_url": r['logo']['value']}
        for r in results['results']['bindings']
        if 'logo' in r
    }
    return transformed


def query_sparql(query, endpoint):
    if endpoint == "wikidata":
        endpoint_url = wikidata_endpoint
    elif endpoint == "politiquices":
        endpoint_url = politiquices_endpoint
    user_agent = "Python/%s.%s" % (sys.version_info[0], sys.version_info[1])
    sparql = SPARQLWrapper(endpoint_url, agent=user_agent)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    results = sparql.query().convert()
    return results
