import re

from cache import all_parties_info, all_entities_info


def make_https(url):
    return re.sub(r"http://", "https://", url)


def invert_relationship(rel_type):
    rel_only = re.match(r"ent[1-2]_(.*)_ent[1-2]", rel_type).groups()[0]
    if rel_type.endswith("ent2"):
        rel_type_inverted = "ent2_" + rel_only + "_ent1"
    elif rel_type.endswith("ent1"):
        rel_type_inverted = "ent1_" + rel_only + "_ent2"
    else:
        raise Exception("this should not happen")

    return rel_type_inverted


def get_info(wiki_id):
    """Returns whether the entity is party or person"""
    for entry in all_parties_info:
        if entry["wiki_id"] == wiki_id:
            return "party"

    for entry in all_entities_info.keys():
        if entry == wiki_id:
            return "person"


def _process_rel_type(rel_type):
    if rel_type in ["ent1_opposes_ent2", "ent1_supports_ent2"]:
        rel_type_inverted = invert_relationship(rel_type)
    elif rel_type == 'all_sentiment':
        rel_type = '.*(opposes|supports).*'
        rel_type_inverted = rel_type
    else:
        rel_type = '.*'
        rel_type_inverted = rel_type
    return rel_type, rel_type_inverted
