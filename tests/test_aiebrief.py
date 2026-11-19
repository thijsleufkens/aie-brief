import json
from datetime import date

from aiebrief import bron, cli, db, mail, samenvat

LIJST = {"entries": [
    {"id": "AAA", "title": "Build an Eval | Ada Lovelace", "duration": 1346.0},
    {"id": "CLIP", "title": "65 seconds inside", "duration": 61},
    {"id": "PREM", "title": "Premiere", "duration": None},
    {"id": "BBB", "title": "Oudere talk", "duration": 900},
    None,
]}


def test_parse_lijst():
    v = bron.parse_lijst(LIJST)
    assert [x.id for x in v] == ["AAA", "CLIP", "PREM", "BBB"]
    assert v[0].duur_s == 1346 and v[2].duur_s is None


def test_bouw_tekst_markers_en_duur():
    snips = [(0, 2, "hello"), (30, 2, "world"), (61, 3, "next\nblock")]
    t = bron.bouw_tekst(snips, blok_s=60)
    assert t.tekst.splitlines() == ["[00:00] hello world", "[01:01] next block"]
    assert t.duur_s == 64 and t.woorden == 4 and not t.afgekapt


def test_bouw_tekst_kapt_af():
    t = bron.bouw_tekst([(i, 1, "een twee") for i in range(10)], max_woorden=5)
    assert t.afgekapt and t.woorden == 4


def test_mmss_uren():
    assert bron.mmss(3725) == "1:02:05"


def test_schoon_vangnet():
    obj = {"inzichten": ["a", " ", "b", "c", "d", "e", "f"], "score": 9, "oordeel": "raar",
           "momenten": [{"sec": 500, "wat": "x"}, {"sec": 10, "wat": "y"}, {"sec": 9999, "wat": "z"}]}
    s = samenvat.schoon(obj, duur_s=600)
    assert s["inzichten"] == ["a", "b", "c", "d", "e"]
    assert s["score"] == 5 and s["oordeel"] == "samenvatting volstaat"
    assert [m["sec"] for m in s["momenten"]] == [10, 500]


def test_ontdek_clips_premieres_en_eerste_run(tmp_path, monkeypatch):
    monkeypatch.setattr(cli.config, "EERSTE_RUN_AANTAL", 1)
    con = db.open_db(tmp_path / "t.db")
    assert cli.ontdek(con, bron.parse_lijst(LIJST)) == 1          # AAA; BBB genegeerd
    assert [r["id"] for r in db.te_doen(con)] == ["AAA"]
    assert cli.ontdek(con, bron.parse_lijst(LIJST)) == 0          # BBB komt niet terug
    later = {"entries": [{"id": "NEW", "title": "n", "duration": 600}, {"id": "PREM", "title": "p", "duration": 3000}]}
    assert cli.ontdek(con, bron.parse_lijst(later)) == 2          # premiere nu wel


def test_opgeven_na_max_pogingen(tmp_path):
    con = db.open_db(tmp_path / "t.db")
    db.voeg_toe(con, "X", "t")
    for _ in range(4):
        db.markeer_mislukt(con, "X", "NoTranscriptFound", 5)
    assert [r["id"] for r in db.te_doen(con)] == ["X"]
    db.markeer_mislukt(con, "X", "NoTranscriptFound", 5)
    assert db.te_doen(con) == []
    assert [r["status"] for r in db.voor_editie(con)] == ["geen_transcript"]


def _samenvatting(oordeel, score, kop="Kop <b>"):
    return {"kop": kop, "lead": "Lead.", "context": "Ctx.", "labels": ["evals"], "inzichten": ["i1", "i2"], "voor_lezer": "iets",
            "oordeel": oordeel, "waarom": "omdat", "score": score, "momenten": [{"sec": 75, "wat": "demo"}]}


def test_editie_groepering_en_mail(tmp_path):
    con = db.open_db(tmp_path / "t.db")
    for vid, oordeel, score in [("A", "samenvatting volstaat", 3), ("B", "kijken", 4),
                                ("C", "kijken", 5), ("D", "overslaan", 1)]:
        db.voeg_toe(con, vid, f"Talk {vid} | Spreker")
        db.markeer_klaar(con, vid, _samenvatting(oordeel, score), 1800, 4000)
    db.voeg_toe(con, "E", "Zonder")
    for _ in range(5):
        db.markeer_mislukt(con, "E", "x", 5)
    g = mail.groepeer(db.voor_editie(con))
    assert [v["id"] for v, _ in g["kijken"]] == ["C", "B"]
    assert [v["id"] for v, _ in g["geen"]] == ["E"]
    assert mail.onderwerp(1, g) == "AIE-brief 1: 5 talks, 2 om te kijken"
    h = mail.html_body(1, date(2026, 11, 22), g, intro="Thema <x>.")
    assert "Thema &lt;x&gt;." in h and "Lezen volstaat" in h and "De kijktips kosten je" in h
    assert "Kop &lt;b&gt;" in h and "<b>Voor jou.</b>" in h
    assert "watch?v=C&amp;t=75s" in h
    t = mail.tekst_body(1, date(2026, 11, 22), g)
    assert "DEZE WEEK" not in t and "De details:" in t
    assert "KIJKEN" in t and "ZONDER TRANSCRIPT" in t and "01:15 demo" in t
    eid = db.leg_editie_vast(con, "2026-11-22", [v["id"] for v in db.voor_editie(con)])
    assert eid == 1 and db.voor_editie(con) == [] and db.editienummer(con) == 2


def test_splits_titel():
    assert mail.splits_titel("A | B | Spreker") == ("A | B", "Spreker")
    assert mail.splits_titel("Alleen titel") == ("Alleen titel", "")


def test_qwen_weigert_direct_adres(monkeypatch):
    import pytest
    from aiebrief import config
    from aiebrief.qwen import Qwen, QwenFout
    monkeypatch.setattr(config, "VERBODEN_LLM_HOST", "192.0.2.1")
    with pytest.raises(QwenFout):
        Qwen(base_url="http://192.0.2.1:8080/v1")


def test_schoon_labels():
    s = samenvat.schoon({"labels": ["evals", "onzin", "evals", "security", "infra & serving", "overig"]}, 60)
    assert s["labels"] == ["evals", "security"]
    assert samenvat.schoon({"labels": []}, 60)["labels"] == ["overig"]


def test_week_intro_valt_stil_terug(monkeypatch):
    from aiebrief import week
    from aiebrief.qwen import QwenFout

    class Kapot:
        def chat_json(self, *a, **k):
            raise QwenFout("model weg")
    items = [("t1", {"kop": "a", "lead": "b", "labels": []}), ("t2", {"kop": "c", "lead": "d", "labels": []})]
    assert week.schrijf_intro(items, Kapot()) == ""
    assert week.schrijf_intro(items[:1], Kapot()) == ""


def test_max_drie_kijken(tmp_path):
    con = db.open_db(tmp_path / "t.db")
    for i, score in enumerate([3, 5, 4, 4, 2]):
        db.voeg_toe(con, f"V{i}", f"T{i}", i)
        db.markeer_klaar(con, f"V{i}", _samenvatting("kijken", score), 600, 100)
    g = mail.groepeer(db.voor_editie(con))
    assert [v["id"] for v, _ in g["kijken"]] == ["V1", "V2", "V3"]
    assert [v["id"] for v, _ in g["samenvatting volstaat"]] == ["V0", "V4"]


def test_tijdbalk_streepjes():
    v = {"id": "X", "duur_s": 1000}
    h = mail.tijdbalk(v, {"momenten": [{"sec": 0, "wat": "a"}, {"sec": 500, "wat": "b"}]})
    assert h.count(f'bgcolor="{mail.GOUD}"') == 2 and "16:40" in h and "t=500s" in h


def test_prompts_bevatten_lezer():
    assert "Over de lezer" in samenvat.systeemprompt()


def test_transcript_wordt_bewaard(tmp_path):
    con = db.open_db(tmp_path / "t.db")
    db.voeg_toe(con, "X", "t")
    db.bewaar_transcript(con, "X", "[00:00] hoi", 61, 1, False)
    r = db.te_doen(con)[0]
    assert r["transcript"] == "[00:00] hoi" and r["duur_s"] == 61
    db.open_db(tmp_path / "t.db")  # migratie is idempotent
