# Divine CDL-A Recruiter - Vapi AI Voice Assistant Specification

> **Version:** 1.0
> **Created:** 2026-01-12
> **Assistant ID:** *(to be assigned after creation)*

---

## Overview

AI-powered voice assistant for outbound calls to CDL-A driver candidates who submitted job applications to Divine Enterprises.

| Property | Value |
|----------|-------|
| AI Name | Nikita Guzenko |
| Role | Recruiter |
| Company | Divine Enterprises |
| Target | CDL-A driver candidates |
| Goal | Pre-screen for TEAM driving positions |

---

## Configuration Summary

### Model
| Setting | Value | Rationale |
|---------|-------|-----------|
| Provider | OpenAI | Best quality for conversation |
| Model | GPT-4o | Latest, most capable |
| Temperature | 0.5 | Balanced - professional but natural |

### Voice
| Setting | Value | Rationale |
|---------|-------|-----------|
| Provider | 11labs | Best quality TTS |
| Voice ID | pNInz6obpgDQGcFmaJgB | Adam - deep, professional, American |
| Stability | 0.5 | Natural variation |
| Similarity Boost | 0.75 | Clear articulation |
| Speaker Boost | true | Enhanced clarity |

### Transcriber
| Setting | Value | Rationale |
|---------|-------|-----------|
| Provider | Deepgram | Industry leading STT |
| Model | nova-2 | Latest, most accurate |
| Language | en | English |
| Smart Format | true | Auto-punctuation |
| Endpointing | 300ms | Balanced response time |
| Keywords | Divine:2, CDL:2, team:2 | Boost recognition |

### Timing
| Setting | Value | Rationale |
|---------|-------|-----------|
| Wait Seconds | 0.4s | Quick response |
| Silence Timeout | 30s | End dead calls |
| Max Duration | 600s (10 min) | Long enough for screening |
| Idle Timeout | 10s | "Are you still there?" |

---

## Conversation Design

### First Message
```
Hi, this is Nikita calling from Divine Enterprises. I'm following up on
your application for a CDL-A driving position. Do you have a couple
minutes for a quick call?
```

### Voicemail Message
```
Hi, this is Nikita from Divine Enterprises. I'm calling about your
CDL-A driver application. We have team driving positions available
with great pay and benefits. Please call me back at 305-413-8988
or visit our website at divinetrans.com. Thank you, and have a great day!
```

### End Call Message
```
Thank you for your time today. I'll follow up with the next steps.
Have a great day and drive safe!
```

---

## Pre-Screening Questions

### CRITICAL Questions (Must Ask)
1. **"How many years of Class A driving experience do you have?"**
2. **"Are you open to driving as part of a team - two drivers per truck?"** *(KEY QUESTION)*
3. **"What's the main reason you're looking for a new company?"**

### Detailed Questions (If Team-Ready)
4. "How many days are you comfortable staying on the road?"
5. "How much home time do you expect between runs?"
6. "Do you have experience hauling temperature-controlled loads with a 53-foot trailer?"
7. "Do you have any endorsements - Hazmat, Tanker, or Doubles/Triples?"
8. "Would you prefer W-2 employment with benefits, or 1099 as an independent contractor?"

---

## Qualification Logic

| Team Ready | CDL-A Exp | Result |
|------------|-----------|--------|
| Yes | 1+ years | **QUALIFIED** - Send IntelliApp |
| Maybe | 1+ years | Explain benefits, reassess |
| No | Any | **NOT QUALIFIED** - Solo only |
| Any | < 1 year | May not qualify, discuss |

---

## Function Tools (3)

### 1. captureDriverInfo
Captures basic driver information.

```json
{
  "driverName": "string (required)",
  "callbackNumber": "string",
  "cdlExperience": "string",
  "openToTeam": "boolean (CRITICAL)",
  "reasonForSwitching": "string"
}
```

### 2. captureQualifications
Captures driver qualifications and preferences.

```json
{
  "daysOnRoad": "string",
  "homeTimeExpected": "string",
  "tempControlledExperience": "boolean",
  "trailerExperience": "boolean",
  "endorsements": ["Hazmat", "Tanker", "Doubles", "Triples"],
  "employmentPreference": "W-2 | 1099 | Either"
}
```

### 3. logCallOutcome
Logs the final outcome of each call.

```json
{
  "outcome": "qualified_team | qualified_solo_willing | not_qualified_solo_only | not_qualified_experience | callback_scheduled | voicemail_left | wrong_number | no_answer | declined",
  "teamReadiness": "yes | no | maybe",
  "nextAction": "string (required)",
  "callbackDateTime": "string",
  "notes": "string"
}
```

---

## Company Information (For Reference)

### Routes & Schedule
- Team runs: 5-7-10 days out, 1-3 days home
- 5,000-6,000 miles per week average
- OTR across all 48 states + Canada (if eligible)
- Exclusive contracted routes with set schedules

### W-2 Employment Benefits
- 401(k) with company matching
- Health, dental, vision insurance
- Paid vacation and sick days
- 5 paid holidays
- Workers Compensation
- Paycheck every 2nd Friday

### 1099 Employment
- $3,000 security deposit for equipment
- $168/month for Occupational Accident insurance
- Requires LLC/Corporation/Partnership + EIN
- No benefits, no taxes deducted
- Paycheck next business day after paperwork

### Compensation
- Team rates: $2,000-$2,700/week (experience dependent)
- Hazmat bonus: +$0.05/mile
- Tanker bonus: +$0.01/mile
- Paid stops after 4th: $50/stop
- Trailer swap: $15
- Referral bonus available

---

## Files

| File | Purpose |
|------|---------|
| `vapi-assistant-divine.json` | Complete configuration |
| `vapi-config.json` | Credentials & IDs |
| `create-assistant.sh` | Create assistant script |
| `test-call.sh` | Test call script |

---

## Usage

### Create Assistant
```bash
cd ~/Desktop/DIVINE/vapi
./create-assistant.sh
```

### Test Call
```bash
./test-call.sh +13054138988
```

### API Commands
```bash
# List assistants
curl -s "https://api.vapi.ai/assistant" \
  -H "Authorization: Bearer ${VAPI_KEY}"

# Get assistant
curl -s "https://api.vapi.ai/assistant/${ASSISTANT_ID}" \
  -H "Authorization: Bearer ${VAPI_KEY}"

# Make call (requires phone number)
curl -s -X POST "https://api.vapi.ai/call" \
  -H "Authorization: Bearer ${VAPI_KEY}" \
  -H "Content-Type: application/json" \
  -d '{
    "assistantId": "'${ASSISTANT_ID}'",
    "customer": {"number": "+1XXXXXXXXXX"}
  }'
```

---

## Next Steps (After Creation)

1. Run `./create-assistant.sh` to create the assistant
2. Add Twilio/Vonage phone number in [Vapi dashboard](https://dashboard.vapi.ai)
3. Assign phone number to assistant
4. Run test call to personal number
5. Integrate with candidate database for batch calling
6. Set up webhook for call results (optional)

---

## Integration with DIVINE Recruiting System

### Database Integration
Call outcomes should update `data/candidates.db`:
- `qualified_team` → status = "Team OK"
- `not_qualified_solo_only` → status = "Solo Only"
- `callback_scheduled` → status = "Callback"

### Google Sheets Sync
Results sync to tracking spreadsheet via `scripts/google_sheets.py`

---

*Document generated: 2026-01-12*
