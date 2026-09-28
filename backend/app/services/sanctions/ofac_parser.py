"""Streaming parser for the OFAC SDN XML export.

The SDN XML uses a default namespace
(https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML).
Tag matching must be namespace aware; plain tag names silently match nothing and
would make the pipeline appear to succeed with zero records. See PROJECT_PLAN.md
section 5.1 (implementation notes) and Phase 1, asset `ofac_sdn_parsed`.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

SDN_NAMESPACE = "https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/XML"
_NSMAP = {"ns": SDN_NAMESPACE}


class SdnParseError(Exception):
    """Raised when the SDN XML cannot be parsed or fails a sanity check."""


@dataclass
class SdnAka:
    uid: int | None
    aka_type: str | None
    category: str | None
    first_name: str | None
    last_name: str | None


@dataclass
class SdnAddress:
    uid: int | None
    address1: str | None
    address2: str | None
    city: str | None
    state_or_province: str | None
    postal_code: str | None
    country: str | None


@dataclass
class SdnIdentifier:
    uid: int | None
    id_type: str | None
    id_number: str | None
    id_country: str | None
    issue_date: str | None
    expiration_date: str | None


@dataclass
class SdnDateOfBirth:
    uid: int | None
    date_of_birth: str | None
    main_entry: bool


@dataclass
class SdnPlaceOfBirth:
    uid: int | None
    place_of_birth: str | None
    main_entry: bool


@dataclass
class SdnNationality:
    uid: int | None
    country: str | None
    main_entry: bool


@dataclass
class SdnEntry:
    uid: int
    first_name: str | None
    last_name: str | None
    title: str | None
    sdn_type: str | None
    remarks: str | None
    programs: list[str] = field(default_factory=list)
    akas: list[SdnAka] = field(default_factory=list)
    addresses: list[SdnAddress] = field(default_factory=list)
    identifiers: list[SdnIdentifier] = field(default_factory=list)
    dates_of_birth: list[SdnDateOfBirth] = field(default_factory=list)
    places_of_birth: list[SdnPlaceOfBirth] = field(default_factory=list)
    nationalities: list[SdnNationality] = field(default_factory=list)
    citizenships: list[SdnNationality] = field(default_factory=list)

    @property
    def primary_name(self) -> str:
        if self.sdn_type == "Individual":
            parts = [p for p in (self.first_name, self.last_name) if p]
            return " ".join(parts)
        return self.last_name or self.first_name or ""


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _text(el: etree._Element, child_tag: str) -> str | None:
    found = el.find(f"ns:{child_tag}", _NSMAP)
    if found is None or found.text is None:
        return None
    value = found.text.strip()
    return value or None


def _bool_text(el: etree._Element, child_tag: str) -> bool:
    value = _text(el, child_tag)
    return (value or "").strip().lower() == "true"


def _int_text(el: etree._Element, child_tag: str) -> int | None:
    value = _text(el, child_tag)
    return int(value) if value is not None else None


def _parse_aka(el: etree._Element) -> SdnAka:
    return SdnAka(
        uid=_int_text(el, "uid"),
        aka_type=_text(el, "type"),
        category=_text(el, "category"),
        first_name=_text(el, "firstName"),
        last_name=_text(el, "lastName"),
    )


def _parse_address(el: etree._Element) -> SdnAddress:
    return SdnAddress(
        uid=_int_text(el, "uid"),
        address1=_text(el, "address1"),
        address2=_text(el, "address2"),
        city=_text(el, "city"),
        state_or_province=_text(el, "stateOrProvince"),
        postal_code=_text(el, "postalCode"),
        country=_text(el, "country"),
    )


def _parse_identifier(el: etree._Element) -> SdnIdentifier:
    return SdnIdentifier(
        uid=_int_text(el, "uid"),
        id_type=_text(el, "idType"),
        id_number=_text(el, "idNumber"),
        id_country=_text(el, "idCountry"),
        issue_date=_text(el, "issueDate"),
        expiration_date=_text(el, "expirationDate"),
    )


def _parse_dob(el: etree._Element) -> SdnDateOfBirth:
    return SdnDateOfBirth(
        uid=_int_text(el, "uid"),
        date_of_birth=_text(el, "dateOfBirth"),
        main_entry=_bool_text(el, "mainEntry"),
    )


def _parse_pob(el: etree._Element) -> SdnPlaceOfBirth:
    return SdnPlaceOfBirth(
        uid=_int_text(el, "uid"),
        place_of_birth=_text(el, "placeOfBirth"),
        main_entry=_bool_text(el, "mainEntry"),
    )


def _parse_nationality(el: etree._Element) -> SdnNationality:
    return SdnNationality(
        uid=_int_text(el, "uid"),
        country=_text(el, "country"),
        main_entry=_bool_text(el, "mainEntry"),
    )


def _parse_entry(entry_el: etree._Element) -> SdnEntry:
    uid = _int_text(entry_el, "uid")
    if uid is None:
        raise SdnParseError("sdnEntry missing required uid")

    programs = [
        (p.text or "").strip()
        for p in entry_el.findall("ns:programList/ns:program", _NSMAP)
        if p.text and p.text.strip()
    ]
    akas = [_parse_aka(a) for a in entry_el.findall("ns:akaList/ns:aka", _NSMAP)]
    addresses = [_parse_address(a) for a in entry_el.findall("ns:addressList/ns:address", _NSMAP)]
    identifiers = [_parse_identifier(i) for i in entry_el.findall("ns:idList/ns:id", _NSMAP)]
    dobs = [
        _parse_dob(d) for d in entry_el.findall("ns:dateOfBirthList/ns:dateOfBirthItem", _NSMAP)
    ]
    pobs = [
        _parse_pob(p) for p in entry_el.findall("ns:placeOfBirthList/ns:placeOfBirthItem", _NSMAP)
    ]
    nationalities = [
        _parse_nationality(n) for n in entry_el.findall("ns:nationalityList/ns:nationality", _NSMAP)
    ]
    citizenships = [
        _parse_nationality(c) for c in entry_el.findall("ns:citizenshipList/ns:citizenship", _NSMAP)
    ]

    return SdnEntry(
        uid=uid,
        first_name=_text(entry_el, "firstName"),
        last_name=_text(entry_el, "lastName"),
        title=_text(entry_el, "title"),
        sdn_type=_text(entry_el, "sdnType"),
        remarks=_text(entry_el, "remarks"),
        programs=programs,
        akas=akas,
        addresses=addresses,
        identifiers=identifiers,
        dates_of_birth=dobs,
        places_of_birth=pobs,
        nationalities=nationalities,
        citizenships=citizenships,
    )


@dataclass
class PublishInfo:
    publish_date: dt.date | None
    record_count: int | None


def iter_sdn_entries(xml_path: str | Path) -> Iterator[SdnEntry]:
    """Stream-parse sdnEntry elements one at a time, releasing memory as it goes."""
    context = etree.iterparse(str(xml_path), events=("end",), tag=f"{{{SDN_NAMESPACE}}}sdnEntry")
    for _, elem in context:
        yield _parse_entry(elem)
        elem.clear()
        while elem.getprevious() is not None:
            del elem.getparent()[0]


def parse_publish_info(xml_path: str | Path) -> PublishInfo:
    """Extract the publshInformation block without loading the full document."""
    context = etree.iterparse(
        str(xml_path), events=("end",), tag=f"{{{SDN_NAMESPACE}}}publshInformation"
    )
    for _, elem in context:
        date_text = _text(elem, "Publish_Date")
        count_text = _text(elem, "Record_Count")
        publish_date = None
        if date_text:
            publish_date = dt.datetime.strptime(date_text, "%m/%d/%Y").date()  # noqa: DTZ007
        record_count = int(count_text) if count_text else None
        elem.clear()
        return PublishInfo(publish_date=publish_date, record_count=record_count)
    raise SdnParseError("publshInformation block not found in SDN XML")


def count_entries(xml_path: str | Path) -> int:
    return sum(1 for _ in iter_sdn_entries(xml_path))
