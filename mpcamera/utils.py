import base64
from typing import Any, Optional


def find_base64_image(obj: Any) -> Optional[str]:
    """Recursively search the result object for a data URL or base64 string representing an image.

    Returns the base64 part (without data:image/...;base64, prefix) or None.
    """
    if obj is None:
        return None

    # If it's a string, check patterns
    if isinstance(obj, str):
        if obj.startswith("data:image") and ";base64," in obj:
            return obj.split(",", 1)[1]
        # Heuristic: long base64 string without prefix
        if len(obj) > 100 and all(c.isalnum() or c in "+/=\n\r" for c in obj):
            return obj
        return None

    # If bytes, base64-encode it
    if isinstance(obj, (bytes, bytearray)):
        return base64.b64encode(bytes(obj)).decode("ascii")

    # If dict or list, recurse
    if isinstance(obj, dict):
        for k, v in obj.items():
            found = find_base64_image(v)
            if found:
                return found

    if isinstance(obj, list):
        for item in obj:
            found = find_base64_image(item)
            if found:
                return found

    return None
