import json
import logging
import os
import urllib.error
import urllib.request

logger = logging.getLogger(__name__)


class LifecycleManagementClient:
    """
    Client for triggering application restarts via an external Lifecycle Manager
    (e.g., AuraGrid Management API).
    """

    def __init__(self):
        self.management_url = os.environ.get("AURAGRID_MANAGEMENT_URL")
        self.auth_token = os.environ.get("AURAGRID_MANAGEMENT_TOKEN")

        if not self.management_url:
            logger.info("AURAGRID_MANAGEMENT_URL not set. LifecycleManagementClient will no-op.")
        else:
            logger.info(f"LifecycleManagementClient configured with url: {self.management_url}")

    def trigger_restart(
        self, app_id: str, version: str = "latest", user_id: str = "auracode-git-poller"
    ):
        """
        Triggers an application restart by calling the external Management API's
        deployment endpoint to redeploy the app.

        If the client is not configured, this is a safe no-op.
        """
        if not self.management_url:
            logger.debug(f"Ignoring restart trigger for {app_id}; no management URL configured.")
            return

        # Typical endpoint might be /api/deployments/restart or just re-posting a deployment
        endpoint = f"{self.management_url.rstrip('/')}/api/deployments/restart"

        payload = {"appId": app_id, "version": version, "userId": user_id}

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(endpoint, data=data, method="POST")
        req.add_header("Content-Type", "application/json")

        if self.auth_token:
            req.add_header("Authorization", f"Bearer {self.auth_token}")

        try:
            logger.info(f"Triggering restart for {app_id} via {endpoint}")
            with urllib.request.urlopen(req) as response:
                if response.status >= 200 and response.status < 300:
                    logger.info(f"Successfully triggered restart for {app_id}")
                else:
                    logger.warning(f"Restart trigger returned status {response.status}")
        except urllib.error.URLError as e:
            logger.error(f"Failed to trigger restart for {app_id}: {e}")
