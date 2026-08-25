import json

with open("json/all_entities_info.json", encoding="utf8") as f_in:
    all_entities_info = json.load(f_in)

with open("json/all_parties_info.json", encoding="utf8") as f_in:
    all_parties_info = json.load(f_in)

with open("json/persons.json", encoding="utf8") as f_in:
    persons = json.load(f_in)

with open("json/parties.json", encoding="utf8") as f_in:
    parties = json.load(f_in)

try:
    with open("json/stats.json", encoding="utf8") as f_in:
        stats = json.load(f_in)
except FileNotFoundError:
    # generate_caches.py's stats_json_cache() writes this file, but it also imports
    # (transitively, via sparql.py) from this module -- so on the very first run,
    # before stats.json exists yet, fall back to an empty dict instead of crashing.
    stats = {}

with open("json/CHAVE-Publico_94_95.jsonl", encoding="utf8") as f_in:
    chave_publico = [json.loads(line) for line in f_in]

