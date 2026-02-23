#!/bin/bash

# Divine CDL-A Recruiter - Test Call Script
# Usage: ./test-call.sh +1XXXXXXXXXX

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAPI_CONFIG="$SCRIPT_DIR/vapi-config.json"

# Extract credentials from config
VAPI_KEY=$(jq -r '.private_key' "$VAPI_CONFIG")
ASSISTANT_ID=$(jq -r '.assistant_id' "$VAPI_CONFIG")

if [ -z "$VAPI_KEY" ] || [ "$VAPI_KEY" == "null" ]; then
    echo "Error: Could not find private_key in vapi-config.json"
    exit 1
fi

if [ -z "$ASSISTANT_ID" ] || [ "$ASSISTANT_ID" == "null" ]; then
    echo "Error: Assistant not created yet. Run create-assistant.sh first."
    exit 1
fi

PHONE_NUMBER="$1"

if [ -z "$PHONE_NUMBER" ]; then
    echo "Usage: $0 +1XXXXXXXXXX"
    echo "Example: $0 +13054138988"
    exit 1
fi

echo "Initiating test call..."
echo "Assistant ID: $ASSISTANT_ID"
echo "Phone Number: $PHONE_NUMBER"
echo ""

RESPONSE=$(curl -s -X POST "https://api.vapi.ai/call" \
    -H "Authorization: Bearer $VAPI_KEY" \
    -H "Content-Type: application/json" \
    -d '{
        "assistantId": "'"$ASSISTANT_ID"'",
        "customer": {
            "number": "'"$PHONE_NUMBER"'"
        }
    }')

# Check for errors
if echo "$RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
    echo "Error initiating call:"
    echo "$RESPONSE" | jq '.'
    exit 1
fi

CALL_ID=$(echo "$RESPONSE" | jq -r '.id')

echo "Call initiated!"
echo "Call ID: $CALL_ID"
echo ""
echo "Check call status at: https://dashboard.vapi.ai/calls"
