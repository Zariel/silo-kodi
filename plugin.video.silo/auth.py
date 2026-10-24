#!/usr/bin/env python3
"""Headless access to the same authentication flow Kodi uses."""
import argparse
import getpass
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'resources/lib'))
from silo.client import Error, Session
from silo.pairing import write_qr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('configure', 'pair', 'poll', 'cancel', 'status', 'profiles', 'select', 'logout', 'verify'))
    parser.add_argument('--profile-dir', required=True, help='Kodi add-on data directory or an isolated test directory')
    parser.add_argument('--server', default=os.environ.get('SILO_SERVER_URL'))
    parser.add_argument('--profile-id')
    args = parser.parse_args()
    if args.command == 'configure':
        if not args.server:
            parser.error('--server is required to configure')
        session = Session.configure(args.server, args.profile_dir)
    else:
        session = Session.open(args.profile_dir)
        if session is None:
            parser.error('Configure a server first')
    if args.command in ('configure', 'status'):
        result = session.status()
    elif args.command == 'pair':
        result = session.start_pairing()
        path = Path(args.profile_dir) / 'pairing.png'
        write_qr(result, path)
        result['qr_path'] = str(path)
    elif args.command == 'poll':
        result = session.poll_pairing()
        if result['status'] != 'pending':
            (Path(args.profile_dir) / 'pairing.png').unlink(missing_ok=True)
    elif args.command == 'cancel':
        session.cancel_pairing()
        (Path(args.profile_dir) / 'pairing.png').unlink(missing_ok=True)
        result = {'status': 'canceled'}
    elif args.command == 'profiles':
        result = [{'id': p['id'], 'name': p['name'], 'has_pin': p['has_pin']} for p in session.profiles()]
    elif args.command == 'select':
        if not args.profile_id:
            parser.error('--profile-id is required')
        profiles = session.profiles()
        profile = next((p for p in profiles if p['id'] == args.profile_id), None)
        pin = getpass.getpass('Profile PIN: ') if profile and profile['has_pin'] else None
        result = session.select_profile(args.profile_id, pin)
    elif args.command == 'logout':
        result = {'server_revoked': session.logout(), 'signed_in': False}
    elif args.command == 'verify':
        session.request('GET', '/account/me', profile=False)
        result = {'account': 'ok', 'profiles': len(session.profiles())}
        if session.status()['profile']:
            result['libraries'] = len(session.request('GET', '/user/libraries')['items'])
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (Error, OSError) as exc:
        print(str(exc) if isinstance(exc, Error) else 'Could not persist local authentication state.', file=sys.stderr)
        sys.exit(1)
