# Test on CoreELEC

Use the development loop below to validate code through the actual Kodi interpreter and player. The client provides library and detail screens, account authentication, and native original playback. The playback smoke test uses a chosen Silo video through the installed add-on.

## Prerequisites

- A CoreELEC device reachable over SSH and Kodi JSON-RPC on a trusted LAN.
- Python 3.11, SSH, and the standard library. Run `nix develop path:.` for the pinned toolchain. No Python package installation is needed.
- For playback checks, power on the display and AVR and select the player's input. They are not required for the nonvisual server probe.

Keep real addresses, SSH options, hardware inventories, cluster paths, and validation results in ignored `.local-testing/`. Create a local `env.sh` there with your own values for these variables:

```sh
export SILO_SSH_TARGET=root@kodi.example.test
export SILO_RPC_URL=http://kodi.example.test:8080/jsonrpc
export SILO_SERVER_URL=https://silo.example.test
```

Source the file from the repository root with `. .local-testing/env.sh`. Optional `SILO_SSH_OPTIONS` supplies SSH arguments, such as a local config or known-hosts file. Establish and verify the target host key before unattended deployment; do not disable host-key checking. Configure **Server address** on the Silo account screen, or set `SILO_SERVER_URL` before deployment to configure it through the headless helper. The add-on has no packaged server default.

If Nix cannot write its cache in a restricted workspace, set `XDG_CACHE_HOME=/tmp/silo-kodi-cache` for the Nix command.

## Edit, package, deploy, observe

From the repository root, in the development shell:

```sh
python scripts/dev.py check
python scripts/dev.py package
python scripts/dev.py probe
python scripts/dev.py deploy
python scripts/dev.py smoke
```

`check` validates the manifest, XML resources, and Python 3.11 syntax, then runs the authentication contract tests. `package` writes a deterministic ZIP to `dist/`, containing only the explicit add-on file allowlist. Extend that list when adding resources. Scratch space and credentials cannot enter the ZIP through a recursive directory walk.

`probe` reads OS, interpreter, Kodi version, active players, HDMI capability files, Ethernet link speed, and Silo's public server identity. Capture raw results under `.scratch/`, not in version control.

`deploy` refuses to run while Kodi is playing. It copies and verifies the ZIP by SHA-256, extracts a fresh add-on tree, and saves the previous tree at `/storage/.kodi/temp/silo-kodi-previous`. It asks Kodi to rescan and enable the add-on through supported interfaces, waits for the expected version, then executes its status route through `Files.GetDirectory`. No Kodi restart or SQLite edits are needed. The backup holds only the previous deployment and is replaced on the next deploy. Deployment preserves user data under `userdata/addon_data`. When `--server` or `SILO_SERVER_URL` is set, it configures that server through the shared helper; using the same URL preserves login, while changing it clears origin-bound credentials.

Before running `smoke`, sign in and choose a profile in the add-on. Set `SILO_TEST_FILE_ID` in ignored local configuration to the `file_id` of a known supported video at least 60 seconds long, or pass `--file-id FILE_ID`. This test starts the video from the beginning and changes its Silo watch progress.

`smoke` refuses to interrupt existing playback. It opens the normal playback route, checks player readiness, pauses and verifies a stable clock, seeks to 45 seconds, resumes and verifies clock advancement, then stops its own playback. It matches a unique invocation identity instead of assuming a fixed player ID. Cleanup preserves another client's replacement item. On an idle device, a separate target process verifies release of playback authority before the harness activates the configured screensaver and observes it active for two seconds. If the returning browser wakes the display, cleanup retries activation within a 30-second deadline; an unobserved activation fails the check. This short check does not qualify HDR, audio passthrough, sustained bitrate, or watch-state resume.

For a longer playback check, set `SILO_TEST_FILE_ID` and `SILO_TEST_CONTENT_ID` in your ignored configuration, choose a video longer than eleven minutes, and run:

```sh
python scripts/dev.py smoke --observe-seconds 600
```

After pause/seek/resume, this observes the owned player's clock and Kodi's buffering flag every five seconds for ten minutes. It fails if playback stops, is replaced, pauses, reports buffering, or diverges from elapsed time by more than three seconds. It prints progress once per minute and uses the same verified cleanup on success or failure. These sampled observations can miss brief interruptions and do not measure dropped frames, bitrate peaks, or maximum throughput. Qualify HDMI/audio output independently; `VideoPlayer.VideoBitrate` is stream metadata, not a runtime throughput measurement.

Workstation acceptance scripts can reuse `protect_idle_display(args)` from `scripts/dev.py` after stopping their own player and waiting for its disappearance. It never stops a player. A false return means replacement playback appeared and was left alone; an exception means idle protection could not be verified. Call it from cleanup so failed checks also protect the display. Do not start another playback check while Kodi is still showing a playback error or busy dialog from the previous run.

Kodi RPC commands acknowledge requests before all player state is updated. The harness waits for resulting state with a deadline rather than assuming a command response means a completed transition.

You can override either target:

```sh
python scripts/dev.py probe --ssh root@kodi.example.test --rpc http://kodi.example.test:8080/jsonrpc --server https://silo.example.test
```

To open the account screen, use **Add-ons > Video add-ons > Silo**. Enter your server address, choose **Sign in**, and approve the QR code through Silo in your browser. Then choose a profile. The add-on is a video provider; audio support refers to soundtracks within video files. To read relevant logs:

```sh
ssh $SILO_SSH_OPTIONS "$SILO_SSH_TARGET" 'tail -n 150 /storage/.kodi/temp/kodi.log'
```

Before sharing logs after authentication is implemented, redact signed stream URLs, tokens, pairing codes, and private titles. Do not enable verbose HTTP logging as a routine test setting.

## Check browsing with the remote

After signing in and choosing a profile, open Silo to show Home. Use the left navigation to change library or open **Account**. Moving right returns to the content selection and collapses the sidebar to icons. Moving left into the sidebar expands its labels; verify that both states retain recognizable icons and the selected destination. Choose a poster to open its details, a season to show episodes, and an episode to show its details. **Back** restores the preceding screen and selection.

Scroll through a library with more than 100 titles. Verify that pages load automatically ahead of the selection, without a **Load more** card or a loading banner. Open a card beyond the first page and go Back; the loaded cards and selection must remain. During a paging outage, existing cards must remain usable and the error must explain how to retry by reopening the page. Empty libraries and unavailable artwork must not prevent navigation. **Play** negotiates media with Silo; original-file presentation is delegated to Kodi with declared codec eligibility up to 2160p. Confirm actual HDR/audio output on the target instead of inferring it from source badges or a successful start.

During playback, press **Back** to reveal the originating Home row, library, or episode list with the playing title selected. Press **Back** again from that collection to return to the same fullscreen video without restarting it. Opening another title's details still uses ordinary Back navigation to its collection. Use the remote's context-menu action (or **C** on a keyboard) in the browser to open **Subtitles** or **Quality**. After playback stops, Back must resume ordinary browsing navigation.

Switch profiles through **Account** and return to browsing. The client must rebuild the library root for the selected profile rather than restore the previous profile's history. Screenshots and private catalog evidence belong in ignored local storage.

When Silo reports a saved position, **Play** offers **Resume from …** and **Play from beginning**. Resume leaves position selection to Silo's playback plan; starting over explicitly requests position zero. Canceling the menu must not start a session. Check the actual player clock after either choice, then stop and verify that the originating collection and selected title return.

For subtitle acceptance, the `action=play` plugin route accepts an optional `subtitle` query parameter containing a `track_id` from Silo's subtitle inventory. Pass that identity unchanged; a Kodi subtitle index is not interchangeable with it. Omitting the parameter leaves selection to Silo. The playback owner applies supported text sidecars after startup seeking, or hides subtitles when Silo returns Off. Verify Kodi selects the added sidecar, inspect visible captions after seeking, then play again with an Off decision and check that the previous selection does not leak. The remote menu also supports embedded PGS in MKV. Verify the native selected track and visible cue in original playback, server-burned captions in 360p HLS, and restoration on returning to Auto. Check Off at the same cue in both deliveries. Test initial selection and switching between same-language tracks with distinct titles; track count alone is insufficient. Authored ASS/fonts and additional bitmap formats remain unfinished.

Developer playback routes must also include `content=<catalog-content-id>` to exercise audio reconciliation and native subtitle selection. The normal browser supplies this automatically. The owner fetches the selected file's audio and subtitle inventories under the originating profile; do not pass track metadata or a guessed Kodi index in the route. Select a nondefault soundtrack through Kodi, pause, change to 360p, and return to Auto. Verify the returned native audio selection, clock, and pause state independently. Include a subtitle change and resume before stopping the owned player and verifying idle display protection.

## Test authentication without the TV

The packaged `auth.py` helper uses the same implementation and protected credential store as the account screen. Run it on the target over SSH to keep tokens on the device:

```sh
ssh $SILO_SSH_OPTIONS "$SILO_SSH_TARGET" 'python3 /storage/.kodi/addons/plugin.video.silo/auth.py pair --profile-dir /storage/.kodi/userdata/addon_data/plugin.video.silo'
```

Open the returned verification link and approve **Silo Kodi**. The output includes a QR image path if you prefer to copy the image to ignored local storage. It does not include tokens or the secret polling code. Leave the Kodi account screen closed during this headless check; closing that screen cancels its pending sign-in.

Poll until the returned status is `approved`, respecting `poll_after` when present:

```sh
ssh $SILO_SSH_OPTIONS "$SILO_SSH_TARGET" 'python3 /storage/.kodi/addons/plugin.video.silo/auth.py poll --profile-dir /storage/.kodi/userdata/addon_data/plugin.video.silo'
```

Replace `poll` with `profiles` to list account profiles, then use `select --profile-id PROFILE_ID` to select one. For PIN entry, allocate an interactive SSH terminal with `-t`; the helper prompts without echoing the PIN. Use `verify` to make authenticated account, profile, and library requests, and `status` to inspect the persisted selection. These commands never print access or refresh tokens.

Use `cancel` to cancel pending pairing. Use `logout` only when you intend to sign out of this installation. Redeploy and run `verify` again to check persistence. A new helper process verifies process-independent storage, but does not substitute for a separate Kodi restart acceptance test.

For isolated workstation tests, run `python plugin.video.silo/auth.py configure --server "$SILO_SERVER_URL" --profile-dir .local-testing/test-account`, then use the same commands and directory. This creates a separate Silo device login and requires browser approval. It is not an authentication bypass.

Keep screenshots brief on OLED displays and return to the existing screensaver after visual checks. Decode a captured QR independently and exercise directional navigation, cancellation, and profile selection on Kodi; the headless helper alone cannot prove those UI behaviors.

## Restore the previous development build

Stop playback and leave the Silo directory first. Restore only this add-on, then rerun the directory check:

```sh
ssh $SILO_SSH_OPTIONS "$SILO_SSH_TARGET" 'test -d /storage/.kodi/temp/silo-kodi-previous && rm -rf /storage/.kodi/addons/plugin.video.silo && mv /storage/.kodi/temp/silo-kodi-previous /storage/.kodi/addons/plugin.video.silo && kodi-send --action=UpdateLocalAddons'
python scripts/dev.py browse
```

`browse` invokes a nonvisual status route to check connectivity without opening the account screen. If there is no backup, uninstall **Silo** using Kodi's add-on manager. No cluster changes need rollback.

## Qualify real Silo playback

For quality acceptance, play a supported SDR video, seek away from the beginning, and choose **context menu → Quality → 360p** when Silo offers it. Verify Kodi's decoded resolution and clock independently of the menu selection. Pause, select **Auto**, and verify the source resolution returns without losing pause or position. Repeat the lower-quality choice while paused, then resume and check clock advancement. Auto describes the preference; Silo can choose a lower delivered rung according to policy. Also test selected subtitles, seeks in both directions, external replacement, and stopping during a transition before qualifying broader use.

For visual subtitle checks, compare the same known cue in original playback, lower-quality HLS, and returned Auto playback, then verify Off removes it. After seeking, observe a position clearly distinct from the pre-seek clock and let playback advance into the cue before briefly pausing to capture it. A clock reading can still reflect the previous position immediately after a seek request; pausing at that point can capture a stale frame. Inspect the actual picture and subtitle, then stop the owned playback and verify idle display protection.

For native audio selection, inspect Kodi's current stream list instead of assuming a file opens on its default track. Kodi can retain a previous choice. Select an identifiable track, pause, select a different codec or language, and verify the position remains paused. Resume and independently verify the receiver's input format, then return to the original track and check continued playback. Kodi stream indices are ordinals in the current demuxed stream list; they are not portable identities across original and HLS playback. Receiver display names can be abbreviated, so distinguish a naming mismatch from an actual format failure.

For subtitle controls, start a video and return to the Silo browser. Choose **context menu → Subtitles**, select a supported track, and verify Kodi's selected subtitle and visible cues. Seek, pause, choose **Off**, then choose the track again while paused. The clock must stay paused; after resuming, it must advance without restarting the video. Return to fullscreen through **Back**. A track marked **Unavailable** must report its limitation without sending a replan. Close playback and confirm that the menu no longer offers the ended session.

This is the acceptance procedure for the complete client, not a claim that the development build passes every step. Representative SDR movies and episodes play, and the UI resume and start-over choices reach their expected positions. Seeking recovery varies. Mid-playback media credential refresh, output qualification, and failure/replacement checks remain open. See the [compatibility status](playback-references.md) for measured results and limits.

1. Approve device sign-in in your existing Silo browser session. Use two account profiles and a PIN-protected profile for authority tests. An admin API key is neither required nor a substitute for account sign-in.
2. Browse a library with more than 50 entries and a series with multiple seasons. Compare access and metadata to the Silo web UI. Switch profile, revisit an old navigation entry, and verify it cannot play with stale authority.
3. Play a known SDR movie from the add-on. Record the server plan's delivery, source file identity, codec, container, average/peak bitrate if known, and audio format without recording the signed URL. Require original HTTP delivery for this milestone.
4. Pause for over 45 seconds; verify the session survives. Seek forward, backward, near the end, and from the beginning. Observe actual player time and HTTP range behavior. Stop and reopen using Silo's independently observed resume state. Repeat after Kodi restart and after token refresh.
5. Repeat with the following media matrix. Confirm the TV/AVR's displayed output as well as Kodi/driver state; software success alone is insufficient.

| Fixture | Evidence required |
| --- | --- |
| H.264 SDR + AAC/AC-3 | Correct picture/sound, pause/seek, selected audio/subtitle tracks |
| HEVC Main10 HDR10 | Original plan, PQ/BT.2020 output, TV HDR indication, no unintended tone mapping |
| DV profile 5 or 8 | Original stream, matching decoder/output mode, correct colors and TV DV indication |
| DV profile 7 FEL discriminator | Both layers preserved, CoreELEC decoder evidence, known visual difference proving FEL reconstruction; DV badge alone fails this check |
| TrueHD/Atmos and DTS-HD MA/DTS:X | AVR confirms expected bitstream when passthrough is configured; distinguish decoding to PCM from passthrough |
| High-bitrate remux | Sustained playback across representative peaks without underruns; seek recovery and actual media-path throughput |

6. Exercise denied/expired profile authority, network loss, playback failure before readiness, immediate stop, and replacement by another item. Verify no duplicate sessions or cross-profile progress. Do not change output settings or the server to hide a failure.

Store fixture identifiers and private measurements in `.scratch/`. Keep deployment-specific target reports in ignored `.local-testing/`. Commit only generic supported limits and sanitized test fixtures. The eventual capability declaration must be no broader than these results.

## Home acceptance

Open the add-on after profile selection. Home must be the initial page, with visible row titles in the profile's server order and the configured accent. Move horizontally to a nonfirst card, open details, and return: the same content must regain focus even if refreshing the row changes its position. If that card disappears, focus must remain on a valid card. Move down beyond the second row and back up; empty rows must not trap navigation.

Choose **View all**, open a title, then return through the section to Home. Verify focus returns to **View all**. In a section with more than 50 cards, keep scrolling and verify the server cursor supplies additional cards automatically without resetting selection. Switch to a library and back to Home through the sidebar. Verify an empty Home leaves library navigation accessible.

After playback, verify Continue Watching reflects the server's updated progress. Switch profiles and verify the previous profile's rows are not retained. Exercise unavailable layout support separately from authentication and network failures: only unsupported endpoints permit compatibility fallback. Keep screenshots brief and verify idle display protection after closing the browser.

## Account navigation and PIN acceptance

Launch Silo from Kodi's video add-ons or through JSON-RPC `Addons.ExecuteAddon` with `addonid: plugin.video.silo`. The browser runs as a script; the root plugin route delegates to it after returning to Kodi Home. Closing Silo must return to Kodi instead of launching another browsing window. Playback remains on the `action=play` plugin route.

Open **Account**, choose profiles, and select a PIN-protected test profile. Incorrect input must leave the original profile active. Correct input must open that profile's Home after closing Account, without retaining the original profile's Continue Watching rows. Switch back and verify the original rows return. Use Kodi's masked text entry: its numeric input ignores the hidden-input option, and Silo accepts nonnumeric PINs. Canceling the dialog must not submit a PIN attempt.

The device check passes incorrect/correct PIN entry and switching in both directions with an empty-history temporary profile. The temporary profile is removed and the original selection restored after acceptance. This does not qualify every content restriction or profile-token expiry scenario.

## Verified Home refresh and ZIP upgrade

An empty-history test profile played an episode, sought beyond two minutes, and stopped. The existing Home window then showed that episode in Continue Watching. An independent Silo watch read confirmed the saved position, and a section read confirmed the same content ID. The browser window ID remained unchanged across playback. The test restored the original profile and removed its temporary profile afterward.

The ZIP upgrade check builds twice and compares the bytes, deploys the archive, then independently hashes every installed package file against its ZIP member. It compares the saved session file before and after deployment, checks its `0600` permissions, and makes an authenticated account request afterward. These checks pass for the development upgrade path. A separate test installs the same archive through Kodi's **Install from zip file** dialog: the installed code is replaced, its digest remains correct, and saved session data is unchanged. With an isolated empty add-on data directory, launching the installed package opens manual server setup without inheriting the existing account. The original data is restored byte-for-byte afterward. These checks do not establish execution of the GitHub Release workflow or repeat browser approval for a new account.

## Home endpoint compatibility

When `/home/layout` is unsupported, use `/home/sections` and preserve its order. When a per-section card endpoint is unsupported, read that section from the aggregate response. Refresh this response on return rather than keeping stale progress. Tests inject unsupported-endpoint responses while using live aggregate data; this exercises the installed client without changing the server. Authentication, rate-limit, transport, and temporary server failures must not trigger a fallback.

If both layout and aggregate endpoints are unsupported, discover visible rows through `/profile/sections/settings?scope=home`. Use their positions when present, otherwise the default recipe order; preserve the returned IDs. A device check injects unavailable layout and aggregate endpoints and missing positions while fetching real settings and section cards. Home, details, and return focus pass. If all discovery endpoints are unsupported, Home reports that limitation and libraries remain available. Do not guess `default-*` IDs from server seed templates.

## Temporary window harness cleanup

Close a test-owned `WindowXML` normally and let `doModal()` return before finishing its script. `StopScript` requests interpreter abort; it does not call the window’s `close()` method. Forced script shutdown during playback’s return to a modal window left the GUI unresponsive in one acceptance run. A service restart restored the GUI and preserved the saved Silo login; the corrected harness passed playback and verified idle protection afterward. Use observed menu focus and dialog identity before sending selections, rather than relying on fixed delays.

## Test token renewal without waiting

Deterministic authentication tests advance the client clock to exercise proactive refresh, overlapping callers, refresh failure, and profile isolation. Rejected-token tests verify one refresh/retry and persistence for a fresh client instance; a second rejection must not loop. Run these through `python scripts/dev.py check`.

For device acceptance, start owned playback and pause it. Under the shared credential-store lock, save the original expiry and an access-token fingerprint, then make only `expires_at` overdue. Let the normal playback owner perform renewal; do not call refresh directly or change server token lifetime. Observe a different persisted credential fingerprint and a future deadline from another process. Verify pause and playback identity remain unchanged, seek to a distant position, resume, and observe clock advancement. Repeat with supported HLS delivery. On failure, restore the old deadline only if the credential fingerprint is unchanged; never overwrite a newly rotated credential pair. Keep this test state and evidence outside version control.

Both original playback and 360p HLS pass this synthetic-expiry check, followed by ownership release and verified idle protection. This exercises real renewal and persistence while avoiding a wait for the server token lifetime. Natural wall-clock expiry remains optional additional coverage, not the renewal release gate.

## Real logout and restart persistence

A separate development-readiness login was renewed through the real server and signed out using the production `Session.logout()` path. A fresh client instance observed cleared local authority, and the server rejected the revoked refresh token with HTTP 401. Session identities were checked before and after to prove that the installed add-on login was distinct and remained authenticated. The installed login also survived the recovery service restart, retained its selected profile, and authenticated afterward. These checks avoid signing the user out merely to repeat device approval.

## Browser and control-plane recovery acceptance

A temporary browser wrapper injects one catalog connection failure and removes artwork URLs from the next real page response. The installed window retains sidebar focus and a readable error; selecting the library again loads its cards. Missing artwork renders as rounded placeholder surfaces with readable titles, and details and return focus work. The wrapper closes its modal normally before removal; idle protection is observed afterward.

Temporary playback wrappers import the installed player without modifying its code or server configuration. One injects three consecutive progress-request failures, exhausting the immediate retries. Playback continues, later reporting succeeds, and independent server watch-state and stopped-stream reads verify persistence and cleanup. Another drops successful start, replan, and stop replies after the real server commits them. It verifies that subsequent retries preserve the request body and receive the same session/plan identity or stop receipt. The paused quality transition and final cleanup pass. Both temporary add-ons are disabled and removed after testing, and playback ownership and idle protection are verified.
