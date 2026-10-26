"""
Refresh the APS access token using the saved refresh token.
Faster than re-running the full PKCE browser flow.

Usage:
    uv run python refresh-token.py
"""

from pathlib import Path
import httpx
from dotenv import dotenv_values, set_key

CLIENT_ID = dotenv_values(Path(__file__).parent / ".env").get("APS_CLIENT_ID", "")
TOKEN_URL = "https://developer.api.autodesk.com/authentication/v2/token"
ENV_FILE = Path(__file__).parent / ".env"


def main():
    env = dotenv_values(ENV_FILE)
    refresh_token = env.get("FUSION_MANAGE_REFRESH_TOKEN", "")
    if not refresh_token:
        print("No FUSION_MANAGE_REFRESH_TOKEN in .env — run get-token.py instead.")
        return

    print("Refreshing APS token...")
    r = httpx.post(
        TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()

    set_key(str(ENV_FILE), "FUSION_MANAGE_TOKEN", data["access_token"])
    if "refresh_token" in data:
        set_key(str(ENV_FILE), "FUSION_MANAGE_REFRESH_TOKEN", data["refresh_token"])

    print(f"Token refreshed and saved to .env")
    print(f"  expires_in: {data.get('expires_in', '?')}s (~{data.get('expires_in', 0)//60} min)")


if __name__ == "__main__":
    main()
