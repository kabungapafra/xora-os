#!/usr/bin/env bash
# Runs xora from this source folder (on Ubuntu today, or installed into the OS image as /usr/bin/xora)
here="$(dirname "$(readlink -f "$0")")"
PYTHONPATH="$here${PYTHONPATH:+:$PYTHONPATH}" exec python3 -P -m xora "$@"
