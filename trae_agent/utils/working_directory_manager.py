# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Working directory management for Trae Agent."""

import os
from typing import List


class WorkingDirectoryManager:
    """Manages multiple working directories for agent tasks."""

    def __init__(self, initial_dir: str | None = None):
        """Initialize with current directory or specified directory.

        Args:
            initial_dir: Initial directory to start with. Defaults to current directory.
        """
        start_dir = initial_dir or os.getcwd()
        self.working_directories: List[str] = [os.path.abspath(start_dir)]

    def add_directory(self, new_dir: str) -> tuple[bool, str]:
        """Add a new working directory.

        Args:
            new_dir: Path to the new directory to add

        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            # Convert to absolute path and validate
            abs_path = os.path.abspath(new_dir)

            # Check if directory exists
            if not os.path.exists(abs_path):
                return False, f"Directory does not exist: {abs_path}"

            # Check if it's actually a directory
            if not os.path.isdir(abs_path):
                return False, f"Path is not a directory: {abs_path}"

            # Check if already added
            if abs_path in self.working_directories:
                return False, f"Directory already added: {abs_path}"

            # Add the directory
            self.working_directories.append(abs_path)
            return True, f"Added directory: {abs_path}"

        except (OSError, ValueError) as e:
            return False, f"Error adding directory: {str(e)}"

    def remove_directory(self, dir_path: str) -> tuple[bool, str]:
        """Remove a working directory.

        Args:
            dir_path: Path to directory to remove (can be relative or absolute)

        Returns:
            Tuple of (success: bool, message: str)
        """
        abs_path = os.path.abspath(dir_path)

        # Cannot remove the last directory
        if len(self.working_directories) <= 1:
            return False, "Cannot remove the last working directory"

        if abs_path in self.working_directories:
            self.working_directories.remove(abs_path)
            return True, f"Removed directory: {abs_path}"
        else:
            return False, f"Directory not found in working directories: {abs_path}"

    def list_directories(self) -> List[str]:
        """Get list of all working directories.

        Returns:
            List of absolute paths of working directories
        """
        return self.working_directories.copy()

    def get_display_string(self) -> str:
        """Get formatted display string of working directories.

        Returns:
            Formatted string showing all working directories
        """
        if len(self.working_directories) == 1:
            return f"Working Directory: {self.working_directories[0]}"
        else:
            lines = ["Working Directories:"]
            for i, path in enumerate(self.working_directories, 1):
                lines.append(f"  {i}. {path}")
            return "\n".join(lines)

    def get_agent_project_path(self) -> str:
        """Get formatted string for agent consumption.

        Returns:
            String formatted for agent's project_path field
        """
        if len(self.working_directories) == 1:
            return self.working_directories[0]
        else:
            # Format multiple directories for agent
            lines = []
            for i, path in enumerate(self.working_directories, 1):
                lines.append(f"[Directory {i}]: {path}")
            return "\n".join(lines)

    def get_primary_directory(self) -> str:
        """Get the primary (first) working directory.

        Returns:
            Absolute path of the primary working directory
        """
        return self.working_directories[0] if self.working_directories else os.getcwd()

    def has_multiple_directories(self) -> bool:
        """Check if there are multiple working directories.

        Returns:
            True if more than one directory is configured
        """
        return len(self.working_directories) > 1

    def clear_additional_directories(self):
        """Remove all directories except the first one."""
        if len(self.working_directories) > 1:
            self.working_directories = self.working_directories[:1]
