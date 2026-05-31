"""
OAuth2 Authentication Script

Run this script to obtain a fresh Upstox access token.
It starts a local Flask server, opens the Upstox login page,
and captures the callback with the authorization code.

Usage:
    python scripts/authenticate.py

After successful authentication, the access token is saved to .env.
"""

import sys
import time
import threading
import logging
from pathlib import Path

from flask import Flask, request
from dotenv import set_key

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings, ENV_PATH
from core.broker import UpstoxBroker

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Flask app for OAuth callback
app = Flask(__name__)

# Global state
auth_success = False
settings = Settings()
broker = UpstoxBroker(settings)


@app.route("/callback")
def callback():
    """
    OAuth2 callback handler.

    Upstox redirects here after user authorization.
    Exchanges the auth code for an access token and saves it to .env.
    """
    global auth_success

    auth_code = request.args.get("code")
    if not auth_code:
        return "Authorization code not found in redirect.", 400

    logger.info(f"Received authorization code: {auth_code[:10]}...")
    logger.info("Exchanging code for access token...")

    token = broker.exchange_code_for_token(auth_code)
    if token:
        # Save token to .env file
        set_key(str(ENV_PATH), "UPSTOX_ACCESS_TOKEN", token)
        logger.info("Access token saved to .env")
        auth_success = True
        return "Authentication successful! You can close this window.", 200
    else:
        return "Authentication failed. Check logs for details.", 400


def run_server():
    """Run Flask in a daemon thread (suppresses Werkzeug logs)."""
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    app.run(host="127.0.0.1", port=5000)


if __name__ == "__main__":
    # Validate that credentials are configured
    if not settings.UPSTOX_CLIENT_ID or not settings.UPSTOX_CLIENT_SECRET:
        logger.error(
            "UPSTOX_CLIENT_ID and UPSTOX_CLIENT_SECRET must be set in .env"
        )
        sys.exit(1)

    login_url = broker.get_login_url()

    print("-" * 60)
    print("  UPSTOX OAUTH2 AUTHENTICATION")
    print("-" * 60)
    print()
    print("  Open this URL in your browser:")
    print()
    print(f"  {login_url}")
    print()
    print("  Waiting for callback on http://127.0.0.1:5000/callback...")
    print("-" * 60)

    # Start Flask server in background
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    try:
        while not auth_success:
            time.sleep(1)
        time.sleep(2)  # Let Flask send the response before exiting
        logger.info("Authentication complete. You are now authenticated.")
    except KeyboardInterrupt:
        logger.info("\nInterrupted by user.")
