#!/usr/bin/env bash

UPWORK=${UPWORK:-$(which upwork)}

if [ -z "$DISPLAY" ]; then
    echo "Looks like Xwayland is not available!"
    exit 1
fi
if [ -z "$WAYLAND_DISPLAY" ]; then
    echo "This wrapper is not needed when running in X11 environment!"
    echo
    # safely fallthrough
    exec "$UPWORK" "$@"
fi

# override session type detection
export XDG_SESSION_TYPE=x11
# save real wayland display for our .so to use
export WAYLAND_DISPLAY_REAL=$WAYLAND_DISPLAY
# make upwork run in Xorg mode, not Wayland mode
export WAYLAND_DISPLAY=
# load our .so
export LD_PRELOAD=$(dirname "$(realpath "$0")")/gdk-screenshotter.so
# Stop Upwork's override-redirect notification windows from stealing keyboard
# focus under sway: the shim rewrites their _NET_WM_WINDOW_TYPE NORMAL->NOTIFICATION
# so wlroots' override_redirect_wants_focus() leaves them unfocused on map.
export UPWORK_FIX_NOTIF_FOCUS=1
# enable debug logging
#LOG4JS_CONFIG=debug.json
#UPWORK_NOTIF_DEBUG=1
exec "$UPWORK" "$@"
