# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Clear command implementation."""

import os

from trae_agent.commands.base import BaseCommand, CommandContext, CommandResult


class ClearCommand(BaseCommand):
    """Command to clear the console output."""

    @property
    def name(self) -> str:
        """Command name."""
        return "clear"

    @property
    def description(self) -> str:
        """Command description."""
        return "Clear the console output"

    async def execute(self, args: list[str], context: CommandContext) -> CommandResult:
        """Execute the clear command.

        Args:
            args: Command arguments (unused for clear)
            context: Command execution context

        Returns:
            CommandResult with success status
        """
        # Different clearing strategy based on console type
        console_type = type(context.console).__name__

        if console_type == "SimpleCLIConsole":
            # For simple console, use system clear command
            os.system("clear" if os.name != "nt" else "cls")
        elif console_type == "RichCLIConsole":
            # For rich console, clear the execution log
            if hasattr(context.console, "app") and context.console.app:
                app = context.console.app
                if hasattr(app, "execution_log") and app.execution_log:
                    app.execution_log.clear()
        else:
            # Fallback to system clear
            os.system("clear" if os.name != "nt" else "cls")

        return CommandResult.success_no_agent("Console cleared")

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        """Validate command arguments.

        Args:
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(args) > 0:
            return False, "Clear command does not accept arguments"
        return True, ""
