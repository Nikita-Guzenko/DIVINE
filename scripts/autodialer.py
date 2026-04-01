#!/usr/bin/env python3
"""
Divine Auto-Dialer
==================
Auto-dials CDL candidates via OpenPhone.
Shows candidate brief in a compact web UI at localhost:8787.

Usage:
    python autodialer.py             # Start (uses tel: protocol to dial)
    python autodialer.py --clipboard # Clipboard-only mode (no auto-dial)

How it works:
    1. Opens http://localhost:8787 — your control panel
    2. Press START — shows first candidate, auto-dials via tel: protocol
    3. Talk in OpenPhone, then click status button → next candidate dials

Requirements:
    pip install supabase
"""

import json
import sys
import time
import signal
import subprocess
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone

from supabase import create_client

# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------
SUPABASE_URL = "https://psrsosfjteeovtmszwgu.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InBzcnNvc2ZqdGVlb3Z0bXN6d2d1Iiwi"
    "cm9sZSI6ImFub24iLCJpYXQiOjE3NzE1MzI2MDAsImV4cCI6MjA4NzEwODYwMH0."
    "15QS6GQ2cEWc-a1OVvzT1DlrExbdWGoRdEnYZ-ypgZs"
)
SERVER_PORT = 9090
CLIPBOARD_ONLY = "--clipboard" in sys.argv

# ---------------------------------------------------------------------------
# SUPABASE CLIENT
# ---------------------------------------------------------------------------
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def fetch_queue(source=None, status_filter=None, limit=500):
    """Fetch candidate queue from Supabase (same logic as dashboard API)."""
    q = sb.table("candidates").select("*").in_("status", ["New", "No Answer"])
    if source:
        q = q.ilike("source", source)
    if status_filter:
        q = q.eq("status", status_filter)
    q = (
        q.order("dialer_priority", desc=True)
        .order("call_count", desc=False)
        .order("created_at", desc=False)
        .limit(limit)
    )
    return q.execute().data or []


def update_candidate(candidate_id, status=None, notes=None):
    """Update candidate status in Supabase."""
    updates = {}
    if notes is not None:
        updates["nikita_comment"] = notes
    if status:
        updates["status"] = status
        if status == "No Answer":
            # Fetch current call_count and increment
            row = (
                sb.table("candidates")
                .select("call_count")
                .eq("id", candidate_id)
                .single()
                .execute()
            )
            current_count = (row.data or {}).get("call_count", 0) or 0
            updates["call_count"] = current_count + 1
            updates["last_call_at"] = datetime.now(timezone.utc).isoformat()
    if updates:
        sb.table("candidates").update(updates).eq("id", candidate_id).execute()


# ---------------------------------------------------------------------------
# SHARED STATE (thread-safe via GIL for simple reads/writes)
# ---------------------------------------------------------------------------
state = {
    "candidates": [],
    "current_index": 0,
    "running": False,
    "dialer_status": "idle",  # idle | dialing | in_call | waiting
    "action_event": threading.Event(),
    "last_action": None,
    "notes": "",
}


def current_candidate():
    idx = state["current_index"]
    if 0 <= idx < len(state["candidates"]):
        return state["candidates"][idx]
    return None


def state_json():
    c = current_candidate()
    return json.dumps({
        "running": state["running"],
        "status": state["dialer_status"],
        "index": state["current_index"],
        "total": len(state["candidates"]),
        "candidate": serialize_candidate(c) if c else None,
    })


def serialize_candidate(c):
    if not c:
        return None
    return {
        "id": c.get("id"),
        "first_name": c.get("first_name", ""),
        "last_name": c.get("last_name", ""),
        "phone": c.get("phone", ""),
        "phone_formatted": format_phone(c.get("phone", "")),
        "email": c.get("email", ""),
        "source": c.get("source", ""),
        "experience": c.get("experience", ""),
        "location": c.get("location", ""),
        "city": c.get("city", ""),
        "state": c.get("state", ""),
        "wants_team": c.get("wants_team"),
        "endorsements": c.get("endorsements", []),
        "trailer_experience": c.get("trailer_experience", []),
        "call_count": c.get("call_count", 0),
        "last_call_at": c.get("last_call_at"),
        "last_call_duration": c.get("last_call_duration"),
        "last_call_transcript": c.get("last_call_transcript"),
        "nikita_comment": c.get("nikita_comment", ""),
        "status": c.get("status", ""),
        "created_at": c.get("created_at", ""),
    }


def format_phone(phone):
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    if len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return phone


def phone_to_tel(phone):
    if not phone:
        return ""
    digits = "".join(c for c in phone if c.isdigit())
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits[0] == "1":
        return f"+{digits}"
    return f"+{digits}"


# ---------------------------------------------------------------------------
# HTTP SERVER — serves UI + API
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Suppress default logging

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(200)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == "/api/state":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self._cors()
            self.end_headers()
            self.wfile.write(state_json().encode())
        elif self.path == "/" or self.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._cors()
            self.end_headers()
            self.wfile.write(HTML_PAGE.encode())
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/api/action":
            action = body.get("action")
            notes = body.get("notes", "")
            if action in ("skip", "no_answer", "not_qualified", "qualified", "stop"):
                state["last_action"] = action
                state["notes"] = notes
                state["action_event"].set()
                self._respond({"ok": True})
            else:
                self._respond({"error": "unknown action"}, 400)

        elif self.path == "/api/start":
            state["running"] = True
            state["action_event"].set()
            self._respond({"ok": True})

        elif self.path == "/api/stop":
            state["running"] = False
            state["last_action"] = "stop"
            state["action_event"].set()
            self._respond({"ok": True})

        elif self.path == "/api/refresh":
            # Refetch queue
            state["candidates"] = fetch_queue()
            state["current_index"] = 0
            self._respond({"ok": True, "total": len(state["candidates"])})

        elif self.path == "/api/goto-start":
            state["current_index"] = 0
            self._respond({"ok": True, "index": 0})

        elif self.path == "/api/goto-end":
            last = max(0, len(state["candidates"]) - 1)
            state["current_index"] = last
            self._respond({"ok": True, "index": last})

        elif self.path == "/api/prev":
            state["current_index"] = max(0, state["current_index"] - 1)
            self._respond({"ok": True, "index": state["current_index"]})

        elif self.path == "/api/next":
            last = max(0, len(state["candidates"]) - 1)
            state["current_index"] = min(last, state["current_index"] + 1)
            self._respond({"ok": True, "index": state["current_index"]})

        else:
            self._respond({"error": "not found"}, 404)

    def _respond(self, data, code=200):
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self._cors()
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())


def start_server():
    server = HTTPServer(("0.0.0.0", SERVER_PORT), Handler)
    server.daemon_threads = True
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


# ---------------------------------------------------------------------------
# DIALING
# ---------------------------------------------------------------------------
def dial_phone(phone_number):
    """
    Dial a number. Copies to clipboard and opens tel: protocol.
    On macOS, tel: triggers the default phone app (OpenPhone if configured).
    """
    tel = phone_to_tel(phone_number)
    if not tel:
        return False

    # Always copy to clipboard
    try:
        subprocess.run(["pbcopy"], input=tel.encode(), check=True, capture_output=True)
    except Exception:
        pass

    if CLIPBOARD_ONLY:
        print(f"  [*] Copied to clipboard: {tel}")
        return True

    # Open tel: protocol — macOS routes to default phone handler
    try:
        subprocess.Popen(
            ["open", f"tel:{tel}"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print(f"  [*] Dialing: {tel}")
        return True
    except Exception as e:
        print(f"  [!] tel: open failed: {e}, number in clipboard")
        return True


# ---------------------------------------------------------------------------
# MAIN AUTO-DIAL LOOP
# ---------------------------------------------------------------------------
def run_autodialer():
    mode = "clipboard-only" if CLIPBOARD_ONLY else "tel: protocol"
    print("\n  ╔══════════════════════════════════════╗")
    print("  ║     DIVINE AUTO-DIALER               ║")
    print(f"  ║     Mode: {mode:<27}║")
    print("  ╚══════════════════════════════════════╝\n")

    # Fetch queue
    print("  [*] Fetching candidate queue...")
    state["candidates"] = fetch_queue()
    total = len(state["candidates"])
    print(f"  [*] {total} candidates in queue\n")

    if total == 0:
        print("  [!] No candidates to call. Exiting.")
        return

    # Start HTTP server
    print(f"  [*] Control panel: http://localhost:{SERVER_PORT}")
    start_server()

    # Open control panel in default browser
    webbrowser.open(f"http://localhost:{SERVER_PORT}")

    state["dialer_status"] = "waiting"
    print("  [*] Press START in the control panel to begin.\n")

    # Wait for start
    while not state["running"]:
        state["action_event"].wait(timeout=1)
        state["action_event"].clear()

    # Main loop
    while state["running"] and state["current_index"] < len(state["candidates"]):
        candidate = current_candidate()
        if not candidate:
            break

        idx = state["current_index"]
        total = len(state["candidates"])
        name = f"{candidate.get('first_name', '')} {candidate.get('last_name', '')}".strip()
        phone = candidate.get("phone", "")

        print(f"  [{idx + 1}/{total}] {name} — {format_phone(phone)}")

        if phone:
            state["dialer_status"] = "dialing"
            dial_phone(phone)
            state["dialer_status"] = "in_call"
        else:
            state["dialer_status"] = "waiting"
            print(f"  [!] No phone number — skipping")
            state["current_index"] += 1
            continue

        # Wait for user action
        state["action_event"].clear()
        while True:
            state["action_event"].wait(timeout=1)
            action = state["last_action"]
            if action:
                state["last_action"] = None
                state["action_event"].clear()
                break
            state["action_event"].clear()

        if action == "stop":
            print(f"  [*] Stopped by user.")
            state["running"] = False
            break

        # Process action
        status_map = {
            "skip": None,
            "no_answer": "No Answer",
            "not_qualified": "Not Qualified",
            "qualified": "Qualified / Awaiting Feedback",
        }
        new_status = status_map.get(action)
        notes = state["notes"]

        if new_status or notes:
            update_candidate(candidate["id"], status=new_status, notes=notes or None)
            print(f"  [✓] {action.replace('_', ' ').title()}" + (f" — {notes}" if notes else ""))
        else:
            print(f"  [→] Skipped")

        state["notes"] = ""
        state["current_index"] += 1

    # Done
    state["dialer_status"] = "idle"
    state["running"] = False
    print(f"\n  [*] Session complete. {state['current_index']} candidates processed.")
    print(f"  [*] Press Ctrl+C to exit.\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


# ---------------------------------------------------------------------------
# HTML UI
# ---------------------------------------------------------------------------
HTML_PAGE = r"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="utf-8">
<title>Divine Auto-Dialer</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0a0a0a;color:#e5e5e5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;min-height:100vh;display:flex;justify-content:center;padding:12px}
#app{width:100%;max-width:420px}
.hdr{display:flex;align-items:center;justify-content:space-between;padding:12px 0;border-bottom:1px solid rgba(255,255,255,.06);margin-bottom:16px}
.logo{font-size:11px;letter-spacing:3px;color:rgba(255,255,255,.25);font-weight:300}
.status-pill{font-size:11px;padding:3px 10px;border-radius:20px;font-weight:400;letter-spacing:.5px}
.status-idle{background:rgba(255,255,255,.05);color:rgba(255,255,255,.3)}
.status-dialing{background:rgba(59,130,246,.15);color:#60a5fa;animation:pulse 1.5s infinite}
.status-in_call{background:rgba(34,197,94,.15);color:#4ade80;animation:pulse 2s infinite}
.status-waiting{background:rgba(251,191,36,.1);color:#fbbf24}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.counter{font-size:12px;color:rgba(255,255,255,.2);font-weight:300}

.card{background:rgba(255,255,255,.02);border:1px solid rgba(255,255,255,.06);border-radius:12px;padding:16px;margin-bottom:12px}
.name{font-size:20px;font-weight:300;letter-spacing:.5px;margin-bottom:2px}
.phone{font-size:14px;color:#4ade80;font-weight:300;letter-spacing:.5px;cursor:pointer;margin-bottom:4px}
.phone:hover{color:#86efac}
.email{font-size:12px;color:rgba(255,255,255,.2);margin-bottom:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 16px;font-size:12px;margin-bottom:12px}
.grid .label{color:rgba(255,255,255,.2);font-weight:300}
.grid .value{color:rgba(255,255,255,.6);font-weight:400}
.badges{display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px}
.badge{font-size:10px;padding:2px 8px;border-radius:10px;background:rgba(59,130,246,.1);color:#60a5fa;border:1px solid rgba(59,130,246,.15)}
.badge.green{background:rgba(34,197,94,.1);color:#4ade80;border-color:rgba(34,197,94,.15)}

.notes-section{margin-bottom:12px}
.notes-existing{font-size:11px;color:rgba(255,255,255,.3);background:rgba(255,255,255,.03);padding:8px 10px;border-radius:8px;margin-bottom:8px;border:1px solid rgba(255,255,255,.04)}
.notes-existing strong{color:rgba(255,255,255,.5)}
.transcript{font-size:11px;color:rgba(255,255,255,.2);background:rgba(255,255,255,.02);padding:8px 10px;border-radius:8px;max-height:80px;overflow-y:auto;border:1px solid rgba(255,255,255,.04);margin-bottom:8px}

.notes-input{width:100%;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.06);border-radius:8px;padding:8px 10px;color:#e5e5e5;font-size:12px;outline:none;font-family:inherit;resize:none}
.notes-input:focus{border-color:rgba(255,255,255,.15)}
.notes-input::placeholder{color:rgba(255,255,255,.15)}

.actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.btn{padding:14px 8px;border-radius:10px;border:1px solid rgba(255,255,255,.06);background:rgba(255,255,255,.02);color:rgba(255,255,255,.5);font-size:12px;font-weight:400;cursor:pointer;transition:all .15s;display:flex;flex-direction:column;align-items:center;gap:4px;font-family:inherit}
.btn:hover{border-color:rgba(255,255,255,.12);color:rgba(255,255,255,.8)}
.btn:active{transform:scale(.97)}
.btn kbd{font-size:10px;color:rgba(255,255,255,.15);font-family:inherit}
.btn-skip:hover{border-color:rgba(255,255,255,.12)}
.btn-na:hover{color:#fbbf24;border-color:rgba(251,191,36,.25);background:rgba(251,191,36,.05)}
.btn-nq:hover{color:#f87171;border-color:rgba(248,113,113,.25);background:rgba(248,113,113,.05)}
.btn-q:hover{color:#4ade80;border-color:rgba(34,197,94,.25);background:rgba(34,197,94,.05)}

.start-btn{width:100%;padding:14px;border-radius:10px;border:1px solid rgba(34,197,94,.2);background:rgba(34,197,94,.08);color:#4ade80;font-size:14px;font-weight:300;letter-spacing:1px;cursor:pointer;transition:all .15s;font-family:inherit}
.start-btn:hover{background:rgba(34,197,94,.15);border-color:rgba(34,197,94,.35)}
.stop-btn{border-color:rgba(248,113,113,.2);background:rgba(248,113,113,.08);color:#f87171}
.stop-btn:hover{background:rgba(248,113,113,.15);border-color:rgba(248,113,113,.35)}

.empty{text-align:center;padding:60px 20px;color:rgba(255,255,255,.15);font-size:14px;font-weight:300}

.call-info{font-size:11px;color:rgba(255,255,255,.15);margin-top:4px}
</style>
</head>
<body>
<div id="app">
  <div class="hdr">
    <span class="logo">DIVINE AUTO-DIALER</span>
    <span class="status-pill status-idle" id="statusPill">idle</span>
    <span class="counter" id="counter">0 / 0</span>
  </div>
  <div id="content"><div class="empty">Loading...</div></div>
  <div id="controls" style="margin-top:8px"></div>
</div>

<script>
let currentState = null;
let notesValue = '';

function poll() {
  fetch('/api/state').then(r => r.json()).then(s => {
    currentState = s;
    render(s);
  }).catch(() => {});
}

function render(s) {
  // Status pill
  const pill = document.getElementById('statusPill');
  pill.textContent = s.status.replace('_', ' ');
  pill.className = 'status-pill status-' + s.status;

  // Counter
  document.getElementById('counter').textContent =
    s.total > 0 ? `${s.index + 1} / ${s.total}` : '0 / 0';

  const content = document.getElementById('content');
  const controls = document.getElementById('controls');

  if (!s.candidate) {
    content.innerHTML = '<div class="empty">No candidates in queue</div>';
    controls.innerHTML = '';
    return;
  }

  const c = s.candidate;
  const loc = [c.city, c.state].filter(Boolean).join(', ') || c.location || '—';
  const team = c.wants_team === true ? 'Yes' : c.wants_team === false ? 'No' : '—';

  let badges = '';
  if (c.endorsements && c.endorsements.length) {
    badges += c.endorsements.map(e => `<span class="badge">${e}</span>`).join('');
  }
  if (c.trailer_experience && c.trailer_experience.length) {
    badges += c.trailer_experience.map(e => `<span class="badge green">${e}</span>`).join('');
  }

  let notesHtml = '';
  if (c.nikita_comment) {
    notesHtml += `<div class="notes-existing"><strong>Notes:</strong> ${esc(c.nikita_comment)}</div>`;
  }
  if (c.last_call_transcript) {
    notesHtml += `<div class="transcript">${esc(c.last_call_transcript)}</div>`;
  }

  let callInfo = '';
  if (c.last_call_at) {
    const d = new Date(c.last_call_at);
    callInfo = `Last call: ${d.toLocaleDateString('en-US', {month:'short',day:'numeric'})}`;
    if (c.last_call_duration != null) callInfo += ` (${c.last_call_duration}s)`;
  }

  content.innerHTML = `
    <div class="card">
      <div class="name">${esc(c.first_name)} ${esc(c.last_name)}</div>
      <div class="phone" onclick="copyPhone('${esc(c.phone)}')" title="Click to copy">${c.phone_formatted || '—'}</div>
      ${c.email ? `<div class="email">${esc(c.email)}</div>` : ''}
      <div class="grid">
        <span class="label">Source</span><span class="value">${esc(c.source) || '—'}</span>
        <span class="label">Experience</span><span class="value">${esc(c.experience) || '—'}</span>
        <span class="label">Location</span><span class="value">${esc(loc)}</span>
        <span class="label">Team</span><span class="value">${team}</span>
        <span class="label">Calls</span><span class="value">${c.call_count || 0}</span>
        <span class="label">Status</span><span class="value">${esc(c.status)}</span>
      </div>
      ${badges ? `<div class="badges">${badges}</div>` : ''}
      ${notesHtml}
      ${callInfo ? `<div class="call-info">${callInfo}</div>` : ''}
    </div>
    <div class="notes-section">
      <textarea class="notes-input" id="notesInput" rows="2" placeholder="Add notes..."
        oninput="notesValue=this.value">${esc(notesValue)}</textarea>
    </div>
    <div class="actions">
      <button class="btn btn-skip" onclick="action('skip')"><kbd>N</kbd>Skip</button>
      <button class="btn btn-na" onclick="action('no_answer')"><kbd>Space</kbd>No Answer</button>
      <button class="btn btn-nq" onclick="action('not_qualified')"><kbd>Q</kbd>Not Qualified</button>
      <button class="btn btn-q" onclick="action('qualified')"><kbd>A</kbd>Qualified</button>
    </div>
  `;

  // Controls
  if (s.running) {
    controls.innerHTML = `<button class="start-btn stop-btn" onclick="stopDialer()">■ STOP</button>`;
  } else {
    controls.innerHTML = `
      <div style="display:flex;gap:8px;margin-bottom:8px">
        <button class="start-btn" style="flex:1;padding:8px;font-size:12px;border-color:rgba(255,255,255,.1);background:rgba(255,255,255,.03);color:rgba(255,255,255,.4)" onclick="gotoStart()">⏮ First</button>
        <button class="start-btn" style="flex:1;padding:8px;font-size:12px;border-color:rgba(255,255,255,.1);background:rgba(255,255,255,.03);color:rgba(255,255,255,.4)" onclick="gotoEnd()">Last ⏭</button>
      </div>
      <button class="start-btn" onclick="startDialer()">▶ START AUTO-DIAL</button>`;
  }
}

function action(act) {
  fetch('/api/action', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({action: act, notes: notesValue})
  }).then(() => { notesValue = ''; });
}

function startDialer() {
  fetch('/api/start', {method: 'POST'});
}

function stopDialer() {
  fetch('/api/stop', {method: 'POST'});
}

function gotoStart() {
  fetch('/api/goto-start', {method: 'POST'}).then(() => poll());
}

function gotoEnd() {
  fetch('/api/goto-end', {method: 'POST'}).then(() => poll());
}

function copyPhone(phone) {
  if (!phone) return;
  const digits = phone.replace(/\D/g, '');
  const tel = digits.length === 10 ? '+1' + digits : '+' + digits;
  navigator.clipboard.writeText(tel).then(() => {
    const el = document.querySelector('.phone');
    if (el) { el.textContent = 'Copied!'; setTimeout(() => poll(), 800); }
  });
}

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Keyboard shortcuts
document.addEventListener('keydown', e => {
  const tag = (e.target.tagName || '').toLowerCase();
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
  switch(e.key.toLowerCase()) {
    case 'n': e.preventDefault(); action('skip'); break;
    case 'q': e.preventDefault(); action('not_qualified'); break;
    case 'a': e.preventDefault(); action('qualified'); break;
    case ' ': e.preventDefault(); action('no_answer'); break;
    case 'c': e.preventDefault(); if(currentState?.candidate?.phone) copyPhone(currentState.candidate.phone); break;
    case 'arrowleft': e.preventDefault(); fetch('/api/prev',{method:'POST'}).then(()=>poll()); break;
    case 'arrowright': e.preventDefault(); fetch('/api/next',{method:'POST'}).then(()=>poll()); break;
    case 'home': e.preventDefault(); gotoStart(); break;
    case 'end': e.preventDefault(); gotoEnd(); break;
  }
});

// Poll every 500ms
setInterval(poll, 500);
poll();
</script>
</body></html>"""


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    signal.signal(signal.SIGINT, lambda *_: sys.exit(0))
    run_autodialer()


if __name__ == "__main__":
    main()
