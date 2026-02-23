# iMessage Outreach Rules

## Overview
SMS/iMessage outreach to CDL-A driver candidates from CareerPlug applications.

---

## Message Template

**Base structure:**
```
Hi {First Name}. {Intro variation}. {Core message}. {Question variation}
```

**Components:**

| Part | Variations |
|------|------------|
| **Intro** | "This is Nikita from Divine Enterprises" / "Nikita here from Divine Enterprises" / "This is Nikita with Divine Enterprises" / "Nikita from Divine here" |
| **Core** | "We received your application for CDL-A driver" / "Saw your CDL-A application" / "Got your application for CDL-A driver" / "Your CDL-A application came through" |
| **Question** | "Are you open for OTR team runs?" / "Would you be open to OTR team driving?" / "Interested in OTR team runs?" / "Open to team driving OTR?" |

---

## Sending Rules

| Rule | Value |
|------|-------|
| **Interval between messages** | 2 minutes minimum |
| **Max per session** | 10-15 candidates |
| **Time window** | 9 AM - 7 PM local time |
| **Days** | Monday - Saturday |

---

## Delivery Check Process

1. Send iMessage via AppleScript
2. Wait 5 seconds
3. Query Messages.db for delivery status:
   ```sql
   SELECT is_delivered, is_sent
   FROM message
   WHERE handle_id = (SELECT ROWID FROM handle WHERE id LIKE '%{phone}%')
   ORDER BY date DESC LIMIT 1;
   ```
4. If `is_delivered = 0` after 10 seconds → retry as SMS
5. Log result

---

## Status Updates

After sending, update candidate in database:
```sql
UPDATE candidates
SET call_status = 'Screening',
    screening_sent_at = CURRENT_TIMESTAMP
WHERE phone = '{phone}';
```

---

## Response Handling

| Response Type | Action | New Status |
|---------------|--------|------------|
| "Yes" / interested in team | Send job details + IntelliApp link | Team OK |
| "Solo only" / not interested in team | Thank, close | Solo Only |
| "Not interested" | Thank, close | Rejected |
| "Already employed" | Thank, close | Rejected |
| "Looking for local" | Explain OTR, close if no | Solo Only |
| No response (48h) | Send follow-up | Screening |

---

## Follow-up Template (after 48h no response)

```
Hi {First Name}, just following up on my message about the CDL-A team driving position. Still interested?
```

---

## Phone Number Format

- Database format: `1916-317-8424`
- iMessage format: `+19163178424`
- Conversion: Remove dashes, add `+`

---

## Do NOT Contact

- Candidates already in active conversation
- Candidates marked as "Rejected" or "Solo Only"
- Numbers that bounced/failed delivery twice
