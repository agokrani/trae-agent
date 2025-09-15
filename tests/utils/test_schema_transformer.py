# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for schema transformation utilities."""

import unittest

from trae_agent.utils.schema_transformer import transform_schema_for_openai


class TestSchemaTransformer(unittest.TestCase):
    """Test schema transformation for OpenAI compatibility."""

    def test_transform_figma_like_schema(self):
        """Test transformation of Figma-like nested schema (the failing case)."""
        # This is the exact structure that was failing
        input_schema = {
            "type": "object",
            "properties": {
                "nodes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {"imageRef": {"type": "string"}},
                        # Missing "required": ["imageRef"] - this causes the error
                    },
                }
            },
        }

        result = transform_schema_for_openai(input_schema)

        # Top level should be transformed
        self.assertEqual(result["required"], ["nodes"])
        self.assertTrue(result["additionalProperties"] is False)

        # Nested schema (items) should be transformed
        items_schema = result["properties"]["nodes"]["items"]
        self.assertEqual(items_schema["required"], ["imageRef"])
        self.assertTrue(items_schema["additionalProperties"] is False)
        self.assertEqual(items_schema["properties"]["imageRef"]["type"], "string")

    def test_transform_with_optional_properties(self):
        """Test transformation with required and optional properties."""
        input_schema = {
            "type": "object",
            "properties": {
                "required_field": {"type": "string"},
                "optional_field": {"type": "string"},
            },
            "required": ["required_field"],
        }

        result = transform_schema_for_openai(input_schema)

        # All properties should be required now
        self.assertEqual(set(result["required"]), {"required_field", "optional_field"})

        # Required field stays as-is
        self.assertEqual(result["properties"]["required_field"]["type"], "string")

        # Optional field becomes nullable
        optional_prop = result["properties"]["optional_field"]
        self.assertIn("anyOf", optional_prop)
        self.assertEqual(len(optional_prop["anyOf"]), 2)
        self.assertIn({"type": "string"}, optional_prop["anyOf"])
        self.assertIn({"type": "null"}, optional_prop["anyOf"])

    def test_non_object_schema_unchanged(self):
        """Test that non-object schemas are returned unchanged."""
        test_cases = [
            {"type": "string"},
            {"type": "array", "items": {"type": "string"}},
            {"type": "integer"},
            "not a dict",
            123,
        ]

        for schema in test_cases:
            result = transform_schema_for_openai(schema)
            self.assertEqual(result, schema)

    def test_complex_schema_skipped(self):
        """Test that complex schemas with oneOf/anyOf/allOf are skipped."""
        test_cases = [
            {"type": "object", "oneOf": [{"type": "string"}, {"type": "integer"}]},
            {"type": "object", "anyOf": [{"properties": {"a": {"type": "string"}}}]},
            {"type": "object", "allOf": [{"required": ["a"]}]},
        ]

        for schema in test_cases:
            result = transform_schema_for_openai(schema)
            self.assertEqual(result, schema)  # Should be unchanged

    def test_deeply_nested_objects(self):
        """Test recursive transformation of deeply nested objects."""
        input_schema = {
            "type": "object",
            "properties": {
                "level1": {
                    "type": "object",
                    "properties": {
                        "level2": {
                            "type": "object",
                            "properties": {"deep_field": {"type": "string"}},
                        }
                    },
                }
            },
        }

        result = transform_schema_for_openai(input_schema)

        # Check all levels have required fields and additionalProperties
        self.assertEqual(result["required"], ["level1"])
        self.assertTrue(result["additionalProperties"] is False)

        level1 = result["properties"]["level1"]
        self.assertEqual(level1["required"], ["level2"])
        self.assertTrue(level1["additionalProperties"] is False)

        level2 = level1["properties"]["level2"]
        self.assertEqual(level2["required"], ["deep_field"])
        self.assertTrue(level2["additionalProperties"] is False)

    def test_array_with_object_items_nested(self):
        """Test arrays with object items containing nested objects."""
        input_schema = {
            "type": "object",
            "properties": {
                "data": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "nested": {
                                "type": "object",
                                "properties": {"value": {"type": "string"}},
                            }
                        },
                    },
                }
            },
        }

        result = transform_schema_for_openai(input_schema)

        # Check nested object in array items is transformed
        items_schema = result["properties"]["data"]["items"]
        self.assertEqual(items_schema["required"], ["nested"])

        nested_schema = items_schema["properties"]["nested"]
        self.assertEqual(nested_schema["required"], ["value"])
        self.assertTrue(nested_schema["additionalProperties"] is False)

    def test_empty_properties_object(self):
        """Test schema with empty properties object."""
        input_schema = {"type": "object", "properties": {}}

        result = transform_schema_for_openai(input_schema)

        self.assertEqual(result["properties"], {})
        self.assertEqual(result["required"], [])
        self.assertTrue(result["additionalProperties"] is False)

    def test_no_properties_field(self):
        """Test object schema without properties field."""
        input_schema = {"type": "object"}

        result = transform_schema_for_openai(input_schema)

        self.assertNotIn("properties", result)
        self.assertTrue(result["additionalProperties"] is False)

    def test_non_dict_property_values(self):
        """Test handling of non-dict property values."""
        input_schema = {
            "type": "object",
            "properties": {
                "simple": "string",  # Not a dict
                "normal": {"type": "string"},
            },
        }

        result = transform_schema_for_openai(input_schema)

        self.assertEqual(result["properties"]["simple"], "string")  # Unchanged
        self.assertEqual(result["properties"]["normal"]["type"], "string")
        self.assertEqual(result["required"], ["simple", "normal"])


if __name__ == "__main__":
    unittest.main()
