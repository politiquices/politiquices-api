from typing import List, Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class Element:
    wiki_id: str
    label: str


@dataclass
class PoliticalParty:
    wiki_id: str
    name: str
    image_url: str
    # Years of the P102 statement's P580/P582 qualifiers, when Wikidata has them.
    # `current` is False only when every statement for this party has an end date.
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    current: bool = True


@dataclass
class Person:
    # pylint: disable=too-many-instance-attributes
    wiki_id: str
    name: Optional[str] = None
    image_url: Optional[str] = None
    parties: Optional[List[PoliticalParty]] = None
    positions: Optional[List[Element]] = None
    education: Optional[List[Element]] = None
    occupations: Optional[List[Element]] = None
    governments: Optional[List[Element]] = None
    assemblies: Optional[List[Element]] = None
    relationships_charts: Optional[List[Dict[str, Any]]] = None
