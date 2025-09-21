# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenAI API client wrapper with tool integration."""

import json
from typing import override

import openai
from openai.types.chat import (
    ChatCompletion,
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessage,
    ChatCompletionMessageParam,
    ChatCompletionMessageToolCall,
    ChatCompletionSystemMessageParam,
    ChatCompletionToolMessageParam,
    ChatCompletionToolParam,
    ChatCompletionUserMessageParam,
)
from openai.types.chat.chat_completion_message_tool_call import Function

from trae_agent.tools.base import Tool, ToolCall, ToolResult
from trae_agent.utils.config import ModelConfig
from trae_agent.utils.llm_clients.base_client import BaseLLMClient
from trae_agent.utils.llm_clients.llm_basics import LLMMessage, LLMResponse, LLMUsage
from trae_agent.utils.llm_clients.retry_utils import retry_with


class OpenAIClient(BaseLLMClient):
    """OpenAI client wrapper with tool schema generation."""

    def __init__(self, model_config: ModelConfig):
        super().__init__(model_config)

        self.client: openai.OpenAI = openai.OpenAI(api_key=self.api_key, base_url=self.base_url)
        self.message_history: list[ChatCompletionMessageParam] = []
        self.pending_tool_calls: dict[str, ToolCall] = {}

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        self.message_history = self.parse_messages(messages)
        # Clear pending tool calls when setting new history
        self.pending_tool_calls.clear()

    def _create_openai_response(
        self,
        messages: list[ChatCompletionMessageParam],
        model_config: ModelConfig,
        tool_schemas: list[ChatCompletionToolParam] | None,
    ) -> ChatCompletion:
        """Create a response using OpenAI API. This method will be decorated with retry logic."""
        return self.client.chat.completions.create(
            model=model_config.model,
            messages=messages,
            tools=tool_schemas if tool_schemas else openai.NOT_GIVEN,
            temperature=model_config.temperature
            if "o3" not in model_config.model
            and "o4-mini" not in model_config.model
            and "gpt-5" not in model_config.model
            else openai.NOT_GIVEN,
            top_p=model_config.top_p,
            max_tokens=model_config.max_tokens,
        )

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to OpenAI with optional tool support."""
        openai_messages: list[ChatCompletionMessageParam] = self.parse_messages(messages)

        tool_schemas = None
        if tools:
            tool_schemas = [
                ChatCompletionToolParam(
                    type="function",
                    function={
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.get_input_schema(),
                        "strict": True,
                    }
                )
                for tool in tools
            ]

        api_messages: list[ChatCompletionMessageParam] = []
        if reuse_history:
            api_messages.extend(self.message_history)

        api_messages.extend(openai_messages)

        # Validate conversation flow before API call
        self._validate_conversation_flow(api_messages)

        # Apply retry decorator to the API call
        retry_decorator = retry_with(
            func=self._create_openai_response,
            provider_name="OpenAI",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(api_messages, model_config, tool_schemas)

        content = ""
        tool_calls: list[ToolCall] = []

        # Handle the response
        if response.choices and len(response.choices) > 0:
            choice = response.choices[0]
            message = choice.message

            if message.content:
                content = message.content

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    tool_calls.append(
                        ToolCall(
                            call_id=tool_call.id,
                            name=tool_call.function.name,
                            arguments=json.loads(tool_call.function.arguments)
                            if tool_call.function.arguments
                            else {},
                            id=tool_call.id,
                        )
                    )

                # Add tool calls to message history and track pending calls
                tool_call_messages = []
                for tool_call in message.tool_calls:
                    # Create tool call object for tracking
                    tracked_call = ToolCall(
                        call_id=tool_call.id,
                        name=tool_call.function.name,
                        arguments=json.loads(tool_call.function.arguments)
                        if tool_call.function.arguments
                        else {},
                        id=tool_call.id,
                    )
                    self.pending_tool_calls[tool_call.id] = tracked_call

                    tool_call_messages.append(
                        ChatCompletionMessageToolCall(
                            id=tool_call.id,
                            function=Function(
                                name=tool_call.function.name,
                                arguments=tool_call.function.arguments,
                            ),
                            type="function",
                        )
                    )

                # Add single assistant message with all tool calls
                self.message_history.append(
                    ChatCompletionAssistantMessageParam(
                        role="assistant",
                        tool_calls=tool_call_messages,
                        content=content if content else "",
                    )
                )

            elif content:
                # Add regular message to history
                self.message_history.append(
                    ChatCompletionAssistantMessageParam(
                        role="assistant",
                        content=content,
                    )
                )

        usage = None
        if response.usage:
            # Handle different possible structures for cached tokens
            cache_read_input_tokens = 0
            if hasattr(response.usage, 'prompt_tokens_details') and response.usage.prompt_tokens_details:
                if hasattr(response.usage.prompt_tokens_details, 'cached_tokens'):
                    cache_read_input_tokens = response.usage.prompt_tokens_details.cached_tokens
                elif hasattr(response.usage.prompt_tokens_details, 'get'):
                    cache_read_input_tokens = response.usage.prompt_tokens_details.get('cached_tokens', 0)

            usage = LLMUsage(
                input_tokens=response.usage.prompt_tokens or 0,
                output_tokens=response.usage.completion_tokens or 0,
                cache_read_input_tokens=cache_read_input_tokens,
                reasoning_tokens=0,  # Standard chat API doesn't have reasoning tokens
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=choice.finish_reason if response.choices and len(response.choices) > 0 else "stop",
            tool_calls=tool_calls if len(tool_calls) > 0 else None,
        )

        # Record trajectory if recorder is available
        if self.trajectory_recorder:
            self.trajectory_recorder.record_llm_interaction(
                messages=messages,
                response=llm_response,
                provider="openai",
                model=model_config.model,
                tools=tools,
            )

        return llm_response

    def parse_messages(self, messages: list[LLMMessage]) -> list[ChatCompletionMessageParam]:
        """Parse the messages to OpenAI format."""
        openai_messages: list[ChatCompletionMessageParam] = []

        for msg in messages:
            if msg.tool_result:
                # Convert tool result to proper tool message
                tool_response_msg = self.parse_tool_call_result(msg.tool_result)
                openai_messages.append(tool_response_msg)
                # Remove from pending calls since it's been handled
                if msg.tool_result.call_id in self.pending_tool_calls:
                    del self.pending_tool_calls[msg.tool_result.call_id]
            elif msg.tool_call:
                # Tool calls are already assistant messages
                openai_messages.append(self.parse_tool_call(msg.tool_call))
            else:
                if not msg.content:
                    raise ValueError("Message content is required")

                # Handle different message roles properly for OpenAI API
                if msg.role == "system":
                    openai_messages.append(ChatCompletionSystemMessageParam(role="system", content=msg.content))
                elif msg.role == "user":
                    openai_messages.append(ChatCompletionUserMessageParam(role="user", content=msg.content))
                elif msg.role == "assistant":
                    openai_messages.append(ChatCompletionAssistantMessageParam(role="assistant", content=msg.content))
                else:
                    raise ValueError(f"Invalid message role: {msg.role}")
        return openai_messages

    def parse_tool_call(self, tool_call: ToolCall) -> ChatCompletionAssistantMessageParam:
        """Parse the tool call from the LLM response."""
        return ChatCompletionAssistantMessageParam(
            role="assistant",
            tool_calls=[
                ChatCompletionMessageToolCall(
                    id=tool_call.call_id,
                    function=Function(
                        name=tool_call.name,
                        arguments=json.dumps(tool_call.arguments),
                    ),
                    type="function",
                )
            ],
            content="",
        )

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> ChatCompletionMessageParam:
        """Parse the tool call result from the LLM response to ChatCompletionMessage format."""
        result_content: str = ""
        if tool_call_result.result is not None:
            result_content += str(tool_call_result.result)
        if tool_call_result.error:
            result_content += f"\nError: {tool_call_result.error}"
        result_content = result_content.strip()

        # Ensure content is not empty for tool messages
        if not result_content:
            result_content = "Tool executed successfully."

        # Convert tool result to proper tool message
        return ChatCompletionToolMessageParam(
            role="tool",
            content=result_content,
            tool_call_id=tool_call_result.call_id,
        )

    def _validate_conversation_flow(self, api_messages: list[ChatCompletionMessageParam]) -> None:
        """Validate that the conversation flow is correct for OpenAI API.
        
        Ensures that every assistant message with tool calls is followed by 
        corresponding tool messages with matching tool_call_ids.
        """
        pending_tool_call_ids: set[str] = set()
        
        for i, msg in enumerate(api_messages):
            msg_role = getattr(msg, 'role', None)
            
            if msg_role == "assistant":
                tool_calls = getattr(msg, 'tool_calls', None)
                if tool_calls:
                    # Assistant message with tool calls - track the call IDs
                    for tool_call in tool_calls:
                        pending_tool_call_ids.add(tool_call.id)
            elif msg_role == "tool":
                # Tool response message - should match a pending tool call
                tool_call_id = getattr(msg, 'tool_call_id', None)
                if tool_call_id and tool_call_id in pending_tool_call_ids:
                    pending_tool_call_ids.remove(tool_call_id)
                elif tool_call_id:
                    # Tool response without matching tool call - this is an error
                    raise ValueError(f"Tool response with ID {tool_call_id} has no matching tool call")
        
        # If we have pending tool calls at the end, it means there are unmatched tool calls
        if pending_tool_call_ids:
            print(f"WARNING: Found {len(pending_tool_call_ids)} unmatched tool calls: {pending_tool_call_ids}")
            # Don't raise error here as the agent might still be processing, just log the warning

    def _update_message_history_with_tool_results(self, tool_results: list) -> None:
        """Update message history with tool results to maintain proper conversation flow."""
        for tool_result in tool_results:
            if hasattr(tool_result, 'call_id'):
                tool_response_msg = self.parse_tool_call_result(tool_result)
                self.message_history.append(tool_response_msg)
                # Remove from pending calls
                if tool_result.call_id in self.pending_tool_calls:
                    del self.pending_tool_calls[tool_result.call_id]
