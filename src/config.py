import os

es_haystack = os.getenv("es_haystack", default=None)
sparql_endpoint = os.getenv("sparql_endpoint", default=None)
wikidata_endpoint = f"{sparql_endpoint}/wikidata/query"
politiquices_endpoint = f"{sparql_endpoint}/politiquices/query"
PS_LOGO = "/assets/images/parties/Q847263.png"
NO_IMAGE = "/assets/images/logos/no_picture.jpg"
STATIC_DATA = "json/"
ENTITIES_BATCH_SIZE = 16  # number of entity cards to read in batch when scrolling down
