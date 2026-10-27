"""A playback-owned, dismissible native Kodi intro prompt."""
import xbmc
import xbmcgui

from .markers import intro_at


class SkipIntro(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, segment, automatic=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.segment = segment
        self.automatic = automatic
        self.current = None
        self.requested = None
        self.dismissed = set()
        self.visible = False
        self.setProperty('intro_dismissed', 'false')

    def update(self, position, duration, enabled=True):
        current = intro_at(self.segment, position, duration) if enabled else None
        requested, self.requested = self.requested, None
        if requested is not None and requested == current:
            self.close()
            return requested[1]
        self.current = current
        fullscreen = xbmcgui.getCurrentWindowId() == 12005
        if self.automatic:
            self.close()
            if (current and current not in self.dismissed and fullscreen
                    and xbmcgui.getCurrentWindowDialogId() <= 9999
                    and not xbmc.getCondVisibility('Player.Paused')):
                self.dismissed.add(current)
                return current[1]
            return None
        if not current or current in self.dismissed or not fullscreen:
            self.close()
        elif not self.visible and xbmcgui.getCurrentWindowDialogId() <= 9999:
            # Kodi can deliver a queued click while querying or opening a window.
            if current not in self.dismissed:
                self.visible = True
                self.show()
                if current in self.dismissed:
                    self.close()
        return None

    def _dismiss(self):
        if self.current:
            self.dismissed.add(self.current)
        # Hide the entire prompt before asking Kodi to close its native dialog.
        self.setProperty('intro_dismissed', 'true')
        self.close()

    def onClick(self, control):
        if control == 10 and self.current:
            self.requested = self.current
            self._dismiss()

    def onAction(self, action):
        identifier = action.getId()
        if identifier in (1, 2, 3, 4, 9, 10, 92):
            self._dismiss()
            navigation = {1: 'StepBack', 2: 'StepForward', 3: 'BigStepForward', 4: 'BigStepBack'}
            if identifier in navigation:
                xbmc.executebuiltin('Action({})'.format(navigation[identifier]))

    def close(self):
        if self.visible:
            self.visible = False
            super().close()
