"""Generate a labelled ground-truth set for the screening evaluation harness.

Produces true matches (real SDN individuals with realistic perturbations:
transliteration variants, token reorder, dropped middle name, a typo, or an
added honorific), hard negatives (names that resemble an SDN entry but do not
belong to it, with a conflicting date of birth), and clean queries (Faker
names unrelated to any SDN entry). Labels are used only by the evaluation
harness; they are never loaded into the operational screening tables. See
PROJECT_PLAN.md section 5.3 item 5.

Usage: uv run python dataset/scripts/generate_ground_truth.py [--seed 42]
"""

from __future__ import annotations

import argparse
import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from faker import Faker
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from backend.app.core.config import get_settings
from backend.app.models.sanctions import SanctionsDob, SanctionsEntity

TRUE_MATCH_COUNT = 220
HARD_NEGATIVE_COUNT = 90
CLEAN_COUNT = 140

HONORIFICS = ["Mr", "Dr", "Sheikh", "Haji", "Eng"]

TRANSLITERATION_VARIANTS = {
    "MOHAMMAD": ["Mohammed", "Muhammad", "Mohamad", "Muhammed", "Mohamed"],
    "ABD": ["Abdul", "Abd al", "Abdel"],
    "YOUSEF": ["Yusuf", "Youssef", "Yousif"],
    "HUSSAIN": ["Hussein", "Husain", "Hussayn"],
    "IBRAHIM": ["Ebrahim"],
    "USAMA": ["Osama", "Usamah"],
}

FAKER_LOCALES = ["en_US", "en_GB", "es_MX", "ar_AA", "ru_RU", "de_DE", "fr_FR", "tr_TR"]


def _perturb_typo(word: str, rng: random.Random) -> str:
    if len(word) < 4:
        return word
    idx = rng.randint(1, len(word) - 2)
    return word[:idx] + word[idx + 1] + word[idx] + word[idx + 2 :]


def _apply_transliteration(tokens: list[str], rng: random.Random) -> list[str]:
    result = []
    for token in tokens:
        upper = token.upper()
        if upper in TRANSLITERATION_VARIANTS:
            result.append(rng.choice(TRANSLITERATION_VARIANTS[upper]))
        else:
            result.append(token)
    return result


def _perturb_name(full_name: str, rng: random.Random) -> str:
    tokens = full_name.split()
    if not tokens:
        return full_name

    strategy = rng.choice(["transliterate", "reorder", "drop_middle", "typo", "honorific"])

    if strategy == "transliterate":
        tokens = _apply_transliteration(tokens, rng)
    elif strategy == "reorder" and len(tokens) >= 2:
        rng.shuffle(tokens)
    elif strategy == "drop_middle" and len(tokens) >= 3:
        drop_idx = rng.randint(1, len(tokens) - 2)
        tokens = tokens[:drop_idx] + tokens[drop_idx + 1 :]
    elif strategy == "typo":
        idx = rng.randrange(len(tokens))
        tokens[idx] = _perturb_typo(tokens[idx], rng)
    elif strategy == "honorific":
        tokens = [rng.choice(HONORIFICS)] + tokens

    return " ".join(tokens)


def generate(seed: int, output_path: Path) -> None:
    rng = random.Random(seed)
    fakers = {locale: Faker(locale) for locale in FAKER_LOCALES}
    for f in fakers.values():
        f.seed_instance(seed)

    settings = get_settings()
    engine = create_engine(settings.sync_database_url())
    Session = sessionmaker(bind=engine)

    rows: list[dict] = []

    with Session() as session:
        individuals = (
            session.execute(
                select(SanctionsEntity)
                .where(
                    SanctionsEntity.source == "ofac_sdn", SanctionsEntity.sdn_type == "Individual"
                )
                .order_by(SanctionsEntity.uid)
            )
            .scalars()
            .all()
        )
        rng.shuffle(individuals)

        dob_by_entity: dict[int, list[int]] = {}
        for entity_id, year in session.execute(
            select(SanctionsDob.entity_uid, SanctionsDob.year_only).where(
                SanctionsDob.year_only.isnot(None)
            )
        ):
            dob_by_entity.setdefault(entity_id, []).append(year)

        true_match_pool = individuals[:TRUE_MATCH_COUNT]
        for entity in true_match_pool:
            perturbed = _perturb_name(entity.primary_name, rng)
            years = dob_by_entity.get(entity.id, [])
            dob_year = rng.choice(years) if years and rng.random() < 0.5 else ""
            rows.append(
                {
                    "query_name": perturbed,
                    "dob_year": dob_year,
                    "label": "true_match",
                    "true_entity_uid": entity.uid,
                }
            )

        hard_negative_pool = individuals[TRUE_MATCH_COUNT : TRUE_MATCH_COUNT + HARD_NEGATIVE_COUNT]
        for entity in hard_negative_pool:
            years = dob_by_entity.get(entity.id, [])
            conflicting_year = (rng.choice(years) + rng.randint(15, 40)) if years else ""
            rows.append(
                {
                    "query_name": entity.primary_name,
                    "dob_year": conflicting_year,
                    "label": "hard_negative",
                    "true_entity_uid": "",
                }
            )

        for _ in range(CLEAN_COUNT):
            faker = fakers[rng.choice(FAKER_LOCALES)]
            name = faker.name()
            rows.append(
                {
                    "query_name": name,
                    "dob_year": "",
                    "label": "clean",
                    "true_entity_uid": "",
                }
            )

    rng.shuffle(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["query_name", "dob_year", "label", "true_entity_uid"]
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "dataset" / "synthetic" / "ground_truth_matches.csv"
    )
    args = parser.parse_args()
    generate(args.seed, args.output)


if __name__ == "__main__":
    main()
