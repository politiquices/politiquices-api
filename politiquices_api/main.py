from fastapi import FastAPI, Query
from sparql_queries import get_person_info, get_person_relationships, get_relationship_between_two_persons

start_year = 1994
end_year = 2022
rel_types = ["ent1_opposes_ent2", "ent1_supports_ent2", "ent2_opposes_ent1", "ent2_supports_ent1", "other"]

wiki_id_regex = r'^Q\d+$'
rel_type_regex = r"(?=("+'|'.join(rel_types)+r"))"

app = FastAPI()


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
        rel_type: str = Query(None, regex=rel_type_regex)
):
    return get_relationship_between_two_persons(ent_1, ent_2, rel_type, start_year, end_year)
