"""
Local screenshot OCR. No API calls or cloud inference.

Expected screenshot row content includes a record timestamp/ID, a room name,
and a duration. The parser tolerates fields split across adjacent OCR lines
by looking at a small window around each detected record ID.
"""
import re
from datetime import datetime
import cv2
import numpy as np
import pytesseract

# On Windows, uncomment and set this if Tesseract is not on PATH:
# pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

LOCATIONS = [
    "Kitchen", "Bedroom", "Living Room", "Laundry Room",
    "Bathroom", "Dining Room", "Office", "Study Room",
    "Livingroom", "Laundry"
]

def preprocess_image(image_bytes: bytes):
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("The uploaded file is not a readable image.")

    h, w = image.shape[:2]
    if w < 1800:
        scale = min(2.0, 1800 / max(w, 1))
        image = cv2.resize(image, None, fx=scale, fy=scale,
                           interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 5, 35, 35)
    # Otsu thresholding works well for common light-background app screenshots.
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary

def extract_lines(image_bytes: bytes):
    image = preprocess_image(image_bytes)
    data = pytesseract.image_to_data(
        image, config="--oem 3 --psm 6",
        output_type=pytesseract.Output.DICT
    )
    # Reassemble words by OCR line, preserving line boundaries.
    grouped = {}
    for i, word in enumerate(data["text"]):
        word = (word or "").strip()
        if not word:
            continue
        key = (data["block_num"][i], data["par_num"][i],
               data["line_num"][i])
        grouped.setdefault(key, []).append(word)
    return [" ".join(words) for words in grouped.values()]

def _normalise_room(text):
    compact = re.sub(r"\s+", " ", text).lower()
    aliases = {
        "livingroom": "Living Room",
        "laundry": "Laundry Room",
    }
    for room in LOCATIONS:
        if room.lower() in compact:
            return aliases.get(room.lower(), room)
    # OCR sometimes drops spaces in the room labels.
    if "livingroom" in compact:
        return "Living Room"
    if "laundryroom" in compact:
        return "Laundry Room"
    return None

def _parse_duration(text):
    text = text.lower().replace(",", " ")
    # Examples: 4 min 12 sec, 4 mins 12 secs, 04:12, 00:04:12.
    m = re.search(r"(\d+)\s*(?:min|mins|minute|minutes)\s*(\d+)\s*(?:sec|secs|second|seconds)", text)
    if m:
        mins, secs = map(int, m.groups())
        total = mins * 60 + secs
    else:
        clock = re.search(r"\b(\d{1,2}):(\d{2})(?::(\d{2}))?\b", text)
        if not clock:
            return None
        a, b, c = clock.groups()
        if c is None:
            total = int(a) * 60 + int(b)
        else:
            total = int(a) * 3600 + int(b) * 60 + int(c)
    if total <= 0 or total > 24 * 3600:
        return None
    mins, secs = divmod(total, 60)
    return total, f"{mins} min {secs} sec"

def _parse_record_id(text):
    match = re.search(r"\b(20\d{6})[_\s-](\d{6})\b", text)
    if not match:
        # Some OCR engines may omit the underscore.
        match = re.search(r"\b(20\d{6})(\d{6})\b", text)
    if not match:
        return None
    date_part, time_part = match.groups()
    try:
        d = datetime.strptime(date_part, "%Y%m%d").strftime("%Y-%m-%d")
        t = datetime.strptime(time_part, "%H%M%S").strftime("%H:%M:%S")
    except ValueError:
        return None
    return f"{date_part}_{time_part}", d, t

def parse_screenshot(image_bytes: bytes):
    lines = extract_lines(image_bytes)
    records = []
    for index, line in enumerate(lines):
        parsed_id = _parse_record_id(line)
        if not parsed_id:
            continue

        record_id, date_str, time_str = parsed_id
        # OCR may put room and duration on a neighbouring line.
        context = " ".join(lines[max(0, index - 1):min(len(lines), index + 3)])
        room = _normalise_room(context)
        duration = _parse_duration(context)

        if not room or not duration:
            continue

        seconds, formatted = duration
        records.append({
            "record_id": record_id,
            "date": date_str,
            "time": time_str,
            "location": room,
            "duration_seconds": seconds,
            "duration_formatted": formatted,
        })

    # Keep first occurrence of each ID.
    unique = {}
    for item in records:
        unique[item["record_id"]] = item
    return list(unique.values())
