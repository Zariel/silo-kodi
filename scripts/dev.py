#!/usr/bin/env python3
"""Build and exercise the add-on using Python's standard library."""

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from urllib.parse import urlencode
import uuid
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parent.parent
ADDON = ROOT / "plugin.video.silo"
ADDON_ID = ADDON.name


def check():
    manifest = ET.parse(ADDON / "addon.xml").getroot()
    assert manifest.attrib["id"] == ADDON_ID
    entry = manifest.find("extension[@point='xbmc.python.pluginsource']")
    assert entry is not None and (ADDON / entry.attrib["library"]).is_file()
    for path in ADDON.rglob("*.xml"):
        ET.parse(path)
    for path in [*ADDON.rglob("*.py"), *(ROOT / "scripts").glob("*.py")]:
        ast.parse(path.read_text(), filename=str(path), feature_version=(3, 11))
    print("Manifest, entry point, and Python 3.11 syntax: OK")


def package_files():
    files = [ADDON / name for name in ("addon.xml", "addon.py", "auth.py", "LICENSE.txt", "THIRD_PARTY.md")]
    for directory, extensions in (("resources/lib", {".py"}), ("resources/skins", {".xml", ".png"})):
        files.extend(path for path in (ADDON / directory).rglob("*")
                     if path.is_file() and path.suffix in extensions and "__pycache__" not in path.parts)
    files.append(ADDON / "resources/lib/segno/LICENSE")
    return sorted(files)


def package(release_tag=None):
    check()
    version = ET.parse(ADDON / "addon.xml").getroot().attrib["version"]
    if release_tag is not None and release_tag != 'v' + version:
        raise SystemExit('Release tag must match addon.xml: v' + version)
    output = ROOT / "dist" / "{}-{}.zip".format(ADDON_ID, version)
    output.parent.mkdir(exist_ok=True)
    # An explicit allowlist keeps scratch files and credentials out of releases.
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in package_files():
            name = path.relative_to(ADDON).as_posix()
            info = zipfile.ZipInfo(ADDON_ID + "/" + name, (2026, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes(), zipfile.ZIP_DEFLATED)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix('.zip.sha256').write_text(digest + '  ' + output.name + '\n')
    print(output.relative_to(ROOT))
    return output


def rpc(args, method, params=None):
    body = {"jsonrpc": "2.0", "id": 1, "method": method}
    if params is not None:
        body["params"] = params
    request = Request(args.rpc, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError("{}: {}".format(method, result["error"]))
    return result["result"]


def ssh(args, command, data=None):
    options = shlex.split(os.environ.get("SILO_SSH_OPTIONS", ""))
    result = subprocess.run(
        ["ssh", *options, "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
         args.ssh, command], input=data, capture_output=True, check=True,
    )
    return result.stdout.decode()


def remote_python(args, source):
    return ssh(args, "python3 -", source.encode())


def idle(args):
    if rpc(args, "Player.GetActivePlayers"):
        raise RuntimeError("Kodi is playing media; stop it before deploying or testing")


def deploy(args):
    idle(args)
    archive = package()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    remote_zip = "/storage/.kodi/temp/silo-kodi-development.zip"
    ssh(args, "cat > " + shlex.quote(remote_zip), archive.read_bytes())
    # Back up the previous add-on and replace the whole tree to remove stale code.
    # User data is outside this tree. Registration uses Kodi, never its SQLite DB.
    print(remote_python(args, '''
import hashlib
from pathlib import Path
import shutil
import tempfile
import zipfile

archive = Path("/storage/.kodi/temp/silo-kodi-development.zip")
assert hashlib.sha256(archive.read_bytes()).hexdigest() == %r
addons = Path("/storage/.kodi/addons")
target = addons / "plugin.video.silo"
backup = Path("/storage/.kodi/temp/silo-kodi-previous")
with tempfile.TemporaryDirectory(prefix="silo-kodi-", dir=addons) as stage:
    with zipfile.ZipFile(archive) as bundle:
        assert set(bundle.namelist()) == set(%r)
        bundle.extractall(stage)
    if target.exists():
        if backup.exists():
            shutil.rmtree(backup)
        target.rename(backup)
    try:
        (Path(stage) / "plugin.video.silo").rename(target)
    except BaseException:
        if backup.exists() and not target.exists():
            backup.rename(target)
        raise
archive.unlink()
print("Installed archive verified by SHA-256; previous build kept in Kodi temp")
''' % (digest, [ADDON_ID + '/' + path.relative_to(ADDON).as_posix() for path in package_files()])).strip())
    ssh(args, "kodi-send --action=UpdateLocalAddons")
    expected = ET.parse(ADDON / "addon.xml").getroot().attrib["version"]
    def addon_details():
        try:
            return rpc(args, "Addons.GetAddonDetails", {
                "addonid": ADDON_ID, "properties": ["enabled", "version"],
            })["addon"]
        except RuntimeError:
            return None
    details = wait_for(addon_details, lambda value: value and value["version"] == expected)
    if not details["enabled"]:
        rpc(args, "Addons.SetAddonEnabled", {"addonid": ADDON_ID, "enabled": True})
    details = wait_for(addon_details, lambda value: value and value["enabled"] and value["version"] == expected)
    print(json.dumps(details, indent=2))
    if args.server:
        command = 'python3 /storage/.kodi/addons/plugin.video.silo/auth.py configure --profile-dir /storage/.kodi/userdata/addon_data/plugin.video.silo --server ' + shlex.quote(args.server)
        # Server configuration is explicit; credentials remain in the add-on's
        # private data directory and are preserved when the URL is unchanged.
        ssh(args, command)
    browse(args)


def browse(args):
    result = rpc(args, "Files.GetDirectory", {
        "directory": "plugin://plugin.video.silo/?action=status", "media": "files",
    })
    labels = [item["label"] for item in result["files"]]
    assert "Silo connected — API v2" in labels, labels
    print("Kodi directory execution and HTTPS Silo probe: OK")


def probe(args):
    print(json.dumps(rpc(args, "Application.GetProperties", {
        "properties": ["name", "version"],
    }), indent=2))
    print("Active players:", rpc(args, "Player.GetActivePlayers"))
    print(remote_python(args, '''
from pathlib import Path
import json
import sys
from urllib.request import urlopen
print("Python:", sys.version.split()[0])
print(Path("/etc/os-release").read_text())
for name in ("hpd_state", "disp_cap", "dv_cap", "hdr_cap", "aud_cap"):
    path = Path("/sys/class/amhdmitx/amhdmitx0") / name
    print(name + ":", path.read_text() if path.exists() else "unavailable")
print("Ethernet link Mbps:", Path("/sys/class/net/eth0/speed").read_text().strip())
with urlopen(%r + "/api/v2/system/info", timeout=10) as response:
    print("Silo:", json.load(response))
''' % args.server.rstrip("/")))


def seconds(value):
    return value["hours"] * 3600 + value["minutes"] * 60 + value["seconds"] + value["milliseconds"] / 1000


def wait_for(observe, ready, timeout=20):
    """Wait for observed state, since RPC acknowledgments precede transitions."""
    deadline = time.monotonic() + timeout
    while True:
        value = observe()
        if ready(value):
            return value
        if time.monotonic() >= deadline:
            raise RuntimeError("State did not converge: {!r}".format(value))
        time.sleep(0.2)


def smoke(args):
    idle(args)
    profile = json.loads(remote_python(args, """
import json, sys
sys.path.insert(0, '/storage/.kodi/addons/plugin.video.silo/resources/lib')
from silo.client import Session
session = Session.open('/storage/.kodi/userdata/addon_data/plugin.video.silo')
print(json.dumps(session.status().get('profile') if session else None))
"""))
    if not profile:
        raise RuntimeError("Sign in and choose a Silo profile before running playback acceptance")
    label = 'Silo playback check ' + uuid.uuid4().hex
    route = 'plugin://plugin.video.silo/?' + urlencode({
        'action': 'play', 'profile': profile['id'], 'file': args.file_id,
        'title': label, 'restart': 'true'})

    def owned_player():
        for active in rpc(args, "Player.GetActivePlayers"):
            item = rpc(args, "Player.GetItem", {
                "playerid": active["playerid"], "properties": ["file"],
            })["item"]
            if item.get("file") == route or item.get("label") == label:
                return active["playerid"]
        return None

    def state():
        player = owned_player()
        if player is None:
            return None
        return rpc(args, "Player.GetProperties", {
            "playerid": player, "properties": ["time", "totaltime", "speed", "canseek"]})

    def control(method, params):
        player = owned_player()
        if player is None:
            raise RuntimeError("The test playback was replaced or stopped")
        return rpc(args, method, dict(params, playerid=player))

    try:
        rpc(args, "Player.Open", {"item": {"file": route}})
        ready = wait_for(state, lambda value: value and value["canseek"]
                         and seconds(value["time"]) > 0, timeout=60)
        if seconds(ready['totaltime']) < 60:
            raise RuntimeError("Choose a test video at least 60 seconds long")
        control("Player.PlayPause", {"play": False})

        def pause_sample():
            before = state()
            time.sleep(1)
            return before, state()

        wait_for(pause_sample, lambda pair: all(v and v["speed"] == 0 for v in pair)
                 and abs(seconds(pair[0]["time"]) - seconds(pair[1]["time"])) < 0.1)
        control("Player.Seek", {"value": {"time": {"seconds": 45}}})
        wait_for(state, lambda value: value and abs(seconds(value["time"]) - 45) < 2, timeout=45)
        control("Player.PlayPause", {"play": True})
        wait_for(state, lambda value: value and value["speed"] == 1 and seconds(value["time"]) > 47)
        print("Silo video played, paused, sought to 45s, and resumed: OK")
    finally:
        # Player IDs can change with playlist context. Match this invocation's
        # identity before stopping, never merely the player ID observed at start.
        player = owned_player()
        if player is not None:
            rpc(args, "Player.Stop", {"playerid": player})
        wait_for(owned_player, lambda player: player is None)
        if not rpc(args, "Player.GetActivePlayers"):
            ssh(args, 'kodi-send --action=ActivateScreensaver')
    probe = """
import sys
sys.path.insert(0, '/storage/.kodi/addons/plugin.video.silo/resources/lib')
from silo.client import Session, Error
session = Session.open('/storage/.kodi/userdata/addon_data/plugin.video.silo')
try:
    with session.store.playback_lock(): print('released')
except Error as exc:
    print(exc.code)
"""
    wait_for(lambda: remote_python(args, probe).strip(), lambda value: value == 'released', timeout=30)
    print("Player stopped and playback authority released: OK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "package", "deploy", "probe", "browse", "smoke"))
    parser.add_argument("--ssh", default=os.environ.get("SILO_SSH_TARGET"))
    parser.add_argument("--rpc", default=os.environ.get("SILO_RPC_URL"))
    parser.add_argument("--server", default=os.environ.get("SILO_SERVER_URL"))
    parser.add_argument("--release-tag", help="Require the package version to match this v-prefixed release tag")
    parser.add_argument("--file-id", default=os.environ.get("SILO_TEST_FILE_ID"), help="Silo video file for playback acceptance")
    args = parser.parse_args()
    required = []
    if args.command not in ("check", "package"):
        required.append("rpc")
    if args.command in ("deploy", "probe", "smoke"):
        required.append("ssh")
    if args.command == "smoke":
        required.append("file_id")
    if args.command == "probe":
        required.append("server")
    for name in required:
        if not getattr(args, name):
            parser.error("--{} or its SILO_* environment variable is required".format(name.replace("_", "-")))
    if args.command == "check":
        check()
        subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"], cwd=ROOT, check=True)
    elif args.command == "package":
        package(args.release_tag)
    else:
        {"deploy": deploy, "probe": probe, "browse": browse, "smoke": smoke}[args.command](args)


if __name__ == "__main__":
    main()
