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

<!-- - Optional: [`swayidle`](https://github.com/swaywm/swayidle) in `PATH` - for accurate idle time calculation -->
