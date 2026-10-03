# AI use, open data and libraries

Running disclosure for HackYeah 2026. It will be completed in the final milestone.

## AI tools

- Claude (Anthropic), used through Claude Code, for planning and code generation. The team reviewed the generated code and understands it.

## Open data

- **Kraków public toilets**, the "ZIW Toalety miejskie" dataset from Zarząd Infrastruktury Wodnej w Krakowie, published on MSIP Kraków: https://msip.krakow.pl/dataset/3121. It is read from the city's ArcGIS service `Obserwatorium/WT_WC_2023`, layer "Toalety publiczne". A snapshot is stored in `data/krakow_toilets.geojson`.
- **OpenStreetMap** tiles and routing links. © OpenStreetMap contributors, ODbL.

## Real vs demo data

- Real: the city toilets above, with `is_demo = 0`. The 2 PLN entry fee is a flat assumption from the brief, not a value in the dataset.
- Demo: every point with id `krk-0001` to `krk-0026` and `krk-demo`, every generated event, and every generated Urgent search. All of these have `is_demo = 1`, and their names and positions are illustrative.

## Libraries

| Library | Licence |
| --- | --- |
| FastAPI | MIT |
| Uvicorn | BSD-3-Clause |
| Pydantic | MIT |
| qrcode | BSD |
| Pillow | MIT-CMU (HPND) |
| tzdata | Apache-2.0 |
| pytest | MIT |
| httpx | BSD-3-Clause |
| Leaflet | BSD-2-Clause |

## Fonts

- Nunito, © The Nunito Project Authors, SIL Open Font License 1.1, from Google Fonts. It is self-hosted in `static/fonts/` (woff2 subsets) for the web app, so pages make no requests to Google. A TTF copy in `scripts/fonts/` is used for the printed stickers. `OFL.txt` sits next to both.
