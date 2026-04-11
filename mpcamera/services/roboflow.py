import os
import logging
from threading import Lock
from typing import Any, Dict

try:
    from mpcamera.config import get_settings
except Exception as _e:
    logger.debug(f"mpcamera.config unavailable in roboflow: {_e}")
    get_settings = None

logger = logging.getLogger(__name__)


class RoboflowClient:
    """Light wrapper around the InferenceHTTPClient used for running workflows.

    Defaults are read from environment variables but fall back to the values
    from the example you provided so it works out-of-the-box for local testing.
    """

    _instance = None
    _lock = Lock()
    _state_lock = Lock()  # Protects mutable instance state

    def __init__(self, api_url=None, api_key=None, workspace=None, workflow=None):
        settings = _get_roboflow_settings()

        self.api_url = (
            api_url
            or os.getenv("ROBOFLOW_API_URL")
            or settings.get("api_url")
            or "http://localhost:9001"
        )
        self.api_key = (
            api_key
            or os.getenv("ROBOFLOW_API_KEY")
            or settings.get("api_key")
            or ""
        )
        self.workspace = (
            workspace
            or os.getenv("ROBOFLOW_WORKSPACE")
            or settings.get("workspace")
            or "soilsight-xstgr"
        )
        self.workflow = (
            workflow
            or os.getenv("ROBOFLOW_WORKFLOW")
            or settings.get("workflow")
            or "detect-count-and-visualize-2"
        )

        # lazy import of the external SDK; keep a reference to the client if available
        self._client = None
        self._create_client()

    def _create_client(self) -> None:
        try:
            if not self.api_key:
                self._client = None
                return

            from inference_sdk import InferenceHTTPClient

            self._client = InferenceHTTPClient(
                api_url=self.api_url, api_key=self.api_key
            )
        except Exception as e:
            # Do not raise — caller should handle absence of dependency gracefully.
            self._client = None
            logger.error("Failed to create RoboflowClient (inference_sdk missing or misconfigured)", exc_info=True)

    def refresh_auth_from_settings(self) -> None:
        """Refresh API URL/key/workspace from env or settings."""
        with RoboflowClient._state_lock:
            settings = _get_roboflow_settings()

            new_api_url = (
                os.getenv("ROBOFLOW_API_URL")
                or settings.get("api_url")
                or self.api_url
            )
            new_api_key = (
                os.getenv("ROBOFLOW_API_KEY")
                or settings.get("api_key")
                or self.api_key
            )
            new_workspace = (
                os.getenv("ROBOFLOW_WORKSPACE")
                or settings.get("workspace")
                or self.workspace
            )

            api_changed = (new_api_url != self.api_url) or (new_api_key != self.api_key)

            self.api_url = new_api_url
            self.api_key = new_api_key
            self.workspace = new_workspace

            if api_changed:
                self._create_client()

    @classmethod
    def get_default(cls):
        """Return a shared RoboflowClient instance (thread-safe singleton)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = RoboflowClient()
        else:
            cls._instance.refresh_auth_from_settings()
        return cls._instance

    # UPDATED: Added confidence and iou parameters here
    def run_workflow(
        self,
        image_path: str,
        confidence: float = 0.5,
        iou: float = 0.5,
        use_cache: bool = True,
    ):
        """Run the configured workflow on `image_path` and return the result.

        Returns the raw result object from the SDK, or a dict describing an error.
        """
        if not self.api_key:
            return {
                "error": "Roboflow API key missing. Set it in Settings or ROBOFLOW_API_KEY env var."
            }

        if self._client is None:
            return {
                "error": "inference_sdk not installed or client initialization failed"
            }

        try:
            # UPDATED: Create a parameters dictionary to pass to the workflow
            workflow_params = {"confidence": confidence, "iou": iou}

            result = self._client.run_workflow(
                workspace_name=self.workspace,
                workflow_id=self.workflow,
                images={"image": image_path},
                parameters=workflow_params,  # UPDATED: Pass the parameters here
                use_cache=use_cache,
            )
            return result
        except Exception as e:
            return {"error": str(e)}


def _get_roboflow_settings() -> Dict[str, Any]:
    if get_settings is None:
        return {}
    try:
        cfg = get_settings()
        services = cfg.get("services", {}) if isinstance(cfg, dict) else cfg.services
        roboflow = (
            services.get("roboflow", {})
            if isinstance(services, dict)
            else services.roboflow
        )
        if isinstance(roboflow, dict):
            return {
                "api_url": roboflow.get("api_url"),
                "api_key": roboflow.get("api_key"),
                "workspace": roboflow.get("workspace"),
                "workflow": roboflow.get("workflow"),
            }
        return {
            "api_url": getattr(roboflow, "api_url", None),
            "api_key": getattr(roboflow, "api_key", None),
            "workspace": getattr(roboflow, "workspace", None),
            "workflow": getattr(roboflow, "workflow", None),
        }
    except Exception:
        logger.debug("Could not read Roboflow settings from config", exc_info=True)
        return {}
