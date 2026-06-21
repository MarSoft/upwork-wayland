#!/usr/bin/env nix-shell
#!nix-shell -i bash -p python3 python3Packages.dbus-next grim
# Nix launcher for screenshot_adapter.py: provides its runtime deps
# (dbus-next, grim) via a transient nix-shell, then execs the portable script.
# On non-Nix distros, install python3 + dbus-next + grim and run
# screenshot_adapter.py directly instead.
exec python3 "$(dirname "$(realpath "$0")")/screenshot_adapter.py" "$@"
