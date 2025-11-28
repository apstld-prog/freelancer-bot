import os
import json
import httpx
from typing import Any, Optional

UPSTASH_URL = os.getenv("UPSTASH_REDIS_REST_URL")
UPSTASH_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN")


class RedisClient:
    def __init__(self) -> None:
        if not UPSTASH_URL or not UPSTASH_TOKEN:
            raise RuntimeError("Upstash Redis env vars not set")
        self.base_url = UPSTASH_URL.rstrip("/")
        self.token = UPSTASH_TOKEN

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_json(self, key: str) -> Optional[Any]:
        """
        Παίρνει JSON value από Redis, ή None αν δεν υπάρχει.
        """
        url = f"{self.base_url}/get/{key}"
        try:
            r = httpx.get(url, headers=self._headers(), timeout=5.0)
            r.raise_for_status()
            data = r.json()
            # Upstash REST GET επιστρέφει {"result": "..."} ή {"result": None}
            value = data.get("result")
            if value is None:
                return None
            return json.loads(value)
        except Exception:
            return None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> bool:
        """
        Αποθηκεύει JSON stringified value με TTL (σε δευτερόλεπτα).
        """
        url = f"{self.base_url}/set/{key}"
        try:
            payload = {
                "value": json.dumps(value),
                "ex": ttl_seconds,
            }
            r = httpx.post(url, headers=self._headers(), json=payload, timeout=5.0)
            r.raise_for_status()
            return True
        except Exception:
            return False


# Global singleton
redis_client = RedisClient()
