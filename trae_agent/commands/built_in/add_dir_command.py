# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Add directory command implementation."""

from rich.panel import Panel

from trae_agent.commands.base import BaseCommand, CommandContext, CommandResult


class AddDirCommand(BaseCommand):
    """Command to add additional working directories."""

    @property
    def name(self) -> str:
        """Command name."""
        return "add-dir"

    @property
    def description(self) -> str:
        """Command description."""
        return "Add an additional working directory for the agent to work with"

    @property
    def usage(self) -> str:
        """Command usage."""
        return "/add-dir <directory_path>"

    async def execute(self, args: list[str], context: CommandContext) -> CommandResult:
        """Execute the add-dir command.

        Args:
            args: Command arguments - should contain directory path
            context: Command execution context

        Returns:
            CommandResult with success status and message
        """
        if not args:
            return CommandResult.error(
                "Directory path is required. Usage: /add-dir <directory_path>"
            )

        directory_path = args[0]

        # Check if console has directory manager
        if not hasattr(context.console, "directory_manager"):
            return CommandResult.error("Directory management not available in current console")

        # Try to add the directory
        success, message = context.console.directory_manager.add_directory(directory_path)

        if success:
            # Show updated directory list
            directories = context.console.directory_manager.list_directories()
            dir_display = self._format_directories_display(directories)

            result_content = f"""[green]{message}[/green]

{dir_display}

[bold]Note:[/bold] All directories will be included in future agent tasks."""

            result_panel = Panel(
                result_content, title="Directory Added Successfully", border_style="green"
            )

            context.console.print("")
            context.console.print(result_panel)

            return CommandResult.success_no_agent(f"Added directory: {directory_path}")
        else:
            # Show error
            error_content = f"""[red]Failed to add directory:[/red] {message}

[bold]Common issues:[/bold]
• Directory does not exist
• Path is not a directory
• Directory already added
• Permission denied

[bold]Current directories:[/bold]
{self._format_directories_display(context.console.directory_manager.list_directories())}"""

            error_panel = Panel(error_content, title="Failed to Add Directory", border_style="red")

            context.console.print("")
            context.console.print(error_panel)

            return CommandResult.error(message)

    def _format_directories_display(self, directories: list[str]) -> str:
        """Format directories for display.

        Args:
            directories: List of directory paths

        Returns:
            Formatted string for display
        """
        if len(directories) == 1:
            return f"Working Directory: [cyan]{directories[0]}[/cyan]"
        else:
            lines = ["Working Directories:"]
            for i, path in enumerate(directories, 1):
                lines.append(f"  [cyan]{i}.[/cyan] {path}")
            return "\n".join(lines)

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        """Validate command arguments.

        Args:
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(args) == 0:
            return False, "Directory path is required"
        elif len(args) > 1:
            return False, "Only one directory path allowed. Use quotes if path contains spaces."
        return True, ""
