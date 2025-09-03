# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Command parser for slash commands."""

import shlex
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedCommand:
    """Result of parsing a command string."""

    command_name: str
    arguments: list[str]
    is_slash_command: bool
    raw_input: str


class CommandParser:
    """Parser for slash commands and arguments."""

    @staticmethod
    def parse(user_input: str) -> Optional[ParsedCommand]:
        """Parse user input to extract command and arguments.

        Args:
            user_input: Raw user input string

        Returns:
            ParsedCommand if input is a slash command, None otherwise
        """
        if not user_input or not user_input.strip():
            return None

        user_input = user_input.strip()

        # Only parse slash commands
        if not user_input.startswith("/"):
            return None

        try:
            # Use shlex to properly handle quoted arguments
            tokens = shlex.split(user_input)
        except ValueError:
            # If shlex fails (e.g., unmatched quotes), fall back to simple split
            tokens = user_input.split()

        if not tokens:
            return None

        # Extract command name (remove leading slash)
        command_name = tokens[0][1:] if tokens[0].startswith("/") else tokens[0]
        arguments = tokens[1:] if len(tokens) > 1 else []

        return ParsedCommand(
            command_name=command_name,
            arguments=arguments,
            is_slash_command=True,
            raw_input=user_input,
        )

    @staticmethod
    def is_slash_command(user_input: str) -> bool:
        """Check if user input is a slash command.

        Args:
            user_input: Raw user input string

        Returns:
            True if input starts with '/', False otherwise
        """
        return bool(user_input and user_input.strip().startswith("/"))
