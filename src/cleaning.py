import re
import pandas as pd

COLUMN_ALIASES = {
    "Date": ["date", "order_date", "sale_date", "sales_date", "transaction_date", "orderdate", "saledate", "datetime", "timestamp"],
    "Region": ["region", "area", "territory", "region_name", "location", "sales_region", "zone"],
    "Category": ["category", "category_name", "product_category", "product_type", "segment", "type"],
    "Product": ["product", "product_name", "item", "item_name", "productname", "sku_name", "description"],
    "Sales": ["sales", "sale", "sales_amount", "sales_value", "revenue", "revenue_amount", "amount", "total_sales", "total_revenue"],
    "Profit": ["profit", "profit_amount", "profit_value", "net_profit", "gross_profit"],
    "Quantity": ["quantity", "qty", "units", "units_sold", "quantity_sold", "qty_sold", "count"],
}


def _normalize_key(name):
    return re.sub(r"[^a-z0-9]+", "_", str(name).strip().lower()).strip("_")


def detect_column_mapping(columns):
    lookup = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        lookup[_normalize_key(canonical)] = canonical
        for alias in aliases:
            lookup[_normalize_key(alias)] = canonical
    mapping = {}
    used = set()
    for col in columns:
        target = lookup.get(_normalize_key(col))
        if target and target not in used and col != target:
            mapping[col] = target
            used.add(target)
    return mapping


def normalize_column_name(name):
    name = str(name).strip()
    name = re.sub(r"\s+", " ", name)
    return name


def make_unique_columns(columns):
    seen = {}
    result = []
    for col in columns:
        base = normalize_column_name(col) or "Unnamed"
        count = seen.get(base, 0)
        result.append(base if count == 0 else f"{base}_{count}")
        seen[base] = count + 1
    return result


def _clean_numeric(series):
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")

    cleaned = (
        series.astype("string")
        .str.strip()
        .str.replace(",", "", regex=False)
        .str.replace(r"[₹$€£¥]", "", regex=True)
        .str.replace(r"\(([^)]+)\)", r"-\1", regex=True)
        .str.replace(r"[^0-9.\-]", "", regex=True)
    )
    return pd.to_numeric(cleaned, errors="coerce")


def _date_candidate_score(series, column_name):
    name = str(column_name).lower()
    name_hint = any(
        token in name
        for token in ["date", "time", "timestamp", "created", "updated", "dob", "year", "month"]
    )
    try:
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
    except (TypeError, ValueError):
        parsed = pd.to_datetime(series, errors="coerce")
    ratio = float(parsed.notna().mean()) if len(series) else 0.0
    if name_hint:
        return ratio * 0.8 + 0.2, parsed
    return ratio, parsed


def clean_data(df, return_report=False):
    """Generic CSV cleaning. No sales-specific required columns."""
    if not isinstance(df, pd.DataFrame):
        raise TypeError("Expected a pandas DataFrame")

    original_rows = len(df)
    original_columns = [str(c) for c in df.columns]
    report = {
        "original_rows": original_rows,
        "original_columns": original_columns,
        "cleaned_rows": 0,
        "original_column_count": len(original_columns),
        "cleaned_column_count": 0,
        "columns_mapped": [],
        "duplicates_removed": 0,
        "trimmed_text_values": 0,
        "numeric_conversions": [],
        "date_columns_detected": [],
        "missing_values_before": {},
        "missing_values_after": {},
        "missing_values_filled": {},
        "invalid_dates_found": {},
        "empty_columns_removed": [],
        "issues": [],
        "warnings": [],
    }

    df = df.copy()
    df.columns = make_unique_columns(df.columns)

    # Remove completely empty columns.
    empty_cols = []
    for col in df.columns:
        s = df[col]
        if s.isna().all() or s.astype("string").str.strip().eq("").all():
            empty_cols.append(col)
    if empty_cols:
        df = df.drop(columns=empty_cols)
        report["empty_columns_removed"] = empty_cols

    # Preserve compatibility with common business/sales aliases without requiring a sales schema.
    mapping = detect_column_mapping(df.columns)
    for original, canonical in mapping.items():
        if canonical not in df.columns:
            df = df.rename(columns={original: canonical})
            report["columns_mapped"].append({"from": original, "to": canonical})

    # Missing counts before any imputation.
    for col in df.columns:
        missing = int(df[col].isna().sum())
        if missing:
            report["missing_values_before"][col] = missing

    # Remove exact duplicate rows.
    before = len(df)
    df = df.drop_duplicates()
    report["duplicates_removed"] = before - len(df)

    # Clean whitespace on string columns and attempt sensible type conversion.
    for col in list(df.columns):
        series = df[col]
        if pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series):
            before_values = series.astype("string")
            normalized = before_values.str.strip().str.replace(r"\s+", " ", regex=True)
            report["trimmed_text_values"] += int((before_values.fillna("") != normalized.fillna("")).sum())
            df[col] = normalized

    # Detect datetime columns before generic numeric conversion.
    for col in list(df.columns):
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            report["date_columns_detected"].append(col)
            continue
        if not (pd.api.types.is_object_dtype(df[col]) or pd.api.types.is_string_dtype(df[col])):
            continue
        score, parsed = _date_candidate_score(df[col], col)
        # Strong signal: high parse success, or explicit date/time-looking header.
        lower_name = str(col).lower()
        explicit_date_name = any(token in lower_name for token in ["date", "time", "timestamp", "created", "updated", "dob"])
        # Avoid turning ordinary numeric/category-like strings into dates by accident.
        if (explicit_date_name and score >= 0.65 and parsed.nunique(dropna=True) >= 1) or (not explicit_date_name and score >= 0.92 and parsed.nunique(dropna=True) >= 2):
            invalid = int(df[col].notna().sum() - parsed.notna().sum())
            if invalid:
                report["invalid_dates_found"][col] = invalid
            df[col] = parsed
            report["date_columns_detected"].append(col)

    # Convert object columns to numeric when conversion is highly reliable.
    for col in list(df.columns):
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        series = df[col]
        if pd.api.types.is_numeric_dtype(series):
            continue
        if not (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            continue

        converted = _clean_numeric(series)
        non_null = int(series.notna().sum())
        parsed_non_null = int(converted.notna().sum())
        ratio = parsed_non_null / non_null if non_null else 0

        # Avoid turning IDs / text into numbers unless the whole column is clearly numeric.
        if ratio >= 0.90 and non_null >= 1:
            name = str(col).lower()
            likely_identifier = any(token in name for token in ["id", "code", "zip", "pin", "phone", "postal"])
            if not likely_identifier:
                df[col] = converted
                report["numeric_conversions"].append({
                    "column": col,
                    "values_converted": parsed_non_null,
                })

    # Fill missing values intelligently while preserving type.
    for col in df.columns:
        series = df[col]
        missing = int(series.isna().sum())
        if missing == 0:
            continue

        if pd.api.types.is_numeric_dtype(series):
            median = series.median()
            if pd.notna(median):
                df[col] = series.fillna(median)
                report["missing_values_filled"][col] = missing
        elif pd.api.types.is_datetime64_any_dtype(series):
            # Keep missing dates as NaT; they simply won't be used in time-series charts.
            continue
        else:
            mode = series.mode(dropna=True)
            fill_value = mode.iloc[0] if not mode.empty else "Unknown"
            df[col] = series.fillna(fill_value)
            report["missing_values_filled"][col] = missing

    # Remove completely unusable rows only.
    before = len(df)
    if len(df.columns):
        df = df.dropna(how="all")
    removed_all_null_rows = before - len(df)
    if removed_all_null_rows:
        report["warnings"].append(f"Removed {removed_all_null_rows} completely empty row(s).")

    for col in df.columns:
        missing = int(df[col].isna().sum())
        if missing:
            report["missing_values_after"][col] = missing

    df = df.reset_index(drop=True)
    report["cleaned_rows"] = len(df)
    report["cleaned_column_count"] = len(df.columns)

    if not len(df):
        report["issues"].append("No usable rows remain after cleaning.")
    if not len(df.columns):
        report["issues"].append("No usable columns remain after cleaning.")

    if return_report:
        return df, report
    return df
