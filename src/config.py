import os

es_haystack = os.getenv("ES_HAYSTACK", default=None)
sparql_endpoint = os.getenv("SPARQL_ENDPOINT", default=None)
wikidata_endpoint = f"{sparql_endpoint}/wikidata/query"
politiquices_endpoint = f"{sparql_endpoint}/politiquices/query"
start_year = 1994
end_year = 2024
LANG = "pt"
PS_LOGO = "../assets/images/parties/Q847263.png"
NO_IMAGE = "../assets/images/logos/no_picture.jpg"
STATIC_DATA = "json/"
ENTITIES_BATCH_SIZE = 16  # number of entity cards to read in batch when scrolling down
