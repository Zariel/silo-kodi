"""A cancellable countdown owned by the active browser."""
import math
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui


class _Countdown(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, title, seconds, **kwargs):
        super().__init__(*args, **kwargs)
        self.title = title
        self.seconds = seconds
        self.deadline = None
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.accepted = False

    def onInit(self):
        self.getControl(20).setLabel(self.title)
        self.deadline = time.monotonic() + self.seconds
        self.update()

    def update(self):
        if self.deadline is None or self.done.is_set():
            return
        remaining = max(0, math.ceil(self.deadline - time.monotonic()))
        self.getControl(21).setLabel('Playing in {} {}'.format(remaining, 'second' if remaining == 1 else 'seconds'))
        if remaining == 0:
            self.finish(True)

    def finish(self, accepted):
        # The remote callback and timeout compete; the first decision wins.
        with self.lock:
            if not self.done.is_set():
                self.accepted = accepted
                self.done.set()

    def onClick(self, control):
        if control in (10, 11):
            self.finish(control == 10)

    def onAction(self, action):
        if action.getId() in (9, 10, 13, 92):
            self.finish(False)


def confirm_next(title, seconds, valid):
    dialog = _Countdown('NextEpisode.xml', xbmcaddon.Addon('plugin.video.silo.kodi').getAddonInfo('path'),
                        'Default', '1080i', title=title, seconds=seconds)
    monitor = xbmc.Monitor()
    opening_deadline = time.monotonic() + 10
    try:
        dialog.show()
        while not dialog.done.is_set():
            if monitor.abortRequested() or not valid():
                return False
            if dialog.deadline is None and time.monotonic() >= opening_deadline:
                return False
            dialog.update()
            monitor.waitForAbort(.1)
        return dialog.accepted and valid() and not monitor.abortRequested()
    finally:
        dialog.close()
