import json
import os
import sys
import requests
from datetime import datetime, timezone

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ANALYSIS_FILE = "analysis.json"


def load_data():
    all_data = {}
    for fname in ("data_2024.json", "data_2025_2026.json"):
        if os.path.exists(fname):
            with open(fname) as f:
                all_data.update(json.load(f))
    return all_data


def sec2h(s):
    return round(s / 3600, 1) if s is not None else None


def avg(values):
    v = [x for x in values if x is not None]
    return round(sum(v) / len(v), 1) if v else None


def build_prompt(all_data):
    dates = sorted(all_data.keys())
    if not dates:
        return None, None

    last_date = dates[-1]
    day = all_data[last_date]

    # Readiness
    rd = (day.get("daily_readiness") or [{}])[0]
    rd_score = rd.get("score", "—")
    rd_c = rd.get("contributors", {})

    # Sleep
    sleep_sessions = day.get("sleep", [])
    sl = next((s for s in sleep_sessions if s.get("type") == "long_sleep"), None)
    if sl is None and sleep_sessions:
        sl = max(sleep_sessions, key=lambda s: s.get("total_sleep_duration") or 0)
    sl = sl or {}

    dsl = (day.get("daily_sleep") or [{}])[0]
    sleep_score = dsl.get("score", "—")
    total_h  = sec2h(sl.get("total_sleep_duration"))
    deep_h   = sec2h(sl.get("deep_sleep_duration"))
    rem_h    = sec2h(sl.get("rem_sleep_duration"))
    light_h  = sec2h(sl.get("light_sleep_duration"))
    awake_h  = sec2h(sl.get("awake_time"))
    eff      = sl.get("efficiency", "—")
    bed_start = (sl.get("bedtime_start") or "")[:16].replace("T", " ")[11:] or "—"
    bed_end   = (sl.get("bedtime_end")   or "")[:16].replace("T", " ")[11:] or "—"

    # 7-day trend (days before last_date)
    prev_dates = [d for d in dates if d < last_date][-7:]
    prev_days  = [all_data[d] for d in prev_dates]

    def get_main_sleep(d):
        ss = d.get("sleep", [])
        s = next((x for x in ss if x.get("type") == "long_sleep"), None)
        return s or (ss[0] if ss else {})

    avg_hrv      = avg([get_main_sleep(d).get("average_hrv")      for d in prev_days])
    avg_rhr      = avg([get_main_sleep(d).get("lowest_heart_rate") for d in prev_days])
    avg_sleep    = avg([sec2h(get_main_sleep(d).get("total_sleep_duration")) for d in prev_days])
    avg_readiness = avg([(all_data[d].get("daily_readiness") or [{}])[0].get("score") for d in prev_dates])

    # Yesterday
    yst_date = prev_dates[-1] if prev_dates else "—"
    yst_day  = all_data.get(yst_date, {})
    yst_act  = (yst_day.get("daily_activity") or [{}])[0]
    yst_steps = yst_act.get("steps")
    yst_steps_str = f"{yst_steps:,}" if yst_steps else "—"

    yst_workouts = yst_day.get("workout", [])
    if yst_workouts:
        def fmt_activity(a):
            parts = a.split("_")
            return " ".join(p.capitalize() for p in parts)
        def duration(w):
            try:
                from datetime import datetime as dt
                s = dt.fromisoformat(w["start_datetime"].replace("Z", "+00:00"))
                e = dt.fromisoformat(w["end_datetime"].replace("Z", "+00:00"))
                return round((e - s).total_seconds() / 60, 0)
            except Exception:
                return "?"
        yst_wk_str = ", ".join(f"{fmt_activity(w.get('activity',''))} {duration(w):.0f}хв" for w in yst_workouts)
    else:
        yst_wk_str = "немає"

    prompt = f"""Проаналізуй мої ранкові метрики здоров'я за {last_date}:

READINESS: {rd_score}/100
Складові: HRV balance {rd_c.get('hrv_balance','—')}, RHR {rd_c.get('resting_heart_rate','—')}, Sleep balance {rd_c.get('sleep_balance','—')}, Activity balance {rd_c.get('activity_balance','—')}, Body temp {rd_c.get('body_temperature','—')}, Recovery {rd_c.get('recovery_index','—')}, Previous night {rd_c.get('previous_night','—')}

СОН: sleep score {sleep_score}/100, загальний {total_h or '—'}г ({bed_start}–{bed_end}), deep {deep_h or '—'}г, REM {rem_h or '—'}г, light {light_h or '—'}г, awake {awake_h or '—'}г, ефективність {eff}%

ТРЕНД 7 ДНІВ: середній HRV {avg_hrv or '—'} ms, середній RHR {avg_rhr or '—'} bpm, середній сон {avg_sleep or '—'}г, середній readiness {avg_readiness or '—'}/100

ВЧОРА ({yst_date}): кроки {yst_steps_str}, тренування: {yst_wk_str}

Дай стислий аналіз — 3-4 короткі абзаци без підзаголовків і нумерації: загальна оцінка стану, головний інсайт дня (що саме впливає на самопочуття), і конкретна рекомендація — тренуватись інтенсивно чи відновлюватись. Пиши українською, коротко і по суті."""

    return prompt, last_date


def call_claude(prompt):
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-5",
            "max_tokens": 1024,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def main():
    if not ANTHROPIC_API_KEY:
        print("Error: ANTHROPIC_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    all_data = load_data()
    if not all_data:
        print("Error: no data files found", file=sys.stderr)
        sys.exit(1)

    prompt, last_date = build_prompt(all_data)
    if not prompt:
        print("Error: could not build prompt", file=sys.stderr)
        sys.exit(1)

    print(f"Generating analysis for {last_date}...")
    text = call_claude(prompt)

    result = {
        "date": last_date,
        "text": text,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }

    with open(ANALYSIS_FILE, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"Saved to {ANALYSIS_FILE} ({len(text)} chars)")


if __name__ == "__main__":
    main()
