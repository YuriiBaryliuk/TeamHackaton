# Kropka: 2-minute demo

**Live:** https://kropka-05q6.onrender.com · stage box: https://kropka-05q6.onrender.com/p/krk-demo

## Roles

| Who | Device | Has open |
| --- | --- | --- |
| **Presenter** | Laptop on the big screen | Map `https://kropka-05q6.onrender.com` in tab 1, `/city` in tab 2 |
| **Scanner** | Phone A | The printed `krk-demo` sticker in hand |
| **Steward** | Phone B | `https://kropka-05q6.onrender.com/steward?watch=krk-demo`, screen kept on |

## 10 minutes before going on stage

1. **Fresh demo data:** in the Render dashboard, open service **kropka**, then **Manual Deploy → Deploy latest commit**. This wakes the free server and re-creates the demo data ending "now". Wait until it shows **Live**, about 3 to 5 minutes.
2. **Laptop:** open the map, allow location, zoom so the TAURON Arena area and the city centre are both visible. Open `/city` in a second tab and let it load.
3. **Phone B:** open the steward link above. "Kropka: stoisko HackYeah" must be in the list, with a filled dot.
4. **Phone A:** scan the sticker once to check it opens the page. **Do not tap "Pusto" now.** The same phone can repeat a mark only after 10 minutes.
5. **Check:** the stage dot near TAURON Arena is a **filled dot** on the big screen.

## Script (120 seconds)

**0:00 to 0:15. The problem.** *Map on screen.*
> "In Kraków there are already free pad boxes in cafés, libraries and schools. But nobody knows whether a box is full right now, or where new ones are needed. Kropka is a live map of them."

**0:15 to 0:35. Urgent.** *Click **Pilne**.*
> "One tap when you need it now. Kropka finds the nearest box that is confirmed in stock and open right now, with walking time and a route. If nothing is near, it calmly shows the nearest pharmacy instead. Nobody is left with nothing."

*The card shows "Kropka: stoisko HackYeah" and a dashed line. Close the card.*

**0:35 to 1:05. A real sticker, live.** *The scanner holds up the sticker and scans it.*
> "Every box gets a QR sticker. No app, no account. My teammate scans it and taps **Pusto**."

*Within about 8 seconds the stage dot on the big screen turns into an **empty ring**. Phone B shows the alert "Pusto. Czas uzupełnić!".*
> "The map updates for everyone, and the person looking after this box gets an alert. One refill, one tap on **Uzupełniłam**…"

*The steward taps **Uzupełniłam** on phone B, and the dot fills again on the big screen.*

**1:05 to 1:30. The honest map.** *Point at a pale dot and a grey dot.*
> "Status is shown by shape, not colour: full, half, empty ring. And the map is honest. If nobody confirms a box for 24 hours it fades, and after 72 hours we say 'we don't know'. No accounts, no locations stored, no personal data."

**1:30 to 2:00. Data for the city.** *Switch to tab 2, `/city`.*
> "Every tap becomes anonymous data for the city and NGOs. These rings are white spots: places where people pressed Urgent and found nothing within 10 minutes. The station and Nowa Huta. This is where the next boxes should go. Kropka: a dot on the map, and a box where it's needed."

## If something goes wrong

| Problem | Do this |
| --- | --- |
| Map takes long to load (server was asleep) | Talk through the problem slide for 20 seconds, then reload. |
| Laptop location is wrong or blocked | Urgent offers **"Szukaj od środka mapy"**: centre the map on TAURON Arena and tap it. |
| Phone A gets "Twój znak już jest zapisany" | That phone tapped within the last 10 minutes. Use phone B or the presenter's phone to scan. |
| Dot does not change after 10 s | Reload the map tab (the server keeps the change). |
| Render is down | Plan B in the README: run locally plus `cloudflared tunnel`, then show the sticker for the new URL on a second screen. |
| No internet at all | Use the slides with `docs/screenshots/`. |

## Slides: screenshots

All screenshots are in `docs/screenshots/`.

| File | Slide |
| --- | --- |
| `01_map.png` | The live map: shapes, faded dots |
| `02_urgent.png` | Urgent finds the nearest box |
| `02b_urgent_fallback_night.png` | Nothing near at night: the 24-hour pharmacy instead |
| `03_qr_page.png` | The QR page: three buttons |
| `04_dashboard.png` | City dashboard: white spots |
| `05_steward_alert.png` | Steward alert "Pusto. Czas uzupełnić!" |
| `06_sticker.png` | The printed sticker |

## Likely jury questions

- **"Can't people send fake marks?"** Rate limits: one mark of the same kind per box per device per 10 minutes, and 30 per day. Marks can also be required to come from within 150 m of the box. Statuses fade, so one bad mark doesn't stick. Steward and partner marks are stored separately and can carry more weight later.
- **"What about privacy and GDPR?"** There are no accounts and no personal data. Locations are rounded to about 100 m or thrown away. The only identifier is a salted hash of a random cookie, used for rate limiting.
- **"Is the data real?"** The 46 city toilets come from Kraków open data. The partner points and the 30 days of activity are demo data, clearly marked in the database and in the UI.
- **"Why not a native app?"** A QR scan has to work in 2 seconds for anyone. A web page works on every phone without installing anything, and it can still be installed as an app (PWA).
- **"How does it scale to other cities?"** City is a field on every point, and new cities only need their open data import. The selector already shows Warszawa, Wrocław and Gdańsk as "soon".
