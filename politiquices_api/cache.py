import json

# load all static generated caching stuff
with open("json/all_entities_info.json") as f_in:
    all_entities_info = json.load(f_in)

with open("json/all_parties_info.json") as f_in:
    all_parties_info = json.load(f_in)

with open("json/party_members.json") as f_in:
    all_parties_members = json.load(f_in)

with open("json/wiki_id_info_all.json") as f_in:
    wiki_id_info_all = json.load(f_in)

with open("json/persons.json") as f_in:
    persons = json.load(f_in)

with open("json/CHAVE-Publico_94_95.jsonl") as f_in:
    chave_publico = [json.loads(line) for line in f_in]

with open("json/top_co_occurrences.json") as f_in:
    top_co_occurrences = json.load(f_in)
