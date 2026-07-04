import os
import requests

class DiscordNotifier:
    def __init__(self):
        # Securely grabs the webhook from your .env file
        self.webhook_url = os.getenv("DISCORD_WEBHOOK_URL")

    def send_message(self, message):
        """Pushes a formatted string to the Trading Assistant Discord channel."""
        if not self.webhook_url:
            print("⚠️ WARNING: DISCORD_WEBHOOK_URL not found in environment.")
            return

        payload = {"content": f"🤖 **Trading Update:** {message}"}
        
        try:
            response = requests.post(self.webhook_url, json=payload)
            response.raise_for_status()
        except Exception as e:
            # If Discord fails, we just log it and move on. 
            # We do NOT crash the trading execution.
            print(f"❌ Failed to send Discord notification: {e}")