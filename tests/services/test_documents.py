import io

from PIL import Image

from backend.app.services.onboarding.documents import (
    check_cross_references,
    check_image_quality,
    check_mime_and_size,
    check_mrz,
)

# The canonical ICAO 9303 sample MRZ (used in the mrz library's own test suite).
VALID_TD3_MRZ = (
    "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"
)


def _png_bytes(width: int, height: int, color=(128, 128, 128)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format="PNG")
    return buf.getvalue()


def test_mime_and_size_accepts_real_png():
    result = check_mime_and_size(_png_bytes(800, 600), "image/png")
    assert result.result == "pass"


def test_mime_and_size_rejects_oversized_file():
    oversized = b"\x00" * (11 * 1024 * 1024)
    result = check_mime_and_size(oversized, "image/png")
    assert result.result == "fail"


def test_image_quality_rejects_low_resolution():
    result = check_image_quality(_png_bytes(100, 100))
    assert result.result == "fail"
    assert "resolution" in result.details["reason"]


def test_image_quality_passes_sharp_high_res_image():
    # A checkerboard has sharp edges everywhere, so Laplacian variance is
    # high; using 200/50 rather than 255/0 keeps it under the glare
    # (overexposure) heuristic, which is a separate concern from sharpness.
    img = Image.new("L", (800, 800))
    pixels = img.load()
    for x in range(800):
        for y in range(800):
            pixels[x, y] = 200 if (x // 20 + y // 20) % 2 == 0 else 50
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    result = check_image_quality(buf.getvalue())
    assert result.result == "pass"


def test_mrz_checksum_valid_sample_passes():
    result, fields = check_mrz(f"some header text\n{VALID_TD3_MRZ}\nfooter")
    assert result.result == "pass"
    assert fields is not None
    assert fields["surname"] == "ERIKSSON"


def test_mrz_no_text_warns():
    result, fields = check_mrz(None)
    assert result.result == "warn"
    assert fields is None


def test_mrz_tampered_checksum_fails():
    tampered = VALID_TD3_MRZ.replace("UTO7408122F", "UTO7408129F")  # corrupt a check digit
    result, fields = check_mrz(tampered)
    assert result.result == "fail"
    assert fields is None


def test_cross_reference_matches_name_and_dob():
    # "UTO" is ICAO's fictional example country, not a real ISO code, so it
    # is compared as-is rather than resolved through pycountry here. The
    # sample document's own expiry (2012) is genuinely in the past, so the
    # overall result is "fail" on that basis alone; what this test actually
    # checks is that name and DOB, the two fields under test, both match.
    _mrz_result, fields = check_mrz(VALID_TD3_MRZ)
    result = check_cross_references(
        fields,
        application_full_name="Anna Maria Eriksson",
        application_dob_iso="1974-08-12",
        application_nationality="UTO",
    )
    issues = result.details.get("issues", [])
    assert not any("name mismatch" in i for i in issues)
    assert "date of birth mismatch" not in issues
    assert "issuing country inconsistent with stated nationality" not in issues
    assert result.details["name_score"] > 95


def test_cross_reference_flags_name_mismatch():
    _mrz_result, fields = check_mrz(VALID_TD3_MRZ)
    result = check_cross_references(
        fields,
        application_full_name="Someone Completely Different",
        application_dob_iso=None,
        application_nationality=None,
    )
    assert result.result == "fail"
    assert any("name mismatch" in issue for issue in result.details["issues"])


def test_cross_reference_no_mrz_warns():
    result = check_cross_references(
        None, application_full_name="Anyone", application_dob_iso=None, application_nationality=None
    )
    assert result.result == "warn"
