import os
from datetime import date, timedelta
from flask import Flask, render_template, request, jsonify
from sqlalchemy.exc import IntegrityError
from database import db, Recording, Setting, Task, initialize_database, get_settings
from ocr_parser import parse_screenshot

MAX_IMAGE_SIZE = 15 * 1024 * 1024
MAX_UPLOAD_SIZE = 60 * 1024 * 1024

app = Flask(__name__, instance_relative_config=True)
os.makedirs(app.instance_path, exist_ok=True)
app.config.update(
    SQLALCHEMY_DATABASE_URI="sqlite:///" + os.path.join(app.instance_path, "dashboard.db"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    MAX_CONTENT_LENGTH=MAX_UPLOAD_SIZE,
)
db.init_app(app)

with app.app_context():
    initialize_database()

@app.errorhandler(413)
def too_large(_error):
    return jsonify({"error": "The total upload size cannot exceed 60 MB."}), 413

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
    images = [image for image in request.files.getlist("image") if image.filename]
    if not images:
        return jsonify({"error": "Please select an image to upload."}), 400

    try:
        image_results = []
        records = []
        added = 0
        duplicates = 0
        seen_record_ids = set()

        for image in images:
            result = {
                "filename": image.filename, "detectedCount": 0,
                "addedCount": 0, "duplicateCount": 0,
            }
            image_results.append(result)

            if image.mimetype not in {"image/jpeg", "image/png", "image/webp"}:
                result["error"] = "Only JPG, PNG and WEBP images are supported."
                continue

            image_bytes = image.stream.read(MAX_IMAGE_SIZE + 1)
            if len(image_bytes) > MAX_IMAGE_SIZE:
                result["error"] = "Image exceeds the 15 MB per-image limit."
                continue

            try:
                extracted = parse_screenshot(image_bytes)
            except ValueError as exc:
                result["error"] = str(exc)
                continue
            except Exception:
                app.logger.exception("Screenshot processing failed for %s", image.filename)
                result["error"] = "OCR processing failed. Check that Tesseract is installed and configured."
                continue

            result["detectedCount"] = len(extracted)
            records.extend(extracted)
            if not extracted:
                result["error"] = (
                    "No complete recording rows were detected. Try a clearer screenshot "
                    "or check the OCR configuration."
                )
                continue

            for rec in extracted:
                record_id = rec["record_id"]
                if record_id in seen_record_ids or Recording.query.filter_by(record_id=record_id).first():
                    result["duplicateCount"] += 1
                    duplicates += 1
                    continue
                seen_record_ids.add(record_id)
                db.session.add(Recording(
                    record_id=record_id, date=rec["date"],
                    time=rec["time"], location=rec["location"],
                    duration_seconds=rec["duration_seconds"],
                    duration_formatted=rec["duration_formatted"], rate=20.0
                ))
                result["addedCount"] += 1
                added += 1

        failures = [
            f'{result["filename"]}: {result["error"]}'
            for result in image_results if "error" in result
        ]
        if not any(result["detectedCount"] for result in image_results):
            return jsonify({
                "error": "No images could be processed. " + " ".join(failures),
                "imageResults": image_results,
            }), 422

        if added:
            db.session.commit()
        return jsonify({
            "addedCount": added, "duplicateCount": duplicates,
            "detectedCount": len(records), "records": records,
            "imageResults": image_results,
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
