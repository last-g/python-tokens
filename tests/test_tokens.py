import json
import os
import pytest
import time
import tokens
from mock import MagicMock


VALID_USER_JSON = {'application_username': 'app', 'application_password': 'pass'}
VALID_CLIENT_JSON = {'client_id': 'cid', 'client_secret': 'sec'}


def test_init_fixed_tokens_from_env(monkeypatch):
    monkeypatch.setattr('os.environ', {'OAUTH2_ACCESS_TOKENS': 'mytok=123,t2=3'})
    tokens.init_fixed_tokens_from_env()
    assert '123' == tokens.get('mytok')
    assert '3' == tokens.get('t2')


def test_read_credentials(tmpdir):
    path = str(tmpdir)
    user = VALID_USER_JSON
    client = VALID_CLIENT_JSON
    with open(os.path.join(path, 'user.json'), 'w') as fd:
        json.dump(user, fd)

    with open(os.path.join(path, 'client.json'), 'w') as fd:
        json.dump(client, fd)

    assert (user, client) == tokens.read_credentials(path)

    with open(os.path.join(path, 'client.json'), 'w') as fd:
        fd.write('invalid')

    with pytest.raises(tokens.InvalidCredentialsError) as exc_info:
        tokens.read_credentials(path)

    with open(os.path.join(path, 'user.json'), 'w') as fd:
        fd.write('invalid')

    with pytest.raises(tokens.InvalidCredentialsError) as exc_info:
        tokens.read_credentials(path)


def test_get():
    tokens.TOKENS = {'test': {'access_token': 'mytok123',
                              'expires_at': time.time() + 3600}}
    tokens.get('test')


def test_refresh_without_configuration():
    # remove URL config
    tokens.configure(dir='', url='')
    tokens.manage('mytok', ['scope'])
    with pytest.raises(tokens.ConfigurationError) as exc_info:
        tokens.refresh('mytok')
    assert str(exc_info.value) == 'Configuration error: Missing OAuth access token URL. Either set OAUTH2_ACCESS_TOKEN_URL or use tokens.configure(url=..).'


def test_refresh(monkeypatch, tmpdir):
    tokens.configure(dir=str(tmpdir), url='')
    tokens.manage('mytok', ['myscope'])
    with pytest.raises(tokens.ConfigurationError):
        tokens.refresh('mytok')

    tokens.configure(dir=str(tmpdir), url='https://example.org')

    with open(os.path.join(str(tmpdir), 'user.json'), 'w') as fd:
        json.dump({'application_username': 'app', 'application_password': 'pass'}, fd)

    with open(os.path.join(str(tmpdir), 'client.json'), 'w') as fd:
        json.dump({'client_id': 'cid', 'client_secret': 'sec'}, fd)

    response = MagicMock()
    response.json.return_value = {'expires_in': 123123, 'access_token': '777'}
    monkeypatch.setattr('requests.post', lambda url, **kwargs: response)
    tok = tokens.get('mytok')
    assert tok == '777'


def test_refresh_invalid_credentials(monkeypatch, tmpdir):
    tokens.configure(dir=str(tmpdir), url='https://example.org')
    tokens.manage('mytok', ['myscope'])
    tokens.start()  # this does not do anything..

    with open(os.path.join(str(tmpdir), 'user.json'), 'w') as fd:
        # missing password
        json.dump({'application_username': 'app'}, fd)

    with open(os.path.join(str(tmpdir), 'client.json'), 'w') as fd:
        json.dump({'client_id': 'cid', 'client_secret': 'sec'}, fd)

    with pytest.raises(tokens.InvalidCredentialsError) as exc_info:
        tokens.get('mytok')
    assert str(exc_info.value) == "Invalid OAuth credentials: Missing key: 'application_password'"


def test_refresh_invalid_response(monkeypatch, tmpdir):
    tokens.configure(dir=str(tmpdir), url='https://example.org')
    tokens.manage('mytok', ['myscope'])
    tokens.start()  # this does not do anything..

    response = MagicMock()
    response.json.return_value = {'foo': 'bar'}
    monkeypatch.setattr('requests.post', lambda url, **kwargs: response)
    monkeypatch.setattr('tokens.read_credentials', lambda path: (VALID_USER_JSON, VALID_CLIENT_JSON))

    with pytest.raises(tokens.InvalidTokenResponse) as exc_info:
        tokens.get('mytok')
    assert str(exc_info.value) == """Invalid token response: Expected a JSON object with keys "expires_in" and "access_token": 'expires_in'"""

    response.json.return_value = {'access_token': '', 'expires_in': 100}
    with pytest.raises(tokens.InvalidTokenResponse) as exc_info:
        tokens.get('mytok')
    assert str(exc_info.value) == 'Invalid token response: Empty "access_token" value'


def test_get_refresh_failure(monkeypatch, tmpdir):
    tokens.configure(dir=str(tmpdir), url='https://example.org')

    with open(os.path.join(str(tmpdir), 'user.json'), 'w') as fd:
        json.dump({'application_username': 'app', 'application_password': 'pass'}, fd)

    with open(os.path.join(str(tmpdir), 'client.json'), 'w') as fd:
        json.dump({'client_id': 'cid', 'client_secret': 'sec'}, fd)

    exc = Exception('FAIL')
    response = MagicMock()
    response.raise_for_status.side_effect = exc
    monkeypatch.setattr('requests.post', lambda url, **kwargs: response)
    logger = MagicMock()
    monkeypatch.setattr('tokens.logger', logger)
    tokens.TOKENS = {'mytok': {'access_token': 'oldtok',
                              'scopes': ['myscope'],
                              # token is still valid for 10 minutes
                              'expires_at': time.time() + (10 * 60)}}
    tok = tokens.get('mytok')
    assert tok == 'oldtok'
    logger.warn.assert_called_with('Failed to refresh access token "%s" (but it is still valid): %s', 'mytok', exc)

    tokens.TOKENS = {'mytok': {'scopes': ['myscope'], 'expires_at': 0}}
    with pytest.raises(Exception) as exc_info:
        tok = tokens.get('mytok')
    assert exc_info.value == exc

def test_get_refresh_failure_ignore_expire(monkeypatch, tmpdir):
    tokens.configure(dir=str(tmpdir), url='https://example.org')

    with open(os.path.join(str(tmpdir), 'user.json'), 'w') as fd:
        json.dump({'application_username': 'app', 'application_password': 'pass'}, fd)

    with open(os.path.join(str(tmpdir), 'client.json'), 'w') as fd:
        json.dump({'client_id': 'cid', 'client_secret': 'sec'}, fd)

    exc = Exception('FAIL')
    response = MagicMock()
    response.raise_for_status.side_effect = exc
    monkeypatch.setattr('requests.post', lambda url, **kwargs: response)
    logger = MagicMock()
    monkeypatch.setattr('tokens.logger', logger)
    tokens.TOKENS = {'mytok': {'access_token': 'oldtok',
                              'ignore_expire': False,
                              'scopes': ['myscope'],
                              # token is still valid for 10 minutes
                              'expires_at': time.time() + (10 * 60)}}
    tok = tokens.get('mytok')
    assert tok == 'oldtok'
    logger.warn.assert_called_with('Failed to refresh access token "%s" (but it is still valid): %s', 'mytok', exc)

    tokens.TOKENS = {'mytok': {'access_token':'expired-token', 'ignore_expire': True, 'scopes': ['myscope'], 'expires_at': 0}}
    tok = tokens.get('mytok')
    assert tok == 'expired-token'
