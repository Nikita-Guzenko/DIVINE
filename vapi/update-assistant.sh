#!/bin/bash

# Divine CDL-A Recruiter - Update Assistant Script
# Run this script to update the assistant configuration on Vapi

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="$SCRIPT_DIR/vapi-assistant-divine.json"
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

echo "Updating Divine CDL-A Recruiter assistant..."
echo "Assistant ID: $ASSISTANT_ID"
echo "Using config: $CONFIG_FILE"

# Update the assistant
RESPONSE=$(curl -s -X PATCH "https://api.vapi.ai/assistant/$ASSISTANT_ID" \
    -H "Authorization: Bearer $VAPI_KEY" \
    -H "Content-Type: application/json" \
    -d @"$CONFIG_FILE")

# Check for errors
if echo "$RESPONSE" | jq -e '.error' > /dev/null 2>&1; then
    echo "Error updating assistant:"
    echo "$RESPONSE" | jq '.'
    exit 1
fi

echo ""
echo "Assistant updated successfully!"
echo "================================"
echo "Assistant ID: $(echo "$RESPONSE" | jq -r '.id')"
echo "Name: $(echo "$RESPONSE" | jq -r '.name')"
echo ""

# Update timestamp in vapi-config.json
jq --arg updated "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
    '.updated_at = $updated' \
    "$VAPI_CONFIG" > "$VAPI_CONFIG.tmp" && mv "$VAPI_CONFIG.tmp" "$VAPI_CONFIG"

echo "Updated vapi-config.json with timestamp"
