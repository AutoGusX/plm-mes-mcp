"""
APS 3-Legged OAuth PKCE Token Helper
-------------------------------------
Runs a local HTTP server on port 3001 to catch the OAuth callback,
exchanges the code for an access token, and saves it to .env.

Usage:
    python -m uv run python get-token.py

The browser will open automatically. Log in with your Autodesk account,
approve access, and the token will be saved to .env automatically.
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import threading
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from dotenv import dotenv_values, set_key

CLIENT_ID = dotenv_values(Path(__file__).parent / ".env").get("APS_CLIENT_ID", "")
REDIRECT_URI = "http://localhost:3001/"
SCOPES = "data:read data:write"
AUTHORIZE_URL = "https://developer.api.autodesk.com/authentication/v2/authorize"
TOKEN_URL = "https://developer.api.autodesk.com/authentication/v2/token"
ENV_FILE = Path(__file__).parent / ".env"

# --- PKCE helpers ---

def generate_code_verifier() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()

def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

# --- Local callback server ---

_auth_code: str | None = None
_server_error: str | None = None

class CallbackHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        global _auth_code, _server_error
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if "code" in params:
            _auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style="font-family:sans-serif;padding:40px">
                <h2>&#10003; Authorization successful!</h2>
                <p>Token saved to .env. You can close this tab.</p>
                </body></html>
            """)
        elif "error" in params:
            _server_error = params.get("error_description", ["Unknown error"])[0]
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(
                f"<html><body><h2>Error: {_server_error}</h2></body></html>".encode()
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass  # suppress request logs

def wait_for_callback() -> str:
    server = http.server.HTTPServer(("localhost", 3001), CallbackHandler)
    server.timeout = 120
    server.handle_request()
    server.server_close()
    if _server_error:
        raise RuntimeError(f"OAuth error: {_server_error}")
    if not _auth_code:
        raise RuntimeError("No authorization code received (timeout?)")
    return _auth_code

# --- Token exchange ---

def exchange_code(code: str, verifier: str) -> dict:
    response = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": CLIENT_ID,
            "code_verifier": verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()

# --- Save to .env ---

def save_token(token_data: dict) -> None:
    access_token = token_data["access_token"]
    set_key(str(ENV_FILE), "FUSION_MANAGE_TOKEN", access_token)
    print(f"\nOK Token saved to .env")
    print(f"  expires_in:    {token_data.get('expires_in', '?')}s (~{token_data.get('expires_in', 0)//60} min)")
    if "refresh_token" in token_data:
        set_key(str(ENV_FILE), "FUSION_MANAGE_REFRESH_TOKEN", token_data["refresh_token"])
        print(f"  refresh_token: saved (valid 15 days)")

# --- Main ---

def main():
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)
    state = secrets.token_urlsafe(16)

    params = urllib.parse.urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    })
    auth_url = f"{AUTHORIZE_URL}?{params}"

    print("Opening browser for Autodesk login...")
    print(f"  URL: {auth_url[:80]}...")
    print("\nWaiting for callback on http://localhost:3001/ (120s timeout)")
    webbrowser.open(auth_url)

    code = wait_for_callback()
    print("OK Authorization code received. Exchanging for token...")

    token_data = exchange_code(code, verifier)
    save_token(token_data)

if __name__ == "__main__":
    main()
