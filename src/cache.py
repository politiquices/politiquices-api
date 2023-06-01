import json

with open("json/all_entities_info.json", encoding="utf8") as f_in:
    all_entities_info = json.load(f_in)

with open("json/all_parties_info.json", encoding="utf8") as f_in:
    all_parties_info = json.load(f_in)

# with open("../json/party_members.json", encoding="utf8") as f_in:
#     all_parties_members = json.load(f_in)

with open("json/persons.json", encoding="utf8") as f_in:
    persons = json.load(f_in)

with open("json/parties.json", encoding="utf8") as f_in:
    parties = json.load(f_in)

with open("json/CHAVE-Publico_94_95.jsonl", encoding="utf8") as f_in:
    chave_publico = [json.loads(line) for line in f_in]

with open("json/top_co_occurrences.json", encoding="utf8") as f_in:
    top_co_occurrences = json.load(f_in)
