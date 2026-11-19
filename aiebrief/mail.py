"""De wekelijkse mail: volledige inhoud, geen website. Tabel-layout met inline CSS
(webfonts en <style> worden in veel mailprogramma's genegeerd). Verzenden via Postmark.
Geen tracking.

Vormgeving: een conferentieprogramma, geen krant. Het ene opvallende
element is de tijdbalk: bovenaan de hele week als strook (een vak per talk, breedte = duur,
kijktips in goudsbloem), en per kijktip de talk als balk met streepjes op de momenten waar je
naartoe springt. Daaromheen rustig: twee kleuren, Georgia voor leestekst, systeemletter voor
koppen. Kleuren staan ook als bgcolor-attribuut zodat clients die omkeren het niet slopen."""
import html
import json
import logging
import os
from datetime import date

import httpx

from . import config
from .bron import mmss

log = logging.getLogger("aiebrief.mail")

SANS = "-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif"
SERIF = "Georgia, 'Times New Roman', serif"
OMGEVING, PAPIER = "#E9ECF2", "#FFFFFF"
INKT, ZACHT, LIJN = "#18202F", "#5A6372", "#DDE2EA"
BLAUW = "#2B44C7"                       # programma-blauw: koppen, links, labels
GOUD, GOUD_BLEEK = "#F2A33A", "#FDF2E1"  # goudsbloem: alleen vlakken (kijktips, momenten)
VAK = {"kijken": GOUD, "samenvatting volstaat": "#AEB9D6", "overslaan": "#DCE1EA", "geen": "#EEF0F4"}
MAX_KIJKEN = 3
SECTIES = [("kijken", "Kijken"), ("samenvatting volstaat", "Lezen volstaat"), ("overslaan", "Overslaan")]
ONDERTITEL = {"kijken": "De video zelf voegt iets toe. Spring naar de gemarkeerde momenten.",
              "samenvatting volstaat": "Goede inhoud, maar dit is het meeste ervan.",
              "overslaan": "Niet voor jou, in één zin waarom."}
MAANDEN = ["januari", "februari", "maart", "april", "mei", "juni", "juli", "augustus", "september",
           "oktober", "november", "december"]


def e(s) -> str:
    return html.escape(str(s or ""), quote=True)


def yt(vid: str, sec: int | None = None) -> str:
    return f"https://www.youtube.com/watch?v={vid}" + (f"&t={sec}s" if sec else "")


def splits_titel(titel: str) -> tuple[str, str]:
    """'Titel | Spreker' -> (titel, spreker)."""
    if " | " in titel:
        t, s = titel.rsplit(" | ", 1)
        return t.strip(), s.strip()
    return titel.strip(), ""


def minuten(duur_s) -> str:
    return f"{round((duur_s or 0) / 60)} min" if duur_s else ""


def groepeer(videos) -> dict:
    """{'kijken': [...], ..., 'geen': [...]}, binnen een groep hoogste score eerst."""
    g = {k: [] for k, _ in SECTIES} | {"geen": []}
    for v in videos:
        if v["status"] != "klaar":
            g["geen"].append((v, None))
            continue
        s = json.loads(v["samenvatting"])
        g[s["oordeel"]].append((v, s))
    for k, _ in SECTIES:
        g[k].sort(key=lambda vs: (-vs[1]["score"], vs[0]["positie"]))
    # Qwen is een slechte beoordelaar: bij een journalistieke toon vindt hij bijna alles
    # kijkwaardig. Daarom een harde grens; de rest schuift door naar "lezen volstaat".
    teveel, g["kijken"] = g["kijken"][MAX_KIJKEN:], g["kijken"][:MAX_KIJKEN]
    g["samenvatting volstaat"] = sorted(teveel + g["samenvatting volstaat"],
                                        key=lambda vs: (-vs[1]["score"], vs[0]["positie"]))
    return g


def voor(s: dict) -> str:
    return s.get("voor_lezer") or s.get("voor_thijs") or ""


def lead(s: dict) -> str:
    return s.get("lead") or s.get("kern", "")


def kijktips(g: dict, n: int = 3) -> list:
    return g["kijken"][:n]


def labeltelling(g: dict) -> list[tuple[str, int]]:
    tel: dict[str, int] = {}
    for k, _ in SECTIES:
        for _, s in g[k]:
            for l in s.get("labels", []):
                tel[l] = tel.get(l, 0) + 1
    return sorted(tel.items(), key=lambda x: (-x[1], x[0]))


def onderwerp(nummer: int, g: dict) -> str:
    n = sum(len(x) for x in g.values())
    k = len(g["kijken"])
    tip = f", {k} om te kijken" if k else ", niets verplichts"
    return f"{config.BRIEF_NAAM} {nummer}: {n} talk{'s' if n != 1 else ''}{tip}"


def tekst_body(nummer: int, datum: date, g: dict, intro: str = "") -> str:
    r = [f"{config.BRIEF_NAAM} {nummer}, {datum_nl(datum)}", ""]
    if intro:
        r += ["DEZE WEEK", intro, ""]
    if kijktips(g):
        r += ["Kijktips:"] + [f"- {s['kop']} ({minuten(v['duur_s'])}): {yt(v['id'])}" for v, s in kijktips(g)] + [""]
    for k, naam in SECTIES:
        if not g[k]:
            continue
        r += [naam.upper(), ""]
        for v, s in g[k]:
            titel, spreker = splits_titel(v["titel"])
            r += [f"[{', '.join(s.get('labels', []))}]", f"* {s['kop']}",
                  f"  {titel}{' — ' + spreker if spreker else ''} ({minuten(v['duur_s'])}, score {s['score']}/5)"]
            if k == "overslaan":
                r.append(f"  {s['waarom']}")
            else:
                r.append(f"  {lead(s)}")
                if k == "kijken" and s.get("context"):
                    r.append(f"  {s['context']}")
                r += ["  De details:"] + [f"  - {i}" for i in s["inzichten"]]
                if k == "kijken":
                    if voor(s):
                        r.append(f"  Voor jou: {voor(s)}")
                    r += [f"  {mmss(m['sec'])} {m['wat']}: {yt(v['id'], m['sec'])}" for m in s["momenten"]]
            r += [f"  {yt(v['id'])}", ""]
    if g["geen"]:
        r += ["ZONDER TRANSCRIPT", ""] + [f"* {v['titel']}: {yt(v['id'])}" for v, _ in g["geen"]] + [""]
    return "\n".join(r)


def datum_nl(d: date) -> str:
    return f"{d.day} {MAANDEN[d.month - 1]} {d.year}"


def uren(sec: int) -> str:
    u, m = divmod(round(sec / 60), 60)
    return f"{u} u {m} min" if u else f"{m} min"


def _a(href: str, inhoud: str, kleur: str = BLAUW, extra: str = "") -> str:
    return f'<a href="{e(href)}" style="color:{kleur};text-decoration:none;{extra}">{inhoud}</a>'


def weekstrook(g: dict) -> str:
    """Een vak per talk, breedte naar duur, kleur naar oordeel. Klikbaar."""
    alle = [(k, v) for k, _ in SECTIES for v, _ in g[k]] + [("geen", v) for v, _ in g["geen"]]
    totaal = sum(max(v["duur_s"] or 600, 60) for _, v in alle) or 1
    cellen = "".join(
        f'<td width="{max(1, round(100 * max(v["duur_s"] or 600, 60) / totaal))}%" bgcolor="{VAK[k]}" '
        f'style="background:{VAK[k]};border-right:3px solid {PAPIER};height:14px;line-height:14px;font-size:0;">'
        f'<a href="{e(yt(v["id"]))}" style="display:block;height:14px;">&nbsp;</a></td>' for k, v in alle)
    return (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="table-layout:fixed;"><tr>{cellen}</tr></table>')


def legenda() -> str:
    def blokje(kleur, tekst):
        return (f'<td bgcolor="{kleur}" width="10" style="background:{kleur};width:10px;height:10px;font-size:0;">&nbsp;</td>'
                f'<td style="padding:0 14px 0 6px;font:12px/1.4 {SANS};color:{ZACHT};white-space:nowrap;">{tekst}</td>')
    return (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:8px;"><tr>'
            f'{blokje(GOUD, "kijken")}{blokje(VAK["samenvatting volstaat"], "lezen volstaat")}'
            f'{blokje(VAK["overslaan"], "overslaan")}</tr></table>')


def tijdbalk(v, s) -> str:
    """De talk als balk; een goudsbloem-streepje op elk moment uit de samenvatting."""
    duur = max(v["duur_s"] or 1, 1)
    punten = sorted({min(99, max(0, round(100 * m["sec"] / duur))) for m in s["momenten"]})
    cellen, vorige = [], 0
    for p in punten:
        if p > vorige:
            cellen.append(f'<td width="{p - vorige}%" bgcolor="{LIJN}" style="background:{LIJN};height:6px;font-size:0;">&nbsp;</td>')
        cellen.append(f'<td width="1%" bgcolor="{GOUD}" style="background:{GOUD};height:6px;font-size:0;">&nbsp;</td>')
        vorige = p + 1
    if vorige < 100:
        cellen.append(f'<td width="{100 - vorige}%" bgcolor="{LIJN}" style="background:{LIJN};height:6px;font-size:0;">&nbsp;</td>')
    balk = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" '
            f'style="table-layout:fixed;margin-top:16px;"><tr>{"".join(cellen)}</tr></table>'
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>'
            f'<td style="font:11px/1.6 {SANS};color:{ZACHT};">0:00</td>'
            f'<td align="right" style="font:11px/1.6 {SANS};color:{ZACHT};">{mmss(duur)}</td></tr></table>')
    rijen = "".join(
        f'<tr><td valign="top" width="52" style="padding:3px 0;font:600 13px/1.45 {SANS};">'
        f'{_a(yt(v["id"], m["sec"]), mmss(m["sec"]))}</td>'
        f'<td style="padding:3px 0;font:13px/1.45 {SANS};color:{INKT};">{e(m["wat"])}</td></tr>' for m in s["momenten"])
    return balk + (f'<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin-top:4px;">{rijen}</table>'
                   if rijen else "")


def _meta(v, s) -> str:
    titel, spreker = splits_titel(v["titel"])
    labels = ", ".join(s.get("labels", []))
    regel2 = ", ".join(x for x in [spreker, minuten(v["duur_s"])] if x)
    return (f'<div style="font:13px/1.5 {SANS};color:{ZACHT};margin-top:4px;">'
            f'<span style="color:{BLAUW};">{e(labels)}</span>{" / " if labels else ""}{e(regel2)}</div>'
            f'<div style="font:italic 13px/1.5 {SERIF};color:{ZACHT};">{e(titel)}</div>')


def _details(s, maat: int) -> str:
    if not s["inzichten"]:
        return ""
    items = "".join(f'<li style="margin:0 0 5px;">{e(i)}</li>' for i in s["inzichten"])
    return (f'<div style="font:600 13px/1 {SANS};color:{INKT};margin-top:14px;">De details</div>'
            f'<ul style="font:{maat}px/1.5 {SANS};color:{INKT};margin:8px 0 0;padding-left:18px;">{items}</ul>')


def talk_kijken(v, s) -> str:
    voor_html = (f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:14px;">'
            f'<tr><td bgcolor="{GOUD_BLEEK}" style="background:{GOUD_BLEEK};border-left:4px solid {GOUD};padding:10px 14px;'
            f'font:14px/1.5 {SANS};color:{INKT};"><b>Voor jou.</b> {e(voor(s))}</td></tr></table>') if voor(s) else ""
    return (f'<tr><td style="padding:26px 0 28px;border-top:1px solid {LIJN};">'
            f'<div style="font:700 22px/1.25 {SANS};color:{INKT};letter-spacing:-0.2px;">{_a(yt(v["id"]), e(s["kop"]), INKT)}</div>'
            f'{_meta(v, s)}'
            f'<div style="font:17px/1.6 {SERIF};color:{INKT};margin-top:12px;">{e(lead(s))}</div>'
            + (f'<div style="font:15px/1.6 {SERIF};color:{ZACHT};margin-top:8px;">{e(s["context"])}</div>' if s.get("context") else "")
            + _details(s, 14) + voor_html + tijdbalk(v, s) + '</td></tr>')


def talk_lezen(v, s) -> str:
    return (f'<tr><td style="padding:20px 0;border-top:1px solid {LIJN};">'
            f'<div style="font:700 18px/1.3 {SANS};color:{INKT};">{_a(yt(v["id"]), e(s["kop"]), INKT)}</div>'
            f'{_meta(v, s)}'
            f'<div style="font:16px/1.6 {SERIF};color:{INKT};margin-top:10px;">{e(lead(s))}</div>'
            f'{_details(s, 14)}</td></tr>')


def talk_overslaan(v, s) -> str:
    titel, spreker = splits_titel(v["titel"])
    return (f'<tr><td style="padding:12px 0;border-top:1px solid {LIJN};font:14px/1.5 {SANS};color:{INKT};">'
            f'{_a(yt(v["id"]), e(s["kop"]), INKT, "font-weight:600;")}'
            f'<span style="color:{ZACHT};">{" (" + e(spreker) + ")" if spreker else ""}. {e(s["waarom"])}</span></td></tr>')


def sectiekop(k: str, naam: str, n: int) -> str:
    return (f'<tr><td style="padding:40px 0 14px;">'
            f'<div style="font:800 26px/1.1 {SANS};color:{BLAUW};letter-spacing:-0.4px;">{naam} '
            f'<span style="font-weight:400;color:{ZACHT};font-size:20px;">{n}</span></div>'
            f'<div style="font:14px/1.5 {SANS};color:{ZACHT};margin-top:6px;">{ONDERTITEL[k]}</div></td></tr>')


def html_body(nummer: int, datum: date, g: dict, intro: str = "") -> str:
    n = sum(len(x) for x in g.values())
    totaal = sum(v["duur_s"] or 0 for x in g.values() for v, _ in x)
    kijk = sum(v["duur_s"] or 0 for v, _ in g["kijken"])
    samen = f"{n} talks, samen {uren(totaal)}." + (f" De kijktips kosten je {uren(kijk)}." if kijk else "")
    blokken = []
    for k, naam in SECTIES:
        if g[k]:
            maak = {"kijken": talk_kijken, "samenvatting volstaat": talk_lezen, "overslaan": talk_overslaan}[k]
            blokken.append(sectiekop(k, naam, len(g[k])))
            blokken += [maak(v, s) for v, s in g[k]]
    if g["geen"]:
        blokken.append(f'<tr><td style="padding:36px 0 8px;font:700 16px/1.3 {SANS};color:{ZACHT};">'
                       f'Nog zonder ondertitels</td></tr>')
        blokken += [f'<tr><td style="padding:8px 0;border-top:1px solid {LIJN};font:14px/1.5 {SANS};">'
                    f'{_a(yt(v["id"]), e(v["titel"]), INKT)}</td></tr>' for v, _ in g["geen"]]
    intro_html = (f'<div style="font:18px/1.6 {SERIF};color:{INKT};margin-top:26px;">{e(intro)}</div>' if intro else "")
    return f"""<!doctype html><html lang="nl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only">
<title>{e(config.BRIEF_NAAM)} {nummer}</title></head>
<body style="margin:0;padding:0;background:{OMGEVING};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{OMGEVING}" style="background:{OMGEVING};">
<tr><td align="center" style="padding:28px 10px;">
<table role="presentation" width="620" cellpadding="0" cellspacing="0" border="0" bgcolor="{PAPIER}" style="width:100%;max-width:620px;background:{PAPIER};">
<tr><td style="padding:30px 30px 0;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
    <td valign="baseline" style="font:800 30px/1 {SANS};color:{INKT};letter-spacing:-0.8px;">{e(config.BRIEF_NAAM)}</td>
    <td valign="baseline" align="right" style="font:14px/1.3 {SANS};color:{ZACHT};">nummer {nummer}<br>{datum_nl(datum)}</td>
  </tr></table>
  <div style="font:15px/1.5 {SANS};color:{ZACHT};margin:6px 0 22px;">Wat er op het AI Engineer-kanaal verscheen, zodat jij niet alles hoeft te kijken.</div>
  {weekstrook(g)}
  {legenda()}
  <div style="font:600 15px/1.5 {SANS};color:{INKT};margin-top:14px;">{samen}</div>
  {intro_html}
</td></tr>
<tr><td style="padding:0 30px 10px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">{''.join(blokken)}</table></td></tr>
<tr><td style="padding:26px 30px 30px;border-top:1px solid {LIJN};font:12px/1.6 {SANS};color:{ZACHT};">
  {e(config.BRIEF_NAAM)} {nummer}, {datum_nl(datum)}. Geschreven door een taalmodel uit de automatische
  YouTube-ondertitels, dus details kunnen afwijken: de tijdstempels brengen je naar de bron.</td></tr>
</table></td></tr></table></body></html>"""


def verstuur(nummer: int, datum: date, g: dict, intro: str = "", client: httpx.Client | None = None) -> bool:
    token, van, aan = (os.environ.get(k, "") for k in ("POSTMARK_TOKEN", "MAIL_FROM", "MAIL_TO"))
    if not (token and van and aan):
        log.warning("POSTMARK_TOKEN/MAIL_FROM/MAIL_TO ontbreken; geen mail")
        return False
    if "<" not in van:
        van = f"{config.BRIEF_NAAM} <{van}>"
    client = client or httpx.Client(timeout=20)
    bericht = {"From": van, "To": aan, "Subject": onderwerp(nummer, g),
               "TextBody": tekst_body(nummer, datum, g, intro), "HtmlBody": html_body(nummer, datum, g, intro),
               "MessageStream": "outbound", "TrackOpens": False, "TrackLinks": "None"}
    try:
        r = client.post("https://api.postmarkapp.com/email", json=bericht,
                        headers={"X-Postmark-Server-Token": token, "Accept": "application/json"})
        if not 200 <= r.status_code < 300:
            log.warning("postmark: HTTP %s %s", r.status_code, r.text[:200])
        return 200 <= r.status_code < 300
    except httpx.HTTPError as ex:
        log.warning("postmark: %s", ex)
        return False
