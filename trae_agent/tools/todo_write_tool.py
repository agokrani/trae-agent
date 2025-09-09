# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Todo write tool for managing task lists during coding sessions."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast, override

from trae_agent.tools.base import Tool, ToolCallArguments, ToolError, ToolExecResult, ToolParameter
from trae_agent.utils.constants import LOCAL_STORAGE_PATH


@dataclass
class TodoItem:
    """Represents a single todo item."""

    id: str
    content: str
    status: str  # 'pending', 'in_progress', 'completed'


class TodoWriteTool(Tool):
    """Tool to create and manage a structured task list for coding sessions.

    This tool helps track progress, organize complex tasks, and demonstrate
    thoroughness during implementation.
    """

    def __init__(self, model_provider: str | None = None) -> None:
        super().__init__(model_provider)

    @override
    def get_model_provider(self) -> str | None:
        return self._model_provider

    @override
    def get_name(self) -> str:
        return "todo_write"

    @override
    def get_description(self) -> str:
        return """Creates and manages a structured task list for your current coding session. This helps track progress, organize complex tasks, and demonstrate thoroughness.

Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning work. Ideally you should only have one todo as in_progress at a time
7. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and tracking it provides no organizational benefit
3. The task can be completed in less than 3 trivial steps
4. The task is purely conversational or informational

NOTE that you should not use this tool if there is only one trivial task to do. In this case you are better off just doing the task directly.

## Task States and Management

1. **Task States**: Use these states to track progress:
   - pending: Task not yet started
   - in_progress: Currently working on (limit to ONE task at a time)
   - completed: Task finished successfully

2. **Task Management**:
   - Update task status in real-time as you work
   - Mark tasks complete IMMEDIATELY after finishing (don't batch completions)
   - Only have ONE task in_progress at any time
   - Complete current tasks before starting new ones
   - Remove tasks that are no longer relevant from the list entirely

3. **Task Completion Requirements**:
   - ONLY mark a task as completed when you have FULLY accomplished it
   - If you encounter errors, blockers, or cannot finish, keep the task as in_progress
   - When blocked, create a new task describing what needs to be resolved
   - Never mark a task as completed if:
     - Tests are failing
     - Implementation is partial
     - You encountered unresolved errors
     - You couldn't find necessary files or dependencies

4. **Task Breakdown**:
   - Create specific, actionable items
   - Break complex tasks into smaller, manageable steps
   - Use clear, descriptive task names

When in doubt, use this tool. Being proactive with task management demonstrates attentiveness and ensures you complete all requirements successfully."""

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="todos",
                type="array",
                description="The updated todo list",
                required=True,
                items={
                    "type": "object",
                    "properties": {
                        "id": {
                            "type": "string",
                            "description": "Unique identifier for the todo item",
                        },
                        "content": {
                            "type": "string",
                            "description": "The textual content of the todo item",
                        },
                        "status": {
                            "type": "string",
                            "enum": ["pending", "in_progress", "completed"],
                            "description": "Current status of the todo item",
                        },
                    },
                    "required": ["id", "content", "status"],
                    "additionalProperties": False,
                },
            ),
            ToolParameter(
                name="session_id",
                type="string",
                description="Optional session identifier for organizing todos by session",
                required=False,
            ),
        ]

    def _get_todo_file_path(self, session_id: str | None = None) -> Path:
        """Get the path to the todo file for a given session."""
        todos_dir = LOCAL_STORAGE_PATH / "todos"
        todos_dir.mkdir(parents=True, exist_ok=True)

        # Use session_id if provided, otherwise use 'default'
        filename = f"{session_id or 'default'}.json"
        return todos_dir / filename

    def _read_todos_from_file(self, session_id: str | None = None) -> list[TodoItem]:
        """Read todos from the file system."""
        try:
            todo_file_path = self._get_todo_file_path(session_id)
            if not todo_file_path.exists():
                return []

            content = todo_file_path.read_text(encoding="utf-8")
            data = json.loads(content)

            if not isinstance(data, dict) or "todos" not in data:
                return []

            todos_data = data["todos"]
            if not isinstance(todos_data, list):
                return []

            todos = []
            for todo_data in todos_data:
                if (
                    isinstance(todo_data, dict)
                    and "id" in todo_data
                    and "content" in todo_data
                    and "status" in todo_data
                ):
                    todos.append(
                        TodoItem(
                            id=str(todo_data["id"]),
                            content=str(todo_data["content"]),
                            status=str(todo_data["status"]),
                        )
                    )
            return todos

        except (json.JSONDecodeError, OSError, ValueError):
            # Return empty list if file doesn't exist or is corrupted
            return []

    def _write_todos_to_file(self, todos: list[TodoItem], session_id: str | None = None) -> None:
        """Write todos to the file system."""
        todo_file_path = self._get_todo_file_path(session_id)

        # Ensure parent directory exists
        todo_file_path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "todos": [
                {"id": todo.id, "content": todo.content, "status": todo.status} for todo in todos
            ],
            "session_id": session_id or "default",
        }

        try:
            todo_file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError as e:
            raise ToolError(f"Failed to write todos to file: {e}") from e

    def _validate_todos(self, todos_data: list[dict]) -> list[TodoItem]:
        """Validate and convert todo data to TodoItem objects."""
        if not isinstance(todos_data, list):
            raise ToolError("Parameter 'todos' must be an array")

        todos = []
        seen_ids = set()

        for i, todo_data in enumerate(todos_data):
            if not isinstance(todo_data, dict):
                raise ToolError(f"Todo item {i} must be an object")

            # Validate required fields
            if "id" not in todo_data:
                raise ToolError(f"Todo item {i} missing required field 'id'")
            if "content" not in todo_data:
                raise ToolError(f"Todo item {i} missing required field 'content'")
            if "status" not in todo_data:
                raise ToolError(f"Todo item {i} missing required field 'status'")

            todo_id = str(todo_data["id"]).strip()
            content = str(todo_data["content"]).strip()
            status = str(todo_data["status"]).strip()

            # Validate values
            if not todo_id:
                raise ToolError(f"Todo item {i} has empty 'id'")
            if not content:
                raise ToolError(f"Todo item {i} has empty 'content'")
            if status not in ["pending", "in_progress", "completed"]:
                raise ToolError(
                    f"Todo item {i} has invalid status '{status}'. Must be one of: pending, in_progress, completed"
                )

            # Check for duplicate IDs
            if todo_id in seen_ids:
                raise ToolError(f"Duplicate todo ID '{todo_id}' found")
            seen_ids.add(todo_id)

            todos.append(TodoItem(id=todo_id, content=content, status=status))

        return todos

    def _format_todos_display(self, todos: list[TodoItem]) -> str:
        """Format todos for display output."""
        if not todos:
            return "📝 Todo list is empty"

        display_lines = ["📝 **Todo List**"]
        display_lines.append("")

        # Group todos by status
        pending_todos = [t for t in todos if t.status == "pending"]
        in_progress_todos = [t for t in todos if t.status == "in_progress"]
        completed_todos = [t for t in todos if t.status == "completed"]

        if in_progress_todos:
            display_lines.append("🔄 **In Progress:**")
            for todo in in_progress_todos:
                display_lines.append(f"   • {todo.content}")
            display_lines.append("")

        if pending_todos:
            display_lines.append("⏳ **Pending:**")
            for todo in pending_todos:
                display_lines.append(f"   • {todo.content}")
            display_lines.append("")

        if completed_todos:
            display_lines.append("✅ **Completed:**")
            for todo in completed_todos:
                display_lines.append(f"   • {todo.content}")
            display_lines.append("")

        # Add summary
        total = len(todos)
        completed_count = len(completed_todos)
        in_progress_count = len(in_progress_todos)
        pending_count = len(pending_todos)

        display_lines.append(
            f"**Summary:** {completed_count}/{total} completed, {in_progress_count} in progress, {pending_count} pending"
        )

        return "\n".join(display_lines)

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        """Execute the todo write tool."""
        try:
            # Extract and validate todos
            todos_data = arguments.get("todos")
            if todos_data is None:
                return ToolExecResult(error="Parameter 'todos' is required", error_code=-1)

            # Type check todos_data before validation
            if not isinstance(todos_data, list):
                return ToolExecResult(error="Parameter 'todos' must be an array", error_code=-1)

            # Cast to the expected type after runtime check
            todos_list = cast(list[dict], todos_data)

            session_id = arguments.get("session_id")
            if session_id is not None:
                session_id = str(session_id).strip() or None

            # Validate and convert todos
            try:
                todos = self._validate_todos(todos_list)
            except ToolError as e:
                return ToolExecResult(error=str(e), error_code=-1)

            # Write todos to file
            self._write_todos_to_file(todos, session_id)

            # Create display output
            display_output = self._format_todos_display(todos)

            # Create structured result for tools that need to parse it
            # result_data = {
            #     "success": True,
            #     "todos": [
            #         {"id": todo.id, "content": todo.content, "status": todo.status}
            #         for todo in todos
            #     ],
            #     "session_id": session_id or "default",
            #     "total_todos": len(todos),
            #     "completed": len([t for t in todos if t.status == "completed"]),
            #     "in_progress": len([t for t in todos if t.status == "in_progress"]),
            #     "pending": len([t for t in todos if t.status == "pending"]),
            # }

            return ToolExecResult(
                output=f"{display_output}\n\nTodos successfully saved to session '{session_id or 'default'}'."
            )

        except ToolError:
            # Re-raise ToolErrors as they already have good error messages
            raise
        except Exception as e:
            error_message = f"Failed to execute todo_write tool: {str(e)}"
            return ToolExecResult(error=error_message, error_code=-1)


def read_todos_for_session(session_id: str | None = None) -> list[TodoItem]:
    """Utility function to read todos for a specific session."""
    tool = TodoWriteTool()
    return tool._read_todos_from_file(session_id)


def list_todo_sessions() -> list[str]:
    """Utility function to list all todo sessions."""
    todos_dir = LOCAL_STORAGE_PATH / "todos"

    if not todos_dir.exists():
        return []

    try:
        sessions = []
        for file_path in todos_dir.glob("*.json"):
            session_name = file_path.stem
            sessions.append(session_name)
        return sorted(sessions)
    except OSError:
        return []
