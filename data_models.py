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


@dataclass
class Person:
    # pylint: disable=R0902
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
