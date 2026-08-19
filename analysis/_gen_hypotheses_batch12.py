"""Generate hypotheses-batch-12.json from parsed visit data."""
import json
from pathlib import Path

COMPACT = Path(__file__).parent / "_batch12_compact.json"
OUT = Path(__file__).parent / "hypotheses-batch-12.json"
CTA_IDS = {414, 438, 462}
FORM_IDS = {485, 490, 495, 500}
SUBMIT_ID = 503


def pct(ms, total):
    return round(100 * ms / total, 1) if total else 0


def card_clicks(r):
    return [c for c in r["clicks"] if c["target"] == 1]


def cta_clicks(r):
    return [c for c in r["clicks"] if c["target"] in CTA_IDS]


def build_hypotheses(r):
    hyps = []
    dur = r["duration_ms"] or 1
    dwell = r["dwell_ms"]
    cards = card_clicks(r)
    ctas = cta_clicks(r)

    if cards:
        stamps = "/".join(str(c["stamp"]) for c in cards)
        sy = cards[0]["scroll_y"]
        sr = cards[0]["scroll_ratio"]
        ys = "/".join(str(c["y"]) for c in cards)
        hyps.append(
            {
                "id": "cards_look_clickable",
                "confidence": "high",
                "evidence": (
                    f"Three document-target-1 clicks at {stamps} ms with click.y {ys} "
                    f"while scroll.meta.y={sy} ({sr:.1%} program), never hitting a mapped CTA or form node."
                ),
            }
        )

    program_ms = dwell.get("program", 0)
    hero_ms = dwell.get("hero", 0)
    price_ms = dwell.get("price", 0)
    photo_ms = dwell.get("photo", 0)
    instr_ms = dwell.get("instructors", 0)
    legal_ms = dwell.get("legal", 0)
    form_ms = dwell.get("form", 0)

    longest = max(dwell, key=dwell.get) if dwell else "hero"
    if program_ms >= 24000 or (program_ms >= 0.4 * dur and longest == "program"):
        hyps.append(
            {
                "id": "program_too_long",
                "confidence": "high" if program_ms >= 25000 else "medium",
                "evidence": (
                    f"Spent ~{program_ms} ms in program ({pct(program_ms, dur)}% of the "
                    f"{r['duration_sec']}s session) — longest section before injuries/legal."
                ),
            }
        )

    if hero_ms >= 20000 and hero_ms >= 0.35 * dur:
        hyps.append(
            {
                "id": "no_hero_cta",
                "confidence": "high",
                "evidence": (
                    f"Dwelt ~{hero_ms} ms in hero 0–10% ({pct(hero_ms, dur)}% of session) with no "
                    f"CTA nodes 414/438/462 in fold; first register button only after scrolling past program."
                ),
            }
        )

    if hero_ms >= 15000 and r["max_scroll_ratio"] < 0.5 and not ctas:
        hyps.append(
            {
                "id": "bounce_hero_no_cta",
                "confidence": "medium",
                "evidence": (
                    f"~{hero_ms} ms in hero, max scroll {r['max_scroll_ratio']:.1%} — never reached program CTA zone."
                ),
            }
        )

    if r["duration_sec"] <= 50 and r["max_scroll_ratio"] < 0.88:
        hyps.append(
            {
                "id": "bounce_short_session",
                "confidence": "medium",
                "evidence": (
                    f"Session {r['duration_sec']}s, deepest {r['deepest_section']} "
                    f"({r['max_scroll_ratio']:.1%}), left before price/form CTAs."
                ),
            }
        )

    if ctas and all(c["stamp"] > dur * 0.7 for c in ctas):
        hyps.append(
            {
                "id": "no_midpage_cta",
                "confidence": "medium",
                "evidence": (
                    f"No CTA click until t={ctas[0]['stamp']} ms (~{ctas[0]['stamp']/1000:.1f}s) "
                    f"after scrolling through full program 18–52% with no mid-page register path."
                ),
            }
        )

    if legal_ms >= 3000:
        hyps.append(
            {
                "id": "legal_concern",
                "confidence": "medium",
                "evidence": f"Paused ~{legal_ms} ms in legal 60–67% before continuing — possible disclaimer friction.",
            }
        )

    if photo_ms >= 4000:
        hyps.append(
            {
                "id": "photo_dropout",
                "confidence": "medium",
                "evidence": (
                    f"Dwelt ~{photo_ms} ms in photo 67–74% (y≈5740–6300) then rushed to price/CTA "
                    f"without instructor engagement."
                ),
            }
        )

    if instr_ms >= 6000 and ctas:
        cta = ctas[0]
        hyps.append(
            {
                "id": "instructors_trust",
                "confidence": "medium",
                "evidence": (
                    f"Paused ~{instr_ms} ms in instructors (y≈{cta['scroll_y']}, {cta['scroll_ratio']:.1%}) "
                    f"before clicking CTA {cta['target']}, suggesting hesitation on instructor cards."
                ),
            }
        )

    if price_ms >= 3000:
        hyps.append(
            {
                "id": "price_sticker_shock",
                "confidence": "high" if price_ms >= 4500 else "medium",
                "evidence": (
                    f"Lingered ~{price_ms} ms in price 81–88% around tariff CTAs 414/438/462 "
                    f"before {'form glance' if form_ms else 'exit'}."
                ),
            }
        )

    if ctas and not r["form_fields_touched"]:
        cta = ctas[0]
        hyps.append(
            {
                "id": "cta_clicked_no_form_fill",
                "confidence": "high",
                "evidence": (
                    f"Clicked CTA node {cta['target']} at {cta['stamp']} ms from "
                    f"{cta['scroll_section']} y={cta['scroll_y']} ({cta['scroll_ratio']:.1%}), "
                    f"then 0 inputs on 485/490/495/500 and no submit {SUBMIT_ID}."
                ),
            }
        )

    if r["max_scroll_ratio"] >= 0.88 and not r["form_fields_touched"] and form_ms >= 1500:
        hyps.append(
            {
                "id": "form_reached_no_interact",
                "confidence": "high",
                "evidence": (
                    f"Reached form max y={r.get('max_y', 0)} ({r['max_scroll_ratio']:.1%}), "
                    f"~{form_ms} ms form dwell, fields 485/490/495/500 never focused; submit {SUBMIT_ID} untouched."
                ),
            }
        )

    if r["form_fields_touched"] and not r["submit_attempted"] and not r["converted"]:
        hyps.append(
            {
                "id": "form_friction_abandoned",
                "confidence": "high",
                "evidence": (
                    f"Touched fields {r['form_fields_touched']} but abandoned without submit {SUBMIT_ID}."
                ),
            }
        )

    if r["submit_attempted"] and not r["converted"]:
        hyps.append(
            {
                "id": "form_validation_failed",
                "confidence": "medium",
                "evidence": f"Clicked submit {SUBMIT_ID} but no conversion signal in mutations/goals.",
            }
        )

    if (
        r["max_scroll_ratio"] >= 0.88
        and r["last_section"] in ("price", "instructors", "photo")
        and r["last_ratio"] < r["max_scroll_ratio"] - 0.01
    ):
        hyps.append(
            {
                "id": "scrolled_past_form",
                "confidence": "high",
                "evidence": (
                    f"Max scroll {r['max_scroll_ratio']:.1%} (form) but last position y={r['last_y']} "
                    f"({r['last_ratio']:.1%} {r['last_section']}) — scrolled away from form after CTA."
                ),
            }
        )

    if r.get("mid_blur"):
        hyps.append(
            {
                "id": "tab_switch_away",
                "confidence": "medium",
                "evidence": (
                    f"windowblur at {r['mid_blur'][0]['stamp']} ms mid-session before form completion."
                ),
            }
        )

    if r["converted"]:
        hyps.append(
            {
                "id": "converted",
                "confidence": "high",
                "evidence": "Successful form submit with post-submit mutation/goal signal.",
            }
        )

    # cap at 4 hypotheses, prioritize high confidence
    hyps.sort(key=lambda h: (0 if h["confidence"] == "high" else 1, h["id"]))
    seen = set()
    unique = []
    for h in hyps:
        if h["id"] not in seen:
            seen.add(h["id"])
            unique.append(h)
    return unique[:4]


def main():
    rows = json.loads(COMPACT.read_text(encoding="utf-8"))
    visits = []
    for r in rows:
        ctas = [c["target"] for c in r["clicks"] if c["target"] in CTA_IDS]
        visits.append(
            {
                "visit_id": r["visit_id"],
                "converted": bool(r["converted"]),
                "duration_sec": r["duration_sec"],
                "max_scroll_ratio": r["max_scroll_ratio"],
                "deepest_section": r["deepest_section"],
                "last_section": r["last_section"],
                "cta_clicked": ctas,
                "form_fields_touched": r["form_fields_touched"],
                "submit_attempted": r["submit_attempted"],
                "hypotheses": build_hypotheses(r),
            }
        )

    out = {"batch": 12, "visits": visits}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} visits={len(visits)}")
    conv = sum(1 for v in visits if v["converted"])
    print(f"converted={conv}/{len(visits)}")
    from collections import Counter

    c = Counter()
    for v in visits:
        for h in v["hypotheses"]:
            c[h["id"]] += 1
    for k, n in c.most_common():
        print(f"  {k}: {n}")


if __name__ == "__main__":
    main()
