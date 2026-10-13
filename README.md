# AI Data Insight Generator — Generic CSV Analyzer

A Flask + Pandas + Chart.js + Gemini application that is designed to work with **many kinds of structured CSV files**, not only sales data.

## What changed

The original project was sales-specific because the backend required these columns:
`Date, Region, Category, Product, Sales, Profit, Quantity`.

This version removes that hard dependency.

### Generic pipeline

1. Upload a CSV.
2. Read it with UTF-8 or CP1252 fallback.
3. Clean duplicate rows, whitespace, empty columns and missing values.
4. Detect likely date/time, numeric, categorical, text and identifier fields.
5. Select a primary numeric metric when one exists.
6. Automatically generate KPIs from the detected dataset.
7. Automatically choose charts such as time trends, category breakdowns, distributions and numeric relationships.
8. Generate rule-based statistical findings for every dataset.
9. Optionally send the dataset summary to Gemini for a richer natural-language analysis.

## Example datasets this design can handle

- Sales / ecommerce
- Customer data
- HR / employee data
- Student / academic data
- Finance / transactions
- Marketing / campaign data
- Inventory / operations
- Survey / feedback data
- Music / streaming data
- Many other rectangular CSV datasets

It does **not** magically understand arbitrary unstructured files. The current upload interface is intentionally for structured CSV data.

## Why this works better

The app no longer asks, “Where are Sales, Profit and Region?”
It asks, “What columns are present, what types are they, which relationships can be measured, and which visualizations fit those relationships?”

## Gemini

Optional but recommended for the full GenAI experience.

Create `.env` from `.env.example` and add:

```text
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

Without Gemini, the app still produces rule-based statistical insights.

## Run

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app\server.py
```

Open:

`http://127.0.0.1:5000`

## Project structure

```text
AI_Sales_Insight_Generator_Ready/
├── app/
│   ├── index.html
│   ├── script.js
│   ├── server.py
│   └── style.css
├── src/
│   ├── analysis.py
│   ├── cleaning.py
│   └── data_loader.py
├── sample_data/
│   └── sales_100_rows.csv
├── uploads/
├── tests/
├── .env.example
├── .gitignore
└── requirements.txt
```


## Automatic Power BI-style visualization logic

The dashboard now adapts visualizations to detected data: **City/State/Country/Location → interactive map**, **Date/Year → line trend**, **numeric metrics + categories → bar/column comparisons**, **rankable categories → top-value bars**, **numeric relationships → correlation chart**, and **categorical-only data → distribution chart**. Latitude/Longitude columns are used as exact map coordinates when present; otherwise common cities are resolved locally and other locations can be geocoded through OpenStreetMap Nominatim from the browser.

## Interactive charts

The visualization cards now support:
- Click a line-chart point to inspect the selected period, value, change vs previous period, and rank.
- Switch line charts between absolute **Trend** and **% Change** views.
- Toggle a compact **Data** table for the chart.
- Download the current chart as a PNG.
- Reset the chart to its original generated view.
- Enhanced hover tooltips show the value and period-over-period change.

These controls are generated automatically for compatible charts, so the app remains dataset-agnostic.
