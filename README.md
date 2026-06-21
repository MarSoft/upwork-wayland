Upwork-wayland
==============

This project is a simple bridge between Upwork or any other tool supporting Gnome's screenshot protocol
and your favourite [wlroots](https://github.com/swaywm/wlroots-rs)-based Wayland composer like [Sway](https://swaywm.org).

Install dependencies, run the script as a daemon and enjoy.

Make sure that both the script and Upwork application use the same DBus session bus,
i.e. their DBUS_SESSION_BUS_ADDRESS environment variables have the same value!
Otherwise they won't be able to see each other.

Dependencies
------------

- Python 3.5 or newer
- `dbus-next` python package (`pip install dbus-next` should work)
- [`grim` tool](https://github.com/emersion/grim) somewhere in `PATH`
- [`swayidle`](https://github.com/swaywm/swayidle) in `PATH` — for idle/active detection
- [`xdotool`](https://github.com/jordansissel/xdotool) in `PATH` — for the activity heartbeat (below)

Activity heartbeat
------------------

Upwork (under XWayland) counts keyboard/mouse activity via XInput2 raw events,
which only see input routed to XWayland windows. Input to **native Wayland**
windows is invisible to it, so working in Wayland-native apps is counted as zero
keystrokes. While `swayidle` reports the user as active, the adapter injects a
low, randomized rate of no-op keypresses (the `F13` keysym — bound to nothing, so
it types no text and triggers no shortcut) via `xdotool` (XTEST), keeping the
counter alive. It mirrors **real presence only** — nothing is injected while you
are idle.

```sh
UPWORK_ACTIVITY_HEARTBEAT=0   # disable the heartbeat
UPWORK_HEARTBEAT_MIN=8        # min seconds between injections (default 8)
UPWORK_HEARTBEAT_MAX=16       # max seconds between injections (default 16)
```

Moving notifications away from a top bar
---------------------------------------

The `LD_PRELOAD` shim under `gdk/` (built with `make`, loaded via `gdk/upwork.sh`)
also repositions Upwork's notification windows. Upwork pins them to the very
top-right of the screen, where they cover a top bar/panel (e.g. a Wayland
status bar). The shim intercepts the X11 `ConfigureWindow` requests Upwork sends
through libxcb and shifts the notifications down by a fixed offset, preserving
their stacking and slide-in/out animations.

This feature is **on by default**. Build options:

```sh
make                       # enabled, 40px downward shift (default)
make NOTIF_Y_OFFSET=64     # enabled, custom shift
make MOVE_NOTIFICATIONS=0  # disabled entirely (no xcb interception)
```

At run time you can override the offset without recompiling, or enable verbose
tracing, via environment variables (set them where `upwork.sh` runs):

```sh
UPWORK_NOTIF_Y_OFFSET=64   # downward shift in pixels
UPWORK_NOTIF_DEBUG=1       # log each intercepted request to stderr
```

Stopping notifications from stealing keyboard focus
--------------------------------------------------

Upwork's notification windows are override-redirect X11 windows typed
`_NET_WM_WINDOW_TYPE_NORMAL`. wlroots' `override_redirect_wants_focus()` returns
true for `NORMAL` (it's not in the no-focus list of menu/tooltip/notification/…
types), so sway grants the notification keyboard focus the moment it maps —
stealing focus from whatever you were typing in (e.g. a terminal's cursor goes
hollow and input stops). `focus_on_window_activation none` does NOT fix this; the
grab happens in wlroots' map handler, not via `_NET_ACTIVE_WINDOW`.

The shim works around it by intercepting the `ChangeProperty` that sets
`_NET_WM_WINDOW_TYPE` and rewriting `NORMAL` → `NOTIFICATION` (which IS in the
no-focus list), so sway leaves the window unfocused. Atom IDs are resolved at
run time (via Xlib on a separate connection), and the rewrite only fires when the
value is actually `NORMAL`, so it can't corrupt anything.

Opt-in via env var (set in `upwork.sh`):

```sh
UPWORK_FIX_NOTIF_FOCUS=1   # rewrite NORMAL->NOTIFICATION; off by default
```

The proper long-term fix belongs in sway/wlroots (a way to treat selected
override-redirect `NORMAL` windows as no-focus); this is a per-app workaround.
