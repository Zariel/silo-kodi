# Silo for Kodi

Browse your Silo movies and TV shows and watch them in Kodi. Sign in with a QR code, choose your profile, and explore your Home page and libraries without importing them into Kodi's library.

## Install

You need Kodi 21 or later, a Silo account, and the address of your Silo server.

1. Download `plugin.video.silo-VERSION.zip` from [GitHub Releases](https://github.com/Zariel/silo-kodi/releases).
2. Copy the ZIP to a location Kodi can access.
3. In Kodi, open **Settings → Add-ons → Install from zip file** and select the ZIP. If prompted, enable **Unknown sources** in Kodi's add-on settings.
4. Open **Silo** from your add-ons.

To update, download and install the replacement ZIP in the same way. Your saved sign-in is preserved.

## Sign in

1. Enter your Silo server address, including `https://`.
2. Choose **Sign in**.
3. Scan the QR code with your phone, or open the displayed address in a browser. Sign in to Silo and approve the device.
4. Choose your profile and enter its PIN if prompted.

Use **Account** in the sidebar to switch profiles or sign out. Stop playback before changing profiles or servers.

## Browse and search

Home shows your Silo sections in their configured order and uses your Silo accent colour. Home preloads its shelves so you can move between them without waiting for another request. Continue Watching loads more cards automatically as you scroll across. For other sections, choose **View all**, or select a library from the sidebar. More titles load automatically as you scroll.

Choose **Search** to find movies, TV shows, and episodes when supported by your server. Select a title to view its details, or open a TV show to browse its seasons and episodes.

Open a title's options with your remote's Menu button, a long press of Select if mapped to Kodi's context menu, or **C** on a keyboard. Options include:

- View details or play/resume a video.
- Mark a title watched or unwatched.
- Add or remove favourites.
- Add or remove watchlist entries.
- Remove a card from Continue Watching or Next Up when offered.

Marking a TV show watched or unwatched applies to all its episodes. Removing an episode from Continue Watching or Next Up hides its whole show from both rows until you watch it again; it does not mark the show watched.

## Watch

Choose **Play** on a movie or episode. If Silo has saved your progress, you can resume or start from the beginning. Use Kodi's playback controls to pause, seek, and select an audio track.

Episode lists show watched ticks and saved viewing progress. Choose **Play next** on an episode's details to move to the following available episode. At the end of an episode, you can choose to play the next one or return to browsing; episodes never start automatically.

When Silo provides an intro marker for your selected video, **Skip intro** appears during the intro. Select it to skip, or press Back to dismiss it.

Press **Back** during playback to pause and return to the page you launched it from. Further Back presses follow your browsing history, restoring selection and scroll position. Choose **Resume playback** in the sidebar, or **Resume** on the playing title, to continue watching. Home and library shortcuts start a fresh browsing history.

While video is playing or paused, a bottom playback bar shows its title, time and progress. Move Down from the bottom of a list or the sidebar to use Play/Pause, skip back 10 seconds, skip forward 30 seconds, Fullscreen, Options or Stop. Up or Back returns to your previous browsing control.

While browsing during playback, open the context menu and choose **Playback options**:

- **Quality:** choose from the qualities offered by Silo, or **Auto** to let Silo choose. Changing quality preserves your position and pause state.
- **Subtitles:** choose an available subtitle track or **Off**. Use this menu for subtitle changes so Silo can apply them when changing playback quality.

4K, HDR10, Dolby Vision, and lossless or surround audio depend on your Kodi device, its settings, and your TV or audio system. Configure video output and audio passthrough in Kodi.
