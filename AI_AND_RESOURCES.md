# AI use, open data and libraries

Disclosure for HackYeah 2026, task "ImpactHer: Technology for Real Change".

## AI tools

- **Claude (Anthropic), used through Claude Code**, for planning, code generation, tests, the seed and sticker scripts, the PL/EN/UK interface texts, the generated demo data and this documentation. It worked milestone by milestone from the team's written specification. Every milestone was run and checked: automated tests, browser checks and a Lighthouse run.
- **Claude** was also used to write the concept document that the specification is based on.
- The team reviewed the generated code and understands it. Each technical decision is commented in the code and summarised in the README.

## Timeline

From file timestamps and git history (Europe/Warsaw time):

| When | What |
| --- | --- |
| 3 Oct 2026, 13:59 | Repository created (two test commits, no project code) |
| 3 Oct 2026, 16:57 | First project file created (project skeleton) |
| 4 Oct 2026, 00:58 | First prototype commit ("project prototype") |
| 4 Oct 2026 | Deploy, optional features, documentation |

## Open data

- **Kraków public toilets:** the "ZIW Toalety miejskie" dataset by Zarząd Infrastruktury Wodnej w Krakowie, published on MSIP Kraków: https://msip.krakow.pl/dataset/3121. It is read from the city's ArcGIS service `Obserwatorium/WT_WC_2023`, layer "Toalety publiczne", in WGS84. A snapshot is stored in `data/krakow_toilets.geojson`. 46 of its 50 toilets are imported; 4 are marked in the data as not working.
- **OpenStreetMap:** map tiles from tile.openstreetmap.org and walking routes through openstreetmap.org (OSRM). © OpenStreetMap contributors, ODbL. The attribution is shown on every map.
- **Route links** to Google Maps and Apple Maps are plain links. No API keys are used and no data is sent to these services by the app.

## Real data and demo data

- **Real:** the 46 city toilets above (`krk-1001` to `krk-1050`, `is_demo = 0`). The 2 PLN entry fee is a flat assumption from our brief, not a value in the dataset.
- **Demo:** every other seeded point (`krk-0001` to `krk-0026` and `krk-demo`), every seeded event and every seeded Urgent search. All of these have `is_demo = 1`. Names and positions are illustrative; they are not real partner venues. The map and the city dashboard show a "demo data" note whenever such rows exist.
- **Marks made live** during the demo are real rows (`is_demo = 0`).

## Libraries and assets in the app

| Library / asset | Use | Licence |
| --- | --- | --- |
| FastAPI | web framework, `/docs` | MIT |
| Uvicorn | web server | BSD-3-Clause |
| Pydantic | data validation | MIT |
| qrcode | QR stickers | BSD |
| Pillow | stickers and icons | MIT-CMU (HPND) |
| tzdata | Europe/Warsaw time zone data | Apache-2.0 |
| Leaflet 1.9.4 (cdnjs) | maps | BSD-2-Clause |
| Nunito font | interface and stickers | SIL Open Font License 1.1 |
| pytest, httpx | tests | MIT, BSD-3-Clause |

Nunito (© The Nunito Project Authors) comes from Google Fonts. It is self-hosted in `static/fonts/` as woff2 subsets, so pages make no requests to Google. A TTF copy in `scripts/fonts/` is used for the printed stickers, and `OFL.txt` sits next to both.

## Tools used during development (not part of the app)

- **Docker:** builds and runs the image for deployment.
- **Render:** hosting, free plan.
- **Lighthouse:** performance and accessibility checks (Apache-2.0).
- **Headless Google Chrome:** browser checks and screenshots.
- **OpenCV:** decoding the generated QR codes to verify them.
