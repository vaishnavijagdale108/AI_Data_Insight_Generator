import math
import re
from typing import Any

import numpy as np
import pandas as pd


METRIC_HINTS = {
    "revenue": 8, "sales": 8, "amount": 7, "price": 6, "profit": 7,
    "income": 6, "salary": 6, "cost": 6, "expense": 6, "value": 5,
    "score": 5, "rating": 5, "marks": 5, "points": 5, "quantity": 5,
    "qty": 5, "units": 5, "balance": 5, "count": 4, "total": 3,
}
IDENTIFIER_HINTS = ["id", "index", "code", "key", "uuid", "zip", "pin", "phone"]
LOCATION_HINTS = ["city", "town", "state", "province", "country", "location", "region", "district", "area", "territory"]
LAT_HINTS = ["lat", "latitude"]
LON_HINTS = ["lon", "lng", "longitude", "long"]
YEAR_HINTS = ["year", "fiscal_year", "fy"]


def _name_tokens(name):
    return set(re.findall(r"[a-z0-9]+", str(name).lower()))


def _score_numeric_column(name, series):
    score = 0
    tokens = _name_tokens(name)
    lower = str(name).lower()
    for hint, points in METRIC_HINTS.items():
        if hint in lower:
            score += points
    if any(h in lower for h in IDENTIFIER_HINTS):
        score -= 8
    if series.nunique(dropna=True) <= 1:
        score -= 10
    return score


def infer_schema(df):
    numeric = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    dates = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    categorical = []
    text = []
    identifiers = []

    # Detect explicit calendar-year columns even when they remain numeric.
    year_columns = []
    for col in df.columns:
        lower = str(col).strip().lower()
        if any(h == lower or h in lower for h in YEAR_HINTS) and pd.api.types.is_numeric_dtype(df[col]):
            vals = pd.to_numeric(df[col], errors="coerce").dropna()
            if len(vals) and vals.between(1900, 2100).mean() >= 0.8:
                year_columns.append(col)

    # Detect geographic fields and coordinate columns for an automatic map.
    location_columns = []
    latitude_column = None
    longitude_column = None
    for col in df.columns:
        lower = str(col).strip().lower()
        tokens = _name_tokens(col)
        if any(h == lower or h in tokens or h in lower for h in LOCATION_HINTS):
            if not pd.api.types.is_numeric_dtype(df[col]):
                location_columns.append(col)
        if any(h == lower or h in tokens or h in lower for h in LAT_HINTS):
            if pd.api.types.is_numeric_dtype(df[col]):
                latitude_column = col
        if any(h == lower or h in tokens or h in lower for h in LON_HINTS):
            if pd.api.types.is_numeric_dtype(df[col]):
                longitude_column = col

    for col in df.columns:
        if col in dates:
            continue
        unique = int(df[col].nunique(dropna=True))
        ratio = unique / max(len(df), 1)
        lower = str(col).lower()
        likely_id = any(h in lower for h in IDENTIFIER_HINTS) and ratio > 0.5
        if likely_id:
            identifiers.append(col)
            continue
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric.append(col)
            continue
        elif unique <= min(100, max(10, int(len(df) * 0.30))):
            categorical.append(col)
        else:
            text.append(col)

    numeric = list(dict.fromkeys(numeric))

    excluded_metric_columns = set(year_columns)
    if latitude_column:
        excluded_metric_columns.add(latitude_column)
    if longitude_column:
        excluded_metric_columns.add(longitude_column)
    metric_candidates = [c for c in numeric if c not in excluded_metric_columns]
    numeric_ranked = sorted(
        metric_candidates,
        key=lambda c: (_score_numeric_column(c, df[c]), df[c].nunique(dropna=True)),
        reverse=True,
    )
    date_col = dates[0] if dates else None
    metric_col = numeric_ranked[0] if numeric_ranked else None
    location_col = location_columns[0] if location_columns else None

    return {
        "numeric": numeric,
        "numeric_ranked": numeric_ranked,
        "datetime": dates,
        "date_column": date_col,
        "year_column": year_columns[0] if year_columns else None,
        "categorical": categorical,
        "text": text,
        "identifiers": identifiers,
        "primary_metric": metric_col,
        "location_column": location_col,
        "location_columns": location_columns,
        "latitude_column": latitude_column,
        "longitude_column": longitude_column,
        "has_coordinates": bool(latitude_column and longitude_column),
    }


def _safe_float(value):
    try:
        if pd.isna(value):
            return None
        value = float(value)
        if not math.isfinite(value):
            return None
        return round(value, 6)
    except Exception:
        return None


def _series_to_dict(series):
    result = {}
    for key, value in series.items():
        result[str(key)] = _safe_float(value)
    return result


def _display_value(value):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:,.2f}"
    return f"{value:,}" if isinstance(value, int) else str(value)


def _time_group(df, date_col, metric_col, year_col=None):
    if year_col and year_col in df.columns:
        clean = df[[year_col, metric_col]].dropna().copy()
        if clean.empty:
            return None
        clean[year_col] = pd.to_numeric(clean[year_col], errors="coerce")
        clean = clean.dropna()
        grouped = clean.groupby(year_col)[metric_col].sum().sort_index()
        return "Year", grouped

    clean = df[[date_col, metric_col]].dropna()
    if clean.empty:
        return None
    span_days = (clean[date_col].max() - clean[date_col].min()).days
    if span_days > 365 * 2:
        clean["period"] = clean[date_col].dt.to_period("Y").astype(str)
        label = "Year"
    elif span_days > 120:
        clean["period"] = clean[date_col].dt.to_period("M").astype(str)
        label = "Month"
    elif span_days > 21:
        clean["period"] = clean[date_col].dt.to_period("W").apply(lambda x: str(x.start_time.date()))
        label = "Week"
    else:
        clean["period"] = clean[date_col].dt.date.astype(str)
        label = "Day"
    grouped = clean.groupby("period")[metric_col].sum().sort_index()
    return label, grouped


def build_charts(df, schema):
    charts = []
    metric = schema["primary_metric"]
    numeric = schema["numeric_ranked"]
    categorical = schema["categorical"]

    # Time trend: real date OR explicit Year column.
    if metric and (schema["date_column"] or schema.get("year_column")):
        result = _time_group(df, schema["date_column"], metric, schema.get("year_column"))
        if result:
            granularity, grouped = result
            charts.append({
                "type": "line",
                "title": f"{metric} over time",
                "description": f"{granularity}-level trend based on {metric}.",
                "labels": [str(x) for x in grouped.index],
                "data": [_safe_float(x) for x in grouped.values],
                "metric": metric,
            })

    # Automatic geographic map when a city/state/country/location field or coordinates exist.
    location_col = schema.get("location_column")
    lat_col = schema.get("latitude_column")
    lon_col = schema.get("longitude_column")
    if location_col or (lat_col and lon_col):
        if location_col and metric:
            grouped = df.groupby(location_col, dropna=False)[metric].sum().sort_values(ascending=False).head(20)
        elif location_col:
            grouped = df[location_col].astype("string").fillna("Unknown").value_counts().head(20)
        else:
            grouped = pd.Series(range(len(df)), index=df.index)
        map_chart = {
            "type": "map",
            "title": f"{metric} by {location_col}" if location_col and metric else f"Records by {location_col}" if location_col else "Geographic distribution",
            "description": "Automatic geographic view based on detected location fields.",
            "labels": [str(x) for x in grouped.index],
            "data": [_safe_float(x) for x in grouped.values],
            "metric": metric or "Records",
            "location_column": location_col,
            "latitude_column": lat_col,
            "longitude_column": lon_col,
        }
        if lat_col and lon_col:
            points = []
            for _, row in df[[lat_col, lon_col] + ([location_col] if location_col else [])].dropna(subset=[lat_col, lon_col]).head(100).iterrows():
                point = {"lat": _safe_float(row[lat_col]), "lon": _safe_float(row[lon_col]), "label": str(row[location_col]) if location_col else "Location"}
                points.append(point)
            map_chart["points"] = points
        charts.append(map_chart)

    # Category breakdowns against the primary metric.
    for col in categorical[:3]:
        # Location is already represented by the map when available.
        if col == schema.get("location_column"):
            continue
        if metric:
            grouped = df.groupby(col, dropna=False)[metric].sum().sort_values(ascending=False).head(10)
            chart_type = "bar"
            title = f"{metric} by {col}"
            label = metric
        else:
            grouped = df[col].astype("string").fillna("Unknown").value_counts().head(10)
            chart_type = "bar"
            title = f"Records by {col}"
            label = "Records"
        if not grouped.empty:
            charts.append({
                "type": chart_type,
                "title": title,
                "description": f"Top values of {col}.",
                "labels": [str(x) for x in grouped.index],
                "data": [_safe_float(x) for x in grouped.values],
                "metric": label,
            })

    # Distribution of the primary metric.
    if metric:
        series = pd.to_numeric(df[metric], errors="coerce").dropna()
        if len(series) >= 5 and series.nunique() > 1:
            counts, edges = np.histogram(series, bins=min(8, max(5, int(math.sqrt(len(series))))))
            labels = []
            for i in range(len(counts)):
                labels.append(f"{edges[i]:.2f}–{edges[i + 1]:.2f}")
            charts.append({
                "type": "bar",
                "title": f"Distribution of {metric}",
                "description": "How the primary numeric metric is distributed.",
                "labels": labels,
                "data": [int(x) for x in counts],
                "metric": "Records",
            })

    # Correlation view when multiple numeric variables exist.
    correlation_columns = [c for c in numeric if c not in set(schema.get("year_column") and [schema.get("year_column")] or []) and c not in {schema.get("latitude_column"), schema.get("longitude_column")}]
    if len(correlation_columns) >= 2:
        corr = df[correlation_columns[:8]].corr(numeric_only=True)
        pairs = []
        for i, a in enumerate(corr.columns):
            for b in corr.columns[i + 1:]:
                value = corr.loc[a, b]
                if pd.notna(value):
                    pairs.append((abs(float(value)), f"{a} ↔ {b}", float(value)))
        pairs.sort(reverse=True)
        top = pairs[:8]
        if top:
            charts.append({
                "type": "bar",
                "title": "Strongest numeric relationships",
                "description": "Absolute Pearson correlation between numeric columns.",
                "labels": [p[1] for p in top],
                "data": [round(p[2], 3) for p in top],
                "metric": "Correlation (-1 to 1)",
            })

    # Fallback: a simple categorical count chart or numeric box summary.
    if not charts:
        if categorical:
            grouped = df[categorical[0]].astype("string").fillna("Unknown").value_counts().head(10)
            charts.append({
                "type": "doughnut",
                "title": f"Distribution of {categorical[0]}",
                "description": "Record share by category.",
                "labels": [str(x) for x in grouped.index],
                "data": [int(x) for x in grouped.values],
                "metric": "Records",
            })

    return charts[:6]


def calculate_kpis(df, schema):
    metric = schema["primary_metric"]
    kpis = [{
        "label": "ROWS",
        "value": int(len(df)),
        "display": f"{len(df):,}",
        "description": "Usable records",
        "format": "number",
    }]

    if metric:
        series = pd.to_numeric(df[metric], errors="coerce").dropna()
        total = float(series.sum()) if len(series) else 0
        avg = float(series.mean()) if len(series) else 0
        kpis.append({
            "label": f"TOTAL {metric.upper()}",
            "value": _safe_float(total),
            "display": _display_value(total),
            "description": f"Sum of {metric}",
            "format": "number",
        })
        kpis.append({
            "label": f"AVG {metric.upper()}",
            "value": _safe_float(avg),
            "display": _display_value(avg),
            "description": f"Average {metric}",
            "format": "number",
        })
    else:
        kpis.extend([
            {
                "label": "COLUMNS",
                "value": int(len(df.columns)),
                "display": f"{len(df.columns):,}",
                "description": "Detected variables",
                "format": "number",
            },
            {
                "label": "UNIQUE ROWS",
                "value": int(len(df.drop_duplicates())),
                "display": f"{len(df.drop_duplicates()):,}",
                "description": "Distinct records",
                "format": "number",
            },
        ])

    missing = int(df.isna().sum().sum())
    kpis.append({
        "label": "MISSING CELLS",
        "value": missing,
        "display": f"{missing:,}",
        "description": "Remaining missing values",
        "format": "number",
    })
    return kpis[:4]


def build_insight_summary(df, schema, charts):
    metric = schema["primary_metric"]
    summary = {
        "rows": len(df),
        "columns": len(df.columns),
        "numeric_columns": schema["numeric_ranked"],
        "categorical_columns": schema["categorical"],
        "date_column": schema["date_column"],
        "year_column": schema.get("year_column"),
        "location_column": schema.get("location_column"),
        "primary_metric": metric,
        "missing_cells": int(df.isna().sum().sum()),
    }

    insights = []
    if metric:
        series = pd.to_numeric(df[metric], errors="coerce").dropna()
        if len(series):
            insights.append(
                f"{metric} ranges from {_display_value(float(series.min()))} to {_display_value(float(series.max()))}, with an average of {_display_value(float(series.mean()))}."
            )
            top_idx = series.idxmax()
            row_label = ""
            for cat in schema["categorical"][:2]:
                if cat in df.columns:
                    row_label = f" {cat}='{df.loc[top_idx, cat]}'."
                    break
            insights.append(f"The highest observed {metric} is {_display_value(float(series.max()))}.{row_label}")
            if len(series) >= 5:
                q1, q3 = series.quantile([0.25, 0.75])
                insights.append(f"The middle 50% of {metric} falls between {_display_value(float(q1))} and {_display_value(float(q3))}.")

    for col in schema["categorical"][:2]:
        counts = df[col].astype("string").fillna("Unknown").value_counts()
        if not counts.empty:
            pct = counts.iloc[0] / len(df) * 100
            insights.append(f"{col}: '{counts.index[0]}' is the most common value ({pct:.1f}% of rows).")

    if schema["date_column"]:
        date_series = df[schema["date_column"]].dropna()
        if len(date_series):
            insights.append(
                f"The dataset spans {date_series.min().date().isoformat()} to {date_series.max().date().isoformat()}."
            )

    if len(schema["numeric_ranked"]) >= 2:
        corr = df[schema["numeric_ranked"][:8]].corr(numeric_only=True)
        pairs = []
        for i, a in enumerate(corr.columns):
            for b in corr.columns[i + 1:]:
                val = corr.loc[a, b]
                if pd.notna(val):
                    pairs.append((abs(float(val)), a, b, float(val)))
        pairs.sort(reverse=True)
        if pairs:
            _, a, b, val = pairs[0]
            strength = "strong" if abs(val) >= 0.7 else "moderate" if abs(val) >= 0.4 else "weak"
            insights.append(f"{a} and {b} have a {strength} correlation (r={val:.2f}).")

    summary["rule_based_insights"] = insights[:7]
    summary["chart_summaries"] = [
        {"title": c["title"], "description": c["description"]}
        for c in charts
    ]
    return summary


def analyze_dataset(df):
    schema = infer_schema(df)
    charts = build_charts(df, schema)
    kpis = calculate_kpis(df, schema)
    insight_summary = build_insight_summary(df, schema, charts)

    profiles = []
    for col in df.columns:
        series = df[col]
        if pd.api.types.is_datetime64_any_dtype(series):
            dtype = "datetime"
        elif pd.api.types.is_numeric_dtype(series):
            dtype = "numeric"
        elif col in schema["identifiers"]:
            dtype = "identifier"
        elif col in schema["categorical"]:
            dtype = "categorical"
        else:
            dtype = "text"
        profiles.append({
            "column": col,
            "type": dtype,
            "unique": int(series.nunique(dropna=True)),
            "missing": int(series.isna().sum()),
        })

    return {
        "schema": schema,
        "kpis": kpis,
        "charts": charts,
        "insight_summary": insight_summary,
        "profiles": profiles,
    }
