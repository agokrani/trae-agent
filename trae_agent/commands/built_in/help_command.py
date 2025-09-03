# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Help command implementation."""

from rich.panel import Panel

from trae_agent.commands.base import BaseCommand, CommandContext, CommandResult


class HelpCommand(BaseCommand):
    """Command to display help information about available commands."""

    @property
    def name(self) -> str:
        """Command name."""
        return "help"

    @property
    def description(self) -> str:
        """Command description."""
        return "Show available slash commands and usage information"

    @property
    def usage(self) -> str:
        """Command usage."""
        return "/help [command_name]"

    async def execute(self, args: list[str], context: CommandContext) -> CommandResult:
        """Execute the help command.

        Args:
            args: Command arguments (optional command name to get specific help)
            context: Command execution context

        Returns:
            CommandResult with success status
        """
        if args:
            # Show help for specific command
            return await self._show_command_help(args[0], context)
        else:
            # Show general help
            return await self._show_general_help(context)

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        """Validate command arguments.

        Args:
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(args) > 1:
            return False, "Too many arguments. Usage: /help [command_name]"
        return True, ""

    async def _show_general_help(self, context: CommandContext) -> CommandResult:
        """Show general help with all available commands."""

        # Get all registered commands from registry
        available_commands = []
        if hasattr(context.console, "command_registry"):
            registry = context.console.command_registry
            commands = registry.list_commands()

            # Create formatted list of commands
            for cmd_name, cmd_instance in sorted(commands.items()):
                available_commands.append(
                    f"• [cyan]/{cmd_name}[/cyan] - {cmd_instance.description}"
                )

        # Create help content with dynamic command list
        slash_commands_section = (
            "\n".join(available_commands)
            if available_commands
            else "• [cyan]/help[/cyan] - Show this help message"
        )

        help_content = f"""[bold]Available Slash Commands:[/bold]

{slash_commands_section}

[bold]Usage:[/bold]
• [cyan]/help <command>[/cyan] - Show detailed help for a specific command

[bold]Regular Commands (legacy):[/bold]

• Type any task description to execute it
• 'status' - Show agent status
• 'clear' - Clear the console
• 'exit' or 'quit' - End the session

[bold]Note:[/bold] Slash commands (like [cyan]/help[/cyan]) use the new command system.
Regular commands (like 'help') use the legacy system. Both work!"""

        # Display help panel
        help_panel = Panel(help_content, title="Trae Agent Help", border_style="cyan", width=80)

        context.console.print("")  # Add some spacing
        context.console.print(help_panel)

        return CommandResult.success_no_agent("Help displayed successfully")

    async def _show_command_help(self, command_name: str, context: CommandContext) -> CommandResult:
        """Show help for a specific command.

        Args:
            command_name: Name of command to show help for
            context: Command execution context

        Returns:
            CommandResult with success status
        """
        # Get the specific command from registry
        if hasattr(context.console, "command_registry"):
            registry = context.console.command_registry
            command = registry.get_command(command_name)

            if command:
                # Create detailed help for the command
                help_content = f"""[bold]Command:[/bold] /{command.name}
[bold]Description:[/bold] {command.description}
[bold]Usage:[/bold] {command.usage}

[bold]Examples:[/bold]
• [cyan]/{command.name}[/cyan] - {command.description}"""

                # Add specific examples based on command
                if command.name == "help":
                    help_content += "\n• [cyan]/help status[/cyan] - Show help for status command"
                elif command.name == "status":
                    help_content += "\n• Shows current agent configuration and available tools"
                elif command.name == "clear":
                    help_content += "\n• Clears the console output or execution log"
                elif command.name == "exit":
                    help_content += "\n• Exits the interactive session gracefully"

                help_panel = Panel(
                    help_content, title=f"Help: /{command_name}", border_style="cyan"
                )

                context.console.print("")
                context.console.print(help_panel)

                return CommandResult.success_no_agent(f"Help for /{command_name} displayed")

        return CommandResult.error(
            f"Unknown command: /{command_name}. Use '/help' to see available commands."
        )
