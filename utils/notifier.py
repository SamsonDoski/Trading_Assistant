import os
import time
import requests


class DiscordNotifier:
    MIN_INTERVAL = 0.5  # seconds between posts, to respect Discord's webhook rate limit

    def __init__(self):
        # Securely grabs the webhook from your .env / Lambda env
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")
        self._last_send = 0.0

    def send_message(self, message):
        """Pushes a formatted string to Discord. Throttles to stay under the
        webhook rate limit and retries once if Discord still returns 429."""
        if not self.webhook_url:
            print("⚠️ WARNING: DISCORD_WEBHOOK_URL not found in environment.")
            return

        # Throttle: keep at least MIN_INTERVAL between requests so a burst of
        # messages (e.g. the trailing-stop pass) doesn't trip Discord's limiter.
        wait = self.MIN_INTERVAL - (time.monotonic() - self._last_send)
        if wait > 0:
            time.sleep(wait)

        payload = {"content": f"🤖 **Trading Update:** {message}"}
        try:
            resp = requests.post(self.webhook_url, json=payload)
            # If we still got rate-limited, honor Retry-After and try once more.
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", 1.0))
                time.sleep(retry_after)
                resp = requests.post(self.webhook_url, json=payload)
            resp.raise_for_status()
        except Exception as e:
            # Never crash trading over a failed notification.
            print(f"❌ Failed to send Discord notification: {e}")
        finally:
            self._last_send = time.monotonic()