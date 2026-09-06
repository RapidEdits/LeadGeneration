"""OAuth 2.0 flows for Gmail (Google) and Microsoft 365 (Microsoft identity platform).

Returns normalized credential dicts:
    {"access_token","refresh_token","expires_at",  # epoch seconds
     "scope","email","provider"}
which are encrypted at rest in ConnectedAccount.encrypted_credentials. `state` is an
HMAC-signed token (see core.security) so callbacks can't be forged or replayed.
"""
from __future__ import annotations

import time
from urllib.parse import urlencode

import httpx

from app.core.config import settings

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]

MS_SCOPES = ["offline_access", "openid", "email", "profile",
             "https://graph.microsoft.com/Mail.Send", "https://graph.microsoft.com/Mail.Read",
             "https://graph.microsoft.com/User.Read"]


def _ms_base() -> str:
    return f"https://login.microsoftonline.com/{settings.MICROSOFT_OAUTH_TENANT}/oauth2/v2.0"


class OAuthNotConfigured(RuntimeError):
    pass


# ---- Google ----
def google_configured() -> bool:
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def google_auth_url(state: str) -> str:
    if not google_configured():
        raise OAuthNotConfigured("Google OAuth client credentials are not set")
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{GOOGLE_AUTH}?{urlencode(params)}"


def _google_token_request(data: dict) -> dict:
    resp = httpx.post(GOOGLE_TOKEN, data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def exchange_google_code(code: str) -> dict:
    tok = _google_token_request({
        "code": code,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": settings.google_redirect_uri,
        "grant_type": "authorization_code",
    })
    email = _google_email(tok["access_token"])
    return {
        "provider": "gmail",
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "expires_at": time.time() + int(tok.get("expires_in", 3600)),
        "scope": tok.get("scope", ""),
        "email": email,
    }


def refresh_google(refresh_token: str) -> dict:
    tok = _google_token_request({
        "refresh_token": refresh_token,
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
        "grant_type": "refresh_token",
    })
    return {
        "access_token": tok["access_token"],
        # Google may omit refresh_token on refresh — keep the old one.
        "refresh_token": tok.get("refresh_token") or refresh_token,
        "expires_at": time.time() + int(tok.get("expires_in", 3600)),
        "scope": tok.get("scope", ""),
    }


def _google_email(access_token: str) -> str | None:
    try:
        resp = httpx.get(GOOGLE_USERINFO,
                         headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        if resp.status_code < 400:
            return resp.json().get("email")
    except httpx.HTTPError:
        pass
    return None


# ---- Microsoft ----
def microsoft_configured() -> bool:
    return bool(settings.MICROSOFT_OAUTH_CLIENT_ID and settings.MICROSOFT_OAUTH_CLIENT_SECRET)


def microsoft_auth_url(state: str) -> str:
    if not microsoft_configured():
        raise OAuthNotConfigured("Microsoft OAuth client credentials are not set")
    params = {
        "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": settings.microsoft_redirect_uri,
        "response_mode": "query",
        "scope": " ".join(MS_SCOPES),
        "state": state,
    }
    return f"{_ms_base()}/authorize?{urlencode(params)}"


def _ms_token_request(data: dict) -> dict:
    resp = httpx.post(f"{_ms_base()}/token", data=data, timeout=30)
    resp.raise_for_status()
    return resp.json()


def exchange_microsoft_code(code: str) -> dict:
    tok = _ms_token_request({
        "code": code,
        "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
        "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
        "redirect_uri": settings.microsoft_redirect_uri,
        "grant_type": "authorization_code",
        "scope": " ".join(MS_SCOPES),
    })
    email = _ms_email(tok["access_token"])
    return {
        "provider": "microsoft",
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token"),
        "expires_at": time.time() + int(tok.get("expires_in", 3600)),
        "scope": tok.get("scope", ""),
        "email": email,
    }


def refresh_microsoft(refresh_token: str) -> dict:
    tok = _ms_token_request({
        "refresh_token": refresh_token,
        "client_id": settings.MICROSOFT_OAUTH_CLIENT_ID,
        "client_secret": settings.MICROSOFT_OAUTH_CLIENT_SECRET,
        "grant_type": "refresh_token",
        "scope": " ".join(MS_SCOPES),
    })
    return {
        "access_token": tok["access_token"],
        "refresh_token": tok.get("refresh_token") or refresh_token,
        "expires_at": time.time() + int(tok.get("expires_in", 3600)),
        "scope": tok.get("scope", ""),
    }


def _ms_email(access_token: str) -> str | None:
    try:
        resp = httpx.get("https://graph.microsoft.com/v1.0/me",
                         headers={"Authorization": f"Bearer {access_token}"}, timeout=15)
        if resp.status_code < 400:
            data = resp.json()
            return data.get("mail") or data.get("userPrincipalName")
    except httpx.HTTPError:
        pass
    return None
