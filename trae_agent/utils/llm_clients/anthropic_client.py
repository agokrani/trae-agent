# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""Anthropic API client wrapper with tool integration."""

import json
import os
from typing import override

import anthropic
import requests
from anthropic.types.tool_union_param import ToolTextEditor20250728Param

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.retry_utils import retry_with


class AnthropicClient(BaseLLMClient):
    """Anthropic client wrapper with tool schema generation."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)

        self.use_bearer_token = False
        self.bearer_token = None
        self.bedrock_region = os.environ.get("AWS_REGION", "us-east-1")

        # Use AnthropicBedrock for bedrock provider, otherwise use standard Anthropic client
        if model_config.model_provider.provider == "bedrock":
            # Check for bearer token first (API Keys for Bedrock)
            bearer_token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK")
            if bearer_token:
                self.use_bearer_token = True
                self.bearer_token = bearer_token
                self.client = None  # We'll use direct HTTP requests
            else:
                from anthropic import AnthropicBedrock
                self.client: anthropic.Anthropic = AnthropicBedrock(
                    # AnthropicBedrock uses AWS credentials from environment (SSO)
                    # api_key is optional and typically not needed
                )
        else:
            self.client = anthropic.Anthropic(api_key=self.api_key, base_url=self.base_url)
        self.message_history: list[anthropic.types.MessageParam] = []
        self.system_message: str | anthropic.NotGiven = anthropic.NOT_GIVEN

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)

    def _serialize_message(self, msg) -> dict:
        """Serialize a single message for Bedrock API."""
        if isinstance(msg, dict):
            role = msg.get("role")
            content = msg.get("content")
        else:
            role = getattr(msg, "role", None)
            content = getattr(msg, "content", None)

        if content is None:
            return {"role": role, "content": ""}

        # If content is a string, return as-is
        if isinstance(content, str):
            return {"role": role, "content": content}

        # If content is a list of blocks, serialize each block
        serialized_content = []
        for block in content:
            serialized_block = self._serialize_content_block(block)
            if serialized_block:
                serialized_content.append(serialized_block)

        return {"role": role, "content": serialized_content}

    def _serialize_content_block(self, block) -> dict | None:
        """Serialize a content block (text, tool_use, tool_result)."""
        # Handle pydantic models first
        if hasattr(block, 'model_dump'):
            return block.model_dump()

        # Handle dicts
        if isinstance(block, dict):
            block_type = block.get("type")
            if block_type == "text":
                return {"type": "text", "text": block.get("text", "")}
            elif block_type == "tool_use":
                return {
                    "type": "tool_use",
                    "id": block.get("id", ""),
                    "name": block.get("name", ""),
                    "input": block.get("input", {})
                }
            elif block_type == "tool_result":
                return {
                    "type": "tool_result",
                    "tool_use_id": block.get("tool_use_id", ""),
                    "content": block.get("content", ""),
                    "is_error": block.get("is_error", False)
                }
            else:
                return block

        # Handle anthropic types by attribute access
        block_type = getattr(block, "type", None)
        if block_type == "text":
            return {"type": "text", "text": getattr(block, "text", "")}
        elif block_type == "tool_use":
            input_data = getattr(block, "input", {})
            # Handle case where input might be a string (JSON)
            if isinstance(input_data, str):
                try:
                    input_data = json.loads(input_data)
                except:
                    pass
            return {
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": input_data
            }
        elif block_type == "tool_result":
            return {
                "type": "tool_result",
                "tool_use_id": getattr(block, "tool_use_id", ""),
                "content": getattr(block, "content", ""),
                "is_error": getattr(block, "is_error", False)
            }

        # Fallback: try model_dump or convert to string
        if hasattr(block, 'model_dump'):
            return block.model_dump()
        return {"type": "text", "text": str(block)}

    def _serialize_for_json(self, obj):
        """Recursively serialize objects for JSON, handling anthropic types."""
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        elif isinstance(obj, dict):
            return {k: self._serialize_for_json(v) for k, v in obj.items()}
        elif isinstance(obj, (list, tuple)):
            return [self._serialize_for_json(item) for item in obj]
        # Check for pydantic models FIRST (before __dict__)
        elif hasattr(obj, 'model_dump'):
            return obj.model_dump()
        elif hasattr(obj, '__dict__'):
            return self._serialize_for_json(vars(obj))
        else:
            return str(obj)

    def _create_bedrock_bearer_response(
        self,
        model_config: ModelConfig,
        tool_schemas: list[anthropic.types.ToolUnionParam] | anthropic.NotGiven,
    ) -> anthropic.types.Message:
        """Create a response using Bedrock API with bearer token auth (API Keys for Bedrock)."""
        url = f"https://bedrock-runtime.{self.bedrock_region}.amazonaws.com/model/{model_config.model}/invoke"

        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

        # Serialize message history using proper message serialization
        serialized_messages = [self._serialize_message(msg) for msg in self.message_history]

        # Fix message sequence: ensure tool_use is always followed by tool_result
        # Bedrock requires that EVERY tool_use ID has a matching tool_result in the NEXT message

        def get_tool_use_ids(msg):
            """Extract all tool_use IDs from an assistant message."""
            content = msg.get("content", [])
            if not isinstance(content, list):
                return set()
            return {b.get("id") for b in content if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("id")}

        def get_tool_result_ids(msg):
            """Extract all tool_use_id references from a user message with tool_results."""
            content = msg.get("content", [])
            if not isinstance(content, list):
                return set()
            return {b.get("tool_use_id") for b in content if isinstance(b, dict) and b.get("type") == "tool_result" and b.get("tool_use_id")}

        # Validate and repair message sequence
        # Strategy:
        # 1. Find all tool_use messages and ensure they have complete tool_result responses
        # 2. Find all tool_result messages and ensure they reference valid tool_use IDs
        # If mismatches exist, filter/repair to maintain consistency

        def filter_tool_results(user_msg, valid_tool_use_ids):
            """Filter tool_result blocks to only keep those with valid tool_use_id references."""
            content = user_msg.get("content", [])
            if not isinstance(content, list):
                return user_msg

            filtered_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    if block.get("tool_use_id") in valid_tool_use_ids:
                        filtered_content.append(block)
                    # Skip tool_results with invalid tool_use_id
                else:
                    filtered_content.append(block)

            if not filtered_content:
                # If no content left, add a placeholder text
                filtered_content = [{"type": "text", "text": "[continued]"}]

            return {**user_msg, "content": filtered_content}

        repaired_messages = []
        i = 0
        last_assistant_tool_use_ids = set()  # Track tool_use IDs from last assistant message

        while i < len(serialized_messages):
            msg = serialized_messages[i]
            role = msg.get("role")

            if role == "assistant":
                tool_use_ids = get_tool_use_ids(msg)

                if tool_use_ids:
                    # This assistant message has tool_use blocks
                    # Check if the next message has ALL the required tool_results
                    if i + 1 < len(serialized_messages):
                        next_msg = serialized_messages[i + 1]
                        next_role = next_msg.get("role")
                        tool_result_ids = get_tool_result_ids(next_msg) if next_role == "user" else set()

                        # Check if all tool_use IDs have matching tool_results
                        missing_results = tool_use_ids - tool_result_ids

                        if missing_results:
                            # Missing tool_results - skip this assistant message AND any following tool_result message
                            # This loses context but prevents the API error
                            i += 1
                            # Also skip the next message if it's a partial tool_result or plain text user message
                            if i < len(serialized_messages):
                                skip_next = serialized_messages[i]
                                if skip_next.get("role") == "user":
                                    i += 1
                            last_assistant_tool_use_ids = set()
                            continue
                        else:
                            # All tool_use IDs have matching tool_results - keep both messages
                            repaired_messages.append(msg)
                            last_assistant_tool_use_ids = tool_use_ids
                            i += 1
                            if i < len(serialized_messages):
                                # Filter the user message to only include valid tool_results
                                user_msg = filter_tool_results(serialized_messages[i], tool_use_ids)
                                repaired_messages.append(user_msg)
                                i += 1
                            continue
                    else:
                        # No next message - this is a dangling tool_use at the end
                        # Skip it
                        i += 1
                        last_assistant_tool_use_ids = set()
                        continue
                else:
                    # Assistant message without tool_use - keep it
                    repaired_messages.append(msg)
                    last_assistant_tool_use_ids = set()
                    i += 1
            elif role == "user":
                # User message - check if it has tool_results that need validation
                tool_result_ids = get_tool_result_ids(msg)
                if tool_result_ids:
                    # This user message has tool_results
                    # Only keep tool_results that reference valid tool_use IDs from the previous assistant message
                    orphaned_results = tool_result_ids - last_assistant_tool_use_ids
                    if orphaned_results:
                        # Filter out orphaned tool_results
                        filtered_msg = filter_tool_results(msg, last_assistant_tool_use_ids)
                        repaired_messages.append(filtered_msg)
                    else:
                        repaired_messages.append(msg)
                else:
                    repaired_messages.append(msg)
                last_assistant_tool_use_ids = set()
                i += 1
            else:
                # Other message type - keep it
                repaired_messages.append(msg)
                last_assistant_tool_use_ids = set()
                i += 1

        serialized_messages = repaired_messages

        # Build request body
        body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": model_config.max_tokens,
            "messages": serialized_messages,
            "temperature": model_config.temperature,
        }

        if self.system_message and self.system_message != anthropic.NOT_GIVEN:
            body["system"] = self.system_message

        if tool_schemas and tool_schemas != anthropic.NOT_GIVEN:
            # Convert tool schemas to dict format
            tools_list = []
            for tool in tool_schemas:
                if hasattr(tool, 'model_dump'):
                    tools_list.append(tool.model_dump())
                elif isinstance(tool, dict):
                    tools_list.append(tool)
                else:
                    # Fallback for TypedDict or other types
                    tools_list.append(dict(tool))
            body["tools"] = tools_list

        response = requests.post(url, headers=headers, json=body, timeout=300)

        if response.status_code != 200:
            raise anthropic.PermissionDeniedError(
                message=f"Bedrock API error: {response.text}",
                response=response,
                body=response.json() if response.text else {}
            )

        data = response.json()

        # Convert Bedrock response to anthropic.types.Message format
        content_blocks = []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content_blocks.append(anthropic.types.TextBlock(type="text", text=block.get("text", "")))
            elif block.get("type") == "tool_use":
                content_blocks.append(anthropic.types.ToolUseBlock(
                    type="tool_use",
                    id=block.get("id", ""),
                    name=block.get("name", ""),
                    input=block.get("input", {})
                ))

        usage_data = data.get("usage", {})
        usage = anthropic.types.Usage(
            input_tokens=usage_data.get("input_tokens", 0),
            output_tokens=usage_data.get("output_tokens", 0),
            cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
            cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
        )

        return anthropic.types.Message(
            id=data.get("id", ""),
            type="message",
            role=data.get("role", "assistant"),
            content=content_blocks,
            model=data.get("model", model_config.model),
            stop_reason=data.get("stop_reason"),
            stop_sequence=data.get("stop_sequence"),
            usage=usage,
        )

    def _create_anthropic_response(
        self,
        model_config: ModelConfig,
        tool_schemas: list[anthropic.types.ToolUnionParam] | anthropic.NotGiven,
    ) -> anthropic.types.Message:
        """Create a response using Anthropic API with streaming support. This method will be decorated with retry logic."""
        # Use bearer token auth for Bedrock if configured
        if self.use_bearer_token:
            return self._create_bedrock_bearer_response(model_config, tool_schemas)

        with self.client.messages.stream(
            model=model_config.model,
            messages=self.message_history,
            max_tokens=model_config.max_tokens,
            system=self.system_message,
            tools=tool_schemas,
            temperature=model_config.temperature,
            # top_p=model_config.top_p,
            top_k=model_config.top_k,
        ) as stream:
            # Consume the entire stream
            for _ in stream:
                pass

            # Return the final accumulated message with complete tool calls
            return stream.get_final_message()

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to Anthropic with optional tool support."""
        # Convert messages to Anthropic format
        anthropic_messages: list[anthropic.types.MessageParam] = self.parse_messages(messages)

        self.message_history = (
            self.message_history + anthropic_messages if reuse_history else anthropic_messages
        )

        # Add tools if provided
        tool_schemas: list[anthropic.types.ToolUnionParam] | anthropic.NotGiven = (
            anthropic.NOT_GIVEN
        )
        if tools:
            tool_schemas = []
            for tool in tools:
                if tool.name == "str_replace_based_edit_tool":
                    tool_schemas.append(
                        ToolTextEditor20250728Param(
                            name="str_replace_based_edit_tool",
                            type="text_editor_20250728",
                            # input_schema=tool.get_input_schema()
                        )
                    )
                elif tool.name == "bash":
                    tool_schemas.append(
                        anthropic.types.ToolBash20250124Param(
                            name="bash", type="bash_20250124"
                        )  # ,input_schema=tool.get_input_schema())
                    )
                else:
                    tool_schemas.append(
                        anthropic.types.ToolParam(
                            name=tool.name,
                            description=tool.description,
                            input_schema=tool.get_input_schema(),
                        )
                    )
        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_anthropic_response,
            provider_name="Anthropic",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(model_config, tool_schemas)

        # Handle tool calls in response
        content = ""
        tool_calls: list[ToolCall] = []
        response_content_blocks = []

        for content_block in response.content:
            if content_block.type == "text":
                content += content_block.text
                response_content_blocks.append(content_block)
            elif content_block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        call_id=content_block.id,
                        name=content_block.name,
                        arguments=content_block.input,  # pyright: ignore[reportArgumentType]
                    )
                )
                response_content_blocks.append(content_block)

        # Add the entire response as ONE assistant message (not separate messages per block)
        if response_content_blocks:
            self.message_history.append(
                anthropic.types.MessageParam(role="assistant", content=response_content_blocks)
            )

        usage = None
        if response.usage:
            usage = LLMUsage(
                input_tokens=response.usage.input_tokens or 0,
                output_tokens=response.usage.output_tokens or 0,
                cache_creation_input_tokens=response.usage.cache_creation_input_tokens or 0,
                cache_read_input_tokens=response.usage.cache_read_input_tokens or 0,
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.stop_reason,
            tool_calls=tool_calls if len(tool_calls) > 0 else None,
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="anthropic",
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(self, messages: list[LLMMessage]) -> list[anthropic.types.MessageParam]:
        """Parse the messages to Anthropic format."""
        anthropic_messages: list[anthropic.types.MessageParam] = []
        for msg in messages:
            if msg.role == "system":
                self.system_message = msg.content if msg.content else anthropic.NOT_GIVEN
            elif msg.tool_result:
                anthropic_messages.append(
                    anthropic.types.MessageParam(
                        role="user",
                        content=[self.parse_tool_call_result(msg.tool_result)],
                    )
                )
            elif msg.tool_call:
                anthropic_messages.append(
                    anthropic.types.MessageParam(
                        role="assistant", content=[self.parse_tool_call(msg.tool_call)]
                    )
                )
            else:
                if msg.role == "user":
                    role = "user"
                elif msg.role == "assistant":
                    role = "assistant"
                else:
                    raise ValueError(f"Invalid message role: {msg.role}")

                if not msg.content:
                    raise ValueError("Message content is required")

                anthropic_messages.append(
                    anthropic.types.MessageParam(role=role, content=msg.content)
                )
        return anthropic_messages

    def parse_tool_call(self, tool_call: ToolCall) -> anthropic.types.ToolUseBlockParam:
        """Parse the tool call from the LLM response."""
        # Keep input as dict, not JSON string - Bedrock API expects object
        return anthropic.types.ToolUseBlockParam(
            type="tool_use",
            id=tool_call.call_id,
            name=tool_call.name,
            input=tool_call.arguments if isinstance(tool_call.arguments, dict) else {},
        )

    def parse_tool_call_result(
        self, tool_call_result: ToolResult
    ) -> anthropic.types.ToolResultBlockParam:
        """Parse the tool call result from the LLM response."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += "Tool call failed with error:\n"
            result += tool_call_result.error
        result = result.strip()

        # Ensure error results always have content to satisfy Anthropic API requirements
        is_error = not tool_call_result.success
        if is_error and not result:
            result = f"Tool '{tool_call_result.name}' failed with no error message"

        return anthropic.types.ToolResultBlockParam(
            tool_use_id=tool_call_result.call_id,
            type="tool_result",
            content=result,
            is_error=is_error,
        )
