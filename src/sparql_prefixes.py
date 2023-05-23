# ToDo: review this prefixes
POLITIQUICES_PREFIXES = """
    PREFIX politiquices: <http://www.politiquices.pt/>
    PREFIX      rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    PREFIX        dc: <http://purl.org/dc/elements/1.1/>
    PREFIX       ns1: <http://xmlns.com/foaf/0.1/>
    PREFIX       ns2: <http://www.w3.org/2004/02/skos/core#>
    """

WIKIDATA_PREFIXES = """
    PREFIX        wd: <http://www.wikidata.org/entity/>
    PREFIX       wds: <http://www.wikidata.org/entity/statement/>
    PREFIX       wdv: <http://www.wikidata.org/value/>
    PREFIX       wdt: <http://www.wikidata.org/prop/direct/>
    PREFIX         p: <http://www.wikidata.org/prop/>
    PREFIX        ps: <http://www.wikidata.org/prop/statement/>
    PREFIX        pq: <http://www.wikidata.org/prop/qualifier/>
    PREFIX      rdfs: <http://www.w3.org/2000/01/rdf-schema#>
    """

PREFIXES = POLITIQUICES_PREFIXES + WIKIDATA_PREFIXES
