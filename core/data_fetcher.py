"""
Unified Data Fetcher

Single module responsible for ALL historical and intraday data retrieval
from the Upstox API. Handles:
- Chunked historical downloads (respecting Upstox's date range limits)
- Intraday candle fetching for today's live data
- Timezone normalization (Upstox returns UTC+5:30 → naive IST)
- Automatic retry with backoff on rate limits
- Data deduplication and sorting

No other module should call Upstox historical endpoints directly.
"""

import time
import logging
import pandas as pd
import requests
from datetime import datetime, timedelta
from typing import Optional
from config.settings import Settings

logger = logging.getLogger(__name__)

# Standard column names for all OHLCV DataFrames in this system
OHLCV_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume", "oi"]


class DataFetcher:
    """
    Fetches and normalizes market data from Upstox API.

    All returned DataFrames have:
    - DateTimeIndex named 'timestamp' (timezone-naive, IST)
    - Columns: open, high, low, close, volume
    - Sorted ascending by timestamp
    - No duplicates

    Attributes:
        settings: Configuration with API credentials and parameters.
        session: Reusable HTTP session for connection pooling.
    """

    def __init__(self, settings: Optional[Settings] = None):
        """
        Initialize the data fetcher.

        Args:
            settings: Configuration object. Creates default if not provided.
        """
        self.settings = settings or Settings()
        self.session = requests.Session()
        self.session.headers.update(self.settings.auth_headers)

    # -----------------------------------------------------------------------
    # Public Interface
    # -----------------------------------------------------------------------

    def fetch_historical(
        self,
        instrument_key: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1minute",
    ) -> pd.DataFrame:
        """
        Fetch historical candle data for an instrument.

        Breaks the date range into chunks of FETCH_CHUNK_DAYS to stay within
        Upstox API limits. Automatically handles pagination.

        Args:
            instrument_key: Upstox instrument identifier.
            start_date: Start of data range. Defaults to DEFAULT_LOOKBACK_DAYS ago.
            end_date: End of data range. Defaults to today.
            interval: Candle interval ("1minute", "5minute", "15minute", "day").

        Returns:
            DataFrame with OHLCV data indexed by timestamp.
            Empty DataFrame if no data available.
        """
        if end_date is None:
            end_date = datetime.now()
        if start_date is None:
            start_date = end_date - timedelta(days=self.settings.DEFAULT_LOOKBACK_DAYS)

        # Build list of date chunks
        chunks = self._build_date_chunks(start_date, end_date)
        logger.info(
            f"Fetching {instrument_key} ({interval}) from "
            f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')} "
            f"in {len(chunks)} chunks"
        )

        all_candles = []
        for i, (chunk_start, chunk_end) in enumerate(chunks):
            url = (
                f"{self.settings.UPSTOX_BASE_URL}/historical-candle/"
                f"{instrument_key}/{interval}/{chunk_end}/{chunk_start}"
            )
            candles = self._fetch_with_retry(url)
            if candles:
                all_candles.extend(candles)
            if i < len(chunks) - 1:
                time.sleep(self.settings.API_RATE_LIMIT_SLEEP)

        if not all_candles:
            logger.warning(f"No data returned for {instrument_key}")
            return pd.DataFrame()

        return self._normalize_dataframe(all_candles)

    def fetch_recent(self, instrument_key: str, days: int = 5) -> pd.DataFrame:
        """
        Fetch recent historical data (last N days).

        Convenience method for the live bot to get prior days' data
        for pivot calculations.

        Args:
            instrument_key: Upstox instrument identifier.
            days: Number of days to look back.

        Returns:
            DataFrame with OHLCV data.
        """
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        return self.fetch_historical(instrument_key, start_date, end_date)

    def fetch_intraday(self, instrument_key: str) -> pd.DataFrame:
        """
        Fetch today's intraday candles up to the current minute.

        Uses the Upstox intraday endpoint which returns only
        today's data without needing date parameters.

        Args:
            instrument_key: Upstox instrument identifier.

        Returns:
            DataFrame with today's OHLCV data.
            Empty DataFrame if market hasn't opened yet.
        """
        url = (
            f"{self.settings.UPSTOX_V3_BASE_URL}/historical-candle/intraday/"
            f"{instrument_key}/minutes/1"
        )

        candles = self._fetch_with_retry(url)
        if not candles:
            return pd.DataFrame()

        return self._normalize_dataframe(candles)

    def fetch_combined(self, instrument_key: str, history_days: int = 5) -> pd.DataFrame:
        """
        Fetch historical + intraday data combined into one DataFrame.

        Essential for the live bot: needs yesterday's data for pivots
        plus today's intraday data for signal detection.

        Args:
            instrument_key: Upstox instrument identifier.
            history_days: Days of historical data to prepend.

        Returns:
            Combined DataFrame with no duplicate timestamps.
        """
        df_hist = self.fetch_recent(instrument_key, days=history_days)
        df_intra = self.fetch_intraday(instrument_key)

        if df_hist.empty and df_intra.empty:
            return pd.DataFrame()

        # Combine and deduplicate (intraday takes precedence for overlapping times)
        combined = pd.concat([df_hist, df_intra])
        combined = combined[~combined.index.duplicated(keep="last")]
        combined.sort_index(inplace=True)
        return combined

    def fetch_expired_instrument(
        self,
        instrument_key: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        Fetch historical data for an expired instrument (e.g., past futures).

        Args:
            instrument_key: Expired instrument key from Upstox.
            start_date: Start date as "YYYY-MM-DD".
            end_date: End date as "YYYY-MM-DD".

        Returns:
            DataFrame with OHLCV data.
        """
        url = (
            f"{self.settings.UPSTOX_BASE_URL}/expired-instruments/historical-candle/"
            f"{instrument_key}/1minute/{end_date}/{start_date}"
        )
        candles = self._fetch_with_retry(url)
        if not candles:
            return pd.DataFrame()
        return self._normalize_dataframe(candles)

    # -----------------------------------------------------------------------
    # Private Helpers
    # -----------------------------------------------------------------------

    def _build_date_chunks(
        self, start_date: datetime, end_date: datetime
    ) -> list:
        """
        Split a date range into chunks of FETCH_CHUNK_DAYS.

        Upstox limits historical data requests to roughly 30 calendar days.
        We use 20-day chunks for safety.

        Args:
            start_date: Beginning of the range.
            end_date: End of the range.

        Returns:
            List of (start_str, end_str) tuples in "YYYY-MM-DD" format.
        """
        chunks = []
        current = start_date
        chunk_size = timedelta(days=self.settings.FETCH_CHUNK_DAYS)

        while current <= end_date:
            chunk_end = min(current + chunk_size, end_date)
            chunks.append((
                current.strftime("%Y-%m-%d"),
                chunk_end.strftime("%Y-%m-%d"),
            ))
            current = chunk_end + timedelta(days=1)

        return chunks

    def _fetch_with_retry(self, url: str, max_retries: int = 3) -> list:
        """
        Fetch candle data from a URL with automatic retry on rate limits.

        Args:
            url: The full API URL to request.
            max_retries: Maximum number of retry attempts on 429 errors.

        Returns:
            List of candle arrays, or empty list on failure.
        """
        retries = max_retries

        while retries > 0:
            try:
                response = self.session.get(url, timeout=30)

                if response.status_code == 200:
                    data = response.json().get("data", {})
                    # Handle both nested and flat response formats
                    if isinstance(data, dict):
                        return data.get("candles", [])
                    return []

                elif response.status_code == 429:
                    # Rate limit hit — back off exponentially
                    wait_time = 2 * (max_retries - retries + 1)
                    logger.warning(f"Rate limited. Waiting {wait_time}s...")
                    time.sleep(wait_time)
                    retries -= 1

                else:
                    logger.error(f"API error ({response.status_code}): {response.text[:200]}")
                    return []

            except requests.Timeout:
                logger.warning(f"Request timed out: {url}")
                retries -= 1
            except Exception as e:
                logger.error(f"Request failed: {e}")
                retries -= 1
                time.sleep(2)

        return []

    def _normalize_dataframe(self, candles: list) -> pd.DataFrame:
        """
        Convert raw candle arrays into a clean, standardized DataFrame.

        Handles:
        - Column naming
        - Timezone conversion (UTC+5:30 → naive IST)
        - Sorting and deduplication
        - Dropping OI column (not needed by strategies)

        Args:
            candles: List of [timestamp, open, high, low, close, volume, oi] arrays.

        Returns:
            Cleaned DataFrame with DateTimeIndex.
        """
        df = pd.DataFrame(candles, columns=OHLCV_COLUMNS)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        # Convert timezone-aware timestamps to naive IST
        try:
            df["timestamp"] = df["timestamp"].dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
        except TypeError:
            # Already timezone-naive
            df["timestamp"] = df["timestamp"].dt.tz_localize(None)

        df.set_index("timestamp", inplace=True)
        df.sort_index(inplace=True)
        df.drop_duplicates(inplace=True)
        # Drop OI — not used by any current strategy
        df.drop(columns=["oi"], inplace=True, errors="ignore")

        return df
