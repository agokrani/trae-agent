# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Status command implementation."""

import os

from rich.panel import Panel

from trae_agent.commands.base import BaseCommand, CommandContext, CommandResult


class StatusCommand(BaseCommand):
    """Command to display agent status and configuration information."""

    @property
    def name(self) -> str:
        """Command name."""
        return "status"

    @property
    def description(self) -> str:
        """Command description."""
        return "Show current agent status and configuration"

    async def execute(self, args: list[str], context: CommandContext) -> CommandResult:
        """Execute the status command.

        Args:
            args: Command arguments (unused for status)
            context: Command execution context

        Returns:
            CommandResult with success status
        """
        # Create status information
        status_content = self._create_status_content(context)

        # Display status panel
        status_panel = Panel(status_content, title="Agent Status", border_style="blue", width=80)

        context.console.print("")
        context.console.print(status_panel)

        return CommandResult.success_no_agent("Agent status displayed")

    def _create_status_content(self, context: CommandContext) -> str:
        """Create the status content string.

        Args:
            context: Command execution context

        Returns:
            Formatted status content string
        """
        content_lines = []

        # Agent information
        if context.has_agent() and context.agent:
            agent_config = getattr(context.agent, "agent_config", None)
            if agent_config:
                model_config = getattr(agent_config, "model", None)
                if model_config:
                    provider_config = getattr(model_config, "model_provider", None)
                    if provider_config:
                        content_lines.append(f"[bold]Provider:[/bold] {provider_config.provider}")
                        content_lines.append(f"[bold]Model:[/bold] {model_config.model}")
                        content_lines.append(f"[bold]Max Tokens:[/bold] {model_config.max_tokens}")
                        content_lines.append(
                            f"[bold]Temperature:[/bold] {model_config.temperature}"
                        )

                # Tool information
                agent_tools = getattr(context.agent, "agent", None)
                if agent_tools and hasattr(agent_tools, "tools"):
                    tool_count = len(agent_tools.tools)
                    content_lines.append(f"[bold]Available Tools:[/bold] {tool_count}")

                    # List tool names if there are tools
                    if tool_count > 0:
                        tool_names = [
                            getattr(tool, "name", "Unknown") for tool in agent_tools.tools
                        ]
                        tools_str = ", ".join(tool_names[:5])  # Show first 5 tools
                        if tool_count > 5:
                            tools_str += f" (+{tool_count - 5} more)"
                        content_lines.append(f"[bold]Tools:[/bold] {tools_str}")

                # Max steps
                max_steps = getattr(agent_config, "max_steps", None)
                if max_steps:
                    content_lines.append(f"[bold]Max Steps:[/bold] {max_steps}")
        else:
            content_lines.append("[yellow]Agent not initialized[/yellow]")

        # Working directory information
        if hasattr(context.console, "directory_manager"):
            directories = context.console.directory_manager.list_directories()
            if len(directories) == 1:
                content_lines.append(f"[bold]Working Directory:[/bold] {directories[0]}")
            else:
                content_lines.append(
                    f"[bold]Working Directories:[/bold] {len(directories)} configured"
                )
                for i, path in enumerate(directories, 1):
                    content_lines.append(f"[bold]  {i}.[/bold] {path}")
        else:
            content_lines.append(
                f"[bold]Working Directory:[/bold] {context.working_dir or os.getcwd()}"
            )
            content_lines.append("[dim]Directory Manager:[/dim] Not available")

        # Configuration
        if context.config:
            content_lines.append("[bold]Config Available:[/bold] Yes")
        else:
            content_lines.append("[bold]Config Available:[/bold] No")

        # Command system status
        if hasattr(context.console, "command_registry"):
            registry = context.console.command_registry
            commands = registry.list_commands()
            content_lines.append(f"[bold]Slash Commands:[/bold] {len(commands)} registered")

            # List available commands
            command_names = sorted(commands.keys())
            commands_str = ", ".join([f"/{name}" for name in command_names])
            content_lines.append(f"[bold]Available:[/bold] {commands_str}")

        return "\n".join(content_lines)

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        """Validate command arguments.

        Args:
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(args) > 0:
            return False, "Status command does not accept arguments"
        return True, ""
