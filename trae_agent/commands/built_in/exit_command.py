# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Exit command implementation."""

from trae_agent.commands.base import BaseCommand, CommandContext, CommandResult


class ExitCommand(BaseCommand):
    """Command to exit the interactive session."""

    @property
    def name(self) -> str:
        """Command name."""
        return "exit"

    @property
    def description(self) -> str:
        """Command description."""
        return "Exit the interactive session"

    async def execute(self, args: list[str], context: CommandContext) -> CommandResult:
        """Execute the exit command.

        Args:
            args: Command arguments (unused for exit)
            context: Command execution context

        Returns:
            CommandResult with success status
        """
        # Display goodbye message
        context.console.print("[green]Goodbye![/green]")

        # Different exit strategy based on console type
        console_type = type(context.console).__name__

        if console_type == "RichCLIConsole":
            # For rich console, exit through the app
            if hasattr(context.console, "app") and context.console.app:
                context.console.app.exit()
        else:
            # For simple console or fallback, the interactive loop will handle the exit
            # by returning None from get_task_input() equivalent behavior
            pass

        # Note: We still return success even though we're exiting
        # The actual exit is handled by the console/app layer
        return CommandResult.success_no_agent("Exiting session")

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        """Validate command arguments.

        Args:
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(args) > 0:
            return False, "Exit command does not accept arguments"
        return True, ""
