"""Connections to institutional systems: single sign-on, Canvas, Canvas Credentials, Open Badges 3.0, Handshake.

Every integration is off until configured, and each talks to the outside world only through `http()`, so tests replace
the network with in-process fakes of the real services.
"""
import httpx

_transport: httpx.BaseTransport | None = None   # tests install an httpx.MockTransport here


def http(**kw) -> httpx.Client:
    return httpx.Client(timeout=kw.pop("timeout", 20), transport=_transport, follow_redirects=False, **kw)
