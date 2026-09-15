import os, csv


def seed_weather_stations(db, WeatherStation):
    """Load seeds/weather_stations.csv into the database (skips placeholder device IDs)."""
    csv_path = os.path.join(os.path.dirname(__file__), "weather_stations.csv")
    if not os.path.exists(csv_path):
        return 0

    created = 0
    with open(csv_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            device_id = row["device_id"].strip()
            if not device_id or device_id.startswith("REPLACE_WITH_"):
                continue  # skip placeholder rows until real device IDs are entered
            if WeatherStation.query.filter_by(device_id=device_id).first():
                continue
            db.session.add(WeatherStation(
                state=row["state"].strip(),
                lga=row["lga"].strip(),
                device_id=device_id,
                device_name=row.get("device_name","").strip(),
                status=row.get("status","pending").strip() or "pending",
            ))
            created += 1
    db.session.commit()
    return created
