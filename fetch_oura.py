import json
import os
import sys
import requests
from datetime import date, timedelta

TOKEN = os.environ.get("OURA_TOKEN", "WEZ24M4QEIZSCHXHNICSE62LX5WJZWHN")
BASE_URL = "https://api.ouraring.com/v2/usercollection"
DATA_FILE = "data.json"


def fetch(endpoint, params):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    resp = requests.get(f"{BASE_URL}/{endpoint}", headers=headers, params=params)
    resp.raise_for_status()
    return resp.json().get("data", [])


def main():
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    print(f"Fetching data for {yesterday}...")

    day_params = {"start_date": yesterday, "end_date": yesterday}
    hr_params = {
        "start_datetime": f"{yesterday}T00:00:00",
        "end_datetime": f"{yesterday}T23:59:59",
    }

    new_entry = {
        "daily_sleep": fetch("daily_sleep", day_params),
        "daily_activity": fetch("daily_activity", day_params),
        "workout": fetch("workout", day_params),
        "heartrate": fetch("heartrate", hr_params),
    }

    # Load existing data without overwriting old days
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            all_data = json.load(f)
        print(f"Loaded {len(all_data)} existing day(s) from {DATA_FILE}")
    else:
        all_data = {}

    all_data[yesterday] = new_entry

    with open(DATA_FILE, "w") as f:
        json.dump(all_data, f, indent=2, ensure_ascii=False)

    print(f"Saved. Total days in {DATA_FILE}: {len(all_data)}")
    for key, section in new_entry.items():
        print(f"  {key}: {len(section)} record(s)")


if __name__ == "__main__":
    try:
        main()
    except requests.HTTPError as e:
        print(f"API error: {e.response.status_code} {e.response.text}", file=sys.stderr)
        sys.exit(1)
