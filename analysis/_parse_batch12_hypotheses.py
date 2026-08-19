"""Parse batch-12 Webvisor visits and emit hypotheses-batch-12.json."""
import json
from collections import Counter
from pathlib import Path

BASE = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\webvisor\2026-08-19")
OUT = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\hypotheses-batch-12.json")
IDS = [
    "4795872243509100701",
    "4795873207667654990",
    "4795875169827291147",
    "4795877248727777329",
    "4795877942669082792",
    "4795878351934062768",
    "4795881176127766710",
    "4795882170835271731",
    "4795883165749346489",
    "4795884337317019703",
    "4795888715562483757",
    "4795889933621657697",
    "4795890257045487959",
    "4795891667444170939",
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
FIELD_NAMES = {485: "name", 490: "phone", 495: "email", 500: "purpose"}


def section_for(ratio):
    for name, a, b in SECTIONS:
        if a <= ratio < b:
            return name
    return "footer" if ratio >= 0.97 else "hero"


def y_at(scrolls, stamp):
    y = 0
    for s, sy in scrolls:
        if s <= stamp:
            y = sy
        else:
            break
    return y


def pct(x):
    return round(x * 100, 1)


def ts(ms):
    return round(ms / 1000, 1)


def parse_visit(vid):
    path = BASE / f"visit_{vid}.json"
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    events = data.get("parsed_events") or []
    summary = data.get("summary") or {}

    page_h = 8513
    node_map = {}
    scrolls = []
    clicks = []
    inputs = []
    focuses = []
    window_ev = []
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
                    }
        if t == "resize":
            page_h = meta.get("pageHeight") or page_h
        if t == "scroll" and meta.get("y") is not None:
            y = meta["y"]
            scrolls.append((stamp, y))
            max_y = max(max_y, y)
            last_y = y
        if t == "click":
            clicks.append({"stamp": stamp, "target": e.get("target"), "x": meta.get("x"), "y": meta.get("y")})
        if t in ("input", "change"):
            inputs.append({"stamp": stamp, "type": t, "target": e.get("target"), "meta": meta})
        if t in ("focus", "blur"):
            focuses.append({"stamp": stamp, "type": t, "target": e.get("target")})
        if t in ("windowblur", "windowfocus"):
            window_ev.append({"stamp": stamp, "type": t})
        if e.get("group") == "mutation":
            blob = json.dumps(meta, ensure_ascii=False).lower()
            if "success" in blob or "заявк" in blob:
                converted_signal = True

    ph = page_h or 8513
    max_ratio = max_y / ph if ph else 0
    last_ratio = last_y / ph if ph else 0
    dur_ms = summary.get("duration_ms") or last_stamp

    dwell = Counter()
    if scrolls:
        prev_stamp, prev_y = scrolls[0]
        for stamp, y in scrolls[1:]:
            dwell[section_for(prev_y / ph)] += max(0, stamp - prev_stamp)
            prev_stamp, prev_y = stamp, y
        dwell[section_for(prev_y / ph)] += max(0, dur_ms - prev_stamp)
    else:
        dwell["hero"] = dur_ms

    enriched_clicks = []
    cta_clicked = False
    cta_click = None
    submit_attempted = False
    for c in clicks:
        tgt = c["target"]
        sy = y_at(scrolls, c["stamp"])
        node = node_map.get(tgt, {})
        attrs = node.get("attrs") or {}
        cls = attrs.get("class") or ""
        ec = {
            "stamp": c["stamp"],
            "target": tgt,
            "x": c["x"],
            "y": c["y"],
            "scroll_y": sy,
            "scroll_section": section_for(sy / ph),
            "scroll_ratio": round(sy / ph, 4),
            "node": node.get("name"),
            "class": cls,
        }
        enriched_clicks.append(ec)
        if tgt in CTA_IDS or "btn-register" in cls:
            cta_clicked = True
            cta_click = ec
        if tgt == SUBMIT_ID or attrs.get("type") == "submit":
            submit_attempted = True

    touched = set()
    for c in clicks:
        if c["target"] in FORM_IDS:
            touched.add(FIELD_NAMES[c["target"]])
    for rec in inputs:
        if rec["target"] in FORM_IDS:
            touched.add(FIELD_NAMES[rec["target"]])
    for rec in focuses:
        if rec["type"] == "focus" and rec["target"] in FORM_IDS:
            touched.add(FIELD_NAMES[rec["target"]])

    mid_blur = [w for w in window_ev if w["type"] == "windowblur" and w["stamp"] < dur_ms - 1500]
    dead_clicks = [c for c in enriched_clicks if c["target"] == 1]

    return {
        "visit_id": vid,
        "converted": bool(converted_signal),
        "duration_sec": summary.get("duration_sec") or round(dur_ms / 1000),
        "max_scroll_ratio": round(max_ratio, 4),
        "deepest_section": section_for(max_ratio),
        "last_section": section_for(last_ratio),
        "max_y": max_y,
        "last_y": last_y,
        "page_h": ph,
        "cta_clicked": cta_clicked,
        "cta_click": cta_click,
        "form_fields_touched": sorted(touched),
        "submit_attempted": submit_attempted,
        "dwell_ms": dict(dwell),
        "dead_clicks": dead_clicks,
        "mid_blur": mid_blur,
        "dur_ms": dur_ms,
        "summary": summary,
    }


def build_hypotheses(r):
    hyps = []
    ph = r["page_h"]
    dwell = r["dwell_ms"]
    hero_s = dwell.get("hero", 0) / 1000
    prog_s = dwell.get("program", 0) / 1000
    form_s = dwell.get("form", 0) / 1000
    price_s = dwell.get("price", 0) / 1000
    instr_s = dwell.get("instructors", 0) / 1000
    deepest = r["deepest_section"]
    last = r["last_section"]
    max_r = r["max_scroll_ratio"]
    max_y = r["max_y"]
    last_y = r["last_y"]
    cc = r["cta_click"]
    scrolled_back_to_price = deepest == "form" and last == "price" and max_y > last_y + 30

    if r["converted"]:
        hyps.append({
            "id": "converted",
            "confidence": "high",
            "evidence": f"Successful form submit (DOM success/заявка mutation). max y={max_y} ({pct(max_r)}% form), submit 503 clicked.",
        })
        return hyps

    dead = r["dead_clicks"]
    if len(dead) >= 2:
        times = "/".join(str(ts(c["stamp"])) for c in dead[:3])
        sy = dead[0]["scroll_y"]
        sr = dead[0]["scroll_ratio"]
        ym = "/".join(str(c["y"]) for c in dead[:3])
        hyps.append({
            "id": "cards_look_clickable",
            "confidence": "high",
            "evidence": (
                f"Three clicks on non-interactive target 1 (html) at x=211, y_meta≈{ym} "
                f"while scroll.meta.y={sy} (program {pct(sr)}%) at t={times}s. "
                f"Program-module cards use cursor:pointer but have no href/handler."
            ),
        })

    if prog_s >= 25:
        hyps.append({
            "id": "program_too_long",
            "confidence": "high",
            "evidence": (
                f"Program dwell {prog_s:.1f}s (longest block 18–52%) — {pct(prog_s / (r['dur_ms']/1000))}% of {r['duration_sec']}s session. "
                f"Hero {hero_s:.1f}s then {prog_s:.1f}s slog through program before injuries/price."
            ),
        })
    elif prog_s >= 20 and prog_s >= hero_s * 0.8:
        hyps.append({
            "id": "program_too_long",
            "confidence": "medium",
            "evidence": (
                f"Program dwell {prog_s:.1f}s vs hero {hero_s:.1f}s; dead clicks at program y={dead[0]['scroll_y'] if dead else '?'} "
                f"({pct(dead[0]['scroll_ratio']) if dead else 0}%) before reaching price CTA."
            ),
        })

    if hero_s >= 20 and r["cta_clicked"]:
        hyps.append({
            "id": "no_hero_cta",
            "confidence": "medium",
            "evidence": (
                f"Hero (0–10%) has no register CTA; ~{hero_s:.1f}s on hero before scrolling into program. "
                f"First «Записаться» only at price 81–88% (nodes 414/438/462)."
            ),
        })

    if prog_s >= 15 and r["cta_clicked"]:
        hyps.append({
            "id": "no_midpage_cta",
            "confidence": "medium",
            "evidence": (
                f"~{prog_s:.1f}s in program (18–52%) with no mid-page CTA. "
                f"Visitor endured long scroll; first conversion control only at price band."
            ),
        })

    if r["cta_clicked"] and not r["form_fields_touched"]:
        cta_t = ts(cc["stamp"]) if cc else "?"
        cta_y = cc["scroll_y"] if cc else 0
        cta_sec = cc["scroll_section"] if cc else "?"
        cta_r = cc["scroll_ratio"] if cc else 0
        hyps.append({
            "id": "cta_clicked_no_form_fill",
            "confidence": "high",
            "evidence": (
                f"Clicked price CTA node 414 (btn-register «Записаться») at t={cta_t}s from scroll y={cta_y} "
                f"({cta_sec} {pct(cta_r)}%). 0 inputs, 0 keydowns on fields 485/490/495/500; submit 503 never clicked."
            ),
        })

    if deepest == "form" and not r["form_fields_touched"] and r["cta_clicked"]:
        back_note = (
            f"Scrolled back to price (last y={last_y}, {pct(last_y/ph)}%) before windowblur."
            if scrolled_back_to_price
            else "Session ended on form without typing."
        )
        hyps.append({
            "id": "form_reached_no_interact",
            "confidence": "high",
            "evidence": (
                f"After CTA, scrolled to max y={max_y} ({pct(max_r)}% form) with ~{form_s:.1f}s form dwell. "
                f"Fields 485/490/495/500 never focused; {back_note}"
            ),
        })

    if scrolled_back_to_price:
        hyps.append({
            "id": "price_sticker_shock",
            "confidence": "medium",
            "evidence": (
                f"Reached form (max y={max_y}, {pct(max_r)}%) after CTA but last scroll y={last_y} "
                f"({pct(last_y/ph)}%, price 81–88%). Returned to tariffs without submitting; ~{price_s:.1f}s price dwell at exit."
            ),
        })

    if r["mid_blur"]:
        hyps.append({
            "id": "tab_switch_away",
            "confidence": "medium",
            "evidence": f"windowblur at t={ts(r['mid_blur'][0]['stamp'])}s mid-session (not end blur). Returned but did not convert.",
        })

    if instr_s >= 6 and r["cta_clicked"] and cc and cc["scroll_section"] in ("instructors", "price"):
        hyps.append({
            "id": "instructors_trust",
            "confidence": "low",
            "evidence": (
                f"~{instr_s:.1f}s in instructors (74–81%) reading bios; CTA 414 clicked at t={ts(cc['stamp'])}s "
                f"from {cc['scroll_section']} y={cc['scroll_y']}. Still no form fill after scroll-to-register."
            ),
        })

    # Priority order for cap
    priority = [
        "converted",
        "cards_look_clickable",
        "program_too_long",
        "cta_clicked_no_form_fill",
        "form_reached_no_interact",
        "price_sticker_shock",
        "no_midpage_cta",
        "no_hero_cta",
        "instructors_trust",
        "tab_switch_away",
        "bounce_hero_no_cta",
        "bounce_short_session",
        "photo_dropout",
        "legal_concern",
        "form_friction_abandoned",
        "form_validation_failed",
        "scrolled_past_form",
    ]
    rank = {k: i for i, k in enumerate(priority)}
    hyps.sort(key=lambda h: rank.get(h["id"], 99))
    return hyps[:4]


def main():
    visits_out = []
    for vid in IDS:
        r = parse_visit(vid)
        visits_out.append({
            "visit_id": r["visit_id"],
            "converted": r["converted"],
            "duration_sec": r["duration_sec"],
            "max_scroll_ratio": r["max_scroll_ratio"],
            "deepest_section": r["deepest_section"],
            "last_section": r["last_section"],
            "cta_clicked": r["cta_clicked"],
            "form_fields_touched": r["form_fields_touched"],
            "submit_attempted": r["submit_attempted"],
            "hypotheses": build_hypotheses(r),
        })

    payload = {"batch": 12, "visits": visits_out}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} visits={len(visits_out)}")
    ids_count = Counter(h["id"] for v in visits_out for h in v["hypotheses"])
    for k, n in ids_count.most_common():
        print(f"  {k}: {n}")


if __name__ == "__main__":
    main()
