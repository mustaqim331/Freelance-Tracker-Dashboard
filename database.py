from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Recording(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    record_id = db.Column(db.String(100), unique=True, nullable=False, index=True)
    date = db.Column(db.String(10), nullable=False, index=True)
    time = db.Column(db.String(8), nullable=False)
    location = db.Column(db.String(100), nullable=False)
    duration_seconds = db.Column(db.Integer, nullable=False)
    duration_formatted = db.Column(db.String(50), nullable=False)
    rate = db.Column(db.Float, nullable=False, default=20.0)

class Setting(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    value = db.Column(db.Float, nullable=False)

class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Work")
    scheduled_date = db.Column(db.String(10), nullable=False, index=True)
    estimated_hours = db.Column(db.Float, nullable=False, default=1.0)
    status = db.Column(db.String(30), nullable=False, default="Pending")

DEFAULT_SETTINGS = {
    "MONTHLY_EARNINGS_TARGET": 3000.0,
    "WEEKLY_EARNINGS_TARGET": 300.0,
    "MONTHLY_HOURS_TARGET": 150.0,
    "DAILY_HOURS_TARGET": 3.0,
}

SETTING_NAMES = {
    "MONTHLY_EARNINGS_TARGET": "monthlyEarningsTarget",
    "WEEKLY_EARNINGS_TARGET": "weeklyEarningsTarget",
    "MONTHLY_HOURS_TARGET": "monthlyHoursTarget",
    "DAILY_HOURS_TARGET": "dailyHoursTarget",
}

def initialize_database():
    db.create_all()
    for key, value in DEFAULT_SETTINGS.items():
        if not Setting.query.filter_by(key=key).first():
            db.session.add(Setting(key=key, value=value))
    db.session.commit()

def get_settings():
    result = {v: DEFAULT_SETTINGS[k] for k, v in SETTING_NAMES.items()}
    for item in Setting.query.all():
        if item.key in SETTING_NAMES:
            result[SETTING_NAMES[item.key]] = item.value
    return result
