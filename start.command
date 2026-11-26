#!/bin/sh
# Spustenie na macOS / Linuxe:  ./start.sh   (na macOS aj dvojklikom na start.command)
cd "$(dirname "$0")" || exit 1
exec python3 netdash.py "$@"
