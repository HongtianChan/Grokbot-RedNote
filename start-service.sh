#!/bin/bash
# Run this in Ghostty. Do not use Terminal.app.
cd "$(dirname "$0")"
exec /usr/bin/python3 xhs_reader.py --service
