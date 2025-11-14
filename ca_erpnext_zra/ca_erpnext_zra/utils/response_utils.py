import json
from typing import Any, Union, List, Dict

def parse_response_data(
    response: Union[str, bytes, dict, list],
    expected_type: type = list
) -> Union[List[Any], Dict[str, Any], Any]:
    """Parse Smart Zambia (ZRA) API response and extract relevant data section.

    Handles the nested structure like:
    {
        "Result": {
            "data": {
                "itemList": [...]
            }
        }
    }

    Args:
        response: Input data (JSON string, bytes, or Python object)
        expected_type: Desired output type (list or dict)

    Returns:
        Extracted data converted to the expected type.

    Raises:
        ValueError: If JSON parsing fails.
        TypeError: If type conversion fails.
    """
    # --- Normalize JSON ---
    if isinstance(response, (str, bytes)):
        try:
            response = json.loads(response)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {str(e)}") from e

    if response is None:
        return expected_type()

    try:
        # --- Smart Zambia structure extraction ---
        if isinstance(response, dict):
            result = response.get("Result", {})
            data = result.get("data", {})
            # Common Smart Zambia data containers
            if "itemList" in data:
                extracted = data["itemList"]
            elif "data" in result:
                extracted = result["data"]
            else:
                extracted = data or result or response
        else:
            extracted = response

        # --- Type casting ---
        if expected_type is list:
            if isinstance(extracted, list):
                return extracted
            elif isinstance(extracted, dict):
                # Convert dict to list if wrapped in data structure
                return [extracted]
            else:
                return [extracted]

        elif expected_type is dict:
            if isinstance(extracted, dict):
                return extracted
            elif isinstance(extracted, list) and extracted:
                return extracted[0]
            else:
                return {}

        # --- Default fallback ---
        return expected_type(extracted)

    except (TypeError, AttributeError) as e:
        raise TypeError(f"Cannot convert response to {expected_type}: {str(e)}") from e
