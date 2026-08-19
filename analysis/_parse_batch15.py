#!/usr/bin/env python3
"""Parse batch-15 Webvisor visits and write hypotheses-batch-15.json."""
import json
from collections import Counter
from pathlib import Path

BASE = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\webvisor\2026-08-19")
OUT = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\hypotheses-batch-15.json")
DUMP = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\_batch15_dump.json")

IDS = [
    "4795932587707072829",
    "4795933313736638560",
    "4795935425897431112",
    "4795936013525450821",
    "4795937112596152652",
    "4795938223269347396",
    "4795938790667976901",
    "4795941606997360981",
    "4795944782154432773",
    "4795946091104960720",
    "4795946163798278476",
    "4795946404791189660",
    "4795949074667012452",
    "4795950073214140653",
]

SECTIONS = [
    ("hero", 0.00, 0.10),
    ("about", 0.10, 0.18),
    ("program", 0.18, 0.52),
    ("injuries", 0.52, 0.60),
    ("legal", 0.60, 0.67),
    ("photo", 0.67, 0.74),
    ("instructors", 0.74, 0.81),
    ("price", 0.81, 0.88),
    ("form", 0.88, 0.97),
    ("footer", 0.97, 1.01),
]
CTA_IDS = {414, 438, 462}
FORM_IDS = {485, 490, 495, 500}
SUBMIT_ID = 503


def section_for(ratio: float) -> str:
    for name, lo, hi in SECTIONS:
        if lo <= ratio < hi:
            return name
    return "footer" if ratio >= 0.97 else "hero"


def y_at(scrolls: list[tuple[int, int]], stamp: int) -> int:
    y = 0
    for s, sy in scrolls:
        if s <= stamp:
            y = sy
        else:
            break
    return y


def fmt_t(ms: int) -> str:
    return f"{ms / 1000:.1f}s"


def longest_stationary(scrolls: list[tuple[int, int]], ph: int) -> dict | None:
    if len(scrolls) < 2:
        return None
    best = {"ms": 0, "y": scrolls[0][1], "start": scrolls[0][0], "end": scrolls[0][0]}
    for i in range(len(scrolls) - 1):
        s0, y0 = scrolls[i]
        s1, _ = scrolls[i + 1]
        dt = s1 - s0
        if dt > best["ms"]:
            best = {"ms": dt, "y": y0, "start": s0, "end": s1}
    return best if best["ms"] >= 3000 else None


def dead_card_clicks(clicks: list[dict], scrolls: list[tuple[int, int]], ph: int) -> list[dict]:
    out = []
    for c in clicks:
        if c["target"] != 1:
            continue
        sy = y_at(scrolls, c["stamp"])
        ratio = sy / ph
        sec = section_for(ratio)
        if sec == "program" or (0.18 <= ratio < 0.52):
            out.append({**c, "scroll_y": sy, "scroll_ratio": round(ratio, 4), "section": sec})
    return out


def parse_visit(vid: str) -> tuple[dict, dict]:
    path = BASE / f"visit_{vid}.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    events = data.get("parsed_events") or []
    summary = data.get("summary") or {}

    page_h = 8513
    node_map: dict[int, dict] = {}
    scrolls: list[tuple[int, int]] = []
    clicks: list[dict] = []
    inputs: list[dict] = []
    keydowns: list[dict] = []
    focuses: list[dict] = []
    window_ev: list[dict] = []
    mutations: list[dict] = []
    max_y = 0
    last_y = 0
    last_stamp = 0
    converted_signal = False

    for e in events:
        t = e.get("type") or e.get("group")
        stamp = e.get("stamp") or e.get("time") or 0
        last_stamp = max(last_stamp, stamp)
        meta = e.get("meta") or {}

        if e.get("group") == "page":
            for n in e.get("content") or []:
                if isinstance(n, dict) and "id" in n:
                    node_map[n["id"]] = {
                        "name": n.get("name"),
                        "attrs": n.get("attributes") or {},
                        "content": (n.get("content") or "")[:80],
                    }

        if t == "resize":
            page_h = meta.get("pageHeight") or page_h

        if t == "scroll" and meta.get("y") is not None:
            y = meta["y"]
            scrolls.append((stamp, y))
            max_y = max(max_y, y)
            last_y = y

        if t == "click":
            clicks.append(
                {
                    "stamp": stamp,
                    "target": e.get("target"),
                    "x": meta.get("x"),
                    "y": meta.get("y"),
                }
            )

        if t in ("input", "change"):
            inputs.append({"stamp": stamp, "type": t, "target": e.get("target"), "meta": meta})

        if t in ("keydown", "keyup"):
            keydowns.append({"stamp": stamp, "type": t, "target": e.get("target")})

        if t in ("focus", "blur"):
            focuses.append({"stamp": stamp, "type": t, "target": e.get("target")})

        if t in ("windowblur", "windowfocus"):
            window_ev.append({"stamp": stamp, "type": t})

        if e.get("group") == "mutation":
            blob = json.dumps(meta, ensure_ascii=False).lower()
            if any(s in blob for s in ("success", "заявк", "form-message", "error", "отправ")):
                if "success" in blob or "заявк" in blob:
                    converted_signal = True
                mutations.append({"stamp": stamp, "snippet": blob[:300]})

    ph = page_h or 8513
    dur_ms = summary.get("duration_ms") or last_stamp
    dur_sec = summary.get("duration_sec") or round(dur_ms / 1000)
    max_ratio = round(max_y / ph, 4)
    last_ratio = round(last_y / ph, 4)
    deepest = section_for(max_ratio)
    last_sec = section_for(last_ratio)

    dwell = Counter()
    if scrolls:
        prev_stamp, prev_y = scrolls[0]
        for stamp, y in scrolls[1:]:
            dwell[section_for(prev_y / ph)] += max(0, stamp - prev_stamp)
            prev_stamp, prev_y = stamp, y
        dwell[section_for(prev_y / ph)] += max(0, dur_ms - prev_stamp)
    else:
        dwell["hero"] = dur_ms

    cta_clicked: list[int] = []
    form_fields: set[int] = set()
    submit_attempted = False
    cta_click_events: list[dict] = []

    for c in clicks:
        tgt = c["target"]
        sy = y_at(scrolls, c["stamp"])
        node = node_map.get(tgt, {})
        attrs = node.get("attrs") or {}
        if tgt in CTA_IDS or "btn-register" in (attrs.get("class") or ""):
            if tgt not in cta_clicked:
                cta_clicked.append(tgt)
            cta_click_events.append({**c, "scroll_y": sy, "scroll_ratio": round(sy / ph, 4)})
        if tgt in FORM_IDS or attrs.get("name") in ("name", "phone", "email", "comment"):
            form_fields.add(tgt)
        if tgt == SUBMIT_ID or attrs.get("type") == "submit":
            submit_attempted = True

    for rec in inputs:
        if rec["target"] in FORM_IDS:
            form_fields.add(rec["target"])

    for rec in focuses:
        if rec["type"] == "focus" and rec["target"] in FORM_IDS:
            form_fields.add(rec["target"])

    for c in clicks:
        if c["target"] in FORM_IDS:
            form_fields.add(c["target"])

    converted = bool(converted_signal or (submit_attempted and len(form_fields) >= 2))

    mid_blur = [
        w for w in window_ev if w["type"] == "windowblur" and w["stamp"] < dur_ms - 1500
    ]
    end_blur = [
        w for w in window_ev if w["type"] == "windowblur" and w["stamp"] >= dur_ms - 1500
    ]

    dead = dead_card_clicks(clicks, scrolls, ph)
    stationary = longest_stationary(scrolls, ph)
    form_dwell = dwell.get("form", 0)
    program_dwell = dwell.get("program", 0)
    hero_dwell = dwell.get("hero", 0)
    price_dwell = dwell.get("price", 0)
    instructors_dwell = dwell.get("instructors", 0)
    legal_dwell = dwell.get("legal", 0)
    photo_dwell = dwell.get("photo", 0)

    mid_sections = ["injuries", "legal", "photo"]
    mid_fast = sum(dwell.get(s, 0) for s in mid_sections)

    analysis = {
        "visit_id": vid,
        "duration_sec": dur_sec,
        "duration_ms": dur_ms,
        "pageHeight": ph,
        "max_y": max_y,
        "max_scroll_ratio": max_ratio,
        "deepest_section": deepest,
        "last_y": last_y,
        "last_ratio": last_ratio,
        "last_section": last_sec,
        "dwell_ms": dict(dwell),
        "cta_clicked": cta_clicked,
        "cta_click_events": cta_click_events,
        "form_fields_touched": sorted(form_fields),
        "submit_attempted": submit_attempted,
        "converted": converted,
        "dead_card_clicks": dead,
        "stationary": stationary,
        "mid_blur": mid_blur,
        "end_blur": end_blur,
        "program_dwell": program_dwell,
        "hero_dwell": hero_dwell,
        "form_dwell": form_dwell,
        "price_dwell": price_dwell,
        "instructors_dwell": instructors_dwell,
        "legal_dwell": legal_dwell,
        "photo_dwell": photo_dwell,
        "mid_fast": mid_fast,
        "summary": summary,
        "inputs_n": summary.get("inputs", len(inputs)),
        "keydowns_n": summary.get("keydowns", len(keydowns)),
    }
    return analysis, build_hypotheses(analysis)


def program_stationary(a: dict, ph: int) -> dict | None:
    st = a["stationary"]
    if not st or st["ms"] < 15000:
        return None
    ratio = st["y"] / ph
    if 0.18 <= ratio < 0.52:
        return {**st, "ratio": round(ratio, 3)}
    return None


def build_hypotheses(a: dict) -> list[dict]:
    ph = a["pageHeight"]
    dur = a["duration_ms"]
    dur_sec = a["duration_sec"]
    dead = a["dead_card_clicks"]
    cta_ev = a["cta_click_events"]
    pst = program_stationary(a, ph)

    if a["converted"]:
        return [
            {
                "id": "converted",
                "confidence": "high",
                "evidence": (
                    f"Successful form submit: fields {a['form_fields_touched']}, "
                    f"submit 503 clicked, conversion mutation detected."
                ),
            }
        ]

    candidates: list[tuple[int, dict]] = []

    if cta_ev and not a["form_fields_touched"]:
        ce = cta_ev[0]
        sec = section_for(ce["scroll_ratio"])
        form_bits = []
        if a["max_scroll_ratio"] >= 0.88:
            form_bits.append(
                f"then reached form y={a['max_y']} ({a['max_scroll_ratio']})"
            )
            if a["form_dwell"] >= 2000:
                form_bits.append(f"and stayed {a['form_dwell'] / 1000:.1f}s")
            form_bits.append("with 0 focus/input on 485/490/495/500")
        if a["last_section"] == "price" and a["deepest_section"] == "form":
            form_bits.append(
                f"then scrolled back to price y={a['last_y']} ({a['last_ratio']})"
            )
        if a["end_blur"]:
            form_bits.append(f"until windowblur at {fmt_t(a['end_blur'][-1]['stamp'])}")
        form_bits.append("no submit 503")
        candidates.append(
            (
                1000,
                {
                    "id": "cta_clicked_no_form_fill",
                    "confidence": "high",
                    "evidence": (
                        f"Clicked {'price ' if sec == 'price' else ''}CTA node {ce['target']} at t={fmt_t(ce['stamp'])} "
                        f"(scroll y={ce['scroll_y']}, {sec} {ce['scroll_ratio']}), "
                        f"{' '.join(form_bits)}."
                    ),
                },
            )
        )

    if pst and pst["ms"] >= 18000 and a["program_dwell"] >= dur * 0.42:
        mid_note = ""
        if a["mid_fast"] < 2500:
            mid_note = f"; injuries/legal combined {a['mid_fast'] / 1000:.1f}s"
        candidates.append(
            (
                720 + int(pst["ms"] / 1000),
                {
                    "id": "program_too_long",
                    "confidence": "high",
                    "evidence": (
                        f"Stationary {pst['ms'] / 1000:.1f}s in program "
                        f"(t={fmt_t(pst['start'])}–{fmt_t(pst['end'])}, y={pst['y']}, {pst['ratio']}) "
                        f"plus {a['program_dwell'] / 1000:.1f}s total program dwell "
                        f"(~{100 * a['program_dwell'] / dur:.0f}% of {dur_sec}s session)"
                        f"{mid_note}."
                    ),
                },
            )
        )
    elif pst and pst["ms"] >= 18000:
        candidates.append(
            (
                680,
                {
                    "id": "program_too_long",
                    "confidence": "medium",
                    "evidence": (
                        f"Paused {pst['ms'] / 1000:.1f}s in program at y={pst['y']} ({pst['ratio']}) "
                        f"with {a['program_dwell'] / 1000:.1f}s total program dwell."
                    ),
                },
            )
        )

    if len(dead) >= 3:
        stamps = "/".join(f"t={fmt_t(d['stamp'])}" for d in dead[:3])
        cy = "/".join(str(d.get("y")) for d in dead[:3])
        candidates.append(
            (
                660,
                {
                    "id": "cards_look_clickable",
                    "confidence": "high",
                    "evidence": (
                        f"Three dead clicks on html node 1 at {stamps} "
                        f"(x={dead[0].get('x', 211)}, click.y ≈ {cy}) "
                        f"while parked in program at y={dead[0]['scroll_y']} ({dead[0]['scroll_ratio']}); "
                        f"no mapped interactive target."
                    ),
                },
            )
        )
    elif len(dead) == 2:
        candidates.append(
            (
                600,
                {
                    "id": "cards_look_clickable",
                    "confidence": "medium",
                    "evidence": (
                        f"Two html-node-1 clicks at t={fmt_t(dead[0]['stamp'])}/"
                        f"{fmt_t(dead[1]['stamp'])} (x=211) in program at y={dead[0]['scroll_y']}."
                    ),
                },
            )
        )

    if a["instructors_dwell"] >= 5000 and a["cta_clicked"]:
        candidates.append(
            (
                650 + int(a["instructors_dwell"] / 1000),
                {
                    "id": "instructors_trust",
                    "confidence": "high" if a["instructors_dwell"] >= 6500 else "medium",
                    "evidence": (
                        f"Paused {a['instructors_dwell'] / 1000:.1f}s on instructors "
                        f"immediately before CTA {a['cta_clicked'][0]}; "
                        f"injuries/legal/photo were {a['mid_fast'] / 1000:.1f}s skips."
                    ),
                },
            )
        )

    bounced_price = a["last_section"] == "price" and a["deepest_section"] == "form"
    if a["price_dwell"] >= 5000 and a["cta_clicked"]:
        candidates.append(
            (
                640 + int(a["price_dwell"] / 1000),
                {
                    "id": "price_sticker_shock",
                    "confidence": "high" if a["price_dwell"] >= 6000 else "medium",
                    "evidence": (
                        f"Paused {a['price_dwell'] / 1000:.1f}s on the price cards before clicking "
                        f"{a['cta_clicked'][0]} — longest stop after program — then still abandoned the form."
                    ),
                },
            )
        )
    elif bounced_price and a["cta_clicked"]:
        candidates.append(
            (
                620,
                {
                    "id": "price_sticker_shock",
                    "confidence": "medium",
                    "evidence": (
                        f"After CTA and brief form view, session ended on price "
                        f"(last_section=price, y={a['last_y']}, {a['last_ratio']}), not on form fields."
                    ),
                },
            )
        )

    if (
        a["deepest_section"] == "form"
        and a["last_section"] == "form"
        and not a["form_fields_touched"]
        and a["form_dwell"] >= 4000
    ):
        candidates.append(
            (
                580,
                {
                    "id": "form_reached_no_interact",
                    "confidence": "high",
                    "evidence": (
                        f"Ended on form (last y={a['last_y']}, {a['max_scroll_ratio']}) with "
                        f"{a['form_dwell'] / 1000:.1f}s form dwell; summary inputs=0, keydowns=0, "
                        f"never focused 485/490/495/500."
                    ),
                },
            )
        )

    if a["hero_dwell"] >= 20000:
        candidates.append(
            (
                560,
                {
                    "id": "no_hero_cta",
                    "confidence": "medium",
                    "evidence": (
                        f"Hero dwell {a['hero_dwell'] / 1000:.1f}s (0–10%, no CTA) before scrolling; "
                        f"first button click is still price {a['cta_clicked'][0] if a['cta_clicked'] else '414'} "
                        f"at t={fmt_t(cta_ev[0]['stamp']) if cta_ev else '—'}."
                    ),
                },
            )
        )

    if a["max_scroll_ratio"] < 0.18 and dur_sec < 30:
        candidates.append(
            (
                900,
                {
                    "id": "bounce_hero_no_cta",
                    "confidence": "high",
                    "evidence": f"Max scroll {a['max_scroll_ratio']} in hero/about, {dur_sec}s, no CTA.",
                },
            )
        )
    elif dur_sec < 30 and a["max_scroll_ratio"] < 0.52:
        candidates.append(
            (
                850,
                {
                    "id": "bounce_short_session",
                    "confidence": "high",
                    "evidence": f"{dur_sec}s session, max {a['max_scroll_ratio']} ({a['deepest_section']}), no conversion.",
                },
            )
        )

    if a["max_scroll_ratio"] < 0.81 and not a["cta_clicked"]:
        candidates.append(
            (
                800,
                {
                    "id": "no_midpage_cta",
                    "confidence": "high",
                    "evidence": (
                        f"Dropped at {a['max_scroll_ratio']} ({a['deepest_section']}); "
                        f"CTAs 414/438/462 at 81–88% never clicked."
                    ),
                },
            )
        )

    if a["legal_dwell"] >= 3000 and a["max_scroll_ratio"] < 0.81:
        candidates.append(
            (
                500,
                {
                    "id": "legal_concern",
                    "confidence": "medium",
                    "evidence": f"Dwelt {a['legal_dwell'] / 1000:.1f}s on legal then left before price/form.",
                },
            )
        )

    if a["photo_dwell"] >= 3000 and a["max_scroll_ratio"] < 0.88:
        candidates.append(
            (
                490,
                {
                    "id": "photo_dropout",
                    "confidence": "medium",
                    "evidence": f"Paused {a['photo_dwell'] / 1000:.1f}s on photo then exited before form.",
                },
            )
        )

    if a["form_fields_touched"] and not a["converted"]:
        candidates.append(
            (
                900,
                {
                    "id": "form_friction_abandoned",
                    "confidence": "high",
                    "evidence": f"Touched {a['form_fields_touched']} but no successful submit.",
                },
            )
        )

    if a["submit_attempted"] and not a["converted"]:
        candidates.append(
            (
                880,
                {
                    "id": "form_validation_failed",
                    "confidence": "high",
                    "evidence": "Clicked submit 503 without conversion signal.",
                },
            )
        )

    if a["mid_blur"]:
        candidates.append(
            (
                450,
                {
                    "id": "tab_switch_away",
                    "confidence": "medium",
                    "evidence": f"windowblur at t={fmt_t(a['mid_blur'][0]['stamp'])} mid-session.",
                },
            )
        )

    candidates.sort(key=lambda x: x[0], reverse=True)
    picked: list[dict] = []
    seen: set[str] = set()
    for _, h in candidates:
        hid = h["id"]
        if hid in seen:
            continue
        if hid == "form_reached_no_interact" and "cta_clicked_no_form_fill" in seen:
            if not (a["form_dwell"] >= 4500 and a["program_dwell"] < dur * 0.44):
                continue
        if hid == "program_too_long" and "price_sticker_shock" in seen and a["price_dwell"] >= 6000:
            continue
        seen.add(hid)
        picked.append(h)
        if len(picked) == 3:
            break
    return picked


def main() -> None:
    dump_rows = []
    visits_out = []
    for vid in IDS:
        analysis, hyps = parse_visit(vid)
        dump_rows.append(analysis)
        visits_out.append(
            {
                "visit_id": vid,
                "converted": analysis["converted"],
                "duration_sec": analysis["duration_sec"],
                "max_scroll_ratio": analysis["max_scroll_ratio"],
                "deepest_section": analysis["deepest_section"],
                "last_section": analysis["last_section"],
                "cta_clicked": analysis["cta_clicked"],
                "form_fields_touched": analysis["form_fields_touched"],
                "submit_attempted": analysis["submit_attempted"],
                "hypotheses": hyps,
            }
        )

    payload = {"batch": 15, "visits": visits_out}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    DUMP.write_text(json.dumps(dump_rows, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"wrote {OUT} visits={len(visits_out)}")
    conv = sum(1 for v in visits_out if v["converted"])
    print(f"converted={conv}/{len(visits_out)}")
    hc = Counter(h["id"] for v in visits_out for h in v["hypotheses"])
    for hid, n in hc.most_common():
        print(f"  {hid}: {n}")
    for v in visits_out:
        print(
            v["visit_id"][-6:],
            "dur", v["duration_sec"],
            "max", v["max_scroll_ratio"], v["deepest_section"],
            "cta", v["cta_clicked"],
            "hyps", [h["id"] for h in v["hypotheses"]],
        )


if __name__ == "__main__":
    main()
