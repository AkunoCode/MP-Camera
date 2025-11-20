import os
from threading import Lock


class RoboflowClient:
    """Light wrapper around the InferenceHTTPClient used for running workflows.

    Defaults are read from environment variables but fall back to the values
    from the example you provided so it works out-of-the-box for local testing.
    """

    _instance = None
    _lock = Lock()

    def __init__(self, api_url=None, api_key=None, workspace=None, workflow=None):
        self.api_url = api_url or os.getenv("ROBOFLOW_API_URL", "http://localhost:9001")
        self.api_key = api_key or os.getenv("ROBOFLOW_API_KEY", "CMSG0BB2Q9eVRoPgGDM1")
        self.workspace = workspace or os.getenv("ROBOFLOW_WORKSPACE", "soilsight-xstgr")
        self.workflow = workflow or os.getenv(
            "ROBOFLOW_WORKFLOW", "detect-count-and-visualize-2"
        )

        # lazy import of the external SDK; keep a reference to the client if available
        self._client = None
        try:
            from inference_sdk import InferenceHTTPClient

            self._client = InferenceHTTPClient(
                api_url=self.api_url, api_key=self.api_key
            )
        except Exception as e:
            # Do not raise — caller should handle absence of dependency gracefully.
            print("RoboflowClient: failed to import inference_sdk or create client:", e)

    @classmethod
    def get_default(cls):
        """Return a shared RoboflowClient instance (thread-safe singleton)."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = RoboflowClient()
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
