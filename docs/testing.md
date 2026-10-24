# Test on CoreELEC

Use the development loop below to validate code through the actual Kodi interpreter and player. The setup build probes the public Silo API and plays a temporary local silent WAV. It does not authenticate, browse libraries, or stream Silo media yet.

## Prerequisites

- A CoreELEC device reachable over SSH and Kodi JSON-RPC on a trusted LAN.
- Python 3.11, SSH, and the standard library. Run `nix develop path:.` for the pinned toolchain. No Python package installation is needed.
- For video/output qualification, power on the display and AVR and select the player's input. They are not required for directory execution or the silent local smoke test.

Keep real addresses, SSH options, hardware inventories, cluster paths, and validation results in ignored `.local-testing/`. Create a local `env.sh` there with your own values for these variables:

```sh
export SILO_SSH_TARGET=root@kodi.example.test
export SILO_RPC_URL=http://kodi.example.test:8080/jsonrpc
export SILO_SERVER_URL=https://silo.example.test
```

Source the file from the repository root with `. .local-testing/env.sh`. Optional `SILO_SSH_OPTIONS` supplies SSH arguments, such as a local config or known-hosts file. Establish and verify the target host key before unattended deployment; do not disable host-key checking. Configure **Server URL** in the Silo add-on's Kodi settings before running the connectivity check. The add-on has no packaged server default.

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

`check` validates the manifest, entry point, and Python 3.11 syntax. `package` writes a deterministic ZIP to `dist/`, containing only the explicit add-on file allowlist. Extend that list when adding resources. Scratch space and credentials cannot enter the ZIP through a recursive directory walk.

`probe` reads OS, interpreter, Kodi version, active players, HDMI capability files, Ethernet link speed, and Silo's public server identity. Capture raw results under `.scratch/`, not in version control.

`deploy` refuses to run while Kodi is playing. It copies and verifies the ZIP by SHA-256, extracts a fresh add-on tree, and saves the previous tree at `/storage/.kodi/temp/silo-kodi-previous`. It asks Kodi to rescan and enable the add-on through supported interfaces, then executes its directory through `Files.GetDirectory`. No Kodi restart or SQLite edits are needed. The backup holds only the previous deployment and is replaced on the next deploy. User data under `userdata/addon_data` is untouched.

`smoke` also refuses to interrupt existing playback. It creates a 120-second silent stereo WAV in Kodi's temporary directory, opens the hidden development route `plugin://plugin.video.silo/?action=smoke`, and observes the resolved file, player readiness, a stable paused clock, a seek to 45 seconds, resumed clock advancement, and stop. It removes the fixture in cleanup. It stops only the fixture if another client takes over during cleanup. The development route is not listed in the add-on UI and must be removed when real playback replaces the scaffold.

Kodi RPC commands acknowledge requests before all player state is updated. The harness waits for resulting state with a deadline rather than assuming a command response means a completed transition.

You can override either target:

```sh
python scripts/dev.py probe --ssh root@kodi.example.test --rpc http://kodi.example.test:8080/jsonrpc --server https://silo.example.test
```

To open the UI, use **Add-ons > Video add-ons > Silo** (it is also an audio provider). Expect a server connectivity row and a setup-build notice. To read relevant logs:

```sh
ssh $SILO_SSH_OPTIONS "$SILO_SSH_TARGET" 'tail -n 150 /storage/.kodi/temp/kodi.log'
```

Before sharing logs after authentication is implemented, redact signed stream URLs, tokens, pairing codes, and private titles. Do not enable verbose HTTP logging as a routine test setting.

## Restore the previous development build

Stop playback and leave the Silo directory first. Restore only this add-on, then rerun the directory check:

```sh
ssh $SILO_SSH_OPTIONS "$SILO_SSH_TARGET" 'test -d /storage/.kodi/temp/silo-kodi-previous && rm -rf /storage/.kodi/addons/plugin.video.silo && mv /storage/.kodi/temp/silo-kodi-previous /storage/.kodi/addons/plugin.video.silo && kodi-send --action=UpdateLocalAddons'
python scripts/dev.py browse
```

The connectivity assertion applies to this scaffold; change it when the real root directory replaces the setup notice. If there is no backup, uninstall **Silo** using Kodi's add-on manager. No cluster changes need rollback.

## Qualify real Silo playback

This is the acceptance procedure for the client implementation, not a claim that the scaffold passes it.

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
