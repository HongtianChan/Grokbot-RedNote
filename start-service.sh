#!/bin/bash
# Run this in Ghostty. Do not use Terminal.app.
cd "$(dirname "$0")"
exec /usr/bin/python3 src/grokbot_rednote.py --service
