# Playback references and compatibility decisions

## PM4K seek handling

Reference: [PM4K player implementation at revision 2707bbe](https://github.com/pannal/plex-for-kodi/blob/2707bbe72a7ea829b69bdd7ebb753c700552b4d0/lib/player.py#L626).

PM4K provides an alternate seek path for platforms with delayed audio after absolute seeks. It pauses when needed, computes a relative offset, invokes Kodi's `Seek` built-in, verifies the resulting position, and restores the previous playing state. Its default recommendation depends on platform detection. It also verifies startup seeks after display resets; a seek callback can report the requested target even when the actual player clock has not reached it.

These are distinct concerns:

- **Transport:** Silo must supply authorized byte ranges with usable throughput.
- **Player convergence:** Kodi must reach the requested position and resume advancing.
- **Output:** Picture and audio must recover together, including passthrough and HDR mode changes.

The Silo client already verifies the observed resume position before reporting progress. A local comparison of absolute seeks and paused relative seeks did not establish a consistent latency advantage for either method. Do not enable a platform workaround solely from the platform name. Keep Kodi's native controls while investigating audio recovery separately. Any adopted workaround must preserve pause state, bound retries, and stop acting when another item replaces playback.

The comparison used four seeks in alternating order on one SDR movie. It measured position convergence and subsequent clock advancement, not audible recovery or HDR display transitions. It cannot establish whether the alternate path solves the delayed-audio problem that motivated PM4K's workaround. Before adding a workaround, reproduce that symptom with a known soundtrack and observe audio alongside player time.

PM4K also delays embedded-subtitle re-enabling until a resume seek settles, because switching streams can trigger a display reset. Apply the same ordering constraint when implementing Silo subtitle selection: verify the requested position after any stream or output transition instead of treating a seek callback as proof.

PM4K is a behavioral reference. Its implementation has not been vendored into this add-on.

## Development compatibility status

This is a validation matrix, not a release support guarantee. Deployment-specific evidence and fixture identities remain in ignored local testing storage.

| Requirement | Evidence or remaining work |
| --- | --- |
| Original HTTP playback | Representative H.264 SDR movie plays with its soundtrack; authenticated range reads work |
| Progress and resume | Silo records position; UI resume reaches it; startup samples wait for the observed position |
| Pause and resume | A 60-second pause keeps a stable clock and playback resumes |
| Seeking | Forward/backward seeks converge; variable recovery latency and audible A/V sync still need qualification |
| Stop cleanup | The episode played through the UI loses media access after stop and releases playback authority |
| External replacement | A second authorized video is identified independently, continues advancing after the old owner releases authority, and loses access after its test session is stopped |
| Failed start | A missing-file request leaves Kodi idle and a subsequent valid video plays without a Kodi restart; post-resolution failures have focused cleanup regression tests |
| Episode playback | Representative H.264 SDR episode with E-AC-3 advances for over 70 seconds |
| Audio selection | Native Kodi selection passes DTS-HD MA → AC-3 while paused → resume → DTS-HD MA, preserving position and advancing afterward; receiver input reports confirm both formats. Source metadata maps native choices into Silo replans. A nondefault AC3 soundtrack passes original → 360p → Auto with paused position and native selection preserved. Ambiguous metadata is rejected; broader soundtrack coverage remains unqualified |
| HDR10 | Installed add-on plays original 2160p HEVC HDR10; device HDMI reports HDR10/ST2084 at 2160p24 before and after pause/seek/resume. Sustained playback and broader output coverage remain |
| Dolby Vision/FEL | Installed add-on preserves the original Profile 7 stream through client-managed presentation. CoreELEC's playback overlay reports profile 7.6 FEL, 12-bit H.265, hardware AM-H265 decoding, and RGB DV tunnel output; HDMI reports standard DV before and after pause/seek/resume. This is player/driver evidence on the tested FEL-capable setup, not a claim based only on the DV flag. The captured DV video plane is distorted and cannot establish displayed picture quality |
| TrueHD/Atmos | During installed HDR10 and DV playback, Kodi reports active passthrough, device HDMI reports eight-channel MAT, and the receiver reports Dolby TrueHD and Atmos input before and after pause/seek/resume. Sustained and audible speaker-output qualification remain |
| DTS-HD MA | Installed original playback reports Kodi passthrough and receiver DTS-HD MA before and after pause/seek/resume. Sustained and audible speaker-output qualification remain |
| Sustained bitrate | A 606-second original DV/TrueHD window on a source averaging about 83 Mbit/s passed 114 clock/cache samples, with no sampled buffering and at most 0.11s clock drift; backward seek passed afterward. Short authenticated media-path probes measured 852–871 Mbit/s. These results do not establish a maximum bitrate or peak coverage. Debug captures showed renderer skips increasing from 10 to 15 with player drops at zero; uninstrumented render-quality qualification remains |
| Media credential rotation | Loopback media transport uses fresh authority on each read; real rotation during a 60-second pause followed by resume and seeking passes without changing playback identity. Natural-expiry acceptance remains |
| Text subtitles | Authenticated WebVTT sidecar displays captions; repeated starts select it and retain selection after seeking. Loading and selection are asynchronous, so track count alone is insufficient evidence. SRT is not yet device-qualified |
| Quality controls | Remote menu passes original → 360p → Auto → 360p, preserving position and pause; Kodi's decoded resolution confirms delivery. A further SDR check passes all six choices offered for its source (720p-high/medium/low, 480p, 480p-low, and 360p), with decoded heights, paused positions, resume, forward/backward seeks, and return to Auto independently checked. Stopping during an observed busy quality transition clears owner state and leaves playback stopped through a subsequent three-second observation; the playback lock and screensaver checks pass. Other sources and external replacement during reopen remain to qualify |
| Combined subtitle and quality controls | Selected WebVTT cues visibly render at the same scene in original, 360p HLS, and returned Auto playback; Off removes the cue in HLS. HLS subtitle Off/On replans reopen the demuxer; forward/backward seeks and clock advancement pass afterward. Embedded MKV PGS cues also visibly render in original, server-burned 360p HLS, and returned Auto playback, with Off removing the same cue in both deliveries. Initial SDH selection and same-language SDH-to-English switching pass. This PGS fixture is SDR H.264; HDR combinations, ASS/fonts, and other bitmap formats remain unqualified |
