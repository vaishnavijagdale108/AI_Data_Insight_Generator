import sys
from pathlib import Path
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cleaning import clean_data

def test_cleaning_aliases_and_values():
    raw = pd.DataFrame({
        "sale_date": ["2026-01-01", "2026-01-01"],
        "region_name": [" west ", " west "],
        "category_name": [" electronics ", " electronics "],
        "product_name": [" phone ", " phone "],
        "sales_amount": ["₹10,000", "₹10,000"],
        "profit_amount": ["1,000", "1,000"],
        "qty": ["2 units", "2 units"],
    })
    cleaned, report = clean_data(raw, return_report=True)
    assert set(["Date","Region","Category","Product","Sales","Profit","Quantity"]).issubset(cleaned.columns)
    assert len(cleaned) == 1
    assert cleaned["Sales"].iloc[0] == 10000
    assert report["duplicates_removed"] == 1
