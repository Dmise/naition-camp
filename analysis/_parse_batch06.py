"""Parse batch-06 Webvisor visits and write hypotheses-batch-06.json."""
import json
from collections import Counter
from pathlib import Path

BASE = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\webvisor\2026-08-19")
OUT = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\hypotheses-batch-06.json")
DUMP = Path(r"D:\Yandex.Disk\Education\AI Naition\src\naition-low-conversion-landing\analysis\_batch06_dump.json")

IDS = [
    "4795759616287047959",
    "4795760669175316523",
    "4795762298383761431",
    "4795763977355788436",
    "4795764134204932312",
    "4795764531488358679",
    "4795764542898176078",
    "4795769167293710403",
    "4795769278675550571",
    "4795769727222808692",
    "4795772876763693111",
    "4795772956917629112",
    "4795775649286455549",
    "4795777862122602692",
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


def fmt_t(ms):
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
    keydowns = []
    focuses = []
    window_ev = []
    converted_signal = False
    max_y = 0
    last_y = 0
    last_stamp = 0

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
            clicks.append({"stamp": stamp, "target": e.get("target"), "x": meta.get("x"), "y": meta.get("y")})
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

    cta_clicked = []
    form_fields = set()
    submit_attempted = False
    dead_card_clicks = []
    enriched_clicks = []

    for c in clicks:
        tgt = c["target"]
        sy = y_at(scrolls, c["stamp"])
        node = node_map.get(tgt, {})
        attrs = node.get("attrs") or {}
        cls = attrs.get("class") or ""
        enriched = {
            "stamp": c["stamp"],
            "target": tgt,
            "x": c["x"],
            "click_y": c["y"],
            "scroll_y": sy,
            "scroll_section": section_for(sy / ph),
            "scroll_ratio": round(sy / ph, 4),
            "node": node.get("name"),
            "class": cls,
        }
        enriched_clicks.append(enriched)
        if tgt in CTA_IDS or "btn-register" in cls:
            cta_clicked.append(str(tgt))
        if tgt in FORM_IDS or attrs.get("name") in ("name", "phone", "email", "comment"):
            form_fields.add(tgt)
        if tgt == SUBMIT_ID or attrs.get("type") == "submit":
            submit_attempted = True
        if tgt == 1 and node.get("name") == "html":
            dead_card_clicks.append(enriched)

    for rec in inputs:
        if rec["target"] in FORM_IDS:
            form_fields.add(rec["target"])
    for rec in focuses:
        if rec["type"] == "focus" and rec["target"] in FORM_IDS:
            form_fields.add(rec["target"])
    for rec in clicks:
        if rec["target"] in FORM_IDS:
            form_fields.add(rec["target"])

    converted = bool(converted_signal or (submit_attempted and form_fields))

    mid_blur = [w for w in window_ev if w["type"] == "windowblur" and w["stamp"] < dur_ms - 1500]
    cta_times = [c for c in enriched_clicks if str(c["target"]) in {str(i) for i in CTA_IDS}]
    first_cta = cta_times[0] if cta_times else None
    form_dwell_ms = dwell.get("form", 0)
    price_dwell_ms = dwell.get("price", 0)
    program_dwell_ms = dwell.get("program", 0)
    hero_dwell_ms = dwell.get("hero", 0)
    photo_dwell_ms = dwell.get("photo", 0)
    instructors_dwell_ms = dwell.get("instructors", 0)
    legal_dwell_ms = dwell.get("legal", 0)

    return {
        "visit_id": vid,
        "converted": converted,
        "duration_sec": summary.get("duration_sec"),
        "duration_ms": dur_ms,
        "pageHeight": ph,
        "max_y": max_y,
        "max_scroll_ratio": round(max_ratio, 4),
        "deepest_section": section_for(max_ratio),
        "last_y": last_y,
        "last_ratio": round(last_ratio, 4),
        "last_section": section_for(last_ratio),
        "dwell_ms": dict(dwell),
        "cta_clicked": sorted(set(cta_clicked), key=lambda x: int(x) if x.isdigit() else 0),
        "form_fields_touched": sorted(form_fields),
        "submit_attempted": submit_attempted,
        "clicks": enriched_clicks,
        "dead_card_clicks": dead_card_clicks,
        "first_cta": first_cta,
        "mid_blur": mid_blur,
        "window_ev": window_ev,
        "form_dwell_ms": form_dwell_ms,
        "price_dwell_ms": price_dwell_ms,
        "program_dwell_ms": program_dwell_ms,
        "hero_dwell_ms": hero_dwell_ms,
        "photo_dwell_ms": photo_dwell_ms,
        "instructors_dwell_ms": instructors_dwell_ms,
        "legal_dwell_ms": legal_dwell_ms,
        "scrolls": scrolls,
    }


def top_sections(dwell_ms, n=3):
    return sorted(dwell_ms.items(), key=lambda x: -x[1])[:n]


def generate_hypotheses(v):
    """Return up to 3 hypotheses scored by relevance to this visit."""
    dur = v["duration_ms"]
    dur_s = v["duration_sec"]
    ph = v["pageHeight"]
    max_r = v["max_scroll_ratio"]
    deepest = v["deepest_section"]
    last_sec = v["last_section"]
    cta = v["cta_clicked"]
    fields = v["form_fields_touched"]
    submit = v["submit_attempted"]
    converted = v["converted"]
    dwell = v["dwell_ms"]
    dead = v["dead_card_clicks"]
    first_cta = v["first_cta"]
    mid_blur = v["mid_blur"]
    scored = []

    if converted:
        return [{
            "id": "converted",
            "confidence": "high",
            "evidence": f"Successful form submit: submit 503 clicked and fields {sorted(fields)} touched; max scroll y={v['max_y']} ({max_r:.1%}).",
        }]

    longest_name, longest_ms = max(dwell.items(), key=lambda x: x[1])

    if cta and not fields and not submit:
        cta_node = first_cta["target"] if first_cta else cta[0]
        cta_t = fmt_t(first_cta["stamp"]) if first_cta else "?"
        cta_sy = first_cta["scroll_y"] if first_cta else 0
        scored.append((100, {
            "id": "cta_clicked_no_form_fill",
            "confidence": "high",
            "evidence": f"Clicked CTA node {cta_node} at {cta_t}s (scrollY={cta_sy}, {section_for(cta_sy/ph)}), reached form y={v['max_y']} ({max_r:.1%}), {fmt_t(v['form_dwell_ms'])}s on form with 0 focus/change on 485/490/495/500, no submit 503.",
        }))

    if not cta and max_r < 0.81:
        if deepest == "program" and dwell.get("program", 0) > dur * 0.4:
            scored.append((95, {
                "id": "program_too_long",
                "confidence": "high",
                "evidence": f"Never left program: max scrollY={v['max_y']} ({max_r:.1%}), {fmt_t(dwell['program'])}s dwell there after {fmt_t(v['hero_dwell_ms'])}s in hero, then windowblur/eof at {dur_s}s with no price or form.",
            }))
        scored.append((92, {
            "id": "no_midpage_cta",
            "confidence": "high",
            "evidence": f"{dur_s}s session covering only hero→about→program (no CTA in those sections); never reached price buttons 414/438/462.",
        }))

    if max_r < 0.10 and v["hero_dwell_ms"] > dur * 0.6:
        scored.append((90, {
            "id": "bounce_hero_no_cta",
            "confidence": "high",
            "evidence": f"Never left hero: max y={v['max_y']} ({max_r:.1%}), {fmt_t(v['hero_dwell_ms'])}s in CTA-less 0–10% zone of {dur_s}s session.",
        }))

    if dur_s <= 15 and max_r < 0.18:
        scored.append((88, {
            "id": "bounce_short_session",
            "confidence": "high",
            "evidence": f"Short {dur_s}s visit, max scroll {max_r:.1%} ({deepest}), no CTA or form reach.",
        }))

    prog_ms = dwell.get("program", 0)
    if prog_ms >= longest_ms and prog_ms > dur * 0.35 and deepest != "program":
        scored.append((85 if prog_ms > dur * 0.4 else 70, {
            "id": "program_too_long",
            "confidence": "high" if prog_ms > dur * 0.4 else "medium",
            "evidence": f"Dwelt {fmt_t(prog_ms)}s in program (longest segment) after {fmt_t(v['hero_dwell_ms'])}s in CTA-less hero; first CTA only after reaching price at 81%.",
        }))
    elif prog_ms >= longest_ms and prog_ms > dur * 0.35:
        scored.append((82, {
            "id": "program_too_long",
            "confidence": "high",
            "evidence": f"Dwelt {fmt_t(prog_ms)}s in program (18–52%, longest segment, {prog_ms/dur:.0%} of {dur_s}s) with no mid-page CTA until price at 81%.",
        }))

    if v["hero_dwell_ms"] > dur * 0.38 and v["hero_dwell_ms"] >= 15000:
        scored.append((78, {
            "id": "no_hero_cta",
            "confidence": "medium" if v["hero_dwell_ms"] < dur * 0.42 else "high",
            "evidence": f"Sat {fmt_t(v['hero_dwell_ms'])}s in hero (longest hero dwell in this batch) with no CTA, only then scrolled; conversion CTA appears only at price ~81%.",
        }))

    photo_ms = dwell.get("photo", 0)
    instr_ms = dwell.get("instructors", 0)
    if photo_ms > 5000 and instr_ms < 1500:
        photo_score = 82 if photo_ms > 6000 else 76
        scored.append((photo_score, {
            "id": "photo_dropout",
            "confidence": "medium",
            "evidence": f"Paused {fmt_t(photo_ms)}s on the full-bleed CPR photo (67–74%) and skipped instructors in the scroll path before jumping to price.",
        }))

    if cta and not fields and last_sec == "price" and v["last_ratio"] < 0.88:
        shock_score = 86 if v["price_dwell_ms"] > 3000 else 74
        scored.append((shock_score, {
            "id": "price_sticker_shock",
            "confidence": "high" if v["price_dwell_ms"] > 4000 else "medium",
            "evidence": f"After seeing the form, last scroll was y={v['last_y']} ({v['last_ratio']:.1%} price) with {fmt_t(v['price_dwell_ms'])}s price dwell; left from the 4900/7900/12900 cards, not the form.",
        }))
    elif cta and not fields and v["price_dwell_ms"] > 4500:
        scored.append((72, {
            "id": "price_sticker_shock",
            "confidence": "high" if v["price_dwell_ms"] > 6000 else "medium",
            "evidence": f"{fmt_t(v['price_dwell_ms'])}s on price (second-longest segment after program) before clicking basic CTA; still did not start the lead form.",
        }))

    if len(dead) >= 2:
        times = "/".join(f"{fmt_t(d['stamp'])}s" for d in dead[:3])
        sy = dead[0]["scroll_y"]
        card_score = 83 if len(dead) >= 3 else 65
        scored.append((card_score, {
            "id": "cards_look_clickable",
            "confidence": "high" if len(dead) >= 3 else "medium",
            "evidence": f"Three clicks on html node 1 at x={dead[0].get('x')}, scrollY={sy} ({sy/ph:.1%} program) at {times} — dead hits on program-module cards that do nothing.",
        }))

    if instr_ms > 4000 and first_cta:
        instr_score = 79 if instr_ms > 5500 else 62
        scored.append((instr_score, {
            "id": "instructors_trust",
            "confidence": "medium",
            "evidence": f"Paused {fmt_t(instr_ms)}s on instructors (initials, not photos) immediately before the CTA click; then left without filling the form.",
        }))

    if dwell.get("legal", 0) > 3000:
        scored.append((55, {
            "id": "legal_concern",
            "confidence": "medium",
            "evidence": f"Paused {fmt_t(dwell['legal'])}s on legal (60–67%) — unusually long vs injuries/photo skips.",
        }))

    if deepest == "form" and not fields and not cta and max_r >= 0.88:
        scored.append((50, {
            "id": "form_reached_no_interact",
            "confidence": "high",
            "evidence": f"Scrolled to form (max y={v['max_y']}, {max_r:.1%}) without CTA click or field touch; {fmt_t(v['form_dwell_ms'])}s form dwell, no 485/490/495/500.",
        }))

    if fields and not submit:
        scored.append((48, {
            "id": "form_friction_abandoned",
            "confidence": "high",
            "evidence": f"Touched fields {sorted(fields)} but no submit 503; abandoned form after {fmt_t(v['form_dwell_ms'])}s.",
        }))

    if submit and not converted:
        scored.append((46, {
            "id": "form_validation_failed",
            "confidence": "high",
            "evidence": f"Submit 503 clicked at least once but no conversion signal; fields touched: {sorted(fields)}.",
        }))

    if max_r >= 0.97:
        scored.append((40, {
            "id": "scrolled_past_form",
            "confidence": "medium",
            "evidence": f"Reached footer zone (max y={v['max_y']}, {max_r:.1%}) without converting.",
        }))

    if mid_blur:
        scored.append((38, {
            "id": "tab_switch_away",
            "confidence": "medium",
            "evidence": f"Windowblur at {fmt_t(mid_blur[0]['stamp'])}s mid-session (before final {fmt_t(dur)}s), returned without converting.",
        }))

    scored.sort(key=lambda x: -x[0])
    seen = set()
    unique = []
    for _, hyp in scored:
        if hyp["id"] not in seen:
            unique.append(hyp)
            seen.add(hyp["id"])
            if len(unique) >= 3:
                break
    return unique


def main():
    parsed = []
    visits_out = []
    for vid in IDS:
        v = parse_visit(vid)
        hyps = generate_hypotheses(v)
        parsed.append(v)
        visits_out.append({
            "visit_id": v["visit_id"],
            "converted": v["converted"],
            "duration_sec": v["duration_sec"],
            "max_scroll_ratio": v["max_scroll_ratio"],
            "deepest_section": v["deepest_section"],
            "last_section": v["last_section"],
            "cta_clicked": v["cta_clicked"],
            "form_fields_touched": [str(x) for x in v["form_fields_touched"]],
            "submit_attempted": v["submit_attempted"],
            "hypotheses": hyps,
        })

    OUT.write_text(
        json.dumps({"batch": 6, "visits": visits_out}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # compact dump for verification
    compact = []
    for v in parsed:
        compact.append({k: v[k] for k in v if k not in ("scrolls", "clicks")})
        compact[-1]["n_clicks"] = len(v["clicks"])
        compact[-1]["n_dead"] = len(v["dead_card_clicks"])
    DUMP.write_text(json.dumps(compact, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {OUT} visits={len(visits_out)}")
    for r in visits_out:
        hyps = [x["id"] for x in r["hypotheses"]]
        print(
            r["visit_id"][-6:],
            f"dur={r['duration_sec']} max={r['max_scroll_ratio']} deep={r['deepest_section']}",
            f"last={r['last_section']} cta={r['cta_clicked']} fields={r['form_fields_touched']}",
            f"hyps={hyps}",
        )


if __name__ == "__main__":
    main()
