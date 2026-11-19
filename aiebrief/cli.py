"""aie-brief nacht | editie [--droog] | voorbeeld"""
import argparse
import logging
import sys
import time
from datetime import date, datetime, timezone

import json
from pathlib import Path

from . import bron, config, db, mail, postgram, samenvat, week
from .qwen import Qwen, QwenFout

log = logging.getLogger("aiebrief")


def schrijf_heartbeat(naam: str) -> None:
    if not config.HEARTBEAT_DIR:
        return
    try:
        (Path(config.HEARTBEAT_DIR) / naam).write_text(datetime.now(timezone.utc).isoformat())
    except OSError as e:
        log.warning("heartbeat %s: %s", naam, e)


def ontdek(con, videos: list[bron.Video]) -> int:
    """Nieuwe talks opslaan. Clips en premieres (duur onbekend) slaan we nu over; een premiere
    komt vanzelf terug zodra de duur bekend is. Eerste run: alleen de nieuwste talks, de rest
    als 'genegeerd' zodat ze later niet alsnog als nieuw binnenkomen."""
    eerste = db.is_leeg(con)
    talks = [v for v in videos if v.duur_s and v.duur_s >= config.MIN_DUUR_S]
    nieuw = 0
    for i, v in enumerate(talks):
        status = "genegeerd" if eerste and i >= config.EERSTE_RUN_AANTAL else "nieuw"
        if db.voeg_toe(con, v.id, v.titel, i, status) and status == "nieuw":
            nieuw += 1
    return nieuw


def nacht() -> int:
    con = db.open_db(config.DB_PATH)
    nieuw = ontdek(con, bron.haal_lijst())
    log.info("lijst: %d nieuwe talks", nieuw)
    qwen = Qwen()
    klaar = opgehaald = 0
    for v in db.te_doen(con):
        if v["transcript"]:
            t = bron.Transcript(v["transcript"], v["duur_s"] or 0, v["woorden"] or 0, bool(v["afgekapt"]))
        else:
            if opgehaald:
                time.sleep(config.PAUZE_S)  # YouTube rate-limit: rustig aan
            try:
                t = bron.haal_transcript(v["id"])
            except bron.GeenTranscript as e:
                log.info("%s: geen transcript (%s), poging %d", v["id"], e, v["pogingen"] + 1)
                db.markeer_mislukt(con, v["id"], str(e), config.MAX_POGINGEN)
                continue
            opgehaald += 1
            db.bewaar_transcript(con, v["id"], t.tekst, t.duur_s, t.woorden, t.afgekapt)
        try:
            s, meta = samenvat.vat_samen(qwen, v["titel"], t.tekst, t.duur_s, t.afgekapt)
        except QwenFout as e:
            log.error("%s: qwen faalde: %s", v["id"], e)
            raise
        db.markeer_klaar(con, v["id"], s, t.duur_s, t.woorden)
        klaar += 1
        log.info("%s: %s [%s, %d/5] %.0fs", v["id"], s["kop"], s["oordeel"], s["score"], meta["latency_s"])
    log.info("nacht klaar: %d samengevat", klaar)
    schrijf_heartbeat("aie-brief-nacht")
    return 0


def editie(droog: bool = False) -> int:
    con = db.open_db(config.DB_PATH)
    videos = db.voor_editie(con)
    vandaag = date.today()
    nummer = db.editienummer(con)
    if not videos:
        log.info("niets nieuws deze week; geen mail")
        if not droog:
            schrijf_heartbeat("aie-brief-editie")
        return 0
    g = mail.groepeer(videos)
    intro = week.schrijf_intro([(v["titel"], json.loads(v["samenvatting"])) for v in videos if v["status"] == "klaar"])
    if droog:
        pad = config.DATA_DIR / "voorbeeld.html"
        pad.write_text(mail.html_body(nummer, vandaag, g, intro), encoding="utf-8")
        print(mail.onderwerp(nummer, g))
        print(f"voorbeeld: {pad}")
        return 0
    if not mail.verstuur(nummer, vandaag, g, intro):
        log.error("mail niet verstuurd; editie niet vastgelegd")
        return 1
    db.leg_editie_vast(con, vandaag.isoformat(), [v["id"] for v in videos])
    postgram.bewaar_editie(mail.tekst_body(nummer, vandaag, g, intro), nummer)
    log.info("editie #%d verstuurd: %d talks", nummer, len(videos))
    schrijf_heartbeat("aie-brief-editie")
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    p = argparse.ArgumentParser(prog="aie-brief")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("nacht")
    ed = sub.add_parser("editie")
    ed.add_argument("--droog", action="store_true", help="niet versturen, schrijf data/voorbeeld.html")
    a = p.parse_args(argv)
    if a.cmd == "nacht":
        return nacht()
    return editie(droog=a.droog)


if __name__ == "__main__":
    sys.exit(main())
