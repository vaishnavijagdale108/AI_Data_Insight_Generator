let chartInstances = [];
let mapInstances = [];
const geocodeCache = {};

const numberFormatter = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

// Professional Power BI-inspired palette for data series.
const VIZ_COLORS = {
    primary: "#22D3EE",      // cyan
    primaryFill: "rgba(34, 211, 238, 0.14)",
    secondary: "#8B5CF6",    // purple
    tertiary: "#3B82F6",     // blue
    positive: "#22C55E",     // green
    warning: "#F59E0B",      // amber
    negative: "#F43F5E",     // red/pink
    pink: "#EC4899",
    teal: "#14B8A6",
    indigo: "#6366F1",
    orange: "#F97316"
};

const SERIES_PALETTE = [
    VIZ_COLORS.primary, VIZ_COLORS.secondary, VIZ_COLORS.tertiary,
    VIZ_COLORS.positive, VIZ_COLORS.warning, VIZ_COLORS.pink,
    VIZ_COLORS.teal, VIZ_COLORS.orange
];

function formatNumber(value) {
    return numberFormatter.format(Number(value || 0));
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function baseChartOptions(chart = {}) {
    const labels = chart.labels || [];
    const values = (chart.data || []).map(v => Number(v ?? 0));
    return {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        animation: { duration: 650, easing: "easeOutQuart" },
        plugins: {
            legend: { labels: { color: "#cbd5e1", font: { size: 11 } } },
            tooltip: {
                backgroundColor: "#111827",
                titleColor: "#f8fafc",
                bodyColor: "#cbd5e1",
                borderColor: "rgba(34, 211, 238, 0.45)",
                borderWidth: 1,
                padding: 12,
                displayColors: false,
                callbacks: {
                    label: (ctx) => `${chart.metric || "Value"}: ${formatNumber(ctx.parsed.y ?? ctx.parsed)}`,
                    footer: (items) => {
                        const i = items?.[0]?.dataIndex;
                        if (i == null || i <= 0) return "Click a point for details";
                        const current = values[i];
                        const previous = values[i - 1];
                        if (!Number.isFinite(previous) || previous === 0) return "Click a point for details";
                        const pct = ((current - previous) / Math.abs(previous)) * 100;
                        return `${pct >= 0 ? "▲" : "▼"} ${Math.abs(pct).toFixed(1)}% vs previous period • Click for details`;
                    }
                }
            }
        },
        scales: {
            x: {
                ticks: { color: "#78859f", font: { size: 11 }, maxRotation: 0 },
                grid: { color: "rgba(71, 85, 105, 0.28)" }
            },
            y: {
                ticks: { color: "#94a3b8", font: { size: 11 } },
                grid: { color: "rgba(71, 85, 105, 0.28)" }
            }
        }
    };
}

function destroyCharts() {
    chartInstances.forEach(chart => chart.destroy());
    chartInstances = [];
    mapInstances.forEach(map => map.remove());
    mapInstances = [];
}

function sleep(ms) { return new Promise(resolve => setTimeout(resolve, ms)); }

function buildChartToolbar(chart, index) {
    const line = chart.type === "line";
    return `
        <div class="chart-toolbar" aria-label="Chart controls">
            ${line ? '<button type="button" class="chart-tool active" data-action="trend">Trend</button><button type="button" class="chart-tool" data-action="change">% Change</button>' : ''}
            <button type="button" class="chart-tool" data-action="data">Data</button>
            <button type="button" class="chart-tool" data-action="download">↓ PNG</button>
            <button type="button" class="chart-tool" data-action="reset">Reset</button>
        </div>`;
}

function renderChartDetails(wrapper, chart, selectedIndex = null) {
    const detail = wrapper.querySelector(".chart-detail");
    if (!detail) return;
    const values = (chart.data || []).map(v => Number(v ?? 0));
    if (selectedIndex == null || !chart.labels?.length) {
        const clean = values.filter(Number.isFinite);
        if (!clean.length) { detail.innerHTML = "Select a data point to explore it."; return; }
        const max = Math.max(...clean), min = Math.min(...clean), avg = clean.reduce((a,b)=>a+b,0)/clean.length;
        detail.innerHTML = `<span><b>${clean.length}</b> periods</span><span>Avg <b>${formatNumber(avg)}</b></span><span>High <b>${formatNumber(max)}</b></span><span>Low <b>${formatNumber(min)}</b></span><em>Click a point for details</em>`;
        return;
    }
    const i = Math.max(0, Math.min(selectedIndex, values.length - 1));
    const value = values[i];
    const prev = i > 0 ? values[i - 1] : null;
    const change = prev != null && Number.isFinite(prev) && prev !== 0 ? ((value - prev) / Math.abs(prev)) * 100 : null;
    const clean = values.filter(Number.isFinite);
    const rank = 1 + clean.filter(v => v > value).length;
    detail.innerHTML = `<span><small>Period</small><b>${escapeHtml(chart.labels[i])}</b></span><span><small>${escapeHtml(chart.metric || "Value")}</small><b>${formatNumber(value)}</b></span><span><small>Vs previous</small><b class="${change == null ? "muted" : change >= 0 ? "positive" : "negative"}">${change == null ? "—" : `${change >= 0 ? "+" : ""}${change.toFixed(1)}%`}</b></span><span><small>Rank</small><b>#${rank}</b></span>`;
}

function showDataTable(wrapper, chart) {
    let panel = wrapper.querySelector(".chart-data-table");
    if (panel) { panel.remove(); return; }
    panel = document.createElement("div");
    panel.className = "chart-data-table";
    const rows = (chart.labels || []).map((label, i) => `<tr><td>${escapeHtml(label)}</td><td>${formatNumber(chart.data?.[i])}</td></tr>`).join("");
    panel.innerHTML = `<div class="table-scroll"><table><thead><tr><th>Period / Category</th><th>${escapeHtml(chart.metric || "Value")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
    wrapper.appendChild(panel);
}

async function geocodeLocation(name) {
    const key = String(name).trim();
    if (!key || key.toLowerCase() === "unknown") return null;
    if (geocodeCache[key]) return geocodeCache[key];

    const common = {
        "mumbai": [19.0760, 72.8777], "pune": [18.5204, 73.8567], "delhi": [28.6139, 77.2090],
        "new delhi": [28.6139, 77.2090], "bengaluru": [12.9716, 77.5946], "bangalore": [12.9716, 77.5946],
        "hyderabad": [17.3850, 78.4867], "chennai": [13.0827, 80.2707], "kolkata": [22.5726, 88.3639],
        "ahmedabad": [23.0225, 72.5714], "jaipur": [26.9124, 75.7873], "nagpur": [21.1458, 79.0882],
        "nashik": [19.9975, 73.7898], "satara": [17.6805, 74.0183], "london": [51.5074, -0.1278],
        "new york": [40.7128, -74.0060], "san francisco": [37.7749, -122.4194], "toronto": [43.6532, -79.3832],
        "singapore": [1.3521, 103.8198], "dubai": [25.2048, 55.2708]
    };
    const known = common[key.toLowerCase()];
    if (known) { geocodeCache[key] = known; return known; }
    try {
        const url = `https://nominatim.openstreetmap.org/search?format=jsonv2&limit=1&q=${encodeURIComponent(key)}`;
        const response = await fetch(url, { headers: { "Accept-Language": "en" } });
        const results = await response.json();
        if (results?.length) {
            const point = [Number(results[0].lat), Number(results[0].lon)];
            geocodeCache[key] = point;
            return point;
        }
    } catch (e) { console.warn("Geocoding failed for", key, e); }
    return null;
}

async function renderMapCard(chart, index) {
    const wrapper = document.createElement("div");
    wrapper.className = "chart-card dynamic-chart-card map-card";
    wrapper.innerHTML = `
        <div class="chart-heading"><div><h3>${escapeHtml(chart.title)}</h3><p>${escapeHtml(chart.description || "Automatically selected geographic analysis")}</p></div><span class="chart-tag">AUTO MAP</span></div>
        <div class="map-container" id="dynamicMap${index}"></div><div class="map-note" id="mapNote${index}">Resolving locations...</div>`;
    document.getElementById("chartsGrid").appendChild(wrapper);
    const map = L.map(`dynamicMap${index}`, { scrollWheelZoom: false }).setView([20, 78], 4);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
    mapInstances.push(map);
    const points = [];
    if (Array.isArray(chart.points) && chart.points.length) {
        chart.points.forEach(p => { if (Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lon))) points.push({lat:Number(p.lat),lon:Number(p.lon),label:p.label||"Location",value:null}); });
    } else {
        const labels = chart.labels || [];
        for (let i=0;i<Math.min(labels.length,12);i++) { const coords=await geocodeLocation(labels[i]); if(coords) points.push({lat:coords[0],lon:coords[1],label:labels[i],value:chart.data?.[i]}); await sleep(250); }
    }
    if (!points.length) { document.getElementById(`mapNote${index}`).textContent="No coordinates could be resolved. Add Latitude/Longitude columns for exact mapping."; return; }
    const bounds=[];
    points.forEach(p=>{ const marker=L.circleMarker([p.lat,p.lon],{radius:9,weight:2,fillOpacity:.75}).addTo(map); const value=p.value==null?"":`<br><strong>${escapeHtml(chart.metric||"Value")}:</strong> ${formatNumber(p.value)}`; marker.bindPopup(`<strong>${escapeHtml(p.label)}</strong>${value}`); bounds.push([p.lat,p.lon]); });
    if(bounds.length>1) map.fitBounds(bounds,{padding:[25,25]}); else map.setView(bounds[0],7);
    document.getElementById(`mapNote${index}`).textContent=`${points.length} location(s) plotted. Click markers for values.`;
}

function createChartCard(chart, index) {
    if (chart.type === "map") { renderMapCard(chart,index); return; }
    const wrapper=document.createElement("div"); wrapper.className="chart-card dynamic-chart-card";
    wrapper.innerHTML=`<div class="chart-heading"><div><h3>${escapeHtml(chart.title)}</h3><p>${escapeHtml(chart.description||"Automatically selected analysis")}</p></div><span class="chart-tag">AUTO</span></div>${buildChartToolbar(chart,index)}<div class="chart-container"><canvas id="dynamicChart${index}"></canvas></div><div class="chart-detail" aria-live="polite"></div>`;
    document.getElementById("chartsGrid").appendChild(wrapper);
    const canvas=document.getElementById(`dynamicChart${index}`);
    const type=chart.type === "doughnut" ? "doughnut" : chart.type === "line" ? "line" : "bar";
    const options=baseChartOptions(chart);
    if(type === "bar" && chart.title.toLowerCase().includes("relationship")){options.scales.y.min=-1;options.scales.y.max=1;}
    if(type === "bar" && chart.labels.length>6) options.indexAxis="y";
    if(type === "doughnut"){options.cutout="65%";options.scales={};options.plugins.legend.position="bottom";options.interaction={mode:"nearest",intersect:true};}
    const dataset={label:chart.metric||"Value",data:chart.data,borderRadius:8,borderWidth:0};
    if(type === "line"){
        dataset.borderColor=VIZ_COLORS.primary;
        dataset.backgroundColor=VIZ_COLORS.primaryFill;
        dataset.pointBackgroundColor=VIZ_COLORS.primary;
        dataset.pointBorderColor="#0b1020";
        dataset.pointBorderWidth=2;
        dataset.fill=true;
        dataset.tension=.35;
        dataset.borderWidth=3;
        dataset.pointRadius=4;
        dataset.pointHoverRadius=7;
        dataset.pointHoverBackgroundColor="#f8fafc";
        dataset.pointHoverBorderColor=VIZ_COLORS.primary;
        dataset.pointHitRadius=14;
    }
    else if(type === "doughnut"){
        dataset.backgroundColor=SERIES_PALETTE;
        dataset.borderColor="#0f172a";
        dataset.borderWidth=2;
        dataset.hoverOffset=8;
    }
    else {
        dataset.backgroundColor=SERIES_PALETTE[0];
        dataset.borderColor=SERIES_PALETTE[0];
        dataset.borderWidth=1;
        dataset.hoverBackgroundColor=SERIES_PALETTE[2];
    }
    if(type === "line") options.onClick=(_,elements)=>{if(elements?.length) renderChartDetails(wrapper,chart,elements[0].index);};
    const instance=new Chart(canvas,{type,data:{labels:chart.labels,datasets:[dataset]},options}); chartInstances.push(instance);
    renderChartDetails(wrapper,chart);
    wrapper.querySelectorAll(".chart-tool").forEach(button=>button.addEventListener("click",()=>{
        const action=button.dataset.action;
        if(action === "data") showDataTable(wrapper,chart);
        if(action === "download"){const link=document.createElement("a");link.download=`${(chart.title||"chart").replace(/[^a-z0-9]+/gi,"_").toLowerCase()}.png`;link.href=instance.toBase64Image();link.click();}
        if(action === "reset"){instance.reset();renderChartDetails(wrapper,chart);wrapper.querySelectorAll(".chart-tool").forEach(b=>b.classList.remove("active"));const trend=wrapper.querySelector('[data-action="trend"]');if(trend)trend.classList.add("active");if(instance.config.type==="line") instance.data.datasets[0].data=chart.data;instance.update();}
        if(action === "trend" || action === "change"){
            if(instance.config.type!=="line") return;
            wrapper.querySelectorAll(".chart-tool").forEach(b=>b.classList.remove("active"));button.classList.add("active");
            if(action === "change"){
                const vals=chart.data.map((v,i)=>i===0?0:((Number(v)-Number(chart.data[i-1]))/Math.abs(Number(chart.data[i-1])||1))*100);
                instance.data.datasets[0].data=vals.map(v=>Number.isFinite(v)?Number(v.toFixed(2)):0);instance.data.datasets[0].label="% Change";instance.options.scales.y.ticks.callback=v=>`${v}%`;instance.update();
            } else {instance.data.datasets[0].data=chart.data;instance.data.datasets[0].label=chart.metric||"Value";instance.options.scales.y.ticks.callback=v=>formatNumber(v);instance.update();}
        }
    }));
}

function renderKPIs(kpis) {
    const grid = document.getElementById("kpiGrid");
    grid.innerHTML = "";
    kpis.forEach((kpi, index) => {
        const card = document.createElement("div");
        card.className = "kpi-card";
        card.innerHTML = `
            <div class="kpi-top">
                <span class="kpi-label">${escapeHtml(kpi.label)}</span>
                <span class="kpi-icon">${index === 0 ? "#" : index === 1 ? "Σ" : index === 2 ? "≈" : "✓"}</span>
            </div>
            <div class="kpi-value">${escapeHtml(kpi.display)}</div>
            <p>${escapeHtml(kpi.description || "Automatically calculated")}</p>
        `;
        grid.appendChild(card);
    });
}

function renderProfiles(profiles, schema) {
    const body = document.getElementById("profileBody");
    body.innerHTML = profiles.map(item => `
        <tr>
            <td>${escapeHtml(item.column)}</td>
            <td><span class="type-pill">${escapeHtml(item.type)}</span></td>
            <td>${formatNumber(item.unique)}</td>
            <td>${formatNumber(item.missing)}</td>
        </tr>
    `).join("");

    const summary = [];
    if (schema.primary_metric) summary.push(`Primary metric: <strong>${escapeHtml(schema.primary_metric)}</strong>`);
    if (schema.date_column) summary.push(`Date: <strong>${escapeHtml(schema.date_column)}</strong>`);
    summary.push(`Numeric: <strong>${schema.numeric.length}</strong>`);
    summary.push(`Categorical: <strong>${schema.categorical.length}</strong>`);
    document.getElementById("detectedSummary").innerHTML = summary.join(" <span>•</span> ");
}

function setCleaningReport(report) {
    const panel = document.getElementById("cleaningReport");
    const summary = document.getElementById("cleaningSummary");
    const list = document.getElementById("cleaningList");
    if (!report) return;

    const items = [];
    (report.columns_mapped || []).forEach(item => items.push(`✓ ${item.from} → ${item.to}`));
    if (report.duplicates_removed) items.push(`✓ ${report.duplicates_removed} duplicate row(s) removed`);
    if (report.trimmed_text_values) items.push(`✓ ${report.trimmed_text_values} text value(s) standardized`);
    (report.numeric_conversions || []).forEach(item => items.push(`✓ ${item.column} converted to numeric`));
    (report.date_columns_detected || []).forEach(item => items.push(`✓ ${item} detected as a date/time column`));
    Object.entries(report.missing_values_filled || {}).forEach(([col, count]) => items.push(`✓ ${count} missing ${col} value(s) filled`));
    (report.empty_columns_removed || []).forEach(col => items.push(`✓ Empty column removed: ${col}`));
    Object.entries(report.invalid_dates_found || {}).forEach(([col, count]) => items.push(`• ${count} value(s) in ${col} could not be parsed as dates`));
    (report.warnings || []).forEach(item => items.push(`• ${item}`));
    if (!items.length) items.push("✓ No major cleaning changes were required.");

    summary.innerHTML = `<strong>${formatNumber(report.original_rows || 0)}</strong> rows → <strong>${formatNumber(report.cleaned_rows || 0)}</strong> clean rows <span class="clean-pill">READY FOR ANALYSIS</span>`;
    list.innerHTML = items.map(item => `<li>${escapeHtml(item)}</li>`).join("");
    panel.classList.remove("hidden");
}

function renderCharts(charts) {
    destroyCharts();
    const grid = document.getElementById("chartsGrid");
    grid.innerHTML = "";
    (charts || []).forEach(createChartCard);
    if (!(charts || []).length) {
        grid.innerHTML = `<div class="empty-state">No chartable relationship was detected. The dataset profile and statistical summary are still available below.</div>`;
    }
}

function renderRuleInsights(summary) {
    const box = document.getElementById("ruleInsights");
    const insights = summary?.rule_based_insights || [];
    box.innerHTML = insights.length
        ? insights.map(text => `<div class="insight-item">• ${escapeHtml(text)}</div>`).join("")
        : `<div class="insight-item">No strong automated pattern was detected from the available columns.</div>`;
}

function renderDashboard(data) {
    const analysis = data.analysis;
    renderKPIs(analysis.kpis || []);
    renderCharts(analysis.charts || []);
    renderProfiles(analysis.profiles || [], analysis.schema || {});
    renderRuleInsights(analysis.insight_summary || {});
    setCleaningReport(data.cleaning);

    document.getElementById("datasetTitle").textContent = data.filename || "Dataset";
    document.getElementById("dataStatus").textContent = `${data.filename || "Dataset"} loaded, cleaned and automatically analyzed`;
    document.getElementById("aiInsights").classList.add("hidden");
    document.getElementById("aiInsights").innerHTML = "";
}

async function loadDashboard() {
    try {
        const response = await fetch("/dashboard-data");
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Unable to load dashboard.");
        renderDashboard(data);
    } catch (error) {
        document.getElementById("dataStatus").textContent = "Error: " + error.message;
    }
}

async function uploadFile() {
    const fileInput = document.getElementById("fileInput");
    const status = document.getElementById("uploadStatus");
    if (!fileInput.files.length) {
        status.textContent = "⚠ Please select a CSV file first.";
        return;
    }

    const file = fileInput.files[0];
    if (!file.name.toLowerCase().endsWith(".csv")) {
        status.textContent = "⚠ Only CSV files are supported.";
        return;
    }

    const formData = new FormData();
    formData.append("file", file);
    status.textContent = "⏳ Inspecting, cleaning, profiling, analyzing and selecting visualizations...";

    try {
        const response = await fetch("/upload", { method: "POST", body: formData });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Upload failed.");
        renderDashboard(data);
        status.textContent = `✓ ${data.filename} analyzed successfully — ${data.cleaned_rows} clean rows.`;
    } catch (error) {
        console.error(error);
        status.textContent = "❌ " + error.message;
    }
}

async function generateAIInsights() {
    const box = document.getElementById("aiInsights");
    const button = document.getElementById("aiButton");
    button.disabled = true;
    button.textContent = "Generating...";
    box.classList.remove("hidden");
    box.innerHTML = "⏳ Generating dataset-specific insights...";

    try {
        const response = await fetch("/ai-insights");
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "AI insights failed.");

        const text = data.insights || data.message || "No insights returned.";
        box.innerHTML = `<div class="ai-text">${escapeHtml(text).replace(/\n/g, "<br>")}</div>`;
        if (!data.available && data.message) {
            box.innerHTML += `<div class="ai-note">${escapeHtml(data.message)}</div>`;
        }
    } catch (error) {
        box.innerHTML = `❌ ${escapeHtml(error.message)}`;
    } finally {
        button.disabled = false;
        button.textContent = "Generate AI Insights";
    }
}

document.addEventListener("DOMContentLoaded", loadDashboard);
