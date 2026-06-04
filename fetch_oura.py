import argparse
import json
import os
import sys
import requests
from datetime import date, timedelta

TOKEN = os.environ.get("OURA_TOKEN", "WEZ24M4QEIZSCHXHNICSE62LX5WJZWHN")
BASE_URL = "https://api.ouraring.com/v2/usercollection"

def data_file_for_year(year: int) -> str:
    return "data_2024.json" if year <= 2024 else "data_2025_2026.json"


def fetch_all(endpoint, params):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    results = []
    current_params = dict(params)
    while True:
        resp = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=current_params)
        resp.raise_for_status()
        body = resp.json()
        results.extend(body.get("data", []))
        next_token = body.get("next_token")
        if not next_token:
            break
        current_params = {"next_token": next_token}
    return results


def organize_by_day(all_data, daily_sleep, sleep, activity, workouts, readiness, spo2):
    EMPTY = lambda: {
        "daily_sleep": [], "sleep": [], "daily_activity": [],
        "workout": [], "daily_readiness": [], "daily_spo2": [],
    }

    for item in daily_sleep:
        d = item.get("day", item.get("start_datetime", "")[:10])
        all_data.setdefault(d, EMPTY())["daily_sleep"].append(item)

    for item in sleep:
        d = item.get("day", item.get("start_datetime", "")[:10])
        entry = all_data.setdefault(d, EMPTY())
        entry["sleep"].append({k: v for k, v in item.items()
                                if k not in ("heart_rate", "hrv", "movement_30_sec",
                                             "sleep_phase_30_sec", "sleep_phase_5_min",
                                             "app_sleep_phase_5_min", "class_5_min")})

    for item in activity:
        d = item.get("day", item.get("start_datetime", "")[:10])
        all_data.setdefault(d, EMPTY())["daily_activity"].append(item)

    for item in workouts:
        d = item.get("day", item.get("start_datetime", "")[:10])
        all_data.setdefault(d, EMPTY())["workout"].append(item)

    for item in readiness:
        d = item.get("day", item.get("start_datetime", "")[:10])
        all_data.setdefault(d, EMPTY())["daily_readiness"].append(item)

    for item in spo2:
        d = item.get("day", item.get("start_datetime", "")[:10])
        all_data.setdefault(d, EMPTY())["daily_spo2"].append(item)


def main():
    parser = argparse.ArgumentParser(description="Fetch Oura data and save to data.json")
    parser.add_argument("--start-date", default=None, help="YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--end-date", default=None, help="YYYY-MM-DD (default: yesterday)")
    args = parser.parse_args()

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    today = date.today().isoformat()
    start = args.start_date or yesterday
    end = args.end_date or today

    print(f"Fetching {start} → {end}")
    day_params = {"start_date": start, "end_date": end}
    # workout and daily_activity endpoints use exclusive end_date, so add 1 day
    end_plus1 = (date.fromisoformat(end) + timedelta(days=1)).isoformat()
    exclusive_params = {"start_date": start, "end_date": end_plus1}

    endpoints = [
        ("daily_sleep",    "daily_sleep_data",  day_params),
        ("sleep",          "sleep_data",         day_params),
        ("daily_activity", "activity_data",      exclusive_params),
        ("workout",        "workout_data",       exclusive_params),
        ("daily_readiness","readiness_data",     day_params),
        ("daily_spo2",     "spo2_data",          day_params),
    ]
    results = {}
    for ep, key, params in endpoints:
        print(f"  {ep}...")
        data = fetch_all(ep, params)
        results[key] = data
        print(f"    {len(data)} records")

    # Group fetched records by target file
    from collections import defaultdict
    buckets: dict[str, dict] = defaultdict(dict)

    # Load existing files
    for year in range(2024, int(end[:4]) + 1):
        fname = data_file_for_year(year)
        if fname not in buckets and os.path.exists(fname):
            with open(fname) as f:
                buckets[fname] = json.load(f)
            print(f"Loaded {len(buckets[fname])} day(s) from {fname}")
        elif fname not in buckets:
            buckets[fname] = {}

    # Build a combined dict, organize, then re-split by file
    all_data: dict = {}
    for d in buckets.values():
        all_data.update(d)

    before = len(all_data)
    organize_by_day(
        all_data,
        results["daily_sleep_data"],
        results["sleep_data"],
        results["activity_data"],
        results["workout_data"],
        results["readiness_data"],
        results["spo2_data"],
    )

    # Write back to the correct file(s)
    written: dict[str, int] = {}
    for day, entry in all_data.items():
        fname = data_file_for_year(int(day[:4]))
        buckets.setdefault(fname, {})[day] = entry

    for fname, data in buckets.items():
        with open(fname, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        written[fname] = len(data)

    total = sum(written.values())
    print(f"Done. Days added/updated: {total - before}. Total across files: {total}")
    for fname, count in sorted(written.items()):
        print(f"  {fname}: {count} days")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"API error: {e.response.status_code} {e.response.text}", file=sys.stderr)
        sys.exit(1)
