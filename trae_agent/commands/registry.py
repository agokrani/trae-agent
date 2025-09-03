# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Command registry for managing and executing commands."""

import logging
from typing import Dict, Optional

from trae_agent.commands.base import BaseCommand, CommandContext, CommandResult
from trae_agent.commands.parser import CommandParser

logger = logging.getLogger(__name__)


class CommandRegistry:
    """Registry for managing and executing commands."""

    def __init__(self):
        """Initialize the command registry."""
        self._commands: Dict[str, BaseCommand] = {}
        self._parser = CommandParser()

    def register_command(self, command: BaseCommand) -> None:
        """Register a command in the registry.

        Args:
            command: Command instance to register
        """
        command_name = command.name.lower()
        if command_name in self._commands:
            logger.warning(f"Command '{command_name}' already registered, overriding")

        self._commands[command_name] = command
        logger.debug(f"Registered command: {command_name}")

    def unregister_command(self, command_name: str) -> None:
        """Unregister a command from the registry.

        Args:
            command_name: Name of command to unregister
        """
        command_name = command_name.lower()
        if command_name in self._commands:
            del self._commands[command_name]
            logger.debug(f"Unregistered command: {command_name}")

    def has_command(self, command_name: str) -> bool:
        """Check if a command is registered.

        Args:
            command_name: Name of command to check

        Returns:
            True if command is registered, False otherwise
        """
        return command_name.lower() in self._commands

    def get_command(self, command_name: str) -> Optional[BaseCommand]:
        """Get a registered command.

        Args:
            command_name: Name of command to get

        Returns:
            Command instance if found, None otherwise
        """
        return self._commands.get(command_name.lower())

    def list_commands(self) -> Dict[str, BaseCommand]:
        """Get all registered commands.

        Returns:
            Dictionary mapping command names to command instances
        """
        return self._commands.copy()

    async def execute_if_command(
        self, user_input: str, context: CommandContext
    ) -> Optional[CommandResult]:
        """Execute user input if it's a slash command.

        Args:
            user_input: Raw user input string
            context: Command execution context

        Returns:
            CommandResult if input was a slash command, None otherwise
        """
        # Parse the input
        parsed = self._parser.parse(user_input)
        if not parsed or not parsed.is_slash_command:
            return None

        # Check if command exists
        command = self.get_command(parsed.command_name)
        if not command:
            return CommandResult.error(f"Unknown command: /{parsed.command_name}")

        try:
            # Validate arguments
            is_valid, error_message = command.validate_args(parsed.arguments)
            if not is_valid:
                return CommandResult.error(f"Invalid arguments: {error_message}")

            # Execute the command
            result = await command.execute(parsed.arguments, context)
            return result

        except Exception as e:
            logger.exception(f"Error executing command /{parsed.command_name}")
            return CommandResult.error(f"Command execution failed: {str(e)}")

    def is_slash_command(self, user_input: str) -> bool:
        """Check if user input is a slash command.

        Args:
            user_input: Raw user input string

        Returns:
            True if input is a slash command, False otherwise
        """
        return self._parser.is_slash_command(user_input)
