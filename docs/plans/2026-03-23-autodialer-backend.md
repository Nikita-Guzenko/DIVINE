# Auto-Dialer Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add auto-dialer backend to existing Divine dashboard -- import Excel candidates to Supabase, add call tracking fields, create Quo webhook endpoint, build dialer queue API.

**Architecture:** Extend existing Next.js dashboard with API routes for webhook + dialer queue. Import Excel candidates via Python script into same Supabase `candidates` table. Quo webhooks notify our API when calls complete, which auto-fetches transcript/recording.

**Tech Stack:** Next.js 16 API routes, Supabase (existing), Python (import script), Quo/OpenPhone API

---

### Task 1: Add call tracking columns to Supabase

**Files:**
- Create: `dashboard/supabase/migrations/001_call_tracking.sql`

**Step 1: Create migration SQL**

```sql
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS call_count integer DEFAULT 0;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS last_call_at timestamptz;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS last_call_transcript text;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS last_call_recording_url text;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS last_call_duration integer;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS last_call_direction text;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS dialer_priority integer DEFAULT 0;
```

**Step 2: Run migration against Supabase**

Run via Supabase SQL Editor or:
```bash
curl -X POST "https://psrsosfjteeovtmszwgu.supabase.co/rest/v1/rpc" \
  -H "apikey: $SUPABASE_KEY" \
  -H "Authorization: Bearer $SUPABASE_KEY" \
  -d '...'
```

Or use Python:
```python
from supabase import create_client
client = create_client(url, key)
# Execute raw SQL via Supabase dashboard SQL editor
```

**Step 3: Verify columns exist**

```bash
curl "https://psrsosfjteeovtmszwgu.supabase.co/rest/v1/candidates?select=call_count,last_call_at,dialer_priority&limit=1" \
  -H "apikey: $SUPABASE_KEY"
```

Expected: 200 OK with null values

---

### Task 2: Import Excel candidates to Supabase

**Files:**
- Create: `scripts/import_excel_to_supabase.py`

**Step 1: Write import script**

```python
#!/usr/bin/env python3
"""Import candidates from Excel tracking sheet into Supabase."""
import openpyxl
import requests
import re
import os

SUPABASE_URL = os.environ.get('SUPABASE_URL', 'https://psrsosfjteeovtmszwgu.supabase.co')
SUPABASE_KEY = os.environ.get('SUPABASE_KEY')
EXCEL_PATH = '/Users/nikitaguzenko/Downloads/divine ent driver tracking.xlsx'

HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal'
}

STATUS_MAP = {
    'No answer': 'No Answer',
    'No answer 2x': 'No Answer',
    'Not Qualified': 'Not Qualified',
    'Potential driver': 'New',
    None: 'New',
}

def normalize_phone(phone):
    """Normalize phone to digits only, ensure 10 digits."""
    if phone is None:
        return None
    digits = re.sub(r'\D', '', str(phone).split('.')[0])
    if len(digits) == 11 and digits.startswith('1'):
        digits = digits[1:]
    if len(digits) != 10:
        return None
    return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"

def get_existing_phones():
    """Fetch all existing phone numbers from Supabase."""
    phones = set()
    r = requests.get(
        f"{SUPABASE_URL}/rest/v1/candidates?select=phone",
        headers=HEADERS
    )
    if r.ok:
        for row in r.json():
            if row.get('phone'):
                digits = re.sub(r'\D', '', row['phone'])
                if len(digits) >= 10:
                    phones.add(digits[-10:])
    return phones

def import_sheet(ws, sheet_name, existing_phones, is_bazar=False):
    """Import candidates from one worksheet."""
    imported = 0
    skipped = 0

    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
        if not any(row):
            continue

        if is_bazar:
            # Bazar sheet has shifted columns (first col is None)
            name = str(row[1] or '').strip() if row[1] else None
            phone_raw = row[2]
            source_val = row[3]
            status_raw = row[4]
        else:
            name = str(row[0] or '').strip() if row[0] else None
            phone_raw = row[1]
            source_val = row[3]
            status_raw = row[4]

        if not name or not phone_raw:
            continue

        phone = normalize_phone(phone_raw)
        if not phone:
            continue

        # Dedup check
        digits = re.sub(r'\D', '', phone)[-10:]
        if digits in existing_phones:
            skipped += 1
            continue

        # Parse name
        parts = name.strip().split(None, 1)
        first_name = parts[0] if parts else name
        last_name = parts[1] if len(parts) > 1 else ''

        # Map status
        status = STATUS_MAP.get(status_raw, 'New')

        # Map source
        source = 'BAZAR.CLUB' if is_bazar or (source_val and 'BAZAR' in str(source_val).upper()) else f'Excel/{sheet_name}'

        # Build candidate record
        candidate = {
            'first_name': first_name,
            'last_name': last_name,
            'phone': phone,
            'source': source,
            'status': status,
            'call_count': 0,
            'dialer_priority': 1 if status == 'New' else 0,
        }

        # Add extra fields if available (non-bazar sheets)
        if not is_bazar:
            email = row[2] if len(row) > 2 else None
            if email and isinstance(email, str) and '@' in email:
                candidate['email'] = email.lower().strip()

            experience = row[9] if len(row) > 9 else None
            if experience:
                candidate['experience'] = str(experience)

            notes = row[8] if len(row) > 8 else None
            if notes:
                candidate['notes'] = str(notes)

        # Insert
        r = requests.post(
            f"{SUPABASE_URL}/rest/v1/candidates",
            headers=HEADERS,
            json=candidate
        )

        if r.status_code in (200, 201):
            imported += 1
            existing_phones.add(digits)
        else:
            print(f"  Error inserting {first_name}: {r.status_code} {r.text[:100]}")

    return imported, skipped

def main():
    wb = openpyxl.load_workbook(EXCEL_PATH, read_only=True)
    existing = get_existing_phones()
    print(f"Existing candidates in Supabase: {len(existing)}")

    total_imported = 0
    total_skipped = 0

    for sheet_name in ['Sheet1', 'Sheet3']:
        ws = wb[sheet_name]
        imp, skip = import_sheet(ws, sheet_name, existing, is_bazar=False)
        print(f"{sheet_name}: imported={imp}, skipped={skip}")
        total_imported += imp
        total_skipped += skip

    ws = wb['CVs from BAZAR.CLUB']
    imp, skip = import_sheet(ws, 'BAZAR', existing, is_bazar=True)
    print(f"BAZAR.CLUB: imported={imp}, skipped={skip}")
    total_imported += imp
    total_skipped += skip

    print(f"\nTotal: {total_imported} imported, {total_skipped} skipped (duplicates)")

if __name__ == '__main__':
    main()
```

**Step 2: Test with dry run (print instead of insert)**

**Step 3: Run import**
```bash
cd ~/Desktop/DIVINE && source venv/bin/activate
SUPABASE_KEY="..." python scripts/import_excel_to_supabase.py
```

**Step 4: Verify in Supabase**
```bash
curl "https://psrsosfjteeovtmszwgu.supabase.co/rest/v1/candidates?select=id,first_name,source&source=eq.BAZAR.CLUB&limit=5" -H "apikey: $KEY"
```

---

### Task 3: Update Supabase types in dashboard

**Files:**
- Modify: `dashboard/src/lib/supabase.ts`

**Step 1: Add new fields to Candidate type**

Add to the `Candidate` type:
```typescript
call_count: number
last_call_at: string | null
last_call_transcript: string | null
last_call_recording_url: string | null
last_call_duration: number | null
last_call_direction: string | null
dialer_priority: number
```

**Step 2: Update STATUSES to include all sources**

Add `'No Answer'` if not present (it's already there as status in Excel data).

---

### Task 4: Create Quo webhook API route

**Files:**
- Create: `dashboard/src/app/api/webhook/quo/route.ts`

**Step 1: Create webhook handler**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY!
)

const QUO_API_KEY = process.env.QUO_API_KEY!
const QUO_BASE = 'https://api.openphone.com/v1'

async function quoFetch(path: string) {
  const r = await fetch(`${QUO_BASE}${path}`, {
    headers: { 'Authorization': `Bearer ${QUO_API_KEY}` }
  })
  return r.ok ? r.json() : null
}

export async function POST(req: NextRequest) {
  const body = await req.json()
  const event = body.type || body.event

  // Handle call.completed event
  if (event === 'call.completed' || event === 'call.ringing.completed') {
    const call = body.data?.object || body.data
    if (!call) return NextResponse.json({ ok: false }, { status: 400 })

    const callId = call.id
    const participants = call.participants || []
    const duration = call.duration || 0
    const direction = call.direction || 'outgoing'

    // Find candidate by phone number
    for (const phone of participants) {
      const digits = phone.replace(/\D/g, '').slice(-10)
      if (!digits) continue

      // Search Supabase for matching candidate
      const formatted = `${digits.slice(0,3)}-${digits.slice(3,6)}-${digits.slice(6)}`
      const { data: candidates } = await supabase
        .from('candidates')
        .select('id, call_count, phone')
        .or(`phone.like.%${digits.slice(-7)}%`)
        .limit(5)

      if (!candidates?.length) continue

      // Fetch transcript and recording from Quo
      let transcript = null
      let recordingUrl = null

      // Wait a bit for processing
      await new Promise(r => setTimeout(r, 3000))

      const transcriptData = await quoFetch(`/call-transcripts/${callId}`)
      if (transcriptData?.data) {
        const dialogue = transcriptData.data.dialogue || transcriptData.data
        if (Array.isArray(dialogue)) {
          transcript = dialogue.map((d: any) => d.content).join('\n')
        }
      }

      const recordingData = await quoFetch(`/call-recordings/${callId}`)
      if (recordingData?.data?.length > 0) {
        recordingUrl = recordingData.data[0].url || recordingData.data[0].mediaUrl
      }

      // Update candidate
      const candidate = candidates[0]
      const { error } = await supabase
        .from('candidates')
        .update({
          call_count: (candidate.call_count || 0) + 1,
          last_call_at: new Date().toISOString(),
          last_call_duration: duration,
          last_call_direction: direction,
          last_call_transcript: transcript,
          last_call_recording_url: recordingUrl,
        })
        .eq('id', candidate.id)

      if (!error) {
        return NextResponse.json({ ok: true, candidateId: candidate.id })
      }
    }
  }

  return NextResponse.json({ ok: true })
}

// Quo sends GET to verify webhook
export async function GET() {
  return NextResponse.json({ status: 'active' })
}
```

**Step 2: Add env vars to Netlify**

```
SUPABASE_URL=https://psrsosfjteeovtmszwgu.supabase.co
SUPABASE_SERVICE_KEY=<service role key>
QUO_API_KEY=<quo api key>
```

**Step 3: Deploy and register webhook with Quo**

```python
import requests
QUO_KEY = "..."
r = requests.post(
    "https://api.openphone.com/v1/webhooks",
    headers={"Authorization": f"Bearer {QUO_KEY}", "Content-Type": "application/json"},
    json={
        "url": "https://divine-recruiting.netlify.app/api/webhook/quo",
        "events": ["call.completed", "call.recording.completed", "call.transcript.completed"]
    }
)
print(r.status_code, r.json())
```

---

### Task 5: Create dialer queue API route

**Files:**
- Create: `dashboard/src/app/api/dialer/queue/route.ts`

**Step 1: Create queue endpoint**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY!
)

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url)
  const source = searchParams.get('source')
  const status = searchParams.get('status')
  const limit = parseInt(searchParams.get('limit') || '100')

  let query = supabase
    .from('candidates')
    .select('*')
    .in('status', ['New', 'No Answer'])
    .order('dialer_priority', { ascending: false })
    .order('call_count', { ascending: true })
    .order('created_at', { ascending: true })
    .limit(limit)

  if (source && source !== 'all') {
    query = query.ilike('source', `%${source}%`)
  }

  if (status && status !== 'all') {
    query = query.eq('status', status)
  }

  const { data, error } = await query

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  return NextResponse.json({ candidates: data, total: data?.length || 0 })
}
```

---

### Task 6: Create dialer status update API route

**Files:**
- Create: `dashboard/src/app/api/dialer/update/route.ts`

**Step 1: Create status update endpoint**

```typescript
import { NextRequest, NextResponse } from 'next/server'
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(
  process.env.SUPABASE_URL!,
  process.env.SUPABASE_SERVICE_KEY!
)

export async function POST(req: NextRequest) {
  const { candidateId, status, notes, skipReason } = await req.json()

  if (!candidateId) {
    return NextResponse.json({ error: 'candidateId required' }, { status: 400 })
  }

  const updates: Record<string, any> = {}

  if (status) updates.status = status
  if (notes) updates.nikita_comment = notes
  if (skipReason) updates.notes = skipReason

  // Increment call_count if status change implies a call was made
  if (status === 'No Answer') {
    const { data: current } = await supabase
      .from('candidates')
      .select('call_count')
      .eq('id', candidateId)
      .single()

    updates.call_count = (current?.call_count || 0) + 1
    updates.last_call_at = new Date().toISOString()
  }

  const { error } = await supabase
    .from('candidates')
    .update(updates)
    .eq('id', candidateId)

  if (error) {
    return NextResponse.json({ error: error.message }, { status: 500 })
  }

  return NextResponse.json({ ok: true })
}
```

---

### Task 7: Test all backend endpoints

**Step 1: Test queue API locally**
```bash
cd ~/Desktop/DIVINE/dashboard
npm run dev
# In another terminal:
curl http://localhost:3000/api/dialer/queue?limit=3
```

**Step 2: Test status update API**
```bash
curl -X POST http://localhost:3000/api/dialer/update \
  -H "Content-Type: application/json" \
  -d '{"candidateId": 1, "status": "No Answer"}'
```

**Step 3: Test webhook endpoint**
```bash
curl -X POST http://localhost:3000/api/webhook/quo \
  -H "Content-Type: application/json" \
  -d '{"type":"call.completed","data":{"object":{"id":"test","participants":["+19168568548"],"duration":45,"direction":"outgoing"}}}'
```

**Step 4: Deploy to Netlify and verify**
```bash
cd ~/Desktop/DIVINE/dashboard
git add -A && git commit -m "feat: add autodialer backend API routes"
# Push to trigger Netlify deploy
curl https://divine-recruiting.netlify.app/api/dialer/queue?limit=1
curl https://divine-recruiting.netlify.app/api/webhook/quo  # GET should return {"status":"active"}
```
