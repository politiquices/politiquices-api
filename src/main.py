import base64
import json
from collections import defaultdict
from typing import List, Union

# import numpy as np

# import requests
# from bertopic import BERTopic
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware

from cache import all_entities_info, all_parties_info, persons, parties, top_co_occurrences
from config import sparql_endpoint

# from config import es_haystack
# from qa_neural_search import NeuralSearch
from sparql import (
    get_nr_of_persons,
    get_person_info,
    get_person_relationships,
    get_person_relationships_by_year,
    get_personalities_by_assembly,
    get_personalities_by_education,
    get_personalities_by_government,
    get_personalities_by_occupation,
    get_personalities_by_party,
    get_personalities_by_public_office,
    get_persons_articles_freq,
    get_relationship_between_parties,
    get_relationship_between_party_and_person,
    get_relationship_between_person_and_party,
    get_relationship_between_two_persons,
    get_timeline_personalities,
    get_top_relationships,
    get_total_articles_by_year_by_relationship_type,
    get_total_nr_of_articles,
    get_wiki_id_affiliated_with_party, get_nr_articles_per_year,
)
from utils import get_info, get_chart_labels_min_max

start_year = 1994
end_year = 2022
rel_types = ["ent1_opposes_ent2", "ent1_supports_ent2", "ent2_opposes_ent1", "ent2_supports_ent1", "other"]

wiki_id_regex = r"^Q\d+$"
rel_type_regex = r"(?=(" + "|".join(rel_types) + r"))"

topics = None
topic_distr = None
topic_token_distr = None
url2index = None

app = FastAPI()

# see: https://fastapi.tiangolo.com/tutorial/cors/
# origins = ["http://localhost:3000"]
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

print("Testing SPARQL endpoint:", sparql_endpoint)
all_articles, no_other_articles = get_total_nr_of_articles()
print(f"Found {get_nr_of_persons()} persons and {all_articles} articles, {no_other_articles} tagged with sentiment")


def local_image(wiki_id: str, org_url: str, ent_type: str) -> str:
    base_url = "/assets/images/"

    if "no_picture.jpg" in org_url:
        return org_url

    if ent_type == "person":
        base_url += "personalities_small"
    f_name = f"{wiki_id}.{org_url.split('.')[-1]}"

    return f"{base_url}/{f_name}"


# ToDo: for Haystack
def get_doc_text(arquivo_url: str):
    """
    # Get the full document from ElasticSearch given a URL
    payload = json.dumps({"query": {"match": {"url": arquivo_url}}})
    url = f"{es_haystack}/document/_search"
    headers = {"Content-Type": "application/json"}
    response = requests.request("GET", url, headers=headers, data=payload, timeout=10)
    return response.json()
    """
    return arquivo_url


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/personality/{wiki_id}")
async def personality(wiki_id: str = Query(None, regex=wiki_id_regex)):
    person = get_person_info(wiki_id)
    person.image_url = local_image(person.wiki_id, person.image_url, ent_type="person")
    for party in person.parties:
        if "no_picture" in party.image_url:
            continue
        f_name = f"{party.wiki_id}.{party.image_url.split('.')[-1]}"
        party.image_url = f"/assets/images/parties/{f_name}"

    def year2index(input_year: int):
        return int(input_year) - start_year

    def index2year(index: int):
        return index + start_year

    per_relationships = get_person_relationships(wiki_id)
    values = [
        {"opposes": 0, "supports": 0, "opposed_by": 0, "supported_by": 0} for _ in range(end_year - start_year + 1)
    ]
    for k in ["opposes", "supports", "opposed_by", "supported_by"]:
        for r in per_relationships[k]:
            year = r["date"][0:4]
            if int(year) > 2022:
                continue
            values[year2index(year)][k] += 1

    # this is a bit tricky, rels.update returns "None", but also updates rels which we want to add to the list
    chart_data = [rels for idx, rels in enumerate(values) if not rels.update({"year": index2year(idx)})]
    person.relationships_charts = chart_data

    return person


@app.get("/personality/relationships/{wiki_id}")
async def personality_relationships(wiki_id: str = Query(None, regex=wiki_id_regex)):
    return get_person_relationships(wiki_id)


@app.get("/personality/relationships_by_year/{wiki_id}")
async def personality_relationships_by_year(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = {}
    for rel_type in rel_types:
        results[rel_type] = get_person_relationships_by_year(wiki_id, rel_type)
    return results


@app.get("/personality/top_related_personalities/{wiki_id}")
async def personality_top_related_personalities(wiki_id: str = Query(None, regex=wiki_id_regex)):
    return get_top_relationships(wiki_id)


@app.get("/relationships/{ent_1}/{rel_type}/{ent_2}")
async def relationships(
    ent_1: str = Query(None, regex=wiki_id_regex),
    rel_type: str = Query(None, regex=rel_type_regex),
    ent_2: str = Query(None, regex=wiki_id_regex),
):
    return get_relationship_between_two_persons(ent_1, ent_2, rel_type, start_year, end_year)


@app.get("/parties/")
async def get_all_parties():
    return list(all_parties_info)


@app.get("/personalities/")
async def get_personalities():
    return [
        {"label": v["name"], "nr_articles": v["nr_articles"], "local_image": v["image_url"], "wiki_id": k}
        for k, v in all_entities_info.items()
    ]


@app.get("/persons/")
async def get_all_persons():
    return persons


@app.get("/persons_and_parties/")
async def persons_and_parties():
    return sorted(persons + parties, key=lambda x: x["label"])


@app.get("/timeline/")
async def timeline(
    q: Union[List[str], None] = Query(default=None),
    selected: bool = Query(default=None),
    sentiment: bool = Query(default=None),
):
    query_items = {"q": q}
    results = get_timeline_personalities(query_items["q"], selected, sentiment)
    return results


@app.get("/queries")
async def queries(
    ent1: str = Query(default=None, regex=wiki_id_regex),
    ent2: str = Query(default=None, regex=wiki_id_regex),
    rel_type: str = Query(default=None),
    start: str = Query(default=None),
    end: str = Query(default=None),
):
    # time interval for the query
    year_from = start
    year_to = end
    e1_type = get_info(ent1)
    e2_type = get_info(ent2)

    if e1_type == "person" and e2_type == "person":
        return get_relationship_between_two_persons(ent1, ent2, rel_type, year_from, year_to)

    if e1_type == "party" and e2_type == "person":
        return get_relationship_between_party_and_person(ent1, ent2, rel_type, year_from, year_to)

    if e1_type == "person" and e2_type == "party":
        return get_relationship_between_person_and_party(ent1, ent2, rel_type, year_from, year_to)

    if e1_type == "party" and e2_type == "party":
        # get the members for each party
        party_a = " ".join(["wd:" + x for x in get_wiki_id_affiliated_with_party(ent1)])
        party_b = " ".join(["wd:" + x for x in get_wiki_id_affiliated_with_party(ent2)])
        return get_relationship_between_parties(party_a, party_b, rel_type, year_from, year_to)


@app.get("/personalities/educated_at/{wiki_id}")
async def personalities_educated_at(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_education(wiki_id)
    for r in results:
        wiki_id = r["ent1"]["value"].split("/")[-1]
        r["image_url"]["value"] = all_entities_info[wiki_id]["image_url"]
        r["nr_articles"] = all_entities_info[wiki_id]["nr_articles"]
    return results


@app.get("/personalities/occupation/{wiki_id}")
async def personalities_occupation(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_occupation(wiki_id)
    for r in results:
        wiki_id = r["ent1"]["value"].split("/")[-1]
        r["image_url"]["value"] = all_entities_info[wiki_id]["image_url"]
        r["nr_articles"] = all_entities_info[wiki_id]["nr_articles"]
    return results


@app.get("/personalities/public_office/{wiki_id}")
async def personalities_public_office(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_public_office(wiki_id)
    for r in results:
        wiki_id = r["ent1"]["value"].split("/")[-1]
        r["image_url"]["value"] = all_entities_info[wiki_id]["image_url"]
        r["nr_articles"] = all_entities_info[wiki_id]["nr_articles"]
    return results


@app.get("/personalities/government/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_government(wiki_id)
    for r in results:
        wiki_id = r["ent1"]["value"].split("/")[-1]
        r["image_url"]["value"] = all_entities_info[wiki_id]["image_url"]
        r["nr_articles"] = all_entities_info[wiki_id]["nr_articles"]
    return results


@app.get("/personalities/assembly/{wiki_id}")
async def personalities_assembly(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_assembly(wiki_id)
    for r in results:
        wiki_id = r["ent1"]["value"].split("/")[-1]
        r["image_url"]["value"] = all_entities_info[wiki_id]["image_url"]
        r["nr_articles"] = all_entities_info[wiki_id]["nr_articles"]
    return results


@app.get("/personalities/party/{wiki_id}")
async def personalities_party(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_party(wiki_id)
    for r in results:
        wiki_id = r["ent1"]["value"].split("/")[-1]
        r["image_url"]["value"] = all_entities_info[wiki_id]["image_url"]
        r["nr_articles"] = all_entities_info[wiki_id]["nr_articles"]
    return results


@app.get("/stats")
async def stats():
    # pylint: disable=too-many-locals
    # number of persons, parties, articles
    nr_persons = get_nr_of_persons()
    nr_parties = len(all_parties_info)

    # total nr of article with and without 'other' relationships
    nr_all_articles, nr_all_articles_sentiment = get_total_nr_of_articles()

    # query returns results for each rel_type, but we aggregate by rel_type discarding direction and 'other'
    all_years = get_chart_labels_min_max()
    values = get_total_articles_by_year_by_relationship_type()
    aggregated_values = defaultdict(lambda: {"oposição": 0, "apoio": 0})
    all_values = []
    for year in all_years:
        if year in values.keys():
            for rel, freq in values[year].items():
                if "opposes" in rel:
                    aggregated_values[year]["oposição"] += int(freq)
                if "supports" in rel:
                    aggregated_values[year]["apoio"] += int(freq)
        else:
            aggregated_values[year]["oposição"] = 0
            aggregated_values[year]["apoio"] = 0

    for k, v in aggregated_values.items():
        v.update({"year": k})
        all_values.append(v)

    # personalities frequency chart
    per_freq = get_persons_articles_freq()
    top_500 = per_freq[0:250]
    top_500.reverse()

    # personalities co-occurrence chart
    co_occurrences_labels = []
    co_occurrences_values = []
    for x in top_co_occurrences:
        co_occurrences_labels.append(x["person_a"]["name"] + " / " + x["person_b"]["name"])
        co_occurrences_values.append(x["nr_occurrences"])

    return {
        "nr_parties": nr_parties,
        "nr_persons": nr_persons,
        "nr_all_articles_sentiment": nr_all_articles_sentiment,
        "nr_all_articles": nr_all_articles,
        "year_values": all_values,
        "personality_freq": top_500,
        "per_co_occurrence_labels": co_occurrences_labels[0:500],
        "per_co_occurrence_values": co_occurrences_values[0:500],
    }


# ToDo: for Haystack
@app.get("/qa/{question}")
async def natural_language_question(question: str):
    """
    # ToDo: do a quick warm-up:
    #     n = NeuralSearch()
    #     q = "Quem acusou José Sócrates?"
    #     answers = n.predict(q)
    neural_search = NeuralSearch()
    answers = neural_search.predict(question)
    return answers
    """
    return question


# ToDo: for BERTopic
@app.get("/topics/bar/{doc_url_encoded}")
async def topics_bar(doc_url_encoded: str):
    """
    url_decoded = base64.b64decode(doc_url_encoded).decode("utf8")
    global topics
    global topic_distr
    global topic_token_distr
    global url2index
    if topics is None:
        print("Loading Topics Model")
        topics = BERTopic.load("bin/topics_bert_2023-02-05.bin")

    if topic_distr is None:
        print("Loading Topics Distributions")
        with open("bin/topic_distr_2023-02-05.npy", "rb") as f_in:
            topic_distr = np.load(f_in, allow_pickle=True)

    if topic_token_distr is None:
        print("Loading Topics Token Distributions")
        with open("bin/topic_token_distr_2023-02-05.npy", "rb") as f_in:
            topic_token_distr = np.load(f_in, allow_pickle=True)

    if url2index is None:
        print("Loading URL2Index mappings")
        with open("bin/url2index_2023-02-05.json", "rt", encoding="utf8") as f_in:
            url2index = json.load(f_in)

    print(f"Getting topics for {url_decoded}")
    doc_idx = url2index[url_decoded]

    doc_topic_distr = topic_distr[doc_idx]
    # doc_topic_token_distr = topic_token_distr[doc_idx]

    # see also: https://stackoverflow.com/questions/36262748/save-plotly-plot-to-local-file-and-insert-into-html
    figure = topics.visualize_distribution(
        doc_topic_distr,
        min_probability=0.20,
    )
    return {"figure": figure.to_dict()}
    """
    return doc_url_encoded


# ToDo: for BERTopic
@app.get("/topics/raw/{doc_url_encoded}")
async def topics_raw(doc_url_encoded: str):
    """
    url_decoded = base64.b64decode(doc_url_encoded).decode("utf8")
    global topics
    global topic_distr
    global topic_token_distr
    global url2index
    if topics is None:
        print("Loading Topics Model")
        topics = BERTopic.load("bin/topics_bert_2023-02-05.bin")

    if topic_distr is None:
        print("Loading Topics Distributions")
        with open("bin/topic_distr_2023-02-05.npy", "rb") as f_in:
            topic_distr = np.load(f_in, allow_pickle=True)

    if topic_token_distr is None:
        print("Loading Topics Token Distributions")
        with open("bin/topic_token_distr_2023-02-05.npy", "rb") as f_in:
            topic_token_distr = np.load(f_in, allow_pickle=True)

    if url2index is None:
        print("Loading URL2Index mappings")
        with open("bin/url2index_2023-02-05.json", "rt", encoding="utf8") as f_in:
            url2index = json.load(f_in)

    with open("../SPARQL-endpoint/entities_names.txt", "rt", encoding="utf8") as f_in:
        all_names = [line.strip() for line in f_in]
        all_token_names = {name.lower() for names in all_names for name in names.split()}
        other = ["hoje", "sobre", "primeiro", "ministro", "porque", "feira", "euros", "estado", "política"]

    min_probability = 0.10

    print(f"Getting topics for {url_decoded}")
    doc_idx = url2index[url_decoded]

    topics_n = np.where(topic_distr[doc_idx] > min_probability)
    all_topics = []
    for n in topics_n[0]:
        all_topics.append(
            [
                word[0]
                for word in topics.topic_representations_[n]
                if word[0] not in other and word[0] not in all_token_names
            ]
        )

    return all_topics
    """
    return doc_url_encoded