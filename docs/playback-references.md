# Playback references and compatibility decisions

## PM4K seek handling

Reference: [PM4K player implementation at revision 2707bbe](https://github.com/pannal/plex-for-kodi/blob/2707bbe72a7ea829b69bdd7ebb753c700552b4d0/lib/player.py#L626).

PM4K provides an alternate seek path for platforms with delayed audio after absolute seeks. It pauses when needed, computes a relative offset, invokes Kodi's `Seek` built-in, verifies the resulting position, and restores the previous playing state. Its default recommendation depends on platform detection. It also verifies startup seeks after display resets; a seek callback can report the requested target even when the actual player clock has not reached it.

These are distinct concerns:

- **Transport:** Silo must supply authorized byte ranges with usable throughput.
- **Player convergence:** Kodi must reach the requested position and resume advancing.
- **Output:** Picture and audio must recover together, including passthrough and HDR mode changes.

The Silo client already verifies the observed resume position before reporting progress. A local comparison of absolute seeks and paused relative seeks did not establish a consistent latency advantage for either method. Do not enable a platform workaround solely from the platform name. Keep Kodi's native controls while investigating audio recovery separately. Any adopted workaround must preserve pause state, bound retries, and stop acting when another item replaces playback.

PM4K is a behavioral reference. Its implementation has not been vendored into this add-on.

## Development compatibility status

This is a validation matrix, not a release support guarantee. Deployment-specific evidence and fixture identities remain in ignored local testing storage.

| Requirement | Evidence or remaining work |
| --- | --- |
| Original HTTP playback | Representative H.264 SDR movie plays with its soundtrack; authenticated range reads work |
| Progress and resume | Silo records position; UI resume reaches it; startup samples wait for the observed position |
| Pause and resume | A 60-second pause keeps a stable clock and playback resumes |
| Seeking | Forward/backward seeks converge; variable recovery latency and audible A/V sync still need qualification |
| Stop cleanup | A stopped test session's media URL is no longer accessible; replacement/failure checks remain |
| Episode playback | Browsing works; playback acceptance remains |
| Audio selection | Kodi controls retained; track changes and language/default mapping remain to be validated |
| HDR10 and Dolby Vision/FEL | Not qualified; the initial decoder declaration is SDR only |
| DTS-HD MA, TrueHD, Atmos | No end-to-end output qualification; decoder/stream labels do not prove AVR output |
| Sustained bitrate | Short range reads measured; long playback across bitrate peaks remains |
| Media credential rotation | API refresh works; native media reopening with fresh credentials remains |
| Quality and subtitles | Not implemented; preserve server policy rather than invent unsupported routes |
