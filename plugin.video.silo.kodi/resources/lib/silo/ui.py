"""Kodi account screen. Network operations never block remote input."""
from pathlib import Path
import re
import threading

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

from .client import Error, Session, server_url
from .pairing import write_qr


def _text(value):
    return str(value).replace('[', '(').replace(']', ')')


class AccountWindow(xbmcgui.WindowXML):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        addon = xbmcaddon.Addon()
        self.directory = Path(xbmcvfs.translatePath(addon.getAddonInfo('profile')))
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.session = None
        self.profiles = []
        self._closed = threading.Event()
        self._cancel = threading.Event()
        self._busy = False
        self._thread = None
        self._pairing = False
        self.monitor = xbmc.Monitor()

    def onInit(self):
        self.setProperty('accent', 'FFE8E8EC')
        self._view('connect')
        self._task(self._load)

    def _view(self, name):
        if self._closed.is_set():
            return
        self.setProperty('screen', name)
        self.getControl(101).setLabel('Cancel sign-in' if name == 'pair' else 'Sign in')
        self.getControl(101).setVisible(name in ('connect', 'pair'))
        self.getControl(102).setVisible(name == 'account')
        self.getControl(103).setVisible(name in ('account', 'profiles'))
        self.getControl(100).setVisible(name != 'pair')
        buttons = {'connect': (100, 101, 104), 'pair': (101, 104),
                   'account': (100, 102, 103, 104), 'profiles': (100, 103, 104)}[name]
        # Hidden XML controls must not become dead ends for directional input.
        for index, identifier in enumerate(buttons):
            control = self.getControl(identifier)
            control.controlLeft(self.getControl(buttons[index - 1]))
            control.controlRight(self.getControl(buttons[(index + 1) % len(buttons)]))
            control.controlUp(self.getControl(200 if name == 'profiles' else identifier))
            control.controlDown(self.getControl(200 if name == 'profiles' else identifier))
        self.setFocusId(200 if name == 'profiles' else 102 if name == 'account' else 101)

    def _message(self, value):
        if not self._closed.is_set():
            self.getControl(3).setText(_text(value))

    def _task(self, operation):
        if self._busy:
            return
        self._busy = True
        def work():
            try:
                operation()
            except Error as exc:
                if not self._closed.is_set():
                    if self._pairing:
                        self._pairing = False
                        self._view('connect')
                    self._message(str(exc))
            except OSError:
                self._message('Could not save local sign-in data. Check device storage.')
            except Exception:
                # Kodi logs are often shared. Do not include exception payloads,
                # server responses, verification URLs, or credentials in them.
                xbmc.log('Silo: account screen operation failed', xbmc.LOGERROR)
                self._message('Could not complete this action. Close Silo and try again.')
            finally:
                self._busy = False
        self._thread = threading.Thread(target=work, daemon=True)
        self._thread.start()

    def _load(self):
        self.session = Session.open(self.directory)
        if self._closed.is_set():
            return
        if self.session is None:
            self._message('Enter your Silo server address to get started.')
            self.setFocusId(100)
            return
        self.getControl(4).setLabel(_text(self.session.server))
        try:
            branding = self.session.public('/theme/branding')
            if self._closed.is_set():
                return
            accent = branding.get('accent_color', '')
            if re.fullmatch(r'#[0-9a-fA-F]{6}', accent):
                self.setProperty('accent', 'FF' + accent[1:].upper())
        except Error:
            pass
        status = self.session.status()
        if self._closed.is_set():
            return
        if not status['signed_in']:
            self._view('connect')
            self._message('Scan a QR code and sign in securely through Silo on your phone.')
            return
        try:
            self.session.request('GET', '/account/me', profile=False)
        except Error as exc:
            if exc.code == 'sign_in_required':
                self._view('connect')
            raise
        if status['profile']:
            self._view('account')
            self._message('Signed in as {}. Choose a profile or close this screen to return to your libraries.'.format(status['profile']['name']))
        else:
            self._show_profiles()

    def _show_profiles(self):
        self.profiles = self.session.profiles()
        if self._closed.is_set():
            return
        control = self.getControl(200)
        control.reset()
        for profile in self.profiles:
            label = profile['name'] + ('   • PIN' if profile['has_pin'] else '')
            control.addItem(xbmcgui.ListItem(_text(label)))
        self._view('profiles')
        self._message('Who is watching?' if self.profiles else 'Create a profile in Silo, then reopen this screen.')

    def _pair(self):
        if self.session is None:
            self._message('Enter your server address first.')
            self.setFocusId(100)
            return
        self._cancel.clear()
        pair = self.session.start_pairing()
        path = self.directory / 'pairing.png'
        write_qr(pair, path)
        if self._closed.is_set():
            self.session.cancel_pairing()
            path.unlink(missing_ok=True)
            return
        self._pairing = True
        self.getControl(5).setImage(str(path), useCache=False)
        self.getControl(6).setLabel(_text(pair['user_code']))
        self.getControl(7).setText(_text(pair['verification_uri']))
        self._view('pair')
        self._message('Scan with your phone and approve Silo Kodi. Or open the address below and enter the code.')
        try:
            while not self._closed.is_set() and not self.monitor.abortRequested():
                if self._cancel.wait(1):
                    break
                try:
                    result = self.session.poll_pairing()
                except Error as exc:
                    self._message(str(exc))
                    if self._closed.wait(max(1, min(exc.retry_after or 5, 30))):
                        break
                    continue
                status = result['status']
                if status == 'approved':
                    self._pairing = False
                    if not self._closed.is_set():
                        self._show_profiles()
                    return
                if status != 'pending':
                    self._pairing = False
                    self._view('connect')
                    self._message('Sign-in {}. Choose Sign in to try again.'.format(status))
                    return
                if result.get('opened'):
                    self._message('Continue on your phone to approve this device.')
            self.session.cancel_pairing()
            if not self._closed.is_set():
                self._view('connect')
                self._message('Sign-in canceled.')
        finally:
            self._pairing = False
            path.unlink(missing_ok=True)

    def onClick(self, control):
        if control == 104:
            self.close()
            return
        if control == 101 and self._pairing:
            self._cancel.set()
            return
        if self._busy:
            return
        if control in (100, 102, 103) and xbmc.Player().isPlaying():
            self._message('Stop playback before changing the server, profile, or account.')
            return
        if control == 100:
            value = xbmcgui.Dialog().input('Silo server URL', self.session.server if self.session else 'https://')
            if not value:
                return
            try:
                value = server_url(value)
            except Error as exc:
                self._message(str(exc))
                return
            if self.session and value != self.session.server and self.session.status()['signed_in']:
                if not xbmcgui.Dialog().yesno('Change server', 'Sign out of this server and connect to the new address?'):
                    return
            def configure():
                if self.session and self.session.server != value:
                    self.session.logout()
                self.session = Session.configure(value, self.directory)
                self.setProperty('accent', 'FFE8E8EC')
                self._load()
            self._task(configure)
        elif control == 101:
            self._task(self._pair)
        elif control == 102:
            self._task(self._show_profiles)
        elif control == 103:
            if xbmcgui.Dialog().yesno('Sign out', 'Sign out of Silo on this device?'):
                def logout():
                    revoked = self.session.logout()
                    self._view('connect')
                    self._message('Signed out.' if revoked else 'Signed out locally. Silo could not be reached to revoke the session.')
                self._task(logout)
        elif control == 200:
            index = self.getControl(200).getSelectedPosition()
            if index < 0 or index >= len(self.profiles):
                return
            profile = self.profiles[index]
            pin = None
            if profile['has_pin']:
                pin = xbmcgui.Dialog().input('Profile PIN', type=xbmcgui.INPUT_ALPHANUM, option=xbmcgui.ALPHANUM_HIDE_INPUT)
                if not pin:
                    return
            def select():
                self.session.select_profile(profile['id'], pin)
                self._load()
            self._task(select)

    def onAction(self, action):
        if action.getId() in (9, 10, 92):
            self.close()

    def close(self):
        self._closed.set()
        self._cancel.set()
        super().close()

    def finish(self):
        self._closed.set()
        self._cancel.set()
        if self._thread:
            self._thread.join(timeout=35)


def open_account():
    addon = xbmcaddon.Addon()
    window = AccountWindow('Account.xml', addon.getAddonInfo('path'), 'Default', '1080i')
    try:
        window.doModal()
    finally:
        window.finish()
