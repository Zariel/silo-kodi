"""Shared sidebar and content geometry for every browser view."""


class _BrowserLayout:
    # These controls fill the content region. Posters and buttons keep their
    # intrinsic sizes; lists let Kodi derive the number of visible cards.
    _FILL = (12, 20, 21, 22, 23, 24, 25, 26, 27, 30, 32, 200, 210, 220)
    _LISTS = (100, 200, 210, 220)
    _COMPACT = 120
    _EXPANDED = 360

    def __init__(self, window, shelves=()):
        self.window = window
        self.lists = self._LISTS + tuple(shelves)
        fill = self._FILL + tuple(identifier + offset for identifier in shelves for offset in (0, 1))
        self.widths = {identifier: window.getControl(identifier).getWidth() for identifier in fill}

    def apply(self, expanded, force=False):
        window = self.window
        inset = self._EXPANDED if expanded else self._COMPACT
        # Geometry belongs to sidebar transitions, not item focus notifications.
        if not force and window.getControl(400).getPosition()[0] == inset:
            return
        selections = {identifier: window.getControl(identifier).getSelectedPosition()
                      for identifier in self.lists if window.getControl(identifier).size()}
        difference = inset - self._COMPACT
        # Shrink/move content before showing the expanded menu; hide the menu
        # before growing content. Intermediate frames cannot overlap either.
        if not expanded:
            window.setProperty('sidebar_expanded', 'false')
            window.getControl(100).setWidth(72)
            window.getControl(400).setPosition(inset, 0)
        for identifier, width in self.widths.items():
            window.getControl(identifier).setWidth(width - difference)
        if expanded:
            window.getControl(400).setPosition(inset, 0)
            window.getControl(100).setWidth(315)
            window.setProperty('sidebar_expanded', 'true')
        for identifier, position in selections.items():
            window.getControl(identifier).selectItem(position)

    def reveal(self, direction):
        # Kodi animates the rendered group without moving its layout or focus.
        self.window.getControl(400).setAnimations([
            ('Conditional', 'effect=slide start=0,{} end=0,0 time=150 tween=cubic easing=out condition=true reversible=false'.format(14 * direction)),
            ('Conditional', 'effect=fade start=80 end=100 time=120 condition=true reversible=false'),
        ])

    def playback(self, visible):
        # Keep fully focused rows above the overlay; the bottom preview may fade beneath it.
        for identifier, height in ((200, 885), (220, 405)):
            control = self.window.getControl(identifier)
            selection = control.getSelectedPosition() if control.size() else None
            control.setHeight(height - 80 if visible else height)
            if selection is not None:
                control.selectItem(selection)
