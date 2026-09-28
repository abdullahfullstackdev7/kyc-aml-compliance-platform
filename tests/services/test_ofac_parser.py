from pathlib import Path

import pytest

from backend.app.services.sanctions.ofac_parser import (
    SdnParseError,
    iter_sdn_entries,
    parse_publish_info,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "sdn_sample.xml"


def test_parse_publish_info():
    info = parse_publish_info(FIXTURE)
    assert info.record_count == 3
    assert info.publish_date.isoformat() == "2026-09-23"


def test_iter_sdn_entries_count_matches_declared():
    info = parse_publish_info(FIXTURE)
    entries = list(iter_sdn_entries(FIXTURE))
    assert len(entries) == info.record_count


def test_entity_primary_name_uses_last_name():
    entries = {e.uid: e for e in iter_sdn_entries(FIXTURE)}
    assert entries[36].primary_name == "AEROCARIBBEAN AIRLINES"


def test_individual_primary_name_combines_first_and_last():
    entries = {e.uid: e for e in iter_sdn_entries(FIXTURE)}
    assert entries[2676].primary_name == "Dr. Ayman AL ZAWAHIRI"


def test_akas_parsed_with_category_and_names():
    entries = {e.uid: e for e in iter_sdn_entries(FIXTURE)}
    akas = entries[2676].akas
    assert len(akas) == 2
    strong = next(a for a in akas if a.category == "strong")
    assert strong.first_name == "Ayman"
    assert strong.last_name == "AL-ZAWAHIRI"


def test_identifiers_parsed():
    entries = {e.uid: e for e in iter_sdn_entries(FIXTURE)}
    ids = entries[2676].identifiers
    assert ids[0].id_type == "Passport"
    assert ids[0].id_number == "1084010"
    assert ids[0].id_country == "Egypt"


def test_date_of_birth_parsed():
    entries = {e.uid: e for e in iter_sdn_entries(FIXTURE)}
    dob = entries[2676].dates_of_birth[0]
    assert dob.date_of_birth == "19 Jun 1951"
    assert dob.main_entry is True


def test_addresses_parsed():
    entries = {e.uid: e for e in iter_sdn_entries(FIXTURE)}
    address = entries[36].addresses[0]
    assert address.city == "Havana"
    assert address.country == "Cuba"


def test_missing_namespace_yields_zero_entries(tmp_path):
    bad_xml = tmp_path / "bad.xml"
    bad_xml.write_text('<?xml version="1.0"?><sdnList><sdnEntry><uid>1</uid></sdnEntry></sdnList>')
    entries = list(iter_sdn_entries(bad_xml))
    assert entries == []


def test_entry_missing_uid_raises(tmp_path):
    from lxml import etree

    from backend.app.services.sanctions.ofac_parser import SDN_NAMESPACE, _parse_entry

    xml = f'<sdnEntry xmlns="{SDN_NAMESPACE}"><lastName>NO UID</lastName></sdnEntry>'
    elem = etree.fromstring(xml.encode())
    with pytest.raises(SdnParseError):
        _parse_entry(elem)
