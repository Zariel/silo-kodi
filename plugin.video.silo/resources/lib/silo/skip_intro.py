"""A playback-owned, dismissible native Kodi intro prompt."""
import xbmc
import xbmcgui

from .markers import intro_at


class SkipIntro(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, segment, **kwargs):
        super().__init__(*args, **kwargs)
        self.segment = segment
        self.current = None
        self.requested = None
        self.dismissed = set()
        self.visible = False

    def update(self, position, duration, enabled=True):
        current = intro_at(self.segment, position, duration) if enabled else None
        requested, self.requested = self.requested, None
        if requested is not None and requested == current:
            self.close()
            return requested[1]
        self.current = current
        fullscreen = xbmcgui.getCurrentWindowId() == 12005
        if not current or current in self.dismissed or not fullscreen:
            self.close()
        elif not self.visible and xbmcgui.getCurrentWindowDialogId() <= 9999:
            self.visible = True
            self.show()
        return None

    def onClick(self, control):
        if control == 10 and self.current:
            self.requested = self.current
            self.dismissed.add(self.current)
            self.close()

    def onAction(self, action):
        identifier = action.getId()
        if identifier in (1, 2, 3, 4, 9, 10, 92):
            if self.current:
                self.dismissed.add(self.current)
            self.close()
            navigation = {1: 'StepBack', 2: 'StepForward', 3: 'BigStepForward', 4: 'BigStepBack'}
            if identifier in navigation:
                xbmc.executebuiltin('Action({})'.format(navigation[identifier]))

    def close(self):
        if self.visible:
            self.visible = False
            super().close()
