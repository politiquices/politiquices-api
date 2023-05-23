import re
import sys
from typing import Dict, Any

from SPARQLWrapper import SPARQLWrapper, JSON

from config import wikidata_endpoint, politiquices_endpoint, NO_IMAGE, PS_LOGO
from sparql_prefixes import PREFIXES

LANG = "en"


def make_https(url):
    return re.sub(r"http://", "https://", url)


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


def get_all_parties_and_members_with_relationships():
    """Get a list of all the parties and the count of members"""

    query = f"""
        SELECT DISTINCT ?political_party ?party_label ?party_logo ?country_label (COUNT(?person) as ?nr_personalities)
        WHERE {{
            ?person p:P102 ?political_partyStmnt.
            ?political_partyStmnt ps:P102 ?political_party.
            ?political_party rdfs:label ?party_label . FILTER(LANG(?party_label) = "pt")
            OPTIONAL {{ ?political_party wdt:P154 ?party_logo. }}
            OPTIONAL {{
                ?political_party wdt:P17 ?party_country.
                ?party_country rdfs:label ?country_label . FILTER(LANG(?country_label) = "{LANG}")
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
        party_logo = x["party_logo"]["value"] if "party_logo" in x else NO_IMAGE
        if x["political_party"]["value"].split("/")[-1] == "Q847263":
            party_logo = PS_LOGO
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
    results = {}
    for e in result["results"]["bindings"]:
        wiki_id = e["wiki_id"]["value"].split("/")[-1]
        results[wiki_id] = {
            "wiki_id": wiki_id,
            "name": e["label"]["value"],
            "image_url": make_https(e["image_url"]["value"]) if "image_url" in e else NO_IMAGE,
        }

    return results


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


def get_all_parties_images():
    query = """
        SELECT ?party ?logo
        WHERE {
            ?party wdt:P31 wd:Q7278 .
            OPTIONAL { ?party wdt:P154 ?logo. }
        }"""

    results = query_sparql(PREFIXES + "\n" + query, "wikidata")
    transformed = {
        r["party"]["value"].split("/")[-1]: {"image_url": r["logo"]["value"]}
        for r in results["results"]["bindings"]
        if "logo" in r
    }
    return transformed


def get_all_persons_images():
    query = """
        SELECT ?person ?image_url
        WHERE {
            ?person wdt:P31 wd:Q5 .
            OPTIONAL { ?person wdt:P18 ?image_url. }
        }"""
    results = query_sparql(PREFIXES + "\n" + query, "wikidata")
    transformed = {
        r["person"]["value"].split("/")[-1]: {"image_url": r["image_url"]["value"]}
        for r in results["results"]["bindings"]
        if "image_url" in r
    }
    return transformed
