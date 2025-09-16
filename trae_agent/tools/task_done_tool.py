# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

from typing import override

from trae_agent.tools.base import Tool, ToolCallArguments, ToolExecResult, ToolParameter


class TaskDoneTool(Tool):
    """Tool to signal task completion or request clarification."""

    def __init__(self, model_provider: str | None = None) -> None:
        super().__init__(model_provider)

    @override
    def get_model_provider(self) -> str | None:
        return self._model_provider

    @override
    def get_name(self) -> str:
        return "task_done"

    @override
    def get_description(self) -> str:
        return """Signals the completion of the current task or requests clarification when you cannot proceed.

Use this tool when:
- You have successfully completed the user's requested task
- You cannot proceed further due to technical limitations or missing information
- You need clarification from the user before continuing
- You encounter blocking issues that require user input

The message should include:
- A clear summary of actions taken and their results (for completion)
- Specific questions or clarification needed (for clarification requests)
- Any next steps for the user
- Explanation if you're unable to complete the task"""

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="message",
                type="string",
                description="Message explaining completion status, results achieved, or clarification needed",
                required=True,
            )
        ]

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        message = arguments.get("message", "Task done.")
        return ToolExecResult(output=str(message))
