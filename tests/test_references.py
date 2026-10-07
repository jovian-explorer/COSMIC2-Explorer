"""Every DOI the app shows points at the work it is quoted for.

Round 4 found 23 variables citing ``10.1029/97RG02808`` (no such DOI) and
others pointing at unrelated papers (a Mars 2020 overview for the ivmL2m
ion density, an Arctic Ocean paper for electron density).  Each DOI below
was resolved at doi.org and its first author checked; the offline test
keeps the code to that list, and the opt-in network test re-resolves them.
"""
from __future__ import annotations

import os
import re
import urllib.request
from pathlib import Path

import pytest

from cosmic2 import catalog, vocab

# DOI -> family name of the first author (or the data set's publisher)
VERIFIED = {
    "10.1029/97JD01569": "Kursinski",
    "10.1029/2019GL086841": "Schreiner",
    "10.1002/qj.49712656606": "Healy",
    "10.3390/atmos13091409": "Weiss",
    "10.1007/s11214-017-0383-3": "Heelis",
    "10.1029/2010RS004591": "Carrano",
    "10.1109/PROC.1982.12313": "Yeh",
    "10.1016/S1364-6826(97)00056-4": "Syndergaard",
    "10.1175/1520-0493(1980)108<1046:TCOEPT>2.0.CO;2": "Bolton",
    "10.1029/1999RS900034": "Schreiner",
    "10.1029/1999RS002199": "Syndergaard",
    "10.1029/97JD02400": "Rocken",
    "10.1002/qj.49705322103": "Brunt",
    "10.1007/s11214-016-0275-y": "Laundal",
    "10.1016/0021-9169(63)90150-8": "Briggs",
    "10.1007/978-3-211-73017-1": "",            # Hofmann-Wellenhof et al. (book)
    "10.1016/C2009-0-63394-8": "",              # Holton & Hakim (book)
    "10.6028/NBS.MONO.92": "Bean",
    "10.1142/3171": "Rodgers",
    "10.1086/111096": "Fjeldbo",
    "10.1109/JRPROC.1953.274297": "Smith",
    "10.1029/1999JD901005": "Tsuda",
    "10.5065/T353-C093": "UCAR",
    "10.3390/rs12244099": "Ho",
    "10.1175/JTECH-D-20-0209.1": "Rieckh",
    "10.5194/amt-7-3947-2014": "Rieckh",
}

FRONTEND = Path(__file__).resolve().parents[1] / "src" / "cosmic2" / "frontend"


def _used() -> set[str]:
    dois = {v["doi"] for v in vocab.VAR_INFO.values() if v.get("doi")}
    dois |= {p.doi for p in catalog.PRODUCTS.values() if p.doi}
    for f in [FRONTEND / "index.html", FRONTEND / "help.html",
              *(FRONTEND / "js").glob("*.js")]:
        dois |= set(re.findall(r"doi\.org/(10\.[^\s\"'<}]+[^\s\"'<}.,)])",
                               f.read_text(encoding="utf-8")))
    dois.discard("${v.doi}")
    return dois


def test_every_doi_shown_is_a_verified_one():
    unknown = _used() - set(VERIFIED)
    assert not unknown, f"unverified DOIs: {sorted(unknown)}"


@pytest.mark.network
@pytest.mark.skipif(os.environ.get("COSMIC2_NETWORK_TESTS") != "1",
                    reason="set COSMIC2_NETWORK_TESTS=1 to resolve DOIs")
@pytest.mark.parametrize("doi", sorted(VERIFIED))
def test_doi_resolves_to_its_author(doi):
    req = urllib.request.Request(
        "https://doi.org/" + doi,
        headers={"Accept": "text/x-bibliography; style=apa"})
    text = urllib.request.urlopen(req, timeout=60).read().decode("utf-8")
    assert VERIFIED[doi] in text
