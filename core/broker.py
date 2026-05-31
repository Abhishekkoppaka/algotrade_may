"""
Upstox Broker Client

Encapsulates ALL communication with the Upstox API:
- OAuth2 authentication flow
- Order placement (market orders)
- Order status checking
- Live quote fetching

This is the ONLY module that imports `requests` for Upstox operations.
All other modules interact with the broker through this interface.
"""

import time
import logging
import requests
import urllib.parse
from typing import Optional, Tuple, List
from config.settings import Settings

logger = logging.getLogger(__name__)


class UpstoxBroker:
    """
    Unified client for all Upstox API interactions.

    Handles authentication, order placement, and market data retrieval.
    Designed to be the single point of contact with the Upstox REST API.

    Attributes:
        settings: Configuration instance for credentials and URLs.
        session: Reusable requests session for connection pooling.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the broker client.

        Args:
            settings: Configuration object. Creates default if not provided.
        """
        self.settings = settings or Settings()
        # Reuse a single session for all requests (connection pooling)
        self.session = requests.Session()
        self.session.headers.update(self.settings.auth_headers)

    # -----------------------------------------------------------------------
    # Authentication
    # -----------------------------------------------------------------------

    def get_login_url(self) -> str:
        """
        Generate the Upstox OAuth2 authorization URL.

        The user must open this URL in a browser to grant access.
        After authorization, Upstox redirects to the callback URL with
        an authorization code.

        Returns:
            The fully-formed login URL string.
        """
        encoded_redirect = urllib.parse.quote(self.settings.UPSTOX_REDIRECT_URI, safe="")
        return (
            f"{self.settings.UPSTOX_BASE_URL}/login/authorization/dialog"
            f"?response_type=code"
            f"&client_id={self.settings.UPSTOX_CLIENT_ID}"
            f"&redirect_uri={encoded_redirect}"
        )

    def exchange_code_for_token(self, auth_code: str) -> Optional[str]:
        """
        Exchange an authorization code for an access token.

        This is called by the OAuth callback handler after the user
        authorizes the application.

        Args:
            auth_code: The authorization code received from Upstox redirect.

        Returns:
            The access token string if successful, None otherwise.
        """
        url = f"{self.settings.UPSTOX_BASE_URL}/login/authorization/token"
        headers = {
            "accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = {
            "code": auth_code,
            "client_id": self.settings.UPSTOX_CLIENT_ID,
            "client_secret": self.settings.UPSTOX_CLIENT_SECRET,
            "redirect_uri": self.settings.UPSTOX_REDIRECT_URI,
            "grant_type": "authorization_code",
        }

        try:
            response = requests.post(url, headers=headers, data=data)
            if response.status_code == 200:
                token = response.json().get("access_token")
                logger.info("Successfully obtained access token")
                return token
            else:
                logger.error(f"Token exchange failed: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Token exchange error: {e}")
            return None

    # -----------------------------------------------------------------------
    # Order Management
    # -----------------------------------------------------------------------

    def place_market_order(
        self,
        instrument_key: str,
        transaction_type: str,
        quantity: int,
        product: str = "I",
        tag: Optional[str] = None,
    ) -> Optional[str]:
        """
        Place a market order on Upstox.

        Args:
            instrument_key: Upstox instrument identifier (e.g., "NSE_EQ|INE467B01029")
            transaction_type: "BUY" or "SELL"
            quantity: Number of shares/units to trade
            product: Upstox product type. "I" is intraday.
            tag: Optional order tag for tracing related orders.

        Returns:
            Order ID string if successful, None if failed.
        """
        url = f"{self.settings.UPSTOX_BASE_URL}/order/place"
        payload = {
            "quantity": int(quantity),
            "product": product,
            "validity": "DAY",
            "price": 0.0,
            "instrument_token": instrument_key,
            "order_type": "MARKET",
            "transaction_type": transaction_type.upper(),
            "disclosed_quantity": 0,
            "trigger_price": 0.0,
            "is_amo": False,
            "market_protection": 0,
        }
        if tag:
            payload["tag"] = tag

        try:
            response = self.session.post(url, json=payload)
            if response.status_code == 200:
                order_id = response.json().get("data", {}).get("order_id")
                logger.info(
                    f"ORDER PLACED: {transaction_type} {quantity} x {instrument_key} "
                    f"(ID: {order_id})"
                )
                return order_id
            else:
                logger.error(f"ORDER FAILED: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Order placement exception: {e}")
            return None

    def get_order_status(self, order_id: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Check the current status of a placed order.

        Args:
            order_id: The Upstox order ID to check.

        Returns:
            Tuple of (status, message). Status can be "complete", "rejected", etc.
            Returns (None, None) if the check fails.
        """
        url = f"{self.settings.UPSTOX_BASE_URL}/order/history?order_id={order_id}"

        try:
            response = self.session.get(url)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if data:
                    latest = data[-1]
                    return latest.get("status"), latest.get("status_message")
        except Exception as e:
            logger.error(f"Order status check error: {e}")

        return None, None

    # -----------------------------------------------------------------------
    # Option Contracts
    # -----------------------------------------------------------------------

    def get_option_contracts(
        self,
        underlying_key: str,
        expiry_date: Optional[str] = None,
    ) -> List[dict]:
        """
        Fetch option contracts for an underlying instrument.

        Args:
            underlying_key: Upstox key for the underlying, e.g. NSE_INDEX|Nifty 50.
            expiry_date: Optional expiry filter in YYYY-MM-DD format.

        Returns:
            List of option contract dictionaries returned by Upstox.
        """
        params = {"instrument_key": underlying_key}
        if expiry_date:
            params["expiry_date"] = expiry_date

        url = f"{self.settings.UPSTOX_BASE_URL}/option/contract"
        try:
            response = self.session.get(url, params=params, timeout=15)
            if response.status_code == 200:
                return response.json().get("data", [])
            logger.error(f"Option contracts fetch failed ({response.status_code}): {response.text}")
        except Exception as e:
            logger.error(f"Option contracts fetch error: {e}")
        return []

    # -----------------------------------------------------------------------
    # Market Data (Live Quotes)
    # -----------------------------------------------------------------------

    def get_live_quotes(self, instrument_keys: list, max_retries: int = 3) -> dict:
        """
        Fetch real-time market quotes for one or more instruments.

        Args:
            instrument_keys: List of Upstox instrument key strings.
            max_retries: Number of retry attempts on transient errors.

        Returns:
            Dictionary keyed by instrument identifier containing quote data.
            Empty dict on failure.
        """
        if not instrument_keys:
            return {}

        keys_str = ",".join(instrument_keys)
        url = f"{self.settings.UPSTOX_BASE_URL}/market-quote/quotes?instrument_key={keys_str}"

        for attempt in range(max_retries):
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code == 200:
                    return response.json().get("data", {})
                elif response.status_code == 429:
                    wait = 2 ** attempt
                    logger.warning(f"Quote rate limited. Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    logger.warning(f"Quote fetch failed ({response.status_code}): {response.text}")
                    return {}
            except Exception as e:
                wait = 2 ** attempt
                logger.warning(f"Quote fetch error (attempt {attempt+1}/{max_retries}): {e}. Retrying in {wait}s...")
                time.sleep(wait)

        return {}

    def get_ltp(self, instrument_key: str) -> Optional[float]:
        """
        Get the Last Traded Price for a single instrument.

        Convenience wrapper around get_live_quotes for single-instrument lookups.

        Args:
            instrument_key: Upstox instrument identifier.

        Returns:
            Last traded price as float, or None if unavailable.
        """
        quotes = self.get_live_quotes([instrument_key])
        if not quotes:
            return None
        # Upstox response keys use the symbol name (e.g. "NSE_EQ:NIFTYBEES"),
        # not the ISIN-based key we sent ("NSE_EQ:INF204KB14I2"). Since we
        # always query exactly one instrument here, grab the single response entry.
        return next(iter(quotes.values())).get("last_price")
