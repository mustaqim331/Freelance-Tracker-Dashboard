import os
from datetime import date, timedelta
from flask import Flask, render_template, request, jsonify
from sqlalchemy.exc import IntegrityError
from database import db, Recording, Setting, Task, initialize_database, get_settings
from ocr_parser import parse_screenshot

app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config.update(
    SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(app.instance_path, "dashboard.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=15 * 1024 * 1024,
)
db.init_app(app)

with app.app_context():
    initialize_database()

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "Image is too large. Maximum upload size is 15 MB."}), 413

@app.route("/")
def index():
    return render_template("index.html")

@app.get("/api/ping")
def ping():
    return jsonify({"status": "ready"})

@app.get("/api/dashboard")
def dashboard_data():
    settings = get_settings()
    recordings = Recording.query.order_by(Recording.date, Recording.time).all()
    daily_map = {}
    total_seconds = 0
    total_earnings = 0.0

    for rec in recordings:
        seconds = rec.duration_seconds or 0
        earnings = seconds / 3600 * (rec.rate or 20)
        total_seconds += seconds
        total_earnings += earnings
        day = daily_map.setdefault(rec.date, {
            "date": rec.date, "seconds": 0, "earnings": 0.0,
            "count": 0, "items": []
        })
        day["seconds"] += seconds
        day["earnings"] += earnings
        day["count"] += 1
        day["items"].append({
            "id": rec.record_id, "time": rec.time,
            "location": rec.location,
            "durationFormatted": rec.duration_formatted,
            "seconds": seconds
        })

    # Preserve the supplied Apps Script's original start date.
    start_date = date(2026, 11, 1)
    end_date = date.today()
    daily = []
    current = start_date
    while current <= end_date:
        key = current.isoformat()
        item = daily_map.get(key)
        if item:
            daily.append({
                "date": key,
                "hours": f'{item["seconds"] / 3600:.2f}',
                "earnings": f'{item["earnings"]:.2f}',
                "count": item["count"], "items": item["items"]
            })
        else:
            daily.append({"date": key, "hours": "0.00",
                          "earnings": "0.00", "count": 0, "items": []})
        current += timedelta(days=1)

    weekly = 0.0
    if daily:
        latest = date.fromisoformat(daily[-1]["date"])
        week_index = (latest - start_date).days // 7
        week_start = start_date + timedelta(days=week_index * 7)
        week_end = week_start + timedelta(days=6)
        weekly = sum(
            float(row["earnings"]) for row in daily
            if week_start <= date.fromisoformat(row["date"]) <= week_end
        )

    return jsonify({
        "totalEarnings": f"{total_earnings:.2f}",
        "totalHours": f"{total_seconds / 3600:.2f}",
        "currentWeeklyEarnings": f"{weekly:.2f}",
        "settings": settings, "dailyBreakdown": daily
    })

@app.post("/api/settings")
def save_settings():
    data = request.get_json(silent=True) or {}
    fields = {
        "MONTHLY_EARNINGS_TARGET": "monthlyEarn",
        "WEEKLY_EARNINGS_TARGET": "weeklyEarn",
        "MONTHLY_HOURS_TARGET": "monthlyHours",
        "DAILY_HOURS_TARGET": "dailyHours",
    }
    try:
        for key, field in fields.items():
            value = float(data[field])
            if value < 0:
                raise ValueError("Targets cannot be negative.")
            setting = Setting.query.filter_by(key=key).first()
            if setting:
                setting.value = value
        db.session.commit()
        return dashboard_data()
    except (KeyError, TypeError, ValueError) as exc:
        db.session.rollback()
        return jsonify({"error": f"Invalid target values: {exc}"}), 400

@app.post("/api/upload")
def upload_screenshot():
    image = request.files.get("image")
    if not image or not image.filename:
        return jsonify({"error": "Please select an image to upload."}), 400
    if image.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
        return jsonify({"error": "Only JPG, PNG and WEBP images are supported."}), 400

    try:
        extracted = parse_screenshot(image.read())
        if not extracted:
            return jsonify({
                "error": "No complete recording rows were detected. "
                         "Try a clearer screenshot or check the OCR configuration."
            }), 422

        added = 0
        duplicates = 0
        for rec in extracted:
            if Recording.query.filter_by(record_id=rec["record_id"]).first():
                duplicates += 1
                continue
            db.session.add(Recording(
                record_id=rec["record_id"], date=rec["date"],
                time=rec["time"], location=rec["location"],
                duration_seconds=rec["duration_seconds"],
                duration_formatted=rec["duration_formatted"], rate=20.0
            ))
            added += 1
        db.session.commit()
        return jsonify({
            "addedCount": added, "duplicateCount": duplicates,
            "detectedCount": len(extracted), "records": extracted
        })
    except Exception as exc:
        db.session.rollback()
        app.logger.exception("Screenshot processing failed")
        return jsonify({"error": str(exc)}), 500

@app.get("/api/tasks")
def get_tasks():
    tasks = Task.query.order_by(Task.scheduled_date.asc(), Task.id.asc()).all()
    return jsonify([{
        "id": t.id, "name": t.name, "category": t.category,
        "date": t.scheduled_date, "hours": t.estimated_hours,
        "status": t.status
    } for t in tasks])

@app.post("/api/tasks")
def add_task():
    data = request.get_json(silent=True) or {}
    name = str(data.get("name", "")).strip()
    task_date = str(data.get("date", "")).strip()
    if not name or not task_date:
        return jsonify({"error": "Task name and date are required."}), 400
    try:
        date.fromisoformat(task_date)
        hours = float(data.get("hours", 1))
        if hours < 0:
            raise ValueError()
    except ValueError:
        return jsonify({"error": "Enter a valid date and non-negative hours."}), 400
    task = Task(name=name, category=data.get("category", "Work"),
                scheduled_date=task_date, estimated_hours=hours)
    db.session.add(task)
    db.session.commit()
    return jsonify({"success": True, "id": task.id})

@app.post("/api/tasks/<int:task_id>/toggle")
def toggle_task(task_id):
    task = db.session.get(Task, task_id)
    if not task:
        return jsonify({"error": "Task not found."}), 404
    task.status = "Pending" if task.status == "Completed" else "Completed"
    db.session.commit()
    return jsonify({"success": True, "status": task.status})

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
