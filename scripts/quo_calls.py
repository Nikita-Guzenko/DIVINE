#!/usr/bin/env python3
"""
Quo (OpenPhone) API integration for Divine Recruiting.

Fetches call recordings, AI transcriptions, and summaries
for all calls made through the Quo phone system.
"""

import os
import json
import time
import requests
from datetime import datetime, timedelta, timezone

import config


def _headers():
    return {"Authorization": config.QUO_API_KEY}


def _get(endpoint, params=None):
    """Make GET request to Quo API with rate limiting."""
    url = f"{config.QUO_API_BASE}/{endpoint}"
    resp = requests.get(url, headers=_headers(), params=params or {})
    resp.raise_for_status()
    return resp.json()


# ─── Core API Calls ─────────────────────────────────────────────────────────


def list_conversations(max_results=50):
    """List all conversations (each conversation = unique phone number contact)."""
    params = {
        "phoneNumberId": config.QUO_PHONE_NUMBER_ID,
        "maxResults": max_results,
    }
    data = _get("conversations", params)
    return data.get("data", [])


def list_calls(participant, max_results=50):
    """List calls with a specific participant phone number."""
    params = {
        "phoneNumberId": config.QUO_PHONE_NUMBER_ID,
        "participants[]": participant,
        "maxResults": max_results,
    }
    data = _get("calls", params)
    return data.get("data", [])


def get_call(call_id):
    """Get a single call by ID."""
    data = _get(f"calls/{call_id}")
    return data.get("data", {})


def get_recording(call_id):
    """Get call recordings. Returns list of recording objects."""
    data = _get(f"call-recordings/{call_id}")
    return data.get("data", [])


def get_transcript(call_id):
    """Get call transcript. Returns transcript object or None."""
    try:
        data = _get(f"call-transcripts/{call_id}")
        return data.get("data")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise


def get_summary(call_id):
    """Get call AI summary. Returns summary object or None."""
    try:
        data = _get(f"call-summaries/{call_id}")
        return data.get("data")
    except requests.HTTPError as e:
        if e.response.status_code == 404:
            return None
        raise


def download_recording(url, call_id, index=0):
    """Download a recording MP3 file to local storage."""
    os.makedirs(config.CALLS_RECORDINGS_DIR, exist_ok=True)
    filepath = os.path.join(config.CALLS_RECORDINGS_DIR, f"{call_id}_{index}.mp3")

    if os.path.exists(filepath):
        return filepath

    resp = requests.get(url, stream=True)
    resp.raise_for_status()
    with open(filepath, "wb") as f:
        for chunk in resp.iter_content(8192):
            f.write(chunk)

    return filepath


# ─── High-Level Functions ────────────────────────────────────────────────────


def fetch_all_calls(days=30):
    """
    Fetch all calls from the last N days with their recordings,
    transcripts, and summaries.
    """
    conversations = list_conversations(max_results=100)
    print(f"Found {len(conversations)} conversations")

    all_calls = []
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    for conv in conversations:
        participants = conv.get("participants", [])
        if not participants:
            continue

        participant = participants[0]
        calls = list_calls(participant)

        for call in calls:
            created = datetime.fromisoformat(call["createdAt"].replace("Z", "+00:00"))
            if created < cutoff:
                continue
            all_calls.append(call)
            time.sleep(0.15)  # respect rate limit

    # Sort by date, newest first
    all_calls.sort(key=lambda c: c["createdAt"], reverse=True)
    return all_calls


def enrich_call(call):
    """Add recording, transcript, and summary to a call object."""
    call_id = call["id"]
    result = {**call}

    # Recordings
    recordings = get_recording(call_id)
    result["recordings"] = recordings
    if recordings:
        local_files = []
        for i, rec in enumerate(recordings):
            if rec.get("url"):
                path = download_recording(rec["url"], call_id, i)
                local_files.append(path)
        result["local_recordings"] = local_files
    time.sleep(0.15)

    # Transcript
    transcript = get_transcript(call_id)
    result["transcript"] = transcript
    time.sleep(0.15)

    # Summary
    summary = get_summary(call_id)
    result["summary"] = summary

    return result


def save_call_data(calls):
    """Save enriched call data to JSON."""
    os.makedirs(config.CALLS_DIR, exist_ok=True)
    filepath = os.path.join(config.CALLS_DIR, "calls.json")

    # Merge with existing data
    existing = {}
    if os.path.exists(filepath):
        with open(filepath) as f:
            for c in json.load(f):
                existing[c["id"]] = c

    for c in calls:
        existing[c["id"]] = c

    merged = sorted(existing.values(), key=lambda c: c["createdAt"], reverse=True)
    with open(filepath, "w") as f:
        json.dump(merged, f, indent=2, default=str)

    return filepath


# ─── Display ─────────────────────────────────────────────────────────────────


def format_duration(seconds):
    """Format seconds to mm:ss."""
    if not seconds:
        return "0:00"
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def format_phone(number):
    """Format E.164 number to readable format."""
    if not number or len(number) != 12 or not number.startswith("+1"):
        return number or "Unknown"
    n = number[2:]
    return f"({n[:3]}) {n[3:6]}-{n[6:]}"


def display_calls(calls):
    """Print calls table to console."""
    print(f"\n{'='*90}")
    print(f"  CALL LOG — {len(calls)} calls")
    print(f"{'='*90}")
    print(f"  {'Date':12} {'Time':7} {'Dir':4} {'Participant':17} {'Dur':6} {'Status':12} {'Rec':4} {'AI':4}")
    print(f"  {'-'*12} {'-'*7} {'-'*4} {'-'*17} {'-'*6} {'-'*12} {'-'*4} {'-'*4}")

    for c in calls:
        dt = datetime.fromisoformat(c["createdAt"].replace("Z", "+00:00"))
        date_str = dt.strftime("%b %d, %Y")
        time_str = dt.strftime("%H:%M")
        direction = "IN" if c["direction"] == "incoming" else "OUT"

        # Find the other participant (not our number)
        other = "Unknown"
        for p in c.get("participants", []):
            if p != f"+1{config.QUO_PHONE_NUMBER_ID.replace('PN', '')}":
                if p != "+19162490761":
                    other = format_phone(p)
                    break

        dur = format_duration(c.get("duration", 0))
        status = c.get("status", "unknown")

        has_rec = "Yes" if c.get("recordings") else "—"
        has_ai = "Yes" if c.get("transcript") or c.get("aiHandled") else "—"

        print(f"  {date_str:12} {time_str:7} {direction:4} {other:17} {dur:>6} {status:12} {has_rec:4} {has_ai:4}")

    print(f"{'='*90}")


def display_call_detail(call):
    """Print detailed call info including transcript."""
    dt = datetime.fromisoformat(call["createdAt"].replace("Z", "+00:00"))
    direction = "Incoming" if call["direction"] == "incoming" else "Outgoing"

    other = "Unknown"
    for p in call.get("participants", []):
        if p != "+19162490761":
            other = format_phone(p)
            break

    print(f"\n{'='*60}")
    print(f"  CALL DETAIL — {call['id']}")
    print(f"{'='*60}")
    print(f"  Date:        {dt.strftime('%b %d, %Y at %H:%M')}")
    print(f"  Direction:   {direction}")
    print(f"  Participant: {other}")
    print(f"  Duration:    {format_duration(call.get('duration', 0))}")
    print(f"  Status:      {call.get('status', 'unknown')}")
    print(f"  AI Handled:  {'Yes' if call.get('aiHandled') else 'No'}")

    # Recordings
    recs = call.get("recordings", [])
    if recs:
        print(f"\n  RECORDINGS ({len(recs)}):")
        for r in recs:
            print(f"    - {r.get('url', 'N/A')}")
        local = call.get("local_recordings", [])
        if local:
            for lf in local:
                print(f"    - Local: {lf}")
    else:
        print(f"\n  RECORDINGS: None")

    # Transcript
    transcript = call.get("transcript")
    if transcript and transcript.get("dialogue"):
        print(f"\n  TRANSCRIPT:")
        print(f"  {'-'*50}")
        for line in transcript["dialogue"]:
            speaker = format_phone(line.get("identifier", ""))
            if line.get("userId"):
                speaker = "You"
            elif line.get("identifier") == "+19162490761":
                speaker = "AI Agent"
            content = line.get("content", "")
            print(f"    [{speaker}]: {content}")
        print(f"  {'-'*50}")
    else:
        print(f"\n  TRANSCRIPT: Not available")

    # Summary
    summary = call.get("summary")
    if summary and summary.get("summary"):
        print(f"\n  AI SUMMARY:")
        for item in summary["summary"]:
            print(f"    - {item}")
        if summary.get("nextSteps"):
            print(f"\n  NEXT STEPS:")
            print(f"    {summary['nextSteps']}")
    else:
        print(f"\n  AI SUMMARY: Not available")

    print(f"{'='*60}")


# ─── CLI Entry Point ─────────────────────────────────────────────────────────


def cmd_calls(detail_id=None, days=30, sync=False):
    """Main command: list calls, optionally show detail or sync."""
    if not config.QUO_API_KEY:
        print("Error: QUO_API_KEY not set in config.py or environment")
        return

    if detail_id:
        print(f"Fetching call {detail_id}...")
        call = get_call(detail_id)
        enriched = enrich_call(call)
        display_call_detail(enriched)
        return

    print(f"Fetching calls from last {days} days...")
    calls = fetch_all_calls(days=days)
    print(f"Found {len(calls)} calls total")

    if sync:
        print("Enriching calls with recordings & transcripts...")
        enriched = []
        for i, call in enumerate(calls, 1):
            print(f"  [{i}/{len(calls)}] {call['id']}...", end=" ", flush=True)
            e = enrich_call(call)
            enriched.append(e)
            has_rec = "REC" if e.get("recordings") else ""
            has_tr = "TR" if e.get("transcript") else ""
            print(f"{has_rec} {has_tr}")
            time.sleep(0.15)

        filepath = save_call_data(enriched)
        print(f"\nSaved to {filepath}")
        display_calls(enriched)
    else:
        display_calls(calls)
