#!/usr/bin/env python3
"""Poll for all batch JSON files and aggregate into hypotheses.md report."""
import json
import os
import sys
import time
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)
REPORT_PATH = os.path.join(ROOT, "analysis", "hypotheses.md")
TIMEOUT_VISITS = {
    "4795965628111650879",
    "4795966191612723460",
    "4795970156773507224",
}
EXPECTED_VISITS = 224
POLL_INTERVAL = 45  # seconds
MAX_WAIT = 30 * 60  # 30 minutes

HYPOTHESIS_RU = {
    "bounce_hero_no_cta": "Bounce в hero — нет CTA, ушёл не начав",
    "bounce_short_session": "Короткая сессия (<30s)",
    "program_too_long": "Устал читать длинную программу (18-52% страницы)",
    "no_midpage_cta": "Нет CTA до блока тарифов (81%)",
    "cards_look_clickable": "Кликал по «кликабельным» карточкам без действия",
    "legal_concern": "Застрял/отвалился на юридическом блоке",
    "photo_dropout": "Отвал на фото-блоке",
    "instructors_trust": "Недостаточно доверия к инструкторам (инициалы без фото)",
    "price_sticker_shock": "Шок от цены (4900/7900/12900)",
    "cta_clicked_no_form_fill": "Нажал «Записаться», но не заполнил форму",
    "form_reached_no_interact": "Дошёл до формы, не начал заполнять",
    "form_friction_abandoned": "Начал заполнять, бросил",
    "form_validation_failed": "Попытка submit без успеха",
    "scrolled_past_form": "Проскроллил мимо формы",
    "tab_switch_away": "Ушёл в другую вкладку (windowblur)",
    "no_hero_cta": "В hero нет кнопки записи",
}

SECTIONS = [
    "hero", "program", "injuries", "legal", "photo",
    "instructors", "price", "form", "footer",
]


def batch_path(n: int) -> str:
    return os.path.join(BASE, f"hypotheses-batch-{n:02d}.json")


def wait_for_all_batches() -> list[int]:
    start = time.time()
    missing = list(range(1, 17))
    while missing:
        still_missing = []
        for n in missing:
            p = batch_path(n)
            if os.path.isfile(p):
                try:
                    with open(p, encoding="utf-8") as f:
                        json.load(f)
                except (json.JSONDecodeError, OSError):
                    still_missing.append(n)
            else:
                still_missing.append(n)
        missing = still_missing
        if not missing:
            break
        elapsed = time.time() - start
        if elapsed >= MAX_WAIT:
            print(f"TIMEOUT after {elapsed:.0f}s. Missing batches: {missing}", file=sys.stderr)
            sys.exit(1)
        print(f"[{elapsed:.0f}s] Waiting for batches: {missing}", flush=True)
        time.sleep(POLL_INTERVAL)
    return list(range(1, 17))


def load_all_visits() -> list[dict]:
    visits = []
    for n in range(1, 17):
        with open(batch_path(n), encoding="utf-8") as f:
            data = json.load(f)
        batch_visits = data.get("visits", [])
        print(f"  batch {n:02d}: {len(batch_visits)} visits")
        visits.extend(batch_visits)
    return visits


def typical_confidence(counts: Counter) -> str:
    if not counts:
        return "—"
    return counts.most_common(1)[0][0]


def build_report(visits: list[dict]) -> str:
    # Deduplicate by visit_id (keep first)
    seen = {}
    duplicates = []
    for v in visits:
        vid = v.get("visit_id")
        if vid in seen:
            duplicates.append(vid)
        else:
            seen[vid] = v
    visits_unique = list(seen.values())

    timeout_found = [v["visit_id"] for v in visits_unique if v.get("visit_id") in TIMEOUT_VISITS]
    visits_clean = [v for v in visits_unique if v.get("visit_id") not in TIMEOUT_VISITS]

    total = len(visits_clean)
    converted = [v for v in visits_clean if v.get("converted")]
    non_converted = [v for v in visits_clean if not v.get("converted")]
    conv_count = len(converted)
    conv_rate = (conv_count / total * 100) if total else 0
    drop_count = len(non_converted)

    # Hypothesis aggregation
    hyp_visit_count: Counter = Counter()
    hyp_confidence: dict[str, Counter] = defaultdict(Counter)

    for v in visits_clean:
        hyp_ids_seen = set()
        for h in v.get("hypotheses", []):
            hid = h.get("id")
            if not hid or hid == "converted":
                continue
            conf = h.get("confidence", "unknown")
            hyp_confidence[hid][conf] += 1
            if hid not in hyp_ids_seen:
                hyp_visit_count[hid] += 1
                hyp_ids_seen.add(hid)

    # Section distribution for non-converted
    section_last: Counter = Counter()
    section_deepest: Counter = Counter()
    for v in non_converted:
        ls = v.get("last_section") or "unknown"
        ds = v.get("deepest_section") or "unknown"
        section_last[ls] += 1
        section_deepest[ds] += 1

    # Build markdown
    lines = []
    lines.append("# Анализ отвалов посетителей лендинга «Первая помощь»")
    lines.append("")
    lines.append("## Методология")
    lines.append("- Кратко: 224 визита Webvisor, 19.08.2026, конверсия = успешная отправка формы #registration-form")
    lines.append("- 10 секций страницы (hero → footer)")
    lines.append("- 3 файла без данных (timeout scrape): " + ", ".join(sorted(TIMEOUT_VISITS)))
    lines.append("")
    lines.append("## Сводка")
    lines.append(f"- Визитов проанализировано: **{total}**")
    lines.append(f"- Конверсий: **{conv_count}** ({conv_rate:.1f}%)")
    lines.append(f"- Без конверсии: **{drop_count}**")
    lines.append("")

    if duplicates:
        lines.append(f"> ⚠ Дубликаты visit_id (удалены): {len(duplicates)} — {', '.join(duplicates[:10])}{'…' if len(duplicates) > 10 else ''}")
        lines.append("")
    if timeout_found:
        lines.append(f"> ⚠ Timeout-визиты найдены в батчах (исключены): {', '.join(timeout_found)}")
        lines.append("")
    if total != EXPECTED_VISITS:
        lines.append(f"> ⚠ Ожидалось ~{EXPECTED_VISITS} визитов, получено {total} (raw до дедупликации: {len(visits)}, unique: {len(visits_unique)})")
        lines.append("")

    lines.append("## Топ гипотез отвала (по частоте)")
    lines.append("")
    lines.append("| # | hypothesis id | описание | визитов | % от неконвертированных | типичная confidence |")
    lines.append("|---|---------------|----------|---------|-------------------------|---------------------|")

    sorted_hyps = hyp_visit_count.most_common()
    for rank, (hid, count) in enumerate(sorted_hyps, 1):
        desc = HYPOTHESIS_RU.get(hid, hid)
        pct = (count / drop_count * 100) if drop_count else 0
        tc = typical_confidence(hyp_confidence[hid])
        lines.append(f"| {rank} | `{hid}` | {desc} | {count} | {pct:.1f}% | {tc} |")

    lines.append("")
    lines.append("### Распределение confidence по гипотезам")
    lines.append("")
    lines.append("| hypothesis id | high | medium | low |")
    lines.append("|---------------|------|--------|-----|")
    for hid, count in sorted_hyps:
        c = hyp_confidence[hid]
        lines.append(f"| `{hid}` | {c.get('high', 0)} | {c.get('medium', 0)} | {c.get('low', 0)} |")

    lines.append("")
    lines.append("## Распределение по секциям отвала")
    lines.append("")
    lines.append("### last_section (неконвертированные)")
    lines.append("")
    lines.append("| секция | визитов | % |")
    lines.append("|--------|---------|---|")
    for sec in SECTIONS + ["unknown"]:
        c = section_last.get(sec, 0)
        if c == 0 and sec == "unknown":
            continue
        pct = (c / drop_count * 100) if drop_count else 0
        if c > 0 or sec in SECTIONS:
            lines.append(f"| {sec} | {c} | {pct:.1f}% |")

    lines.append("")
    lines.append("### deepest_section (неконвертированные)")
    lines.append("")
    lines.append("| секция | визитов | % |")
    lines.append("|--------|---------|---|")
    for sec in SECTIONS + ["unknown"]:
        c = section_deepest.get(sec, 0)
        if c == 0 and sec == "unknown":
            continue
        pct = (c / drop_count * 100) if drop_count else 0
        if c > 0 or sec in SECTIONS:
            lines.append(f"| {sec} | {c} | {pct:.1f}% |")

    # Patterns
    lines.append("")
    lines.append("## Паттерны поведения")
    lines.append("")
    top5 = sorted_hyps[:5]
    patterns = []
    for hid, count in top5:
        desc = HYPOTHESIS_RU.get(hid, hid)
        pct = (count / drop_count * 100) if drop_count else 0
        patterns.append(f"- **{desc}** (`{hid}`): {count} визитов ({pct:.1f}% неконвертированных)")

    # Additional pattern bullets based on data
    cta_no_fill = hyp_visit_count.get("cta_clicked_no_form_fill", 0)
    program_long = hyp_visit_count.get("program_too_long", 0)
    cards = hyp_visit_count.get("cards_look_clickable", 0)
    hero_bounce = hyp_visit_count.get("bounce_hero_no_cta", 0) + hyp_visit_count.get("no_hero_cta", 0)
    form_issues = (
        hyp_visit_count.get("form_reached_no_interact", 0)
        + hyp_visit_count.get("form_friction_abandoned", 0)
        + hyp_visit_count.get("form_validation_failed", 0)
    )

    lines.extend(patterns)
    lines.append(f"- Клик по CTA без заполнения формы — доминирующий паттерн среди дошедших до тарифов ({cta_no_fill} визитов)")
    lines.append(f"- Длинная программа (18–52% страницы) — частая точка задержки ({program_long} визитов)")
    lines.append(f"- «Мёртвые» клики по карточкам программы ({cards} визитов)")
    if hero_bounce:
        lines.append(f"- Ранний отвал в hero / отсутствие CTA ({hero_bounce} визитов)")
    if form_issues:
        lines.append(f"- Проблемы на этапе формы: дошёл но не тронул / начал и бросил / validation ({form_issues} визитов суммарно)")

    # Recommendations
    lines.append("")
    lines.append("## Рекомендации (приоритет)")
    lines.append("")
    recs = generate_recommendations(sorted_hyps, hyp_visit_count, drop_count)
    for i, rec in enumerate(recs, 1):
        lines.append(f"{i}. {rec}")

    return "\n".join(lines) + "\n", sorted_hyps[:5], {
        "total": total,
        "converted": conv_count,
        "drop_count": drop_count,
        "duplicates": duplicates,
        "timeout_found": timeout_found,
    }


def generate_recommendations(sorted_hyps, hyp_visit_count, drop_count) -> list[str]:
    recs = []
    top_ids = [h[0] for h in sorted_hyps[:7]]

    rec_map = {
        "cta_clicked_no_form_fill": "После клика «Записаться» — автоскролл к форме + sticky mini-форма или модал с полями; сократить путь от CTA до первого поля.",
        "program_too_long": "Свернуть программу в аккордеон / «показать ещё»; добавить промежуточный CTA после блока программы (~50% страницы).",
        "cards_look_clickable": "Убрать hover/active-стили с неинтерактивных карточек или сделать их раскрывающимися; явно показать, что это информация, а не кнопки.",
        "no_midpage_cta": "Добавить CTA «Записаться» после программы и фото — до блока тарифов (сейчас 81% страницы без действия).",
        "bounce_hero_no_cta": "Добавить заметную кнопку «Записаться» в hero; усилить value proposition above the fold.",
        "no_hero_cta": "Добавить CTA в первый экран — сейчас единственный путь вниз через скролл.",
        "form_reached_no_interact": "Упростить форму: меньше полей, placeholder-подсказки, social proof рядом с формой.",
        "form_friction_abandoned": "Сохранять прогресс формы; маска телефона; убрать необязательные поля.",
        "price_sticker_shock": "Показать рассрочку/скидку раньше; якорная цена; «от X ₽/мес» в hero.",
        "instructors_trust": "Добавить фото инструкторов, сертификаты, отзывы — блок доверия перед ценой.",
        "legal_concern": "Сократить юридический текст; вынести детали в collapsible; добавить «что вы получите» рядом.",
        "photo_dropout": "Оптимизировать фото-блок: lazy load, меньше высота; CTA сразу после фото.",
        "tab_switch_away": "Exit-intent popup с напоминанием; ограниченное предложение при возврате.",
        "scrolled_past_form": "Sticky CTA + повтор формы в footer; визуальный акцент на форме при скролле.",
        "form_validation_failed": "Inline-валидация с понятными сообщениями; не сбрасывать введённые данные.",
        "bounce_short_session": "Ускорить LCP/TTI; сильнее hook в hero для удержания первых 30 секунд.",
    }

    seen = set()
    for hid in top_ids:
        if hid in rec_map and hid not in seen:
            count = hyp_visit_count[hid]
            pct = (count / drop_count * 100) if drop_count else 0
            recs.append(f"**{HYPOTHESIS_RU.get(hid, hid)}** ({count} виз., {pct:.0f}%): {rec_map[hid]}")
            seen.add(hid)
        if len(recs) >= 7:
            break

    # Fill up to 5 if needed
    for hid, text in rec_map.items():
        if len(recs) >= 5:
            break
        if hid not in seen and hyp_visit_count.get(hid, 0) > 0:
            count = hyp_visit_count[hid]
            pct = (count / drop_count * 100) if drop_count else 0
            recs.append(f"**{HYPOTHESIS_RU.get(hid, hid)}** ({count} виз., {pct:.0f}%): {text}")
            seen.add(hid)

    return recs[:7]


def main():
    print("Waiting for all 16 batch files...")
    wait_for_all_batches()
    print("All batches ready. Loading...")
    visits = load_all_visits()
    print(f"Total raw visits: {len(visits)}")
    report, top5, stats = build_report(visits)
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Report written to {REPORT_PATH}")
    print("\n=== TOP 5 HYPOTHESES ===")
    for hid, count in top5:
        print(f"  {hid}: {count}")
    print(f"\nStats: total={stats['total']}, converted={stats['converted']}, drop={stats['drop_count']}")
    if stats["duplicates"]:
        print(f"Duplicates: {stats['duplicates']}")
    if stats["timeout_found"]:
        print(f"Timeout visits in data: {stats['timeout_found']}")


if __name__ == "__main__":
    main()
