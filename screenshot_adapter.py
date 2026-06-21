#!/usr/bin/env python3
# Bridge script between Gnome Screenshot API and wlroots-based Wayland composer
# Usage:
# Run this script in the background.
# Make sure it will connect to the same DBus session daemon as Upwork does,
# i.e. they should get the same value in DBUS_SESSION_BUS_ADDRESS env var.
#
# Dependencies:
# - python 3.5+
# - dbus-next python package (pip install dbus-next)
# - grim (https://github.com/emersion/grim)
# - swayidle (optional, for activity time tracking)

import asyncio
import datetime as dt
import json
import os
import random
from pathlib import Path
import subprocess
import sys

from dbus_next.aio import MessageBus
from dbus_next.service import ServiceInterface, method, dbus_property, signal
from dbus_next import Variant, BusType, DBusError


def debug(*msg):
    try:
        print(*msg, file=sys.stderr)
    except OSError:
        # can happen if stderr's terminal was closed
        pass


class ScreenshotInterface(ServiceInterface):
    def __init__(self, on_shot=None):
        super().__init__('org.gnome.Shell.Screenshot')
        self.on_shot = on_shot

    @method()
    def Screenshot(self, include_cursor: 'b', flash: 'b', filename: 's') -> 'bs':
        debug(dt.datetime.now(dt.UTC), 'Got Screenshot call', include_cursor, flash, filename)
        subprocess.run(['grim', *(['-c'] if include_cursor else []), filename])
        if self.on_shot:
            self.on_shot()
        return [True, filename]

    @method()
    def ScreenshotWindow(self, include_frame: 'b', include_cursor: 'b', flash: 'b', filename: 's') -> 'bs':
        debug('Got Window call', include_frame, include_cursor, flash, filename)
        # TODO capture current window somehow
        subprocess.run(['grim', *(['-c'] if include_cursor else []), filename])
        return [True, filename]

    @method()
    def ScreenshotArea(self, x: 'i', y: 'y', width: 'i', height: 'i', flash: 'b', filename: 's') -> 'bs':
        debug('Got Area call', (x, y, width, height), flash, filename)
        subprocess.run(['grim', '-g', f'{x},{y} {width}x{height}', filename])
        return [True, filename]


class IdleTime(ServiceInterface):
    def __init__(self, on_shot):
        super().__init__('org.gnome.Mutter.IdleMonitor')
        self.last_active = dt.datetime.now(dt.UTC)
        self.is_active = True  # we'll get 'timeout' when user becomes idle
        self.on_shot = on_shot

    async def start(self):
        try:
            self.monitor = await asyncio.create_subprocess_exec(
                'swayidle',
                '-w', 'timeout', '1', 'echo timeout', 'resume', 'echo resume',
                stdout=subprocess.PIPE,
            )
            self.worker = asyncio.create_task(self.run())
        except FileNotFoundError:
            debug('swayidle not available')
            self.worker = None

    async def run(self):
        async for line in self.monitor.stdout:
            line = line.decode().strip()
            if line == 'timeout':
                self.is_active = False
                # user was active 1 second ago
                self.last_active = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
            elif line == 'resume':
                self.is_active = True
                self.last_active = dt.datetime.now(dt.UTC)
                # Inject immediately on wake-up so Upwork registers the
                # idle->active transition without waiting for the next heartbeat.
                if heartbeat_enabled():
                    asyncio.create_task(inject_activity())
            else:
                debug('Got unknown line', line)

    @method()
    def GetIdletime(self) -> 't':
        # What unit do we want?
        if self.is_active:
            delta = dt.timedelta(0)  # active right now
        else:
            delta = dt.datetime.now(dt.UTC) - self.last_active
        debug(dt.datetime.now(dt.UTC), 'Asked idletime. It is', delta)
        if self.on_shot:
            self.on_shot()
        # return milliseconds
        return round(delta.total_seconds() * 1000)


DUMMY = dt.datetime(2000, 1, 1, tzinfo=dt.UTC)

# Where the LD_PRELOAD shim (gdk/gdk-screenshotter.c, TEMPFILE) writes the
# screenshot it grabs via grim. When Upwork runs in XWayland mode it takes
# screenshots through the native gdk path rather than the GnomeShell DBus
# method, so this file's mtime is the only signal of "last screenshot taken".
SHIM_SHOT = Path('/tmp/upwork.png')

class WaybarReporter:
    def __init__(self):
        self.last_shot = DUMMY
        self.last_idle = DUMMY
        self.update = asyncio.Event()

    def screenshot_taken(self):
        self.last_shot = dt.datetime.now(dt.UTC)
        self.update.set()
        # XXX this is a temporary workaround,
        # because Upwork's native notification steals focus in Sway
        # and doesn't seem to show up in Sway's window tree.
        subprocess.run([
            'notify-send',
            'Upwork', 'Screenshot taken!',
            # TODO: use dbus instead, to add actions:
            # /org/freedesktop/Notifications
            # org.freedesktop.Notifications
            # Notify
            # 'notify-send', 0, '', Title, Body, dict(urgency=1, ...), -1
        ])

    def idle_taken(self):
        self.last_idle = dt.datetime.now(dt.UTC)
        self.update.set()

    async def report_waybar(self):
        second = dt.timedelta(seconds=1)
        minute = second * 60
        interval = minute * 10
        hour = minute * 60

        while True:
            # Prefer the in-process value set via the GnomeShell DBus path;
            # fall back to the shim's screenshot file mtime (XWayland mode, or
            # after a restart when last_shot has reset to DUMMY).
            last_shot = self.last_shot
            if last_shot == DUMMY:
                try:
                    last_shot = dt.datetime.fromtimestamp(
                        SHIM_SHOT.stat().st_mtime, dt.UTC)
                except OSError:
                    pass

            now = dt.datetime.now(dt.UTC)
            current_interval = dt.datetime.fromtimestamp(
                now.timestamp() // 600 * 600, dt.UTC)
            next_interval = current_interval + interval
            prev_interval = current_interval - interval
            since_last = now - last_shot
            till_next = next_interval - now

            # this interval has its screenshot taken already
            this_taken = last_shot > current_interval
            # a screenshot landed in the previous (or current) interval. Upwork
            # takes EXACTLY ONE shot per clock-aligned 10-min interval, at an
            # unpredictable moment within it -- so consecutive shots can be up to
            # ~20 min apart. prev_taken aligns with that structure (unlike a flat
            # time window, which would wrongly read "inactive" across a long gap).
            prev_taken = last_shot > prev_interval

            # Best-effort "is Upwork tracking enabled right now?" -- a positive
            # reminder so you notice if you forgot to start tracking (the Upwork
            # window often sits hidden on a rear workspace). We can only infer it
            # from the two tracking-only signals Upwork gives us:
            #   - it polls GetIdletime (~every 60s) WHILE IDLE (it skips polling
            #     when raw input is flowing, since it already knows you're active);
            #   - it takes a screenshot, exactly one per 10-min interval.
            # Either means tracking is (most likely) on. Blind spot: active +
            # tracking, in a fresh interval before its shot lands, may briefly read
            # "inactive" until the shot or an idle poll arrives. Better than nothing.
            since_lastidle = now - self.last_idle
            # +5s margin so we don't blip "off" for a moment right at the ~60s
            # poll boundary (the loop re-evaluates every second).
            tracking_on = since_lastidle < minute + 5*second or prev_taken

            percentage = 100 - till_next.total_seconds() / 600 * 100
            if since_last > 24*hour:
                since_last_fmt = 'inf'
            else:
                since_last_fmt = str(since_last // minute * minute)[:-3]
                if since_last_fmt.startswith('0:'):
                    since_last_fmt = since_last_fmt[2:]
            till_next_fmt = str(till_next // second * second)[-4:]
            cls = 'done' if this_taken else 'active' if tracking_on else 'inactive'

            if last_shot != DUMMY:
                lastshot_local = last_shot.astimezone()
                text = f'@{lastshot_local:%H:%M}  {since_last_fmt}'
            else:
                text = f'@__:__  {since_last_fmt}'
            if tracking_on:
                text += f'  x{till_next_fmt}'
            #if not this_taken:
            #    text += f'  {round(percentage, 1)}%'

            print(json.dumps({
                # Generic stuff — for both waybar and noctalia
                'text': text,
                'class': cls,
                'alt': cls,
                'percentage': round(percentage),
                'tooltip': f'{cls}',
                # Noctalia-specific addons (harmless for waybar)
                'icon': 'check' if this_taken else 'eye',
                'color': 'secondary' if this_taken else 'primary' if tracking_on else 'tertiary',
            }), flush=True)

            # Sleep for one second, but wake up early if update event happens
            try:
                await asyncio.wait_for(self.update.wait(), 1)
                self.update.clear()  # reset event
            except asyncio.TimeoutError:
                pass


# Activity heartbeat: while the user is genuinely active (per swayidle), inject a
# few no-op keypresses per minute so Upwork's keystroke counter stays alive.
#
# Why this is needed: Upwork (XWayland) counts keyboard/mouse activity via XInput2
# raw events, which only see input routed to XWayland windows. Input to NATIVE
# Wayland windows is invisible to it, so working in Wayland-native apps shows up as
# 0 keystrokes. We inject F13 -- a keysym bound to nothing, so it types no text and
# triggers no shortcut, but still counts as a raw keypress. xdotool uses XTEST.
#
# This deliberately mirrors REAL presence only (gated on swayidle 'active'); it does
# NOT fabricate activity while you are away. Rate is intentionally low and randomized.
# Set UPWORK_ACTIVITY_HEARTBEAT=0 to disable, or UPWORK_HEARTBEAT_MIN/MAX=<sec>.

# No-op keysym to inject (bound to nothing -> types nothing, triggers nothing).
HEARTBEAT_KEY = 'F13'

async def inject_activity():
    """Inject one no-op keypress (XTEST via xdotool). Returns False if xdotool
    is missing so callers can stop trying."""
    try:
        p = await asyncio.create_subprocess_exec(
            'xdotool', 'key', HEARTBEAT_KEY,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        await p.wait()
        return True
    except FileNotFoundError:
        debug('xdotool not available; activity injection off')
        return False

def heartbeat_enabled():
    return os.environ.get('UPWORK_ACTIVITY_HEARTBEAT', '1') not in ('0', '', 'false')

async def activity_heartbeat(idle):
    if not heartbeat_enabled():
        debug('activity heartbeat disabled')
        return
    try:
        lo = float(os.environ.get('UPWORK_HEARTBEAT_MIN', '8'))
        hi = float(os.environ.get('UPWORK_HEARTBEAT_MAX', '16'))
    except ValueError:
        lo, hi = 8.0, 16.0
    if hi < lo:
        lo, hi = hi, lo
    while True:
        await asyncio.sleep(random.uniform(lo, hi))
        if not idle.is_active:
            continue
        if not await inject_activity():
            return


async def main():
    bus = MessageBus() #bus_type=BusType.SYSTEM)
    await bus.connect()

    workers = [
        # empty future to make sure we will wait forever
        asyncio.get_event_loop().create_future(),
    ]

    reporter = WaybarReporter()
    workers.append(reporter.report_waybar())

    screenshots = ScreenshotInterface(on_shot=reporter.screenshot_taken)
    bus.export('/org/gnome/Shell/Screenshot', screenshots)
    idle = IdleTime(on_shot=reporter.idle_taken)
    await idle.start()
    if idle.worker:
        workers.append(idle.worker)
        workers.append(activity_heartbeat(idle))
    bus.export('/org/gnome/Mutter/IdleMonitor/Core', idle)
    # Now we are ready to handle messages!
    await bus.request_name('org.gnome.Shell.Screenshot')
    if idle.worker:
        await bus.request_name('org.gnome.Mutter.IdleMonitor')

    debug('Started!')

    # run forever (FIXME is it a good way?)
    #await asyncio.get_event_loop().create_future()
    await asyncio.gather(*workers)


if __name__ == '__main__':
    asyncio.run(main())
