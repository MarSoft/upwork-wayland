#!/usr/bin/env nix-shell
#!nix-shell -i bash -p python3 python3Packages.dbus-next grim xdotool
# Nix launcher for screenshot_adapter.py: provides its runtime deps
# (dbus-next, grim, xdotool) via a transient nix-shell, then execs the portable
# script. grim = screenshots; xdotool = activity heartbeat (XTEST keypress).
# On non-Nix distros, install python3 + dbus-next + grim + xdotool and run
# screenshot_adapter.py directly instead.
exec python3 "$(dirname "$(realpath "$0")")/screenshot_adapter.py" "$@"
