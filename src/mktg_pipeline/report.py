"""HTML and Markdown quality report with charts."""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

INK, MUTED = "#1b1f2a", "#6b7280"
COLORS = {"paid_search": "#6366f1", "paid_social": "#f59e0b", "email": "#16a34a", "organic_search": "#0ea5e9", "direct": "#94a3b8"}

CSS = """
body{font:16px/1.6 -apple-system,Segoe UI,Roboto,Arial,sans-serif;color:#1b1f2a;max-width:1000px;margin:36px auto;padding:0 20px}
h1{margin-bottom:4px} h2{margin-top:36px;border-bottom:1px solid #e5e7eb;padding-bottom:6px}
.sub{color:#6b7280;margin-top:0} .cards{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}
.card{flex:1;min-width:150px;border:1px solid #e5e7eb;border-radius:10px;padding:12px 16px}.card b{display:block;font-size:26px}
.ok{color:#15803d}.bad{color:#b91c1c}.warn{color:#b45309}
table{border-collapse:collapse;width:100%;font-size:13.5px;margin:12px 0} th,td{padding:6px 10px;border-bottom:1px solid #e5e7eb;text-align:left;vertical-align:top}
th{background:#f3f4f6} img{max-width:100%;border:1px solid #e5e7eb;border-radius:8px}
.note{background:#fef9c3;border:1px solid #fde68a;padding:10px 14px;border-radius:8px}
"""


def _fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buf, format="png", dpi=130, facecolor="white")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def spend_chart(mart: pd.DataFrame, incidents: pd.DataFrame, path: Path) -> str:
    fig, ax = plt.subplots(figsize=(9.5, 3.8))
    paid = mart[mart["is_paid"] == 1].assign(date=lambda d: pd.to_datetime(d["date"]))
    for ch, part in paid.groupby("channel"):
        ax.plot(part["date"], part["spend"], color=COLORS[ch], label=ch.replace("_", " "), linewidth=1.3)
    for r in incidents[incidents["metric"] == "spend"].itertuples():
        ax.axvspan(r.start - pd.Timedelta(hours=12), r.end + pd.Timedelta(hours=12), color="#fecaca", alpha=0.8)
    ax.set_ylabel("Daily spend")
    ax.set_title("Paid spend by channel (red = flagged anomaly)", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.savefig(path, dpi=130, facecolor="white")
    return _fig_b64(fig)


def transactions_chart(mart: pd.DataFrame, incidents: pd.DataFrame, path: Path) -> str:
    fig, ax = plt.subplots(figsize=(9.5, 3.8))
    m = mart.assign(date=lambda d: pd.to_datetime(d["date"]))
    for ch, part in m.groupby("channel"):
        ax.plot(part["date"], part["transactions"], color=COLORS[ch], label=ch.replace("_", " "), linewidth=1.2)
    for r in incidents[incidents["metric"].isin(["transactions", "conversion_rate"])].itertuples():
        ax.axvspan(r.start - pd.Timedelta(hours=12), r.end + pd.Timedelta(hours=12), color="#fecaca", alpha=0.8)
    ax.set_ylabel("Daily web transactions")
    ax.set_title("Web transactions by channel (red = flagged anomaly)", loc="left", color=INK, fontsize=11)
    ax.legend(frameon=False, fontsize=8, ncol=3)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    fig.savefig(path, dpi=130, facecolor="white")
    return _fig_b64(fig)


def weekly_kpis(mart: pd.DataFrame) -> pd.DataFrame:
    """Last seven days against the seven before, by channel, from the mart."""
    m = mart.assign(date=pd.to_datetime(mart["date"]))
    end = m["date"].max()
    cur = m[m["date"] > end - pd.Timedelta(days=7)]
    prev = m[(m["date"] <= end - pd.Timedelta(days=7)) & (m["date"] > end - pd.Timedelta(days=14))]

    def agg(df):
        g = df.groupby("channel").agg(spend=("spend", "sum"), sessions=("sessions", "sum"), orders=("orders", "sum"),
                                      revenue=("order_revenue", "sum"), leads=("leads", "sum"))
        g["conversion_rate"] = g["orders"] / g["sessions"].where(g["sessions"] > 0)
        g["cac"] = g["spend"].where(g["spend"] > 0) / g["orders"].where(g["orders"] > 0)
        g["roas"] = g["revenue"] / g["spend"].where(g["spend"] > 0)
        return g

    a, b = agg(cur), agg(prev)
    out = a.join(b[["revenue", "orders"]].add_suffix("_prev"))
    out["revenue_change"] = out["revenue"] / out["revenue_prev"] - 1
    out["orders_change"] = out["orders"] / out["orders_prev"] - 1
    return out.reset_index()[["channel", "spend", "sessions", "orders", "revenue", "conversion_rate", "cac", "roas", "orders_change", "revenue_change"]]


def _table(df: pd.DataFrame, fmt=None) -> str:
    return df.to_html(index=False, border=0, escape=True, na_rep="", float_format=lambda v: f"{v:,.2f}" if abs(v) < 100 else f"{v:,.0f}")


def build_report(out: Path, title: str, results: pd.DataFrame, incidents: pd.DataFrame, mart: pd.DataFrame, meta: dict,
                 evaluation: dict | None = None) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    gate = not ((results["severity"] == "error") & (results["status"] == "fail")).any()
    errors = int(((results["severity"] == "error") & (results["status"] == "fail")).sum())
    warns = int(((results["severity"] == "warn") & (results["status"] == "fail")).sum())
    passed = int((results["status"] == "pass").sum())
    kpis = weekly_kpis(mart)
    spend_b64 = spend_chart(mart, incidents, out / "spend.png")
    tx_b64 = transactions_chart(mart, incidents, out / "transactions.png")

    show = results.assign(status=lambda d: d["status"].map({"pass": "pass", "fail": "FAIL"}))[
        ["id", "name", "category", "severity", "status", "failing_rows", "detail"]]
    inc = incidents.assign(start=lambda d: d["start"].dt.strftime("%Y-%m-%d"), end=lambda d: d["end"].dt.strftime("%Y-%m-%d"))

    parts = [
        f"<!doctype html><html lang='en'><meta charset='utf-8'><title>{html.escape(title)}</title><style>{CSS}</style><body>",
        f"<h1>{html.escape(title)}</h1><p class='sub'>Reporting window {meta['start']} to {meta['end']}. Synthetic data.</p>",
        "<p class='note'>All data in this report is synthetic and generated by <code>mktg_pipeline.generate</code>. "
        "Nothing here is employer or customer data.</p>",
        "<div class='cards'>"
        f"<div class='card'><b class='{'ok' if gate else 'bad'}'>{'PASS' if gate else 'FAIL'}</b>quality gate</div>"
        f"<div class='card'><b class='ok'>{passed}</b>checks passed</div>"
        f"<div class='card'><b class='{'bad' if errors else 'ok'}'>{errors}</b>errors</div>"
        f"<div class='card'><b class='{'warn' if warns else 'ok'}'>{warns}</b>warnings</div>"
        f"<div class='card'><b>{len(incidents)}</b>anomaly incidents</div></div>",
        "<h2>Quality checks</h2>", _table(show),
        "<h2>Anomaly incidents</h2>", _table(inc) if len(inc) else "<p>None.</p>",
        f"<img alt='spend' src='data:image/png;base64,{spend_b64}'>", f"<img alt='transactions' src='data:image/png;base64,{tx_b64}'>",
        "<h2>Last seven days versus the previous seven</h2>", _table(kpis),
    ]
    if evaluation is not None:
        e = evaluation
        parts += [
            "<h2>Detection scorecard (against the answer key)</h2>",
            f"<p>{e['defects_caught']} of {e['defects_injected']} injected defects were caught "
            f"(recall {e['recall'] * 100:.0f}%). Unexpected failing checks: "
            f"{', '.join(e['unexpected_failures']) if e['unexpected_failures'] else 'none'}.</p>",
            _table(e["table"]),
        ]
    parts.append("</body></html>")
    path = out / "report.html"
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def markdown_summary(title: str, results: pd.DataFrame, incidents: pd.DataFrame, evaluation: dict | None = None) -> str:
    errors = results[(results["severity"] == "error") & (results["status"] == "fail")]
    warns = results[(results["severity"] == "warn") & (results["status"] == "fail")]
    lines = [f"## {title}", "", f"**Quality gate: {'PASS' if errors.empty else 'FAIL'}**  ",
             f"{int((results.status == 'pass').sum())} of {len(results)} checks passed, {len(errors)} errors, {len(warns)} warnings, "
             f"{len(incidents)} anomaly incidents.", ""]
    if len(errors) or len(warns):
        lines += ["| Check | Severity | Failing rows | Detail |", "|---|---|---:|---|"]
        for r in pd.concat([errors, warns]).itertuples():
            lines.append(f"| {r.id} {r.name} | {r.severity} | {r.failing_rows} | {r.detail[:140]} |")
        lines.append("")
    if evaluation is not None:
        lines += [f"Detection: {evaluation['defects_caught']} of {evaluation['defects_injected']} injected defects caught.", ""]
    return "\n".join(lines)
