import io
import logging
from unittest import mock

import pytest

from unearth.auth import MultiDomainBasicAuth
from unearth.link import Link


@pytest.mark.parametrize(
    "url, is_secure",
    [
        ("https://pypi.org/simple", True),
        ("wss://abc.com/", True),
        ("http://localhost:8000/", True),
        ("http://127.0.0.1:8000/", True),
        ("http://[::1]:8000/", True),
        ("file:///tmp/", True),
        ("ftp://localhost/", True),
        ("http://example.org/", True),
        ("http://example.org/foo/bar", True),
        ("ftp://example.org:8000", True),
        ("http://insecure.com/", False),
        ("http://192.168.0.1/", False),
        ("http://192.168.0.1:8080/simple", True),
    ],
)
def test_session_is_secure_origin(session, url, is_secure):
    for host in ["example.org", "192.168.0.1:8080"]:
        session.add_trusted_host(host)
    assert session.is_secure_origin(Link(url)) == is_secure


@mock.patch("flask.render_template_string", return_value="<html>test</html>")
def test_session_is_cached(renderer, pypi, session):
    resp = session.get("https://pypi.org/simple")
    assert resp.text == "<html>test</html>"
    renderer.assert_called_once()

    resp = session.get("https://pypi.org/simple")
    assert resp.text == "<html>test</html>"
    renderer.assert_called_once()


def test_session_auth_401_if_no_prompting(pypi_auth, session):
    session.auth = MultiDomainBasicAuth(prompting=False)
    resp = session.get("https://pypi.org/simple")
    assert resp.status_code == 401


def test_session_auth_from_source_urls(pypi_auth, session):
    session.auth = MultiDomainBasicAuth(
        prompting=False, index_urls=["https://test:password@pypi.org/simple"]
    )
    resp = session.get("https://pypi.org/simple/click")
    assert resp.status_code == 200
    assert not any(r.status_code == 401 for r in resp.history)


def test_session_auth_from_prompting(pypi_auth, session, monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("test\npassword\n\n"))
    session.auth = MultiDomainBasicAuth(prompting=True)
    resp = session.get("https://pypi.org/simple/click")
    assert resp.status_code == 200
    assert any(r.status_code == 401 for r in resp.history)
    # The second attempt should use the cached credentials
    # but before that we need to clear the cache
    session.cache.clear()
    resp = session.get("https://pypi.org/simple/click")
    assert resp.status_code == 200
    assert not any(r.status_code == 401 for r in resp.history)


def test_session_auth_warn_agains_wrong_credentials(
    pypi_auth, session, monkeypatch, caplog
):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr("sys.stdin", io.StringIO("test\nwrong\n\n"))
    session.auth = MultiDomainBasicAuth(prompting=True)
    resp = session.get("https://pypi.org/simple/click")
    assert resp.status_code == 401
    record = caplog.records[-1]
    assert record.levelname == "WARNING"
    assert "401 Error, Credentials not correct" in record.message
