#!/bin/bash

# Divine CDL-A Recruiter - Vapi Assistant Creation Script
# Run this script to create the assistant on Vapi

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/vapi-assistant-divine.json"
VAPI_CONFIG="$SCRIPT_DIR/vapi-config.json"

# Extract API key from config
VAPI_KEY=$(jq -r '.private_key' "$VAPI_CONFIG")

if [ -z "$VAPI_KEY" ] || [ "$VAPI_KEY" == "null" ]; then
    echo "Error: Could not find private_key in vapi-config.json"
    exit 1
fi

echo "Creating Divine CDL-A Recruiter assistant..."
echo "Using config: $CONFIG_FILE"

# Create the assistant
RESPONSE=$(curl -s -X POST "https://api.vapi.ai/assistant" \
    -H "Authorization: Bearer $VAPI_KEY" \
    -H "Content-Type: application/json" \
    -d @"$CONFIG_FILE")

# Check for errors
if echo "$RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
    echo "Error creating assistant:"
    echo "$RESPONSE" | jq '.'
    exit 1
fi

# Extract assistant ID
ASSISTANT_ID=$(echo "$RESPONSE" | jq -r '.id')

if [ -z "$ASSISTANT_ID" ] || [ "$ASSISTANT_ID" == "null" ]; then
    echo "Error: Could not extract assistant ID from response"
    echo "$RESPONSE" | jq '.'
    exit 1
fi

echo ""
echo "Assistant created successfully!"
echo "================================"
echo "Assistant ID: $ASSISTANT_ID"
echo "Name: $(echo "$RESPONSE" | jq -r '.name')"
echo ""

# Update vapi-config.json with the new assistant ID
jq --arg id "$ASSISTANT_ID" --arg created "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
    '.assistant_id = $id | .created_at = $created | .status = "ready_for_phone_number"' \
    "$VAPI_CONFIG" > "$VAPI_CONFIG.tmp" && mv "$VAPI_CONFIG.tmp" "$VAPI_CONFIG"

echo "Updated vapi-config.json with assistant ID"
echo ""
echo "Next steps:"
echo "1. Go to https://dashboard.vapi.ai"
echo "2. Add a phone number (Twilio or Vonage)"
echo "3. Assign it to this assistant"
echo "4. Run test call: ./test-call.sh +1XXXXXXXXXX"
