# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Base classes for the command system."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from trae_agent.agent import Agent
    from trae_agent.utils.cli.cli_console import CLIConsole
    from trae_agent.utils.config import Config


@dataclass
class CommandContext:
    """Context object passed to commands with access to agent resources."""

    console: "CLIConsole"
    agent: "Agent | None" = None
    config: "Config | None" = None
    working_dir: str = ""

    def has_agent(self) -> bool:
        """Check if agent context is available."""
        return self.agent is not None


@dataclass
class CommandResult:
    """Result returned by command execution."""

    success: bool
    message: str = ""
    should_continue_to_agent: bool = False
    generated_task: str = ""

    @classmethod
    def success_no_agent(cls, message: str = "") -> "CommandResult":
        """Create a successful result that doesn't continue to agent."""
        return cls(success=True, message=message, should_continue_to_agent=False)

    @classmethod
    def success_with_task(cls, task: str, message: str = "") -> "CommandResult":
        """Create a successful result that generates a task for the agent."""
        return cls(
            success=True, message=message, should_continue_to_agent=True, generated_task=task
        )

    @classmethod
    def error(cls, message: str) -> "CommandResult":
        """Create an error result."""
        return cls(success=False, message=message, should_continue_to_agent=False)


class BaseCommand(ABC):
    """Abstract base class for all commands."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name (without leading slash)."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of what the command does."""
        pass

    @property
    def usage(self) -> str:
        """Usage string for the command. Override if command takes arguments."""
        return f"/{self.name}"

    @abstractmethod
    async def execute(self, args: list[str], context: CommandContext) -> CommandResult:
        """Execute the command.

        Args:
            args: List of arguments passed to the command
            context: Command context with access to agent resources

        Returns:
            CommandResult indicating success/failure and any generated task
        """
        pass

    def validate_args(self, args: list[str]) -> tuple[bool, str]:
        """Validate command arguments. Override to add validation.

        Args:
            args: Arguments to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        return True, ""
