import argparse
import json
import os
import sys
import requests
from datetime import date, timedelta

TOKEN = os.environ.get("OURA_TOKEN", "WEZ24M4QEIZSCHXHNICSE62LX5WJZWHN")
BASE_URL = "https://api.ouraring.com/v2/usercollection"
DATA_FILE = "data.json"


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
    start = args.start_date or yesterday
    end = args.end_date or yesterday

    print(f"Fetching {start} → {end}")
    day_params = {"start_date": start, "end_date": end}

    endpoints = [
        ("daily_sleep",    "daily_sleep_data"),
        ("sleep",          "sleep_data"),
        ("daily_activity", "activity_data"),
        ("workout",        "workout_data"),
        ("daily_readiness","readiness_data"),
        ("daily_spo2",     "spo2_data"),
    ]
    results = {}
    for ep, key in endpoints:
        print(f"  {ep}...")
        data = fetch_all(ep, day_params)
        results[key] = data
        print(f"    {len(data)} records")

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            all_data = json.load(f)
        print(f"\nLoaded {len(all_data)} existing day(s) from {DATA_FILE}")
    else:
        all_data = {}

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

    with open(DATA_FILE, "w") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"Done. Days added/updated: {len(all_data) - before}. Total in file: {len(all_data)}")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"API error: {e.response.status_code} {e.response.text}", file=sys.stderr)
        sys.exit(1)
