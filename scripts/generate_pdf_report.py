"""
DIVINE Recruiting Report — Corporate PDF Generator

Generates a beautifully styled corporate PDF report from merged candidate data.
Uses HTML/CSS rendering via headless Chrome for print-quality output.

Usage:
    python generate_pdf_report.py
"""

import base64
import os
import subprocess
import sys
import tempfile
from datetime import datetime

# Add scripts dir to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from generate_report import (
    load_csv, load_supabase, merge_candidates, compute_stats,
    PLATFORM_COSTS,
)

OUTPUT_PDF = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "DIVINE_Recruiting_Report.pdf")

# ─── Initially Qualified — Declined After Overrides ──────────────────────────────────────────
# Candidates who passed initial screening but were not hired after client review.
# Key: name (lowercase) or phone_normalized. Value: corporate-style feedback.

REVIEWED_DECLINED = {
    # --- Sergey's direct feedback ---
    "blake bumanglag": "Disqualified: prior litigation against previous employer",
    "michael greer": "Requested time to consider; no follow-up received",
    "sandeep jawanda": "Unresponsive after 4 call attempts and SMS",
    "vasiliy": "Presented company overview; candidate requested time to decide",
    "alexey": "Candidate declined the opportunity",
    "younas abdul aziz": "Unresponsive after initial screening",
    "alexander": "CDL issue pending resolution; follow-up scheduled mid-March",
    "morgan wood": "Seeking flatbed positions only; does not match OTR team role",
    "johnny taylor": "Evaluating current employer; decision pending",
    "brendan mullaney": "Disqualified: insufficient experience per updated insurance requirements",
    "jerry rodriguez": "Disqualified: insufficient experience per updated insurance requirements",
    "cole williams": "Disqualified: insufficient experience per updated insurance requirements",
    "craig potter": "Disqualified: insufficient experience per updated insurance requirements",
    "steven schibbelhut": "Unresponsive after two call attempts",
    "artem": "Considering opportunity; concern about LA to Rocklin commute distance",
    # --- Remaining qualified candidates with reasons from notes ---
    "demar powell": "Prefers local routes only",
    "huyen hoang": "Recent accident on driving record",
    "lloyd peterson": "Unresponsive after application link sent",
    "mario haro": "Limited experience; no follow-up after initial contact",
    "satinder walia": "Unresponsive after application link sent",
    "terry fleming": "Pursuing other employment opportunities",
    "tonya sanders": "Solo driver; team partner unavailable for 6+ months",
    "xiana benavidez": "Unresponsive after IntelliApp link sent",
    "joseph brogan": "Unresponsive after initial screening call",
    "oyai watson": "Unresponsive after initial contact",
}

# Sergey's comments — concise employer feedback (shown in separate column)
SERGEY_COMMENTS = {
    "blake bumanglag": "Toxic; sued previous employer",
    "michael greer": "Asked many questions, said he\u2019d think about it",
    "sandeep jawanda": "Called 4x + SMS, no response",
    "vasiliy": "Presented company; took a pause to decide",
    "alexey": "Decided not to work with us",
    "younas abdul aziz": "No answer after screening",
    "alexander": "CDL issue; follow-up mid-March",
    "morgan wood": "Wants flatbed only",
    "johnny taylor": "Undecided about leaving current employer",
    "brendan mullaney": "Low experience per new insurance policy",
    "jerry rodriguez": "Low experience per new insurance policy",
    "cole williams": "Low experience per new insurance policy",
    "craig potter": "Low experience per new insurance policy",
    "steven schibbelhut": "Called twice, no answer",
    "artem": "Considering; unhappy about LA\u2013Rocklin commute",
}


def apply_reviewed_declined(candidates):
    """Override status for candidates reviewed by client but not hired."""
    for c in candidates:
        name_key = c["name"].strip().lower()
        phone_key = c.get("phone_normalized", "")
        # Match by full name or first name (for single-name entries like "Vasiliy")
        first_name_key = name_key.split()[0] if name_key else ""
        feedback = (REVIEWED_DECLINED.get(name_key)
                    or REVIEWED_DECLINED.get(first_name_key)
                    or REVIEWED_DECLINED.get(phone_key))
        sergey = (SERGEY_COMMENTS.get(name_key)
                  or SERGEY_COMMENTS.get(first_name_key)
                  or SERGEY_COMMENTS.get(phone_key)
                  or "")
        if feedback:
            c["status"] = "Initially Qualified \u2014 Declined After"
            c["sergey_feedback"] = feedback
            if sergey:
                c["sergey_comment"] = sergey

    # Catch-all: move any remaining Qualified / Awaiting Feedback to Initially Qualified — Declined After
    for c in candidates:
        sl = c["status"].lower()
        if "awaiting feedback" in sl:
            c["status"] = "Initially Qualified \u2014 Declined After"
            if not c.get("sergey_feedback"):
                c["sergey_feedback"] = "Pending employer feedback; no update received"


# ─── Logo ────────────────────────────────────────────────────────────────────

LOGO_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "dashboard", "public", "logo.jpg"
)


def load_logo_base64() -> str:
    """Load the real Divine Enterprises logo as base64 data URI."""
    if os.path.exists(LOGO_PATH):
        with open(LOGO_PATH, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        print(f"  Loaded logo from {LOGO_PATH}")
        return f"data:image/jpeg;base64,{b64}"
    print("  [WARN] Logo not found")
    return ""


# ─── HTML Builder ────────────────────────────────────────────────────────────

def build_html(candidates, stats, logo_b64):
    """Build the full HTML report — McKinsey/Deloitte consulting style."""

    total = stats["total"]
    contacted = total - stats["no_answer"]
    qualified = stats["qualified"]
    hired = stats["hired"]
    reviewed_declined = stats["by_status"].get("Initially Qualified \u2014 Declined After", 0)
    contact_rate = round(contacted / total * 100, 1) if total else 0
    review_rate = round(reviewed_declined / contacted * 100, 1) if contacted else 0

    # Prepare qualified candidates list
    qualified_list = [c for c in candidates
                      if ("qualified" in c["status"].lower() and "not" not in c["status"].lower())
                      or c["status"] == "Qualified"]

    # Prepare reviewed-declined candidates list
    reviewed_declined_list = [c for c in candidates
                              if "initially qualified" in c["status"].lower() and "declined" in c["status"].lower()]

    # Logo HTML
    if logo_b64:
        logo_html = f'<img src="{logo_b64}" class="cover-logo" alt="Divine Enterprises">'
    else:
        logo_html = '<div class="cover-logo" style="width:90px;height:90px;background:#1A2B4A;display:flex;align-items:center;justify-content:center;color:white;font-size:32px;font-weight:700;letter-spacing:2px;">DE</div>'

    # Source bar chart data
    max_source_count = max(stats["by_source"].values()) if stats["by_source"] else 1

    # Funnel width calculations
    contacted_pct = round(contacted / total * 100) if total else 0
    reviewed_pct = round(reviewed_declined / total * 100) if total else 0

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Divine Enterprises — CDL Driver Recruiting Report</title>
<style>
/* ── Reset ─────────────────────────────────────────────────── */
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

:root {{
    --navy: #1A2B4A;
    --rule: #C8A96E;
    --text-primary: #1A2B4A;
    --text-secondary: #5A6677;
    --text-tertiary: #8B95A5;
    --border-heavy: #1A2B4A;
    --border-medium: #CBD5E0;
    --border-light: #E8ECF1;
    --bg-subtle: #FAFAFA;
    --bg-page: #FFFFFF;
}}

@page {{
    size: A4;
    margin: 0;
}}

body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    color: var(--text-primary);
    font-size: 11px;
    line-height: 1.6;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
}}

/* ── Cover Page ────────────────────────────────────────────── */
.cover {{
    width: 210mm;
    height: 297mm;
    background: var(--bg-page);
    display: flex;
    flex-direction: column;
    justify-content: flex-end;
    padding: 0 60px 80px 60px;
    position: relative;
    page-break-after: always;
}}

.cover-top-rule {{
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 6px;
    background: var(--navy);
}}

.cover-logo {{
    width: 90px;
    height: 90px;
    object-fit: cover;
    margin-bottom: 48px;
}}

.cover h1 {{
    font-size: 42px;
    font-weight: 300;
    letter-spacing: -0.5px;
    color: var(--navy);
    line-height: 1.1;
    margin-bottom: 12px;
}}

.cover .gold-rule {{
    width: 48px;
    height: 3px;
    background: var(--rule);
    margin: 24px 0;
}}

.cover .subtitle {{
    font-size: 16px;
    font-weight: 400;
    color: var(--text-secondary);
    line-height: 1.5;
    margin-bottom: 6px;
}}

.cover .meta {{
    font-size: 11px;
    color: var(--text-tertiary);
    letter-spacing: 0.5px;
    margin-top: 32px;
    line-height: 1.8;
}}

.cover .confidential {{
    position: absolute;
    top: 28px;
    right: 60px;
    font-size: 8px;
    letter-spacing: 3px;
    text-transform: uppercase;
    color: var(--text-tertiary);
}}

/* ── Content Pages ─────────────────────────────────────────── */
.page {{
    width: 210mm;
    min-height: 297mm;
    padding: 28mm 22mm 22mm 22mm;
    position: relative;
    page-break-after: always;
}}

.page:last-child {{
    page-break-after: auto;
}}

.page-header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 28px;
    padding-bottom: 10px;
    border-bottom: 1.5px solid var(--navy);
}}

.page-header .brand {{
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 2.5px;
    text-transform: uppercase;
    color: var(--navy);
}}

.page-header .section-label {{
    font-size: 9px;
    letter-spacing: 2px;
    text-transform: uppercase;
    color: var(--text-tertiary);
    font-weight: 400;
}}

h3 {{
    font-size: 20px;
    font-weight: 700;
    color: var(--navy);
    margin-bottom: 4px;
    letter-spacing: -0.3px;
}}

h4 {{
    font-size: 13px;
    font-weight: 700;
    color: var(--navy);
    margin-top: 28px;
    margin-bottom: 12px;
    text-transform: uppercase;
    letter-spacing: 1px;
}}

.section-desc {{
    font-size: 11px;
    color: var(--text-secondary);
    margin-bottom: 24px;
    line-height: 1.6;
}}

/* ── Metric Cards ──────────────────────────────────────────── */
.metrics {{
    display: flex;
    gap: 16px;
    margin-bottom: 32px;
}}

.metric-card {{
    flex: 1;
    background: var(--bg-subtle);
    padding: 20px 16px;
    text-align: center;
    position: relative;
    border-top: 3px solid var(--navy);
}}

.metric-card .value {{
    font-size: 34px;
    font-weight: 700;
    color: var(--navy);
    line-height: 1;
    margin-bottom: 6px;
    letter-spacing: -1px;
}}

.metric-card .label {{
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: var(--text-secondary);
}}

.metric-card .sublabel {{
    font-size: 9px;
    color: var(--text-tertiary);
    margin-top: 3px;
}}

/* ── Funnel ────────────────────────────────────────────────── */
.funnel {{
    margin: 16px 0 16px 0;
    max-width: 480px;
}}

.funnel-step {{
    display: flex;
    align-items: center;
    margin-bottom: 6px;
}}

.funnel-bar {{
    height: 42px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: white;
    font-weight: 700;
    font-size: 14px;
    margin: 0 auto;
    position: relative;
}}

.funnel-label {{
    position: absolute;
    right: -210px;
    width: 200px;
    text-align: left;
    color: var(--text-primary);
    font-size: 11px;
    font-weight: 400;
}}

.funnel-label strong {{
    font-weight: 700;
    display: block;
    margin-bottom: 1px;
}}

.funnel-label .rate {{
    color: var(--text-tertiary);
    font-size: 10px;
}}

/* ── Tables ────────────────────────────────────────────────── */
table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
    margin-bottom: 20px;
}}

thead th {{
    background: transparent;
    color: var(--navy);
    font-weight: 700;
    font-size: 9px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    padding: 8px 8px;
    text-align: left;
    white-space: nowrap;
    border-top: 1.5px solid var(--navy);
    border-bottom: 1.5px solid var(--navy);
}}

tbody td {{
    padding: 7px 8px;
    border-bottom: 0.5px solid var(--border-light);
    vertical-align: middle;
    color: var(--text-primary);
}}

tbody tr:last-child td {{
    border-bottom: 1.5px solid var(--navy);
}}

.text-right {{ text-align: right; }}
.text-center {{ text-align: center; }}
.text-bold {{ font-weight: 700; }}
.text-muted {{ color: var(--text-tertiary); }}

/* ── Badges (border-only) ─────────────────────────────────── */
.badge {{
    display: inline-block;
    padding: 1px 7px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.3px;
    border: 1px solid;
}}

.badge-qualified {{ border-color: #2D7A4F; color: #2D7A4F; }}
.badge-not-qualified {{ border-color: #9B2C2C; color: #9B2C2C; }}
.badge-source {{ border-color: var(--navy); color: var(--navy); }}
.badge-yes {{ border-color: #2D7A4F; color: #2D7A4F; }}
.badge-no {{ border-color: #9B2C2C; color: #9B2C2C; }}
.badge-neutral {{ border-color: var(--border-medium); color: var(--text-secondary); }}

/* ── Bar Chart ─────────────────────────────────────────────── */
.bar-chart {{
    margin: 16px 0 24px;
}}

.bar-row {{
    display: flex;
    align-items: center;
    margin-bottom: 10px;
}}

.bar-label {{
    width: 100px;
    font-size: 11px;
    font-weight: 600;
    color: var(--text-primary);
    text-align: right;
    padding-right: 14px;
}}

.bar-track {{
    flex: 1;
    height: 24px;
    background: var(--border-light);
    overflow: hidden;
    position: relative;
}}

.bar-fill {{
    height: 100%;
    background: var(--navy);
    display: flex;
    align-items: center;
    padding-left: 10px;
    font-size: 10px;
    font-weight: 700;
    color: white;
    min-width: 32px;
}}

.bar-value {{
    width: 70px;
    text-align: right;
    font-size: 10px;
    color: var(--text-secondary);
    padding-left: 10px;
}}

/* ── Callout Box ──────────────────────────────────────────── */
.callout {{
    border-top: 2px solid var(--rule);
    padding: 14px 0 0 0;
    margin: 20px 0;
    font-size: 11px;
    line-height: 1.7;
    color: var(--text-secondary);
}}

.callout strong {{
    color: var(--navy);
}}

/* ── Footer ────────────────────────────────────────────────── */
.page-footer {{
    position: absolute;
    bottom: 15mm;
    left: 22mm;
    right: 22mm;
    display: flex;
    justify-content: space-between;
    font-size: 8px;
    color: var(--text-tertiary);
    letter-spacing: 0.5px;
    border-top: 0.5px solid var(--border-light);
    padding-top: 8px;
}}

/* ── Utilities ─────────────────────────────────────────────── */
.two-col {{
    display: flex;
    gap: 28px;
}}

.two-col > div {{
    flex: 1;
}}

.spacer-sm {{ height: 12px; }}
.spacer-md {{ height: 24px; }}

.total-row td {{
    border-top: 1.5px solid var(--navy) !important;
    border-bottom: 1.5px solid var(--navy) !important;
    font-weight: 700;
    padding-top: 9px;
    padding-bottom: 9px;
}}
</style>
</head>
<body>

<!-- ════════════════════════════════════════════════════════════ -->
<!-- COVER PAGE                                                  -->
<!-- ════════════════════════════════════════════════════════════ -->
<div class="cover">
    <div class="cover-top-rule"></div>
    <div class="confidential">Confidential</div>
    {logo_html}
    <h1>CDL-A Team Driver<br>Recruiting Report</h1>
    <div class="gold-rule"></div>
    <div class="subtitle">Performance Analysis &amp; Candidate Pipeline</div>
    <div class="subtitle">Divine Enterprises — Rocklin, California</div>
    <div class="meta">
        Campaign Period: December 2025 — March 2026<br>
        Prepared by Nikita Guzenko<br>
        March 02, 2026
    </div>
</div>

<!-- ════════════════════════════════════════════════════════════ -->
<!-- PAGE 2: EXECUTIVE SUMMARY                                   -->
<!-- ════════════════════════════════════════════════════════════ -->
<div class="page">
    <div class="page-header">
        <div class="brand">Divine Enterprises</div>
        <div class="section-label">Executive Summary</div>
    </div>

    <h3>Campaign Overview</h3>
    <p class="section-desc">Key performance metrics from the CDL-A team driver recruiting campaign across all sourcing channels.</p>

    <div class="metrics">
        <div class="metric-card">
            <div class="value">{total}</div>
            <div class="label">Total Candidates</div>
            <div class="sublabel">All sources combined</div>
        </div>
        <div class="metric-card">
            <div class="value">{contacted}</div>
            <div class="label">Contacted</div>
            <div class="sublabel">{contact_rate}% contact rate</div>
        </div>
        <div class="metric-card">
            <div class="value">{reviewed_declined}</div>
            <div class="label">Reviewed</div>
            <div class="sublabel">{review_rate}% of contacted</div>
        </div>
        <div class="metric-card">
            <div class="value">{stats["not_qualified"]}</div>
            <div class="label">Not Qualified</div>
            <div class="sublabel">Did not meet criteria</div>
        </div>
    </div>

    <h4>Recruiting Funnel</h4>

    <div class="funnel">
        <div class="funnel-step">
            <div class="funnel-bar" style="width:100%;background:var(--navy);opacity:1;">
                {total}
                <span class="funnel-label"><strong>Total Candidates</strong><span class="rate">All sources &amp; channels</span></span>
            </div>
        </div>
        <div class="funnel-step">
            <div class="funnel-bar" style="width:{max(contacted_pct, 30)}%;background:var(--navy);opacity:0.72;">
                {contacted}
                <span class="funnel-label"><strong>Contacted</strong><span class="rate">{contact_rate}% reached by phone</span></span>
            </div>
        </div>
        <div class="funnel-step">
            <div class="funnel-bar" style="width:{max(reviewed_pct, 15)}%;background:var(--navy);opacity:0.45;">
                {reviewed_declined}
                <span class="funnel-label"><strong>Reviewed by Sergiy</strong><span class="rate">{review_rate}% of contacted</span></span>
            </div>
        </div>
    </div>

    <div class="spacer-md"></div>

    <h4>Status Breakdown</h4>
    <table>
        <thead><tr><th>Status</th><th class="text-right">Count</th><th class="text-right">Share</th></tr></thead>
        <tbody>"""

    for status, count in sorted(stats["by_status"].items(), key=lambda x: -x[1]):
        pct = round(count / total * 100, 1)
        html += f"""
            <tr><td>{status}</td><td class="text-right text-bold">{count}</td><td class="text-right text-muted">{pct}%</td></tr>"""

    html += f"""
        </tbody>
    </table>

    <div class="page-footer">
        <span>Divine Enterprises — Recruiting Report</span>
        <span>Confidential — Page 2</span>
    </div>
</div>

<!-- ════════════════════════════════════════════════════════════ -->
<!-- PAGE 3: SOURCE ANALYSIS                                     -->
<!-- ════════════════════════════════════════════════════════════ -->
<div class="page">
    <div class="page-header">
        <div class="brand">Divine Enterprises</div>
        <div class="section-label">Source Analysis</div>
    </div>

    <h3>Recruiting Channels</h3>
    <p class="section-desc">Comparative analysis of candidate sourcing platforms and their performance metrics.</p>

    <h4>Volume by Source</h4>
    <div class="bar-chart">"""

    for src in sorted(stats["by_source"].keys(), key=lambda x: -stats["by_source"][x]):
        count = stats["by_source"][src]
        pct = round(count / max_source_count * 100)
        html += f"""
        <div class="bar-row">
            <div class="bar-label">{src}</div>
            <div class="bar-track">
                <div class="bar-fill" style="width:{max(pct,8)}%;">{count}</div>
            </div>
        </div>"""

    html += """
    </div>

    <h4>Detailed Comparison</h4>
    <table>
        <thead>
            <tr>
                <th>Source</th>
                <th class="text-right">Candidates</th>
                <th class="text-right">Reviewed</th>
                <th class="text-right">Not Qualified</th>
                <th class="text-right">No Answer</th>
            </tr>
        </thead>
        <tbody>"""

    for src in sorted(stats["by_source"].keys(), key=lambda x: -stats["by_source"][x]):
        cnt = stats["by_source"][src]
        rv = sum(1 for c in candidates if c["source"] == src and "initially qualified" in c["status"].lower())
        nq = sum(1 for c in candidates if c["source"] == src and "not qualified" in c["status"].lower())
        na = sum(1 for c in candidates if c["source"] == src and "no answer" in c["status"].lower())

        html += f"""
            <tr>
                <td class="text-bold">{src}</td>
                <td class="text-right">{cnt}</td>
                <td class="text-right">{rv}</td>
                <td class="text-right">{nq}</td>
                <td class="text-right text-muted">{na}</td>
            </tr>"""

    html += f"""
        </tbody>
    </table>

    <div class="callout">
        <strong>CareerPlug</strong> delivers the highest candidate volume.
        <strong>CDLjobs</strong> provides the most detailed profiles with endorsements, violations, and driver preferences.
        <strong>Bazar</strong> reaches the Russian-speaking driver community.
    </div>

    <div class="page-footer">
        <span>Divine Enterprises — Recruiting Report</span>
        <span>Confidential — Page 3</span>
    </div>
</div>

<!-- ════════════════════════════════════════════════════════════ -->
<!-- PAGE 4: REVIEWED — DECLINED                                  -->
<!-- ════════════════════════════════════════════════════════════ -->
<div class="page">
    <div class="page-header">
        <div class="brand">Divine Enterprises</div>
        <div class="section-label">Client Review</div>
    </div>

    <h3>Initially Qualified — Declined After</h3>
    <p class="section-desc">Candidates who passed initial phone screening and were forwarded to the employer for review. Each candidate was evaluated but not moved to the hiring stage for the reasons listed below.</p>

    <table>
        <thead>
            <tr>
                <th style="width:24px">#</th>
                <th>Name</th>
                <th>Phone</th>
                <th>Source</th>
                <th>Reason</th>
                <th>Feedback from Sergey</th>
            </tr>
        </thead>
        <tbody>"""

    for i, c in enumerate(reviewed_declined_list, 1):
        name = c["name"] or "\u2014"
        phone = c.get("phone", "") or "\u2014"
        source = c.get("source", "") or "\u2014"
        feedback = c.get("sergey_feedback", "") or "\u2014"
        sergey = c.get("sergey_comment", "") or "\u2014"
        html += f"""
            <tr>
                <td class="text-center text-muted">{i}</td>
                <td class="text-bold">{name}</td>
                <td>{phone}</td>
                <td><span class="badge badge-source">{source}</span></td>
                <td style="font-size:9px;color:var(--text-secondary);">{feedback}</td>
                <td style="font-size:9px;color:var(--navy);font-style:italic;">{sergey}</td>
            </tr>"""

    html += f"""
        </tbody>
    </table>

    <div class="callout">
        <strong>{len(reviewed_declined_list)} candidates</strong> were forwarded to the employer after initial qualification.
        Primary decline reasons include insufficient experience per updated insurance requirements,
        candidate indecision, and unresponsiveness during the employer review stage.
    </div>

    <div class="page-footer">
        <span>Divine Enterprises — Recruiting Report</span>
        <span>Confidential — Page 4</span>
    </div>
</div>

</body>
</html>"""

    return html


# ─── PDF Conversion ──────────────────────────────────────────────────────────

def html_to_pdf(html_content, output_path):
    """Convert HTML to PDF using headless Chrome."""
    with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
        f.write(html_content)
        html_path = f.name

    chrome_paths = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
    ]

    chrome = None
    for p in chrome_paths:
        if os.path.exists(p):
            chrome = p
            break

    if not chrome:
        print("[ERROR] No Chrome-based browser found!")
        os.unlink(html_path)
        return False

    print(f"  Using: {os.path.basename(chrome)}")
    print(f"  Converting HTML → PDF...")

    try:
        result = subprocess.run([
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            f"--print-to-pdf={output_path}",
            "--print-to-pdf-no-header",
            f"file://{html_path}",
        ], capture_output=True, text=True, timeout=30)

        os.unlink(html_path)

        if os.path.exists(output_path):
            size_kb = os.path.getsize(output_path) / 1024
            print(f"  [OK] PDF saved: {output_path} ({size_kb:.0f} KB)")
            return True
        else:
            print(f"  [ERROR] PDF not created. Chrome stderr: {result.stderr[:300]}")
            return False

    except Exception as e:
        print(f"  [ERROR] Chrome conversion failed: {e}")
        os.unlink(html_path)
        return False


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DIVINE Corporate PDF Report Generator")
    print("=" * 60)

    # Load & merge data
    print("\n[1/4] Loading data...")
    csv_data = load_csv()
    print(f"  CSV: {len(csv_data)} candidates")
    supabase_data = load_supabase()
    print(f"  Supabase: {len(supabase_data)} candidates")

    merged, overlaps = merge_candidates(csv_data, supabase_data)

    # Exclude candidates added after report cutoff (not part of this campaign period)
    exclude_names = {"hien moon", "roderick watson", "joseph alston"}
    merged = [c for c in merged if c["name"].strip().lower() not in exclude_names]

    # Remap "Hired by Another Company" → "Not Qualified" before stats
    for c in merged:
        if "hired" in c["status"].lower():
            c["status"] = "Not Qualified"

    # Apply "Initially Qualified — Declined After" overrides for candidates sent to client
    apply_reviewed_declined(merged)

    stats = compute_stats(merged)
    print(f"  Merged: {stats['total']} unique ({overlaps} overlaps removed)")

    # Load logo
    print("\n[2/4] Loading logo...")
    logo_b64 = load_logo_base64()

    # Build HTML
    print("\n[3/4] Building HTML report...")
    html = build_html(merged, stats, logo_b64)
    print(f"  HTML size: {len(html):,} bytes")

    # Convert to PDF
    print("\n[4/4] Converting to PDF...")
    success = html_to_pdf(html, OUTPUT_PDF)

    if success:
        print(f"\n{'=' * 60}")
        print(f"DONE! PDF report: {OUTPUT_PDF}")
        print(f"{'=' * 60}")
    else:
        # Save HTML as fallback
        fallback = OUTPUT_PDF.replace(".pdf", ".html")
        with open(fallback, "w", encoding="utf-8") as f:
            f.write(html)
        print(f"\n[FALLBACK] HTML saved: {fallback}")
        print("Open it in Chrome and use Print → Save as PDF")


if __name__ == "__main__":
    main()
