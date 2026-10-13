import json
import os
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from analysis import analyze_dataset
from cleaning import clean_data

load_dotenv(ROOT_DIR / ".env")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024  # 200 MB

UPLOAD_FOLDER = ROOT_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)
ALLOWED_EXTENSIONS = {"csv"}

DATA_FILE = ROOT_DIR / "sample_data" / "sales_100_rows.csv"
current_df = None
current_report = None
current_analysis = None
current_filename = "sales_100_rows.csv"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_csv_flexible(path_or_buffer):
    try:
        return pd.read_csv(path_or_buffer, low_memory=False)
    except UnicodeDecodeError:
        if hasattr(path_or_buffer, "seek"):
            path_or_buffer.seek(0)
        return pd.read_csv(path_or_buffer, encoding="cp1252", low_memory=False)


def load_initial_data():
    global current_df, current_report, current_analysis, current_filename
    try:
        raw = read_csv_flexible(DATA_FILE)
        current_df, current_report = clean_data(raw, return_report=True)
        current_analysis = analyze_dataset(current_df)
        current_filename = DATA_FILE.name
        print("Initial dataset loaded.")
    except Exception as e:
        print("Could not load initial dataset:", e)
        current_df = pd.DataFrame()
        current_report = {"issues": [str(e)], "original_rows": 0, "cleaned_rows": 0}
        current_analysis = None


def _analysis_payload():
    if current_analysis is None:
        return {}
    return current_analysis


@app.route("/")
def home():
    return send_from_directory(ROOT_DIR / "app", "index.html")


@app.route("/style.css")
def style():
    return send_from_directory(ROOT_DIR / "app", "style.css")


@app.route("/script.js")
def script():
    return send_from_directory(ROOT_DIR / "app", "script.js")


@app.route("/dashboard-data")
def dashboard_data():
    if current_df is None or current_df.empty or current_analysis is None:
        return jsonify({"error": "No usable dataset is loaded."}), 400

    return jsonify({
        "filename": current_filename,
        "rows": len(current_df),
        "columns": list(current_df.columns),
        "cleaning": current_report,
        "analysis": _analysis_payload(),
    })


@app.route("/cleaning-report")
def cleaning_report():
    return jsonify(current_report or {})


@app.route("/upload", methods=["POST"])
def upload_file():
    global current_df, current_report, current_analysis, current_filename

    try:
        if "file" not in request.files:
            return jsonify({"error": "No file selected."}), 400

        file = request.files["file"]
        if not file.filename:
            return jsonify({"error": "Please select a CSV file."}), 400
        if not allowed_file(file.filename):
            return jsonify({"error": "Only CSV files are supported."}), 400

        filename = secure_filename(file.filename)
        if not filename:
            return jsonify({"error": "Invalid filename."}), 400

        file_path = UPLOAD_FOLDER / filename
        file.save(file_path)
        raw_df = read_csv_flexible(file_path)
        df, report = clean_data(raw_df, return_report=True)

        if df.empty or len(df.columns) == 0:
            current_df = pd.DataFrame()
            current_report = report
            current_analysis = None
            current_filename = filename
            return jsonify({
                "error": "The uploaded CSV contains no usable data after cleaning.",
                "filename": filename,
                "cleaning": report,
            }), 400

        analysis = analyze_dataset(df)
        current_df = df
        current_report = report
        current_analysis = analysis
        current_filename = filename

        return jsonify({
            "message": "File cleaned and analyzed successfully.",
            "filename": filename,
            "rows": len(raw_df),
            "cleaned_rows": len(df),
            "cleaning": report,
            "analysis": analysis,
        })

    except Exception as e:
        print("Upload error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/ai-insights")
def ai_insights():
    if current_df is None or current_df.empty or current_analysis is None:
        return jsonify({"error": "No usable dataset loaded."}), 400

    summary = current_analysis["insight_summary"]
    api_key = os.getenv("GEMINI_API_KEY")
    rule_based = summary.get("rule_based_insights", [])

    if not api_key:
        return jsonify({
            "available": False,
            "insights": rule_based,
            "message": "Rule-based insights are available. Add GEMINI_API_KEY to .env to enable richer Gemini explanations.",
        })

    try:
        from google import genai

        payload = {
            "filename": current_filename,
            "rows": len(current_df),
            "columns": current_analysis["profiles"],
            "kpis": current_analysis["kpis"],
            "insight_summary": summary,
        }

        client = genai.Client(api_key=api_key)
        prompt = f"""
You are a careful data analyst. Analyze the dataset metadata and statistical summary below.
This is NOT necessarily a sales dataset. It may be HR, finance, marketing, customer, student,
operations, survey, music, inventory, or another structured CSV.

Rules:
- Use only evidence in the provided summary.
- Do not invent business facts or causal explanations.
- Do not assume money, sales, customers, or profit unless the columns support that interpretation.
- Explain what the strongest patterns mean in plain language.
- Mention data-quality limitations when relevant.

Return these sections:
1. Overall dataset summary
2. Key findings
3. Notable relationships or trends
4. Data-quality observations
5. Practical questions or next analyses to explore

Dataset summary:
{json.dumps(payload, default=str, indent=2)}
"""
        result = client.models.generate_content(
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=prompt,
        )
        text = getattr(result, "text", None) or str(result)
        return jsonify({
            "available": True,
            "insights": text,
            "rule_based": rule_based,
        })
    except Exception as e:
        return jsonify({
            "available": False,
            "insights": rule_based,
            "message": f"Gemini could not be reached, so the app returned statistical insights instead: {e}",
        })


load_initial_data()


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
