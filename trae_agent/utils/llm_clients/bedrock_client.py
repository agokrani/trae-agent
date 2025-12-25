# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT
"""Anthropic Bedrock client wrapper for Claude models accessed via AWS Bedrock."""

import json
import os
from typing import override

import anthropic
from anthropic import AnthropicBedrock

try:
    from anthropic.types.tool_union_param import TextEditor20250429
except ImportError:  # Older anthropic releases omit the specialized text editor schema
    TextEditor20250429 = None  # type: ignore[assignment]

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.retry_utils import retry_with


class BedrockClient(BaseLLMClient):
    """LLM client that routes Anthropic calls through AWS Bedrock."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)
        region = (
            model_config.model_provider.aws_region
            or os.getenv("AWS_REGION")
            or "us-east-1"
        )
        profile = model_config.model_provider.aws_profile or os.getenv("AWS_PROFILE")
        client_kwargs: dict[str, str] = {"aws_region": region}
        if profile:
            client_kwargs["aws_profile"] = profile
        self.client: AnthropicBedrock = AnthropicBedrock(**client_kwargs)
        self.message_history: list[anthropic.types.MessageParam] = []
        self.system_message: str | anthropic.NotGiven = anthropic.NOT_GIVEN

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history for the Bedrock client."""
        self.message_history = self.parse_messages(messages)

    def _create_bedrock_response(
        self,
        model_config: ModelConfig,
        tool_schemas: list[anthropic.types.ToolUnionParam] | anthropic.NotGiven,
    ) -> anthropic.types.Message:
        """Send the chat request through Anthropic Bedrock with streaming."""
        with self.client.messages.stream(
            model=model_config.model,
            messages=self.message_history,
            max_tokens=model_config.max_tokens,
            system=self.system_message,
            tools=tool_schemas,
            temperature=model_config.temperature,
            top_k=model_config.top_k,
        ) as stream:
            for _ in stream:
                pass
            return stream.get_final_message()

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to Anthropic via Bedrock with optional tool support."""
        anthropic_messages: list[anthropic.types.MessageParam] = self.parse_messages(messages)
        self.message_history = (
            self.message_history + anthropic_messages if reuse_history else anthropic_messages
        )

        tool_schemas: list[anthropic.types.ToolUnionParam] | anthropic.NotGiven = anthropic.NOT_GIVEN
        if tools:
            tool_schemas = []
            for tool in tools:
                if tool.name == "str_replace_based_edit_tool":
                    if TextEditor20250429 is not None:
                        tool_schemas.append(
                            TextEditor20250429(
                                name="str_replace_based_edit_tool",
                                type="text_editor_20250429",
                            )
                        )
                    else:
                        tool_schemas.append(
                            anthropic.types.ToolParam(
                                name="str_replace_based_edit_tool",
                                description=tool.description,
                                input_schema=tool.get_input_schema(),
                            )
                        )
                elif tool.name == "bash":
                    tool_schemas.append(
                        anthropic.types.ToolBash20250124Param(name="bash", type="bash_20250124")
                    )
                else:
                    tool_schemas.append(
                        anthropic.types.ToolParam(
                            name=tool.name,
                            description=tool.description,
                            input_schema=tool.get_input_schema(),
                        )
                    )

        retry_decorator = retry_with(
            func=self._create_bedrock_response,
            provider_name="Bedrock",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(model_config, tool_schemas)

        content = ""
        tool_calls: list[ToolCall] = []
        for content_block in response.content:
            if content_block.type == "text":
                content += content_block.text
                self.message_history.append(
                    anthropic.types.MessageParam(role="assistant", content=content_block.text)
                )
            elif content_block.type == "tool_use":
                tool_calls.append(
                    ToolCall(
                        call_id=content_block.id,
                        name=content_block.name,
                        arguments=content_block.input,
                    )
                )
                self.message_history.append(
                    anthropic.types.MessageParam(role="assistant", content=[content_block])
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
            tool_calls=tool_calls if tool_calls else None,
        )

        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="bedrock",
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(self, messages: list[LLMMessage]) -> list[anthropic.types.MessageParam]:
        """Convert OmniPerf messages into Anthropic-compatible message blocks."""
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
                        role="assistant",
                        content=[self.parse_tool_call(msg.tool_call)],
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
        """Convert tool call instructions into Anthropic payloads."""
        return anthropic.types.ToolUseBlockParam(
            type="tool_use",
            id=tool_call.call_id,
            name=tool_call.name,
            input=json.dumps(tool_call.arguments),
        )

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> anthropic.types.ToolResultBlockParam:
        """Convert tool call results into Anthropic-compatible responses."""
        result: str = ""
        if tool_call_result.result:
            result = result + tool_call_result.result + "\n"
        if tool_call_result.error:
            result += "Tool call failed with error:\n"
            result += tool_call_result.error
        result = result.strip()

        return anthropic.types.ToolResultBlockParam(
            tool_use_id=tool_call_result.call_id,
            type="tool_result",
            content=result,
            is_error=not tool_call_result.success,
        )


