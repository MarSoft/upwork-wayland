#!/usr/bin/env python
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
        debug(dt.datetime.utcnow(), 'Got Screenshot call', include_cursor, flash, filename)
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
        self.last_active = dt.datetime.utcnow()
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
                pass  # do nothing
            elif line == 'resume':
                self.last_active = dt.datetime.utcnow()
            else:
                debug('Got unknown line', line)

    @method()
    def GetIdletime(self) -> 't':
        # What unit do we want?
        delta = dt.datetime.utcnow() - self.last_active
        debug(dt.datetime.utcnow(), 'Asked idletime. It is', delta)
        if self.on_shot:
            self.on_shot()
        # return milliseconds
        return round(delta.total_seconds() * 1000)


class WaybarReporter:
    def __init__(self):
        self.last_shot = dt.datetime(2000, 1, 1)
        self.last_idle = dt.datetime(2000, 1, 1)
        self.update = asyncio.Event()

    def screenshot_taken(self):
        self.last_shot = dt.datetime.utcnow()
        self.update.set()

    def idle_taken(self):
        self.last_idle = dt.datetime.utcnow()
        self.update.set()

    async def report_waybar(self):
        second = dt.timedelta(seconds=1)
        minute = second * 60
        interval = minute * 10
        hour = minute * 60

        while True:
            now = dt.datetime.utcnow()
            current_interval = dt.datetime.fromtimestamp(
                now.timestamp() // 600 * 600)
            next_interval = current_interval + interval
            prev_interval = current_interval - interval
            since_last = now - self.last_shot
            till_next = next_interval - now

            since_lastidle = now - self.last_idle
            # When active, it will query idletime at least every minute.
            # So if they didn't query it for a minute then they are inactive.
            idle_active = since_lastidle < minute

            # this interval has its screenshot taken already
            this_taken = self.last_shot > current_interval
            prev_taken = self.last_shot > prev_interval

            percentage = 100 - till_next.total_seconds() / 600 * 100
            if since_last > 24*hour:
                since_last_fmt = 'inf'
            else:
                since_last_fmt = str(since_last // minute * minute)[:-3]
                if since_last_fmt.startswith('0:'):
                    since_last_fmt = since_last_fmt[2:]
            till_next_fmt = str(till_next // second * second)[-4:]
            cls = 'done' if this_taken else 'active' if idle_active else 'inactive'

            text = f'@{self.last_shot:%H:%M}  {since_last_fmt}'
            if idle_active:
                text += f'  {till_next_fmt}'
            #if not this_taken:
            #    text += f'  {round(percentage, 1)}%'

            print(json.dumps({
                'text': text,
                'class': cls,
                'alt': cls,
                'percentage': round(percentage),
                'tooltip': f'{cls}',
            }), flush=True)

            # Sleep for one second, but wake up early if update event happens
            try:
                await asyncio.wait_for(self.update.wait(), 1)
                self.update.clear()  # reset event
            except asyncio.TimeoutError:
                pass


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
