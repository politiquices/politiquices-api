from typing import List, Union

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from cache import all_entities_info, all_parties_info, persons
from sparql_queries import (
    get_person_info,
    get_person_relationships,
    get_personalities_by_assembly,
    get_personalities_by_education,
    get_personalities_by_government,
    get_personalities_by_occupation,
    get_personalities_by_party,
    get_personalities_by_public_office,
    get_relationship_between_two_persons,
    get_timeline_personalities,
)

start_year = 1994
end_year = 2022
rel_types = ["ent1_opposes_ent2", "ent1_supports_ent2", "ent2_opposes_ent1", "ent2_supports_ent1", "other"]

wiki_id_regex = r"^Q\d+$"
rel_type_regex = r"(?=(" + "|".join(rel_types) + r"))"

app = FastAPI()

# see: https://fastapi.tiangolo.com/tutorial/cors/
origins = ["http://localhost:3000"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def local_image(wiki_id: str, org_url: str, ent_type: str) -> str:
    base_url = "/assets/images/"

    if 'no_picture.jpg' in org_url:
        return org_url

    if ent_type == 'person':
        base_url += 'personalities_small'
    f_name = f"{wiki_id}.{org_url.split('.')[-1]}"

    return f"{base_url}/{f_name}"


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/personality/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    person = get_person_info(wiki_id)
    person.image_url = local_image(person.wiki_id, person.image_url, ent_type='person')
    for party in person.parties:
        if 'no_picture' in party.image_url:
            continue
        f_name = f"{party.wiki_id}.{party.image_url.split('.')[-1]}"
        party.image_url = f"/assets/images/parties/{f_name}"
    return person


@app.get("/personality/relationships/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    return get_person_relationships(wiki_id)


@app.get("/relationships/{ent_1}/{rel_type}/{ent_2}")
async def read_item(
    ent_1: str = Query(None, regex=wiki_id_regex),
    ent_2: str = Query(None, regex=wiki_id_regex),
    rel_type: str = Query(None, regex=rel_type_regex),
):
    return get_relationship_between_two_persons(ent_1, ent_2, rel_type, start_year, end_year)


@app.get("/parties/")
async def read_item():
    return [party for party in all_parties_info]


@app.get("/personalities/")
async def read_item():
    personalities = []
    for k, v in all_entities_info.items():
        personalities.append(
            {
                "label": v["name"],
                "nr_articles": v["nr_articles"],
                "local_image": v["image_url"],
                "wiki_id": k,
            }
        )
    return personalities


@app.get("/persons/")
async def read_item():
    return persons


@app.get("/timeline/")
async def read_items(
    q: Union[List[str], None] = Query(default=None),
    selected: bool = Query(default=None),
    sentiment: bool = Query(default=None),
):
    query_items = {"q": q}
    results = get_timeline_personalities(query_items["q"], selected, sentiment)

    # add images
    for entry in results:
        ent1_id = entry["ent1"]["value"].split("/")[-1]
        ent2_id = entry["ent2"]["value"].split("/")[-1]
        entry["ent1_img"] = all_entities_info[ent1_id]
        entry["ent2_img"] = all_entities_info[ent2_id]

    return results


@app.get("/personalities/educated_at/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_education(wiki_id)
    for r in results:
        wiki_id = r['ent1']['value'].split("/")[-1]
        r['image_url']['value'] = all_entities_info[wiki_id]['image_url']
        r['nr_articles'] = all_entities_info[wiki_id]['nr_articles']
    return results


@app.get("/personalities/occupation/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_occupation(wiki_id)
    for r in results:
        wiki_id = r['ent1']['value'].split("/")[-1]
        r['image_url']['value'] = all_entities_info[wiki_id]['image_url']
        r['nr_articles'] = all_entities_info[wiki_id]['nr_articles']
    return results


@app.get("/personalities/public_office/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_public_office(wiki_id)
    for r in results:
        wiki_id = r['ent1']['value'].split("/")[-1]
        r['image_url']['value'] = all_entities_info[wiki_id]['image_url']
        r['nr_articles'] = all_entities_info[wiki_id]['nr_articles']
    return results


@app.get("/personalities/government/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_government(wiki_id)
    for r in results:
        wiki_id = r['ent1']['value'].split("/")[-1]
        r['image_url']['value'] = all_entities_info[wiki_id]['image_url']
        r['nr_articles'] = all_entities_info[wiki_id]['nr_articles']
    return results


@app.get("/personalities/assembly/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_assembly(wiki_id)
    for r in results:
        wiki_id = r['ent1']['value'].split("/")[-1]
        r['image_url']['value'] = all_entities_info[wiki_id]['image_url']
        r['nr_articles'] = all_entities_info[wiki_id]['nr_articles']
    return results


@app.get("/personalities/party/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    results = get_personalities_by_party(wiki_id)
    for r in results:
        wiki_id = r['ent1']['value'].split("/")[-1]
        r['image_url']['value'] = all_entities_info[wiki_id]['image_url']
        r['nr_articles'] = all_entities_info[wiki_id]['nr_articles']
    return results
