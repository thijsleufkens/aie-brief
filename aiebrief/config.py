"""Instellingen uit de omgeving (op de VPS via EnvironmentFile=.env)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("AIE_DATA", ROOT / "data"))
DB_PATH = Path(os.environ.get("AIE_DB", DATA_DIR / "aie-brief.db"))

# De /videos-tab, niet de RSS-feed: die toont vooral clips van 1 minuut en mist de talks.
KANAAL_URL = os.environ.get("AIE_KANAAL_URL", "https://www.youtube.com/@aiDotEngineer/videos")
LIJST_LENGTE = 40             # zoveel nieuwste video's bekijken we per nacht
MIN_DUUR_S = 240              # korter = clip/teaser, overslaan

# OpenAI-compatibel endpoint (bijvoorbeeld llama.cpp of een proxy ervoor). Geen fallback:
# een vergeten env-var moet falen.
QWEN_BASE_URL = os.environ.get("QWEN_BASE_URL", "")
QWEN_MODEL = os.environ.get("QWEN_MODEL", "Qwen3.8-Flash-Next")
# Optioneel: een host waar de client nooit rechtstreeks heen mag (bijv. als alles via een proxy moet).
VERBODEN_LLM_HOST = os.environ.get("QWEN_VERBODEN_HOST", "")

POSTGRAM_URL = os.environ.get("POSTGRAM_URL", "http://127.0.0.1:3100").rstrip("/")
POSTGRAM_KEY = os.environ.get("POSTGRAM_KEY", "")

# Optioneel: map waarin na elke geslaagde run een heartbeat-bestand komt (monitoring).
HEARTBEAT_DIR = os.environ.get("HEARTBEAT_DIR", "")
# Wie de lezer is: bepaalt het oordeel "kijken of niet". Zet je eigen lens in prompts/lezer.md
# (staat in .gitignore) of wijs er een aan met AIE_LEZER; anders geldt het voorbeeld.
_EIGEN_LEZER = ROOT / "prompts" / "lezer.md"
LEZER_PAD = Path(os.environ.get("AIE_LEZER") or (_EIGEN_LEZER if _EIGEN_LEZER.exists() else ROOT / "prompts" / "lezer.voorbeeld.md"))
BRIEF_NAAM = os.environ.get("AIE_NAAM", "AIE-brief")

MAX_WOORDEN = 45_000          # langere transcripten worden afgekapt
MAX_POGINGEN = 5              # nachten zonder transcript voordat we opgeven
EERSTE_RUN_AANTAL = 12        # eerste run: alleen de nieuwste talks, de rest genegeerd
BLOK_SECONDEN = 60            # [mm:ss]-marker per minuut transcript
PAUZE_S = float(os.environ.get("AIE_PAUZE_S", "20"))          # tussen transcripten (rate-limit)
NACHTBUDGET = int(os.environ.get("AIE_NACHTBUDGET", "12"))    # max nieuwe transcripten per nacht
# "zelf": de server haalt de transcripten. "extern": een andere machine levert ze (zie extern.py),
# de nacht vat alleen samen wat al binnen is.
TRANSCRIPTEN = os.environ.get("AIE_TRANSCRIPTEN", "zelf")
