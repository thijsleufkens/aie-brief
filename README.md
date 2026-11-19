# AIE-brief

Een wekelijkse nieuwsbrief van een YouTube-kanaal dat je niet bij kunt houden. Gebouwd voor
[AI Engineer](https://www.youtube.com/@aiDotEngineer): elke nacht de nieuwe talks ophalen,
de automatische ondertitels lezen en door een **lokaal taalmodel** laten omzetten in een kort
nieuwsbericht. Elke zondag één mail met:

- een opening die de thema's van de week verbindt;
- een strook met alle talks van de week (breedte = duur), de kijktips gemarkeerd;
- per talk een kop, een lead, "De details" en een oordeel: **kijken**, **lezen volstaat** of
  **overslaan**;
- bij de kijktips een tijdbalk met links die direct naar de interessante momenten springen.

Geen API-key van YouTube, geen cloud-LLM, geen website: alleen een mail.

## Hoe het werkt

```
yt-dlp (plat, /videos-tab, talks ≥ 4 min)  →  youtube-transcript-api  →  taalmodel (JSON-schema)
        →  SQLite  →  zondag: opening + mail via Postmark
```

- **Waarom niet de RSS-feed?** Die toonde bij dit kanaal vooral clips van een minuut en geen
  enkele echte talk.
- **Waarom een harde grens op kijktips?** Een klein lokaal model is een goede schrijver maar een
  slechte beoordelaar: met een journalistieke toon vond het 9 van de 12 talks "kijken waard".
  De code laat er hooguit 3 door, op score.
- **De lens is een tekstbestand.** Wie de lezer is, bepaalt het oordeel. Schrijf je eigen lens in
  `prompts/lezer.md` (staat in `.gitignore`) of zet `AIE_LEZER` naar een ander bestand; zonder
  eigen lens geldt `prompts/lezer.voorbeeld.md`.

## Zelf draaien

Nodig: Python 3.12, een OpenAI-compatibel endpoint met `response_format: json_schema` (wij
gebruiken llama.cpp met Qwen), en voor de mail een Postmark-token.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
export QWEN_BASE_URL=http://localhost:8080/v1   # jouw endpoint
.venv/bin/python -m aiebrief.cli nacht           # ophalen + samenvatten
.venv/bin/python -m aiebrief.cli editie --droog  # mail als data/voorbeeld.html
```

| Variabele | Betekenis |
|---|---|
| `QWEN_BASE_URL`, `QWEN_MODEL` | endpoint en modelnaam |
| `AIE_KANAAL_URL` | het kanaal (de `/videos`-tab) |
| `AIE_NAAM` | naam van de brief (onderwerp en kop) |
| `AIE_LEZER` | pad naar je eigen lens |
| `QWEN_VERBODEN_HOST` | optioneel: host waar de client nooit rechtstreeks heen mag |
| `POSTMARK_TOKEN`, `MAIL_FROM`, `MAIL_TO` | verzending |
| `HEARTBEAT_DIR` | optioneel: heartbeat-bestand na elke geslaagde run |
| `POSTGRAM_URL`, `POSTGRAM_KEY` | optioneel: editie bewaren in [Postgram](https://github.com/ivo-toby/postgram) |

Op een server: `deploy.sh` (vul eerst `deploy.env` in, zie `deploy.env.example`) plaatst de
code, maakt een venv en zet twee systemd-timers aan: nacht 01:00 en zondag 08:00
(Europe/Amsterdam). De units in `systemd/` zijn sjablonen: `deploy.sh` vult de installatiemap
(`DEST`) en de gebruiker (`RUN_USER`) in uit `deploy.env`.

## Grenzen

- Samenvattingen komen uit automatische ondertitels plus een klein model: details kunnen
  afwijken. De tijdstempels brengen je naar de bron.
- YouTube kan het IP van een datacenter blokkeren voor transcripten. Dan faalt de nachtrun
  zichtbaar (geen heartbeat).
- Gebouwd voor één lezer en één kanaal tegelijk; een tweede kanaal is een tweede installatie
  met eigen `.env`.

Licentie: 0BSD.
