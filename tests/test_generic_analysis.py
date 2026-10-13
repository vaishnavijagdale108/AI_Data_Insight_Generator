import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis import analyze_dataset
from cleaning import clean_data


def test_non_sales_dataset_is_supported():
    raw = pd.DataFrame({
        "Employee_ID": ["E1", "E2", "E3", "E3"],
        "Department": ["IT", "HR", "Sales", "Sales"],
        "Salary": [70000, 55000, 62000, 62000],
        "Joined_Date": ["2024-01-01", "2023-02-01", "2022-03-01", "2022-03-01"],
    })
    cleaned, report = clean_data(raw, return_report=True)
    result = analyze_dataset(cleaned)

    assert report["duplicates_removed"] == 1
    assert result["schema"]["primary_metric"] == "Salary"
    assert result["schema"]["date_column"] == "Joined_Date"
    assert any("Salary by Department" == chart["title"] for chart in result["charts"])
    assert len(result["kpis"]) == 4


def test_categorical_dataset_is_supported():
    raw = pd.DataFrame({
        "student_id": ["S1", "S2", "S3", "S4"],
        "course": ["BTech", "BCom", "BTech", "BSc"],
        "city": ["Pune", "Mumbai", "Pune", "Nashik"],
    })
    cleaned = clean_data(raw)
    result = analyze_dataset(cleaned)
    assert result["schema"]["primary_metric"] is None
    assert result["charts"]
    assert result["schema"]["categorical"]
