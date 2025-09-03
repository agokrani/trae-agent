# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Tools command implementation."""

from rich.panel import Panel
from rich.table import Table

from trae_agent.commands.base import BaseCommand, CommandContext, CommandResult


class ToolsCommand(BaseCommand):
    """Command to display available tools."""

    @property
    def name(self) -> str:
        """Command name."""
        return "tools"

    @property
    def description(self) -> str:
        """Command description."""
        return "List all available tools and their descriptions"

    @property
    def usage(self) -> str:
        """Command usage."""
        return "/tools [tool_name]"

    async def execute(self, args: list[str], context: CommandContext) -> CommandResult:
        """Execute the tools command.

        Args:
            args: Command arguments (optional tool name for specific info)
            context: Command execution context

        Returns:
            CommandResult with success status
        """
        if args:
            # Show specific tool information
            return await self._show_specific_tool(args[0], context)
        else:
            # Show all tools
            return await self._show_all_tools(context)

    async def _show_all_tools(self, context: CommandContext) -> CommandResult:
        """Show all available tools."""

        if not context.has_agent() or not context.agent:
            context.console.print("[yellow]No agent available - cannot display tools[/yellow]")
            return CommandResult.success_no_agent("No agent available")

        # Get tools from agent
        agent_tools = getattr(context.agent, "agent", None)
        if not agent_tools or not hasattr(agent_tools, "tools"):
            context.console.print("[yellow]No tools available in current agent[/yellow]")
            return CommandResult.success_no_agent("No tools available")

        tools = agent_tools.tools
        if not tools:
            context.console.print("[yellow]No tools configured for this agent[/yellow]")
            return CommandResult.success_no_agent("No tools configured")

        # Create tools table
        table = Table(title="Available Agent Tools")
        table.add_column("Tool Name", style="cyan", width=25)
        table.add_column("Type", style="green", width=20)
        table.add_column("Description", style="white", width=50)

        for tool in tools:
            tool_name = getattr(tool, "name", "Unknown")
            tool_type = type(tool).__name__
            tool_description = getattr(tool, "description", "No description available")

            # Truncate long descriptions
            if len(tool_description) > 80:
                tool_description = tool_description[:77] + "..."

            table.add_row(tool_name, tool_type, tool_description)

        # Also show tool registry information
        registry_info = self._get_registry_info()
        if registry_info:
            table.add_section()
            table.add_row(
                "[dim]Available in Registry[/dim]",
                "[dim]Registry[/dim]",
                f"[dim]{len(registry_info)} tools available for instantiation[/dim]",
            )

        # Display in panel
        tools_panel = Panel(
            table, title=f"Tools ({len(tools)} active)", border_style="green", expand=False
        )

        context.console.print("")
        context.console.print(tools_panel)

        return CommandResult.success_no_agent(f"Displayed {len(tools)} tools")

    async def _show_specific_tool(self, tool_name: str, context: CommandContext) -> CommandResult:
        """Show information about a specific tool."""

        if not context.has_agent() or not context.agent:
            return CommandResult.error("No agent available to query tools")

        # Get tools from agent
        agent_tools = getattr(context.agent, "agent", None)
        if not agent_tools or not hasattr(agent_tools, "tools"):
            return CommandResult.error("No tools available in current agent")

        # Find the specific tool
        target_tool = None
        for tool in agent_tools.tools:
            if getattr(tool, "name", "").lower() == tool_name.lower():
                target_tool = tool
                break

        if not target_tool:
            # Check if it's available in registry
            registry_info = self._get_registry_info()
            if registry_info and tool_name.lower() in [name.lower() for name in registry_info]:
                return CommandResult.error(
                    f"Tool '{tool_name}' exists in registry but is not active in current agent. "
                    f"Available active tools: {', '.join([getattr(t, 'name', 'Unknown') for t in agent_tools.tools])}"
                )
            else:
                return CommandResult.error(
                    f"Tool '{tool_name}' not found. Use '/tools' to see available tools."
                )

        # Create detailed tool info
        tool_info = f"""[bold]Tool Name:[/bold] {getattr(target_tool, "name", "Unknown")}
[bold]Type:[/bold] {type(target_tool).__name__}
[bold]Description:[/bold] {getattr(target_tool, "description", "No description available")}

[bold]Tool Class:[/bold] {target_tool.__class__.__module__}.{target_tool.__class__.__name__}"""

        # Add any additional attributes if available
        if hasattr(target_tool, "model_provider"):
            tool_info += f"\n[bold]Model Provider:[/bold] {target_tool.model_provider}"

        tool_panel = Panel(
            tool_info,
            title=f"Tool Details: {getattr(target_tool, 'name', 'Unknown')}",
            border_style="cyan",
        )

        context.console.print("")
        context.console.print(tool_panel)

        return CommandResult.success_no_agent(f"Displayed details for tool '{tool_name}'")

    def _get_registry_info(self) -> dict:
        """Get information about available tools in registry."""
        try:
            from trae_agent.tools import tools_registry

            return tools_registry
        except ImportError:
            return {}

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        """Validate command arguments.

        Args:
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(args) > 1:
            return False, "Too many arguments. Usage: /tools [tool_name]"
        return True, ""
