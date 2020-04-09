# -*- coding: utf-8 -*-
"""
@author: Sam Schott  (ss2151@cam.ac.uk)

(c) Sam Schott; This work is licensed under a Creative Commons
Attribution-NonCommercial-NoDerivs 2.0 UK: England & Wales License.

This module is responsible for authorization and token store in the system keyring.

"""
# system imports
import logging

# external packages
import click
from keyring.errors import KeyringLocked
import keyrings.alt.file
from dropbox.oauth import DropboxOAuth2FlowNoRedirect

# maestral modules
from maestral.config import MaestralConfig
from maestral.constants import DROPBOX_APP_KEY
from maestral.errors import DropboxAuthError
from maestral.client import CONNECTION_ERRORS
from maestral.utils.backend import get_keyring_backend
from maestral.utils.oauth_implicit import DropboxOAuth2FlowImplicit

logger = logging.getLogger(__name__)


class OAuth2Session:
    """
    OAuth2Session provides OAuth 2 login and token store in the preferred system kering.
    To authenticate with Dropbox, run :meth:`get_auth_url`` first and direct the user to
    visit that URL and retrieve an auth token. Verify the provided auth token with
    :meth:`verify_auth_token` and save it in the system keyring together with the
    corresponding Dropbox ID by calling :meth:`save_creds`.

    This will currently use PKCE if available and fall back to the implicit grant flow
    implemented in :mod:`utils.oauth_implicit` otherwise.

    :param str config_name: Name of maestral config.

    :cvar int Success: Exit code for successful auth.
    :cvar int InvalidToken: Exit code for invalid token.
    :cvar int ConnectionFailed: Exit code for connection errors.
    """

    Success = 0
    InvalidToken = 1
    ConnectionFailed = 2

    def __init__(self, config_name):

        self.keyring = get_keyring_backend(config_name)
        self._conf = MaestralConfig(config_name)

        self.account_id = self._conf.get('account', 'account_id')
        self.access_token = ''

        self.auth_flow = None
        self.oAuth2FlowResult = None

    def load_token(self):
        """
        Load auth token from system keyring.

        :returns: Auth token.
        :rtype: str
        :raises: ``KeyringLocked`` if the system keyring cannot be accessed.
        """
        logger.debug(f'Using keyring: {self.keyring}')

        try:
            if self.account_id == '':
                self.access_token = None
            else:
                self.access_token = self.keyring.get_password('Maestral', self.account_id)
            return self.access_token
        except KeyringLocked:
            info = 'Please make sure that your keyring is unlocked and restart Maestral.'
            raise KeyringLocked(info)

    def get_auth_url(self):
        """
        Gets the auth URL to start the OAuth2 implicit grant flow.

        :returns: Dropbox auth URL.
        :rtype: str
        """
        try:
            self.auth_flow = DropboxOAuth2FlowNoRedirect(DROPBOX_APP_KEY, use_pkce=True)
        except TypeError:
            self.auth_flow = DropboxOAuth2FlowImplicit(DROPBOX_APP_KEY)
        authorize_url = self.auth_flow.start()
        return authorize_url

    def verify_auth_token(self, token):
        """
        Verify the provided authorization token with Dropbox servers.

        :returns: :attr:`Success`, :attr:`InvalidToken`, or :attr:`ConnectionFailed`.
        :rtype: int
        """

        if not self.auth_flow:
            raise RuntimeError('Auth flow not yet started. Please call "get_auth_url".')

        try:
            self.oAuth2FlowResult = self.auth_flow.finish(token)
            self.access_token = self.oAuth2FlowResult.access_token
            self.account_id = self.oAuth2FlowResult.account_id
            return self.Success
        except DropboxAuthError:
            return self.InvalidToken
        except CONNECTION_ERRORS:
            return self.ConnectionFailed

    def save_creds(self):
        """Saves auth key to system keyring."""
        self._conf.set('account', 'account_id', self.account_id)
        try:
            self.keyring.set_password('Maestral', self.account_id, self.access_token)
            click.echo(' > Credentials written.')
            if isinstance(self.keyring, keyrings.alt.file.PlaintextKeyring):
                click.echo(' > Warning: No supported keyring found, '
                           'Dropbox credentials stored in plain text.')
        except KeyringLocked:
            logger.error('Could not access the user keyring to save your authentication '
                         'token. Please make sure that the keyring is unlocked.')

    def delete_creds(self):
        """Deletes auth key from system keyring."""
        self._conf.set('account', 'account_id', "")
        try:
            self.keyring.delete_password('Maestral', self.account_id)
            click.echo(' > Credentials removed.')
        except KeyringLocked:
            logger.error('Could not access the user keyring to delete your authentication'
                         ' token. Please make sure that the keyring is unlocked.')
