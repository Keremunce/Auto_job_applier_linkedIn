import csv
import os
from typing import List, Dict

from flask import Flask, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

LOG_DIR = os.path.join("outputs", "logs")
SUCCESS_FILE = os.path.join(LOG_DIR, "success.csv")
FAILURE_FILE = os.path.join(LOG_DIR, "failure.csv")


def _read_csv(path: str, status: str) -> List[Dict[str, str]]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as csv_file:
        reader = csv.DictReader(csv_file)
        return [
            {
                "timestamp": row.get("timestamp", ""),
                "job_title": row.get("job_title", ""),
                "company": row.get("company", ""),
                "job_url": row.get("job_url", ""),
                "applied": row.get("applied", ""),
                "resume_path": row.get("resume_path", ""),
                "error_message": row.get("error_message", ""),
                "status": status,
            }
            for row in reader
        ]


@app.route("/")
def home() -> str:
    return render_template("index.html")


@app.route("/applications", methods=["GET"])
def get_applications() -> tuple:
    successes = _read_csv(SUCCESS_FILE, "success")
    failures = _read_csv(FAILURE_FILE, "failure")
    data = successes + failures
    if not data:
        return jsonify({"error": "No application history found"}), 404
    return jsonify(data)


if __name__ == "__main__":
    app.run(debug=True)
