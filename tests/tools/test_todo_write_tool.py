# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tests for the todo write tool."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from trae_agent.tools.todo_write_tool import TodoItem, TodoWriteTool


class TestTodoWriteTool(unittest.IsolatedAsyncioTestCase):
    """Test cases for TodoWriteTool."""

    def setUp(self):
        """Set up test fixtures."""
        self.tool = TodoWriteTool()
        self.temp_dir = tempfile.mkdtemp()
        self.todos_dir = Path(self.temp_dir) / "todos"
        self.todos_dir.mkdir(parents=True, exist_ok=True)

    def test_get_name(self):
        """Test tool name."""
        self.assertEqual(self.tool.get_name(), "todo_write")

    def test_get_description(self):
        """Test tool description is not empty."""
        description = self.tool.get_description()
        self.assertIsInstance(description, str)
        self.assertGreater(len(description), 100)
        self.assertIn("task list", description.lower())

    def test_get_parameters(self):
        """Test tool parameters."""
        parameters = self.tool.get_parameters()
        self.assertIsInstance(parameters, list)
        self.assertGreater(len(parameters), 0)

        # Check required todos parameter
        todos_param = next((p for p in parameters if p.name == "todos"), None)
        self.assertIsNotNone(todos_param)
        self.assertTrue(todos_param.required)
        self.assertEqual(todos_param.type, "array")

    def test_validate_todos_valid(self):
        """Test validation with valid todos."""
        todos_data = [
            {"id": "1", "content": "Test task 1", "status": "pending"},
            {"id": "2", "content": "Test task 2", "status": "in_progress"},
        ]

        todos = self.tool._validate_todos(todos_data)
        self.assertEqual(len(todos), 2)
        self.assertEqual(todos[0].id, "1")
        self.assertEqual(todos[0].content, "Test task 1")
        self.assertEqual(todos[0].status, "pending")

    def test_validate_todos_missing_fields(self):
        """Test validation with missing required fields."""
        todos_data = [
            {
                "id": "1",
                "content": "Test task 1",
                # Missing status
            }
        ]

        with self.assertRaises(Exception) as context:
            self.tool._validate_todos(todos_data)
        self.assertIn("missing required field 'status'", str(context.exception))

    def test_validate_todos_invalid_status(self):
        """Test validation with invalid status."""
        todos_data = [{"id": "1", "content": "Test task 1", "status": "invalid_status"}]

        with self.assertRaises(Exception) as context:
            self.tool._validate_todos(todos_data)
        self.assertIn("invalid status", str(context.exception))

    def test_validate_todos_duplicate_ids(self):
        """Test validation with duplicate IDs."""
        todos_data = [
            {"id": "1", "content": "Test task 1", "status": "pending"},
            {
                "id": "1",  # Duplicate ID
                "content": "Test task 2",
                "status": "in_progress",
            },
        ]

        with self.assertRaises(Exception) as context:
            self.tool._validate_todos(todos_data)
        self.assertIn("Duplicate todo ID", str(context.exception))

    def test_format_todos_display_empty(self):
        """Test formatting empty todo list."""
        display = self.tool._format_todos_display([])
        self.assertIn("Todo list is empty", display)

    def test_format_todos_display_with_todos(self):
        """Test formatting todo list with items."""
        todos = [
            TodoItem(id="1", content="Pending task", status="pending"),
            TodoItem(id="2", content="In progress task", status="in_progress"),
            TodoItem(id="3", content="Completed task", status="completed"),
        ]

        display = self.tool._format_todos_display(todos)
        self.assertIn("Todo List", display)
        self.assertIn("Pending task", display)
        self.assertIn("In progress task", display)
        self.assertIn("Completed task", display)
        self.assertIn("Summary:", display)

    @patch("trae_agent.tools.todo_write_tool.LOCAL_STORAGE_PATH")
    def test_file_operations(self, mock_storage_path):
        """Test file read/write operations."""
        mock_storage_path.__truediv__ = lambda self, other: Path(self.temp_dir) / other
        mock_storage_path.return_value = Path(self.temp_dir)

        # Test writing todos
        todos = [TodoItem(id="1", content="Test task", status="pending")]

        with patch.object(self.tool, "_get_todo_file_path") as mock_get_path:
            todo_file = self.todos_dir / "test.json"
            mock_get_path.return_value = todo_file

            self.tool._write_todos_to_file(todos, "test")
            self.assertTrue(todo_file.exists())

            # Test reading todos
            read_todos = self.tool._read_todos_from_file("test")
            self.assertEqual(len(read_todos), 1)
            self.assertEqual(read_todos[0].id, "1")
            self.assertEqual(read_todos[0].content, "Test task")
            self.assertEqual(read_todos[0].status, "pending")

    @patch("trae_agent.tools.todo_write_tool.LOCAL_STORAGE_PATH")
    async def test_execute_success(self, mock_storage_path):
        """Test successful tool execution."""
        mock_storage_path.__truediv__ = lambda self, other: Path(self.temp_dir) / other

        arguments = {"todos": [{"id": "1", "content": "Test task", "status": "pending"}]}

        with patch.object(self.tool, "_get_todo_file_path") as mock_get_path:
            todo_file = self.todos_dir / "default.json"
            mock_get_path.return_value = todo_file

            result = await self.tool.execute(arguments)
            self.assertIsNone(result.error)
            self.assertIsNotNone(result.output)
            self.assertIn("Todo List", result.output)
            self.assertIn("Test task", result.output)

    async def test_execute_missing_todos(self):
        """Test execution with missing todos parameter."""
        arguments = {}

        result = await self.tool.execute(arguments)
        self.assertIsNotNone(result.error)
        self.assertIn("Parameter 'todos' is required", result.error)
        self.assertEqual(result.error_code, -1)

    async def test_execute_invalid_todos(self):
        """Test execution with invalid todos."""
        arguments = {
            "todos": [
                {
                    "id": "1",
                    "content": "Test task",
                    # Missing status
                }
            ]
        }

        result = await self.tool.execute(arguments)
        self.assertIsNotNone(result.error)
        self.assertIn("missing required field 'status'", result.error)


if __name__ == "__main__":
    unittest.main()
