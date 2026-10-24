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

After signing in and choosing a profile, open Silo to show the first video library. Use the left navigation to change library or open **Account**. Moving right returns to the content selection. Choose a poster to open its details, a season to show episodes, and an episode to show its details. **Back** restores the preceding screen and selection.

Scroll to **Load more** after the first 50 titles and select it. Verify that another page appears and focus remains at the first appended card. Open that card and go Back; the loaded page and selection must remain. Empty libraries and unavailable artwork must not prevent navigation. **Play** negotiates media with Silo; original-file presentation is delegated to Kodi with declared codec eligibility up to 2160p. Confirm actual HDR/audio output on the target instead of inferring it from source badges or a successful start.

Switch profiles through **Account** and return to browsing. The client must rebuild the library root for the selected profile rather than restore the previous profile's history. Screenshots and private catalog evidence belong in ignored local storage.

When Silo reports a saved position, **Play** offers **Resume from …** and **Play from beginning**. Resume leaves position selection to Silo's playback plan; starting over explicitly requests position zero. Canceling the menu must not start a session. Check the actual player clock after either choice, then stop and verify that the same detail screen returns with **Play** focused.

For subtitle acceptance, the `action=play` plugin route accepts an optional `subtitle` query parameter containing a `track_id` from Silo's subtitle inventory. Pass that identity unchanged; a Kodi subtitle index is not interchangeable with it. Omitting the parameter leaves selection to Silo. The playback owner applies supported text sidecars after startup seeking, or hides subtitles when Silo returns Off. Verify Kodi selects the added sidecar, inspect visible captions after seeking, then play again with an Off decision and check that the previous selection does not leak. The remote selection UI and other subtitle delivery modes remain unfinished.

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

For quality acceptance, play a supported SDR video, seek away from the beginning, and choose **Now playing → Quality → 360p** when Silo offers it. Verify Kodi's decoded resolution and clock independently of the menu selection. Pause, select **Auto**, and verify the source resolution returns without losing pause or position. Repeat the lower-quality choice while paused, then resume and check clock advancement. Auto describes the preference; Silo can choose a lower delivered rung according to policy. Also test selected subtitles, seeks in both directions, external replacement, and stopping during a transition before qualifying broader use.

For visual subtitle checks, compare the same known cue in original playback, lower-quality HLS, and returned Auto playback, then verify Off removes it. After seeking, observe a position clearly distinct from the pre-seek clock and let playback advance into the cue before briefly pausing to capture it. A clock reading can still reflect the previous position immediately after a seek request; pausing at that point can capture a stale frame. Inspect the actual picture and subtitle, then stop the owned playback and verify idle display protection.

For subtitle controls, start a video and return to the Silo browser. Choose **Now playing → Subtitles**, select a supported track, and verify Kodi's selected subtitle and visible cues. Seek, pause, choose **Off**, then choose the track again while paused. The clock must stay paused; after resuming, it must advance without restarting the video. Return to fullscreen through **Now playing → Return to video**. A track marked **Unavailable** must report its limitation without sending a replan. Close playback and confirm that the menu no longer offers the ended session.

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
