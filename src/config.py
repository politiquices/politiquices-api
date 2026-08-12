import os
from pathlib import Path

es_haystack = os.getenv("ES_HAYSTACK", default=None)
sparql_endpoint = os.getenv("SPARQL_ENDPOINT", default=None)
wikidata_endpoint = f"{sparql_endpoint}/wikidata/query"
politiquices_endpoint = f"{sparql_endpoint}/politiquices/query"
start_year = 1994
end_year = 2026
LANG = "pt"
NO_IMAGE = "/assets/images/logos/no_picture.jpg"  # the file lives under logos/
PARTY_LOGO_DIR = "assets/images/parties"
_PARTY_LOGO_PREFERENCE = (".svg", ".png", ".jpg", ".jpeg", ".gif")


def party_logo_url(wiki_id: str) -> str:
    """Serve the logo we downloaded, never the Wikidata URL we downloaded it from.

    Three different shapes used to reach the browser — 112 external
    commons.wikimedia.org URLs, some local paths, and one "../assets/..." — because
    three call sites each built this string their own way. Resolving it in one place
    keeps them from drifting again.

    Unlike portraits, party logos keep their original extension (SVG scales and is
    the best choice for a logo), so the extension is looked up on disk instead of
    guessed. 11 parties have a file under two extensions; SVG wins.
    """
    folder = Path(PARTY_LOGO_DIR)
    found = {f.suffix.lower(): f.name for f in folder.glob(f"{wiki_id}.*")} if folder.is_dir() else {}
    for suffix in _PARTY_LOGO_PREFERENCE:
        if suffix in found:
            return f"/{PARTY_LOGO_DIR}/{found[suffix]}"
    if found:
        return f"/{PARTY_LOGO_DIR}/{sorted(found.values())[0]}"
    return NO_IMAGE
STATIC_DATA = "json/"
ENTITIES_BATCH_SIZE = 16  # number of entity cards to read in batch when scrolling down
