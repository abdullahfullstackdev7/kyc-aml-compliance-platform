# Dataset

This directory holds the data sources SentinelKYC ingests and generates. See
`PROJECT_PLAN.md` section 5 for the full specification.

## Sources implemented in Phase 1

| Dataset | Source | License | Status |
|---|---|---|---|
| OFAC SDN list (XML) | Sanctions List Service | U.S. Government work, public domain | Ingested by the Dagster pipeline in `pipelines/` |

Other sources listed in the project plan (SDN Advanced, Consolidated non-SDN, UN
Consolidated List, FATF jurisdictions, MIDV-2020 documents, synthetic tenants and
customers) are introduced in later phases and are not yet part of this directory.

## Refreshing the OFAC SDN list

The Dagster schedule `ofac_sdn_poll_schedule` polls the list every 6 hours while
`dagster-daemon` is running. To fetch on demand without Dagster:

```
uv run python dataset/scripts/download_ofac.py
```

This performs the same conditional GET (ETag / Last-Modified / SHA-256 comparison)
as the `ofac_sdn_raw` asset and writes the file to `raw/ofac/sdn/`.

## Folder layout

```
dataset/
├── README.md
├── ATTRIBUTION.md
├── raw/ofac/sdn/          # every fetched SDN.XML version, named YYYY-MM-DD_<sha8>.xml
├── processed/              # normalized Parquet output (sdn_entities.parquet, sdn_names.parquet)
└── scripts/
    ├── download_ofac.py    # manual fetch outside of the Dagster schedule
    └── load_all.py         # applies migrations and reports pipeline status
```

`raw/`, `processed/`, `synthetic/` and `documents/` are gitignored; only scripts,
reference CSVs and this documentation are committed.

## Loading the database

```
make migrate
make seed
```

`make seed` currently applies migrations and runs the sanctions ingestion pipeline
in-process. Synthetic tenant, customer and document generation is introduced in
later phases per the project plan.
