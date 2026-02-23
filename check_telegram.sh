#!/bin/bash
# Hook script for Claude Code - checks Telegram messages

MESSAGES_FILE="/Users/nikitaguzenko/Desktop/DIVINE/telegram_messages.txt"
LAST_READ_FILE="/Users/nikitaguzenko/Desktop/DIVINE/.telegram_last_read"

if [ -f "$MESSAGES_FILE" ]; then
    # Get line count of last read
    if [ -f "$LAST_READ_FILE" ]; then
        LAST_LINE=$(cat "$LAST_READ_FILE")
    else
        LAST_LINE=0
    fi

    CURRENT_LINES=$(wc -l < "$MESSAGES_FILE")

    if [ "$CURRENT_LINES" -gt "$LAST_LINE" ]; then
        echo "📱 Новые сообщения из Telegram:"
        tail -n +$((LAST_LINE + 1)) "$MESSAGES_FILE"
        echo "$CURRENT_LINES" > "$LAST_READ_FILE"
    fi
fi
