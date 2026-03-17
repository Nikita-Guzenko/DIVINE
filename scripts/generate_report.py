"""
DIVINE Report Generator — Merge CSV + Supabase data, generate images, build Obsidian report.

Usage:
    python generate_report.py                # Full pipeline: merge + images + report
    python generate_report.py --merge-only   # Just merge data and print stats
    python generate_report.py --no-images    # Skip image generation
"""

import csv
import json
import os
import re
import sys
import time
import httpx
from datetime import datetime
from pathlib import Path

from supabase import create_client

# ─── Config ──────────────────────────────────────────────────────────────────

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

FAL_API_KEY = os.environ.get("FAL_KEY", "")

CSV_PATH = os.path.expanduser(
    "~/Downloads/divine ent driver tracking - Sheet1.csv"
)

OBSIDIAN_VAULT = os.path.expanduser("~/Documents/Obsidian Vault")
REPORT_DIR = os.path.join(OBSIDIAN_VAULT, "DIVINE Report")
ASSETS_DIR = os.path.join(REPORT_DIR, "assets")

# Financial data (costs removed per client request)
PLATFORM_COSTS = {}

# ─── Phone Normalization ─────────────────────────────────────────────────────

def normalize_phone(phone: str) -> str:
    if not phone:
        return ""
    digits = re.sub(r"[^\d]", "", phone)
    if digits.startswith("1") and len(digits) == 11:
        digits = digits[1:]
    return digits


# ─── CSV Status Mapping ─────────────────────────────────────────────────────

def map_csv_status(status: str) -> str:
    if not status:
        return "Unknown"
    s = status.strip().lower()
    if "potential" in s:
        return "Qualified"
    if "not qualified" in s:
        return "Not Qualified"
    if "no answer" in s:
        return "No Answer"
    if s == "hired" or "hired by" in s:
        return "Not Qualified"
    return status.strip()


def map_csv_source(source: str) -> str:
    if not source:
        return "Unknown"
    s = source.strip().lower()
    if "carrerplug" in s or "careerplug" in s:
        return "CareerPlug"
    if "cdljobs" in s or "cdl" in s:
        return "CDLjobs"
    if "bazar" in s:
        return "Bazar"
    if "intelliapp" in s or "submitted" in s:
        return "CareerPlug"
    if "interested" in s or "replied" in s:
        return "CareerPlug"
    if "already has" in s:
        return "CareerPlug"
    if "wants local" in s:
        return "CareerPlug"
    return source.strip()


def map_supabase_source(source: str) -> str:
    if not source:
        return "Unknown"
    s = source.strip().lower()
    if "careerplug" in s:
        return "CareerPlug"
    if "cdljobs" in s:
        return "CDLjobs"
    if "bazar" in s:
        return "Bazar"
    if "manual" in s:
        return "Manual"
    return source.strip()


# ─── Data Loading ────────────────────────────────────────────────────────────

def load_csv():
    candidates = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Name", "").strip()
            parts = name.split(None, 1)
            first_name = parts[0] if parts else ""
            last_name = parts[1] if len(parts) > 1 else ""

            team_ready = row.get("Ready to work in Team?", "").strip()
            if team_ready.lower() == "yes":
                team_ready = True
            elif team_ready.lower() == "no":
                team_ready = False
            else:
                team_ready = None

            endorsements = []
            if row.get("Doubles", "").strip().lower() == "yes":
                endorsements.append("Doubles/Triples")
            if row.get("Tanker", "").strip().lower() == "yes":
                endorsements.append("Tanker")
            if row.get("Hazmat", "").strip().lower() == "yes":
                endorsements.append("Hazmat")

            reason = row.get("Reason", "").strip()
            notes_raw = row.get("Notes", "").strip()
            # Combine reason and notes for richer context
            combined_notes = f"{reason}. {notes_raw}".strip(". ") if reason and notes_raw else (reason or notes_raw)

            candidates.append({
                "name": name,
                "first_name": first_name,
                "last_name": last_name,
                "phone": row.get("Phone", "").strip(),
                "phone_normalized": normalize_phone(row.get("Phone", "")),
                "email": row.get("Email", "").strip(),
                "source": map_csv_source(row.get("Source", "")),
                "status": map_csv_status(row.get("Status", "")),
                "notes": combined_notes,
                "experience": row.get("Experience", "").strip(),
                "team_ready": team_ready,
                "endorsements": endorsements,
                "origin": "pre-dashboard",
                "sergey_date": row.get("Sergiy date", "").strip(),
                "sergey_feedback": row.get("Sergiy feedback", "").strip(),
            })
    return candidates


def load_supabase():
    sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    result = sb.table("candidates").select("*").execute()
    candidates = []
    for c in result.data:
        name = f"{c.get('first_name', '')} {c.get('last_name', '')}".strip()
        endorsements = c.get("endorsements") or []
        experience = c.get("experience", "") or ""

        candidates.append({
            "name": name,
            "first_name": c.get("first_name", ""),
            "last_name": c.get("last_name", ""),
            "phone": c.get("phone", ""),
            "phone_normalized": normalize_phone(c.get("phone", "")),
            "email": c.get("email", ""),
            "source": map_supabase_source(c.get("source", "")),
            "status": c.get("status", ""),
            "notes": c.get("notes", ""),
            "experience": experience,
            "team_ready": c.get("wants_team"),
            "endorsements": endorsements,
            "origin": "dashboard",
            "sergey_date": "",
            "sergey_feedback": c.get("sergey_comment", "") or "",
            "supabase_id": c.get("id"),
            "created_at": c.get("created_at", ""),
        })
    return candidates


# ─── Merge & Deduplicate ────────────────────────────────────────────────────

def merge_candidates(csv_data, supabase_data):
    """Merge CSV + Supabase, dedup by phone. Dashboard data takes priority."""
    seen_phones = {}
    merged = []
    overlaps = 0

    # Dashboard data first (higher priority)
    for c in supabase_data:
        phone = c["phone_normalized"]
        if phone and phone in seen_phones:
            continue
        if phone:
            seen_phones[phone] = len(merged)
        merged.append(c)

    # Then CSV data
    for c in csv_data:
        phone = c["phone_normalized"]
        if phone and phone in seen_phones:
            overlaps += 1
            # Enrich dashboard record with CSV notes if empty
            idx = seen_phones[phone]
            if not merged[idx].get("notes") and c.get("notes"):
                merged[idx]["notes"] = c["notes"]
            if not merged[idx].get("sergey_date") and c.get("sergey_date"):
                merged[idx]["sergey_date"] = c["sergey_date"]
            if not merged[idx].get("sergey_feedback") and c.get("sergey_feedback"):
                merged[idx]["sergey_feedback"] = c["sergey_feedback"]
            continue
        if phone:
            seen_phones[phone] = len(merged)
        merged.append(c)

    return merged, overlaps


# ─── Statistics ──────────────────────────────────────────────────────────────

def compute_stats(candidates):
    stats = {
        "total": len(candidates),
        "by_source": {},
        "by_status": {},
        "by_origin": {"pre-dashboard": 0, "dashboard": 0},
        "team_ready": 0,
        "with_experience": 0,
        "qualified": 0,
        "not_qualified": 0,
        "no_answer": 0,
        "hired": 0,
    }

    for c in candidates:
        src = c["source"]
        stats["by_source"][src] = stats["by_source"].get(src, 0) + 1

        status = c["status"]
        stats["by_status"][status] = stats["by_status"].get(status, 0) + 1

        origin = c.get("origin", "unknown")
        stats["by_origin"][origin] = stats["by_origin"].get(origin, 0) + 1

        if c.get("team_ready") is True:
            stats["team_ready"] += 1
        if c.get("experience"):
            stats["with_experience"] += 1

        sl = status.lower()
        if "qualified" in sl and "not" not in sl:
            stats["qualified"] += 1
        elif "not qualified" in sl:
            stats["not_qualified"] += 1
        elif "no answer" in sl:
            stats["no_answer"] += 1
        elif "hired" in sl:
            stats["hired"] += 1

    # Financial stats
    stats["total_spend"] = sum(PLATFORM_COSTS.values())
    stats["cost_per_lead"] = {}
    stats["cost_per_qualified"] = {}
    for src, cost in PLATFORM_COSTS.items():
        count = stats["by_source"].get(src, 0)
        qualified_count = sum(
            1 for c in candidates
            if c["source"] == src and "qualified" in c["status"].lower() and "not" not in c["status"].lower()
        )
        stats["cost_per_lead"][src] = round(cost / count, 2) if count > 0 else 0
        stats["cost_per_qualified"][src] = round(cost / qualified_count, 2) if qualified_count > 0 else 0

    return stats


# ─── Image Generation ────────────────────────────────────────────────────────

IMAGE_PROMPTS = [
    {
        "name": "hero-banner.png",
        "prompt": (
            "Professional corporate banner for a trucking recruitment report. "
            "A fleet of modern semi-trucks driving on an American highway at golden hour. "
            "Clean, corporate aesthetic with blue sky. No text, no logos. "
            "Photorealistic, cinematic lighting, wide angle."
        ),
        "aspect_ratio": "16:9",
    },
    {
        "name": "recruiting-funnel.png",
        "prompt": (
            "Abstract business infographic concept art: a glowing funnel shape made of light particles, "
            "transitioning from wide at top (many small human silhouettes) to narrow at bottom (few golden figures). "
            "Dark professional background, blue and gold color scheme. Modern minimalist corporate style."
        ),
        "aspect_ratio": "4:3",
    },
    {
        "name": "source-comparison.png",
        "prompt": (
            "Corporate illustration of multiple digital platforms and job boards connected by glowing data streams. "
            "Abstract representation of online recruiting channels — computer screens, mobile devices, networking nodes. "
            "Blue and white color palette, clean modern design, dark background."
        ),
        "aspect_ratio": "4:3",
    },
    {
        "name": "financial-roi.png",
        "prompt": (
            "Corporate finance concept: golden coins, upward arrow charts, and bar graphs floating in a clean "
            "blue environment. Professional business ROI visualization. Abstract, no specific numbers or text. "
            "Clean, modern, minimalist corporate style."
        ),
        "aspect_ratio": "4:3",
    },
    {
        "name": "team-drivers.png",
        "prompt": (
            "Two professional CDL truck drivers standing confidently next to a modern semi-truck. "
            "American highway backdrop, clear sky. They are wearing professional uniforms, "
            "looking determined and professional. Team driving concept. Photorealistic, warm lighting."
        ),
        "aspect_ratio": "16:9",
    },
]


def generate_images():
    os.makedirs(ASSETS_DIR, exist_ok=True)
    generated = []

    for img in IMAGE_PROMPTS:
        filepath = os.path.join(ASSETS_DIR, img["name"])
        if os.path.exists(filepath):
            print(f"  [SKIP] {img['name']} already exists")
            generated.append(filepath)
            continue

        print(f"  [GEN] {img['name']}...")
        try:
            resp = httpx.post(
                "https://fal.run/fal-ai/nano-banana-2",
                headers={
                    "Authorization": f"Key {FAL_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "prompt": img["prompt"],
                    "num_images": 1,
                    "aspect_ratio": img["aspect_ratio"],
                    "output_format": "png",
                    "resolution": "1K",
                },
                timeout=120,
            )
            resp.raise_for_status()
            data = resp.json()

            if data.get("images"):
                image_url = data["images"][0]["url"]
                img_resp = httpx.get(image_url, timeout=60)
                img_resp.raise_for_status()
                with open(filepath, "wb") as f:
                    f.write(img_resp.content)
                print(f"  [OK] {img['name']} saved")
                generated.append(filepath)
            else:
                print(f"  [WARN] No images returned for {img['name']}")
        except Exception as e:
            print(f"  [ERROR] {img['name']}: {e}")

        time.sleep(1)  # Rate limiting

    return generated


# ─── Obsidian Report Builder ────────────────────────────────────────────────

def build_report(candidates, stats):
    os.makedirs(REPORT_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

    # Index page
    write_index(stats)
    write_executive_summary(candidates, stats)
    write_source_analysis(candidates, stats)
    write_candidate_pipeline(candidates, stats)
    write_financial_report(candidates, stats)
    write_recommendations(candidates, stats)

    print(f"\n[OK] Report written to {REPORT_DIR}")


def write_index(stats):
    content = f"""---
title: DIVINE Enterprises — CDL Driver Recruiting Report
date: {datetime.now().strftime('%Y-%m-%d')}
tags: [divine, recruiting, report, CDL]
---

![[hero-banner.png]]

# DIVINE Enterprises — CDL Driver Recruiting Report

> [!info] Report Overview
> Comprehensive recruiting performance report for Divine Enterprises CDL-A Team Driver campaign.
> Generated on **{datetime.now().strftime('%B %d, %Y')}**

---

## Key Metrics at a Glance

| Metric | Value |
|--------|-------|
| **Total Candidates** | {stats['total']} |
| **Qualified Candidates** | {stats['qualified']} |
| **Not Qualified** | {stats['not_qualified']} |
| **No Answer** | {stats['no_answer']} |
| **Team-Ready Drivers** | {stats['team_ready']} |
| **Total Investment** | ${stats['total_spend']:,} |

---

## Report Sections

1. [[1 - Executive Summary]]
2. [[2 - Source Analysis]]
3. [[3 - Candidate Pipeline]]
4. [[4 - Financial Report]]
5. [[5 - Recommendations]]

---

> [!tip] Navigation
> Click any section above to dive into the details. Each section contains data-driven insights and visualizations.
"""
    _write(os.path.join(REPORT_DIR, "index.md"), content)


def write_executive_summary(candidates, stats):
    # Calculate funnel numbers
    total = stats["total"]
    contacted = total - stats["no_answer"]
    qualified = stats["qualified"]
    hired = stats["hired"]

    contact_rate = round(contacted / total * 100, 1) if total else 0
    qualify_rate = round(qualified / contacted * 100, 1) if contacted else 0

    content = f"""---
title: Executive Summary
parent: "[[index]]"
---

![[recruiting-funnel.png]]

# Executive Summary

> [!info] Campaign Period
> December 2025 — March 2026

## Campaign Overview

Divine Enterprises launched a CDL-A Team Driver recruitment campaign targeting qualified team drivers across multiple platforms. The campaign utilized automated scraping, manual outreach, and a custom-built analytics dashboard to track and manage candidates.

---

## Recruiting Funnel

```mermaid
graph TD
    A["Total Candidates\\n{total}"] --> B["Contacted / Responded\\n{contacted}"]
    B --> C["Qualified\\n{qualified}"]
    C --> D["Hired / In Process\\n{hired}"]

    style A fill:#3b82f6,color:#fff
    style B fill:#6366f1,color:#fff
    style C fill:#8b5cf6,color:#fff
    style D fill:#10b981,color:#fff
```

| Funnel Stage | Count | Rate |
|-------------|-------|------|
| Total Candidates | {total} | 100% |
| Contacted / Responded | {contacted} | {contact_rate}% |
| Qualified | {qualified} | {qualify_rate}% of contacted |
| Hired / In Process | {hired} | — |

---

## Status Breakdown

| Status | Count | % of Total |
|--------|-------|-----------|
"""

    for status, count in sorted(stats["by_status"].items(), key=lambda x: -x[1]):
        pct = round(count / total * 100, 1)
        content += f"| {status} | {count} | {pct}% |\n"

    content += f"""
---

## Team Driver Readiness

| Category | Count |
|----------|-------|
| Ready for Team | {stats['team_ready']} |
| Solo Only / Unknown | {total - stats['team_ready']} |

> [!note] Key Takeaway
> Out of {contacted} candidates who were reached, **{qualified}** ({qualify_rate}%) met the qualifications for team driving positions at Divine Enterprises.

---

← [[index|Back to Report Index]]
"""
    _write(os.path.join(REPORT_DIR, "1 - Executive Summary.md"), content)


def write_source_analysis(candidates, stats):
    content = f"""---
title: Source Analysis
parent: "[[index]]"
---

![[source-comparison.png]]

# Source Analysis

> [!info] Platform Comparison
> Analysis of all recruiting channels used during the campaign.

---

## Candidates by Source

| Source | Total | Qualified | Not Qualified | No Answer | Cost |
|--------|-------|-----------|---------------|-----------|------|
"""

    for src in sorted(stats["by_source"].keys(), key=lambda x: -stats["by_source"][x]):
        total = stats["by_source"][src]
        q = sum(1 for c in candidates if c["source"] == src and "qualified" in c["status"].lower() and "not" not in c["status"].lower())
        nq = sum(1 for c in candidates if c["source"] == src and "not qualified" in c["status"].lower())
        na = sum(1 for c in candidates if c["source"] == src and "no answer" in c["status"].lower())
        cost = PLATFORM_COSTS.get(src, 0)
        cost_str = f"${cost:,}" if cost > 0 else "Free"
        content += f"| {src} | {total} | {q} | {nq} | {na} | {cost_str} |\n"

    content += """
---

## Cost Efficiency

| Source | Cost | Leads | Cost/Lead | Qualified | Cost/Qualified |
|--------|------|-------|-----------|-----------|----------------|
"""

    for src, cost in sorted(PLATFORM_COSTS.items(), key=lambda x: -x[1]):
        total = stats["by_source"].get(src, 0)
        cpl = stats["cost_per_lead"].get(src, 0)
        q = sum(1 for c in candidates if c["source"] == src and "qualified" in c["status"].lower() and "not" not in c["status"].lower())
        cpq = stats["cost_per_qualified"].get(src, 0)
        cost_str = f"${cost:,}" if cost > 0 else "Free"
        cpl_str = f"${cpl:.2f}" if cpl > 0 else "Free"
        cpq_str = f"${cpq:.2f}" if cpq > 0 else "Free"
        content += f"| {src} | {cost_str} | {total} | {cpl_str} | {q} | {cpq_str} |\n"

    content += """
---

## Source Distribution

```mermaid
pie title Candidates by Source
"""
    for src, count in sorted(stats["by_source"].items(), key=lambda x: -x[1]):
        content += f'    "{src}" : {count}\n'

    content += """```

> [!tip] Key Insight
> CareerPlug provides the highest volume of candidates at zero cost, making it the most cost-effective channel. CDLjobs delivers pre-qualified candidates with detailed profiles. Bazar is the most expensive per lead but provides Russian-speaking candidates with direct communication.

---

← [[index|Back to Report Index]]
"""
    _write(os.path.join(REPORT_DIR, "2 - Source Analysis.md"), content)


def write_candidate_pipeline(candidates, stats):
    content = f"""---
title: Candidate Pipeline
parent: "[[index]]"
---

# Candidate Pipeline — All Candidates

> [!info] Total: {stats['total']} unique candidates
> Data merged from pre-dashboard manual tracking and automated dashboard system.

---

"""

    # Group by status
    groups = {}
    for c in candidates:
        status = c["status"]
        if status not in groups:
            groups[status] = []
        groups[status].append(c)

    # Order: Qualified first, then others
    status_order = ["Qualified", "Qualified / Awaiting Feedback", "Hired", "Hired by Another Company",
                    "Not Qualified", "No Answer", "New", "Unknown"]

    for status in status_order:
        if status not in groups:
            continue
        group = groups[status]
        content += f"## {status} ({len(group)})\n\n"
        content += "| # | Name | Phone | Email | Source | Experience | Team | Notes |\n"
        content += "|---|------|-------|-------|--------|------------|------|-------|\n"

        for i, c in enumerate(group, 1):
            name = c["name"] or "—"
            phone = c.get("phone", "") or "—"
            email = c.get("email", "") or "—"
            source = c.get("source", "") or "—"
            exp = c.get("experience", "") or "—"
            team = "Yes" if c.get("team_ready") is True else ("No" if c.get("team_ready") is False else "—")
            notes = (c.get("notes", "") or "")[:60]
            if notes and len(c.get("notes", "")) > 60:
                notes += "..."
            # Escape pipes in notes
            notes = notes.replace("|", "\\|")
            content += f"| {i} | {name} | {phone} | {email} | {source} | {exp} | {team} | {notes} |\n"

        content += "\n---\n\n"

    # Handle any remaining statuses
    for status, group in groups.items():
        if status in status_order:
            continue
        content += f"## {status} ({len(group)})\n\n"
        content += "| # | Name | Phone | Source | Status | Notes |\n"
        content += "|---|------|-------|--------|--------|-------|\n"
        for i, c in enumerate(group, 1):
            name = c["name"] or "—"
            phone = c.get("phone", "") or "—"
            source = c.get("source", "") or "—"
            notes = (c.get("notes", "") or "")[:60].replace("|", "\\|")
            content += f"| {i} | {name} | {phone} | {source} | {status} | {notes} |\n"
        content += "\n---\n\n"

    content += "\n← [[index|Back to Report Index]]\n"
    _write(os.path.join(REPORT_DIR, "3 - Candidate Pipeline.md"), content)


def write_financial_report(candidates, stats):
    total_spend = stats["total_spend"]
    total_candidates = stats["total"]
    total_qualified = stats["qualified"]
    avg_cpl = round(total_spend / total_candidates, 2) if total_candidates else 0
    avg_cpq = round(total_spend / total_qualified, 2) if total_qualified else 0

    content = f"""---
title: Financial Report
parent: "[[index]]"
---

![[financial-roi.png]]

# Financial Report

> [!info] Campaign Investment Analysis
> Total recruiting spend across all platforms: **${total_spend:,}**

---

## Investment Summary

| Metric | Value |
|--------|-------|
| **Total Spend** | ${total_spend:,} |
| **Total Candidates** | {total_candidates} |
| **Qualified Candidates** | {total_qualified} |
| **Avg. Cost per Lead** | ${avg_cpl:.2f} |
| **Avg. Cost per Qualified** | ${avg_cpq:.2f} |

---

## Platform Breakdown

| Platform | Investment | Leads | Cost/Lead | Qualified | Cost/Qualified |
|----------|-----------|-------|-----------|-----------|----------------|
"""

    for src, cost in sorted(PLATFORM_COSTS.items(), key=lambda x: -x[1]):
        total = stats["by_source"].get(src, 0)
        cpl = stats["cost_per_lead"].get(src, 0)
        q = sum(1 for c in candidates if c["source"] == src and "qualified" in c["status"].lower() and "not" not in c["status"].lower())
        cpq = stats["cost_per_qualified"].get(src, 0)
        cost_str = f"${cost:,}"
        cpl_str = f"${cpl:.2f}" if cost > 0 else "Free"
        cpq_str = f"${cpq:.2f}" if cost > 0 else "Free"
        content += f"| {src} | {cost_str} | {total} | {cpl_str} | {q} | {cpq_str} |\n"

    content += f"""
---

## Investment Distribution

```mermaid
pie title Spend by Platform
    "Bazar ($1,800)" : 1800
    "CDLjobs ($1,000)" : 1000
    "CareerPlug ($0)" : 0
```

---

## ROI Analysis

> [!warning] Cost Efficiency Ranking
> 1. **CareerPlug** — Free platform generating the highest candidate volume
> 2. **CDLjobs** — $1,000 investment providing detailed driver profiles and pre-screening
> 3. **Bazar** — $1,800 for targeted Russian-speaking community outreach

### Key Financial Insights

- **Total campaign cost**: ${total_spend:,} across {len(PLATFORM_COSTS)} platforms
- **Average cost per candidate**: ${avg_cpl:.2f}
- **Average cost per qualified candidate**: ${avg_cpq:.2f}
- **CareerPlug** delivers the best volume-to-cost ratio (free)
- **CDLjobs** provides the most comprehensive candidate data for screening

---

← [[index|Back to Report Index]]
"""
    _write(os.path.join(REPORT_DIR, "4 - Financial Report.md"), content)


def write_recommendations(candidates, stats):
    content = f"""---
title: Recommendations
parent: "[[index]]"
---

![[team-drivers.png]]

# Recommendations & Next Steps

> [!tip] Data-Driven Recommendations
> Based on analysis of {stats['total']} candidates across {len(stats['by_source'])} sources.

---

## Platform Recommendations

### 1. CareerPlug — Continue & Expand
- **Verdict**: Best ROI — high volume at zero cost
- Produces the largest candidate pipeline
- Automated scraping already in place (every 4 hours)
- **Action**: Continue using as primary sourcing channel

### 2. CDLjobs — Evaluate ROI
- **Investment**: $1,000
- Provides detailed candidate profiles with endorsements, violations, and preferences
- Higher data quality per candidate than CareerPlug
- **Action**: Assess whether the depth of data justifies the cost vs. CareerPlug volume

### 3. Bazar — Targeted Use Only
- **Investment**: $1,800 (highest per-lead cost)
- Small but targeted candidate pool (Russian-speaking community)
- Direct phone communication possible
- **Action**: Use only for targeted ethnic community outreach when other channels underperform

---

## Pipeline Health

| Indicator | Status |
|-----------|--------|
| Candidate Volume | {"Strong" if stats['total'] > 150 else "Moderate"} ({stats['total']} total) |
| Qualification Rate | {"Good" if stats['qualified'] / max(stats['total'] - stats['no_answer'], 1) > 0.15 else "Needs Improvement"} |
| Response Rate | {"Good" if (stats['total'] - stats['no_answer']) / max(stats['total'], 1) > 0.4 else "Below Average"} |
| Team-Ready Pool | {stats['team_ready']} drivers available |

---

## Recommended Next Steps

1. **Follow up on No Answer candidates** — {stats['no_answer']} candidates never responded; consider a second call or SMS campaign
2. **Re-engage Qualified candidates** — {stats['qualified']} qualified candidates should be actively pursued
3. **Optimize CareerPlug pipeline** — Already automated; ensure all new applicants are contacted within 24 hours
4. **Review CDLjobs ROI quarterly** — Track cost per hire to determine if continued investment is warranted
5. **Build referral program** — Leverage hired drivers to refer team partners (referral bonus already available)

---

> [!note] Report Generated
> This report was generated on {datetime.now().strftime('%B %d, %Y')} using data from the DIVINE recruiting dashboard and manual tracking records.

← [[index|Back to Report Index]]
"""
    _write(os.path.join(REPORT_DIR, "5 - Recommendations.md"), content)


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [WROTE] {os.path.basename(path)}")


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="DIVINE Report Generator")
    parser.add_argument("--merge-only", action="store_true", help="Only merge data, don't generate report")
    parser.add_argument("--no-images", action="store_true", help="Skip image generation")
    args = parser.parse_args()

    print("=" * 60)
    print("DIVINE Report Generator")
    print("=" * 60)

    # Step 1: Load data
    print("\n[1/3] Loading data...")
    print(f"  CSV: {CSV_PATH}")
    csv_data = load_csv()
    print(f"  Loaded {len(csv_data)} candidates from CSV")

    print(f"  Supabase: {SUPABASE_URL}")
    supabase_data = load_supabase()
    print(f"  Loaded {len(supabase_data)} candidates from Supabase")

    # Step 2: Merge
    print("\n[2/3] Merging & deduplicating...")
    merged, overlaps = merge_candidates(csv_data, supabase_data)
    stats = compute_stats(merged)

    print(f"\n  === MERGE STATS ===")
    print(f"  CSV candidates:      {len(csv_data)}")
    print(f"  Supabase candidates: {len(supabase_data)}")
    print(f"  Overlaps (deduped):  {overlaps}")
    print(f"  Unique candidates:   {stats['total']}")
    print(f"\n  By source:")
    for src, count in sorted(stats["by_source"].items(), key=lambda x: -x[1]):
        cost = PLATFORM_COSTS.get(src, 0)
        cost_str = f" (${cost:,})" if cost > 0 else " (Free)"
        print(f"    {src}: {count}{cost_str}")
    print(f"\n  By status:")
    for status, count in sorted(stats["by_status"].items(), key=lambda x: -x[1]):
        print(f"    {status}: {count}")
    print(f"\n  Team-ready: {stats['team_ready']}")
    print(f"  Total spend: ${stats['total_spend']:,}")

    if args.merge_only:
        return merged, stats

    # Step 3: Generate images
    if not args.no_images:
        print("\n[3/3] Generating images...")
        generate_images()
    else:
        print("\n[3/3] Skipping image generation (--no-images)")
        os.makedirs(ASSETS_DIR, exist_ok=True)

    # Step 4: Build report
    print("\nBuilding Obsidian report...")
    build_report(merged, stats)

    print(f"\n{'=' * 60}")
    print(f"DONE! Report at: {REPORT_DIR}")
    print(f"Open Obsidian and navigate to 'DIVINE Report/index'")
    print(f"{'=' * 60}")

    return merged, stats


if __name__ == "__main__":
    main()
