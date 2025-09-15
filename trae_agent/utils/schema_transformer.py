# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Schema transformation utilities for different LLM providers."""

from typing import Any, Dict


def transform_schema_for_openai(schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform a JSON schema to be compatible with OpenAI's strict requirements.

    OpenAI requires:
    1. All properties must be in the 'required' array
    2. Optional properties should be nullable (anyOf with null)
    3. additionalProperties: false for strict mode

    Args:
        schema: Original schema (could be nested)

    Returns:
        Transformed schema compatible with OpenAI
    """
    # Handle non-dict input
    if not isinstance(schema, dict):
        return schema

    # Skip transformation for non-object schemas
    if schema.get("type") != "object":
        return schema

    # Skip complex schemas with composition keywords
    if any(key in schema for key in ["oneOf", "anyOf", "allOf"]):
        return schema

    # If no properties, just add additionalProperties and return
    if "properties" not in schema:
        result = schema.copy()
        result["additionalProperties"] = False
        return result

    # Create transformed schema
    transformed = schema.copy()
    properties = schema["properties"]
    original_required = set(schema.get("required", []))

    # Transform properties
    new_properties = {}
    for prop_name, prop_def in properties.items():
        if not isinstance(prop_def, dict):
            # Handle non-dict property definitions
            new_properties[prop_name] = prop_def
            continue

        # Start with a copy of the original property
        transformed_prop = prop_def.copy()

        # Recursively transform nested objects
        if prop_def.get("type") == "object":
            transformed_prop = transform_schema_for_openai(prop_def)

        # Transform array items if they're objects
        elif prop_def.get("type") == "array" and "items" in prop_def:
            items = prop_def["items"]
            if isinstance(items, dict) and items.get("type") == "object":
                transformed_prop = prop_def.copy()
                transformed_prop["items"] = transform_schema_for_openai(items)

        # Make optional properties nullable ONLY if there was an explicit required array
        # If no required array exists, treat all properties as required (common MCP pattern)
        if "required" in schema and prop_name not in original_required:
            new_properties[prop_name] = {"anyOf": [transformed_prop, {"type": "null"}]}
        else:
            new_properties[prop_name] = transformed_prop

    # All properties become required
    transformed["properties"] = new_properties
    transformed["required"] = list(properties.keys())

    # Add additionalProperties: false for OpenAI strict mode
    transformed["additionalProperties"] = False

    return transformed
