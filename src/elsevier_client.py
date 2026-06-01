"""Thin, polite Elsevier API client.

Design goals (the things that bit us last time):
  * Never exceed per-second throttle  -> token-bucket sleep per API.
  * Never blow the weekly quota silently -> read X-RateLimit-Remaining and
    abort cleanly (with a saved cursor) before hitting zero.
  * Never re-fetch -> every successful payload is checkpointed to disk by the
    callers; this client just does one well-behaved request.
  * Survive 429/5xx -> exponential backoff with cap.
"""
import time

import requests

from . import config

_last_call = {}  # api_name -> monotonic timestamp


class QuotaExhausted(Exception):
    """Raised when the weekly quota is (near) zero so callers can stop & resume."""


def _throttle(api: str):
    rate = config.THROTTLE.get(api, 2)
    min_gap = 1.0 / rate
    now = time.monotonic()
    last = _last_call.get(api, 0.0)
    wait = min_gap - (now - last)
    if wait > 0:
        time.sleep(wait)
    _last_call[api] = time.monotonic()


def _headers():
    if not config.API_KEY:
        raise RuntimeError(
            "No API key. Put it in ~/.config/elsevier/apikey or set ELSEVIER_API_KEY."
        )
    h = {"X-ELS-APIKey": config.API_KEY, "Accept": "application/json"}
    if config.INST_TOKEN:
        h["X-ELS-Insttoken"] = config.INST_TOKEN
    return h


def get(url, api, params=None, accept="application/json",
        quota_floor=50, max_retries=6, extra_headers=None):
    """One GET with throttle, quota-guard, and backoff.

    Returns the requests.Response on success. Raises QuotaExhausted if the
    remaining weekly quota drops to <= quota_floor.
    """
    _throttle(api)
    headers = _headers()
    headers["Accept"] = accept
    if extra_headers:
        headers.update(extra_headers)

    backoff = 2.0
    for attempt in range(max_retries):
        resp = requests.get(url, headers=headers, params=params, timeout=60)
        remaining = resp.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                if int(remaining) <= quota_floor:
                    raise QuotaExhausted(
                        f"{api}: {remaining} requests left; stopping to preserve resume."
                    )
            except ValueError:
                pass

        if resp.status_code == 200:
            return resp
        if resp.status_code == 429:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        if resp.status_code in (500, 502, 503, 504):
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
            continue
        # 401/403/400/404 etc. -> surface immediately; caller decides.
        resp.raise_for_status()
        return resp
    raise RuntimeError(f"{api}: exhausted {max_retries} retries for {url}")
