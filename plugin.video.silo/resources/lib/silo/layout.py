"""Shared sidebar and content geometry for every browser view."""


class _BrowserLayout:
    # These controls fill the content region. Posters and buttons keep their
    # intrinsic sizes; lists let Kodi derive the number of visible cards.
    _FILL = (12, 20, 21, 22, 23, 24, 25, 26, 27, 30, 32, 40, 41, 42, 200, 210, 220, 230, 231, 232)
    _LISTS = (100, 200, 210, 220, 230, 231, 232)
    _COMPACT = 120
    _EXPANDED = 360

    def __init__(self, window):
        self.window = window
        self.widths = {identifier: window.getControl(identifier).getWidth() for identifier in self._FILL}

    def apply(self, expanded):
        window = self.window
        selections = {identifier: window.getControl(identifier).getSelectedPosition()
                      for identifier in self._LISTS if window.getControl(identifier).size()}
        inset = self._EXPANDED if expanded else self._COMPACT
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
