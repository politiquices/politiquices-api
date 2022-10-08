from typing import List, Union

import loguru

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from cache import (
    all_entities_info,
    all_parties_info,
    wiki_id_info_all
)
from sparql_queries import (
    get_person_info,
    get_person_relationships,
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


@app.get("/")
async def root():
    return {"message": "Hello World"}


@app.get("/personality/{wiki_id}")
async def read_item(wiki_id: str = Query(None, regex=wiki_id_regex)):
    return get_person_info(wiki_id)


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
    return all_parties_info


@app.get("/personalities/")
async def read_item():
    return all_entities_info


@app.get("/timeline/")
async def read_items(q: Union[List[str], None] = Query(default=None)):
    query_items = {"q": q}

    print(query_items["q"])

    results = get_timeline_personalities(query_items["q"])

    # add images
    for entry in results:
        ent1_id = entry['ent1']['value'].split("/")[-1]
        ent2_id = entry['ent2']['value'].split("/")[-1]
        entry['ent1_img'] = wiki_id_info_all[ent1_id]
        entry['ent2_img'] = wiki_id_info_all[ent2_id]

    return results
