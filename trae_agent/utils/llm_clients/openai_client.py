# Copyright (c) 2025 ByteDance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

"""OpenAI API client wrapper with tool integration."""

import json
from typing import override

import openai
from openai.types.responses import (
    EasyInputMessageParam,
    FunctionToolParam,
    Response,
    ResponseFunctionToolCallParam,
    ResponseInputParam,
    ToolParam,
)
from openai.types.responses.response_input_param import FunctionCallOutput

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
        self.message_history: ResponseInputParam = []
        self.current_response_id: str | None = None
        self.pending_function_calls: dict[str, ResponseFunctionToolCallParam] = {}
        self.pending_reasoning_blocks: dict[str, dict] = {}
        self.use_conversation_state: bool = True

    @override
    def set_chat_history(self, messages: list[LLMMessage]) -> None:
        """Set the chat history."""
        if not self.use_conversation_state:
            self.message_history = self.parse_messages(messages)
        # When using conversation state, we don't manually manage history
        # The conversation is managed by OpenAI via response_id

    def reset_conversation_state(self) -> None:
        """Reset conversation state for debugging or new conversation."""
        self.current_response_id = None
        self.pending_function_calls.clear()
        self.pending_reasoning_blocks.clear()
        self.message_history.clear()

    def _create_openai_response(
        self,
        api_call_input: ResponseInputParam,
        model_config: ModelConfig,
        tool_schemas: list[ToolParam] | None,
    ) -> Response:
        """Create a response using OpenAI API. This method will be decorated with retry logic."""

        api_params = {
            "input": api_call_input,
            "model": model_config.model,
            "tools": tool_schemas if tool_schemas else openai.NOT_GIVEN,
            "top_p": model_config.top_p,
            "max_output_tokens": model_config.max_tokens,
        }

        # Only add temperature for models that support it
        if not any(model in model_config.model for model in ["o3", "o4-mini", "gpt-5"]):
            api_params["temperature"] = model_config.temperature

        # Add high reasoning effort for all reasoning models
        if any(model in model_config.model for model in ["o3", "o4-mini", "gpt-5"]):
            api_params["reasoning"] = {"effort": "high"}

        # Use native state management
        if self.use_conversation_state:
            api_params["store"] = True
            if self.current_response_id:
                api_params["previous_response_id"] = self.current_response_id

        try:
            response = self.client.responses.create(**api_params)
            return response
        except Exception:
            raise

    @override
    def chat(
        self,
        messages: list[LLMMessage],
        model_config: ModelConfig,
        tools: list[Tool] | None = None,
        reuse_history: bool = True,
    ) -> LLMResponse:
        """Send chat messages to OpenAI with optional tool support."""
        openai_messages: ResponseInputParam = self.parse_messages(messages)

        tool_schemas = None
        if tools:
            tool_schemas = [
                FunctionToolParam(
                    name=tool.name,
                    description=tool.description,
                    parameters=tool.get_input_schema(),
                    strict=True,
                    type="function",
                )
                for tool in tools
            ]

        api_call_input: ResponseInputParam = []

        # When using conversation state, we let OpenAI handle the history
        # Only manually add history if not using conversation state
        if reuse_history and not self.use_conversation_state:
            api_call_input.extend(self.message_history)

        api_call_input.extend(openai_messages)

        # Apply retry decorator to the API call

        retry_decorator = retry_with(
            func=self._create_openai_response,
            provider_name="OpenAI",
            max_retries=model_config.max_retries,
        )
        response = retry_decorator(api_call_input, model_config, tool_schemas)

        content = ""
        tool_calls: list[ToolCall] = []

        # Capture response ID for future conversation state
        if hasattr(response, "id") and response.id:
            self.current_response_id = response.id

        for output_block in response.output:
            if output_block.type == "reasoning":
                # In manual history mode, we need to store reasoning blocks that are associated with function calls
                if not self.use_conversation_state:
                    reasoning_block = {
                        "type": "reasoning",
                        "id": output_block.id,
                        "summary": "Model reasoning process",
                    }
                    # Store reasoning block for potential pairing with function calls
                    if output_block.id:
                        self.pending_reasoning_blocks[output_block.id] = reasoning_block
                # Otherwise skip reasoning blocks in auto mode
            elif output_block.type == "function_call":
                tool_calls.append(
                    ToolCall(
                        call_id=output_block.call_id,
                        name=output_block.name,
                        arguments=json.loads(output_block.arguments)
                        if output_block.arguments
                        else {},
                        id=output_block.id,
                    )
                )
                tool_call_param = ResponseFunctionToolCallParam(
                    arguments=output_block.arguments,
                    call_id=output_block.call_id,
                    name=output_block.name,
                    type="function_call",
                )
                if output_block.status:
                    tool_call_param["status"] = output_block.status
                if output_block.id:
                    tool_call_param["id"] = output_block.id

                # Store pending function calls for proper lifecycle management
                self.pending_function_calls[output_block.call_id] = tool_call_param

                # Don't add function calls to history immediately in manual mode
                # They will be added when their results are processed to ensure proper ordering
            elif output_block.type == "message":
                content = "".join(
                    content_block.text
                    for content_block in output_block.content
                    if content_block.type == "output_text"
                )

        # Only add content to history if not using conversation state
        if content != "" and not self.use_conversation_state:
            self.message_history.append(
                EasyInputMessageParam(content=content, role="assistant", type="message")
            )

        usage = None
        if response.usage:
            usage = LLMUsage(
                input_tokens=response.usage.input_tokens or 0,
                output_tokens=response.usage.output_tokens or 0,
                cache_read_input_tokens=response.usage.input_tokens_details.cached_tokens or 0,
                reasoning_tokens=response.usage.output_tokens_details.reasoning_tokens or 0,
            )

        llm_response = LLMResponse(
            content=content,
            usage=usage,
            model=response.model,
            finish_reason=response.status,
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

    def parse_messages(self, messages: list[LLMMessage]) -> ResponseInputParam:
        """Parse the messages to OpenAI format."""
        openai_messages: ResponseInputParam = []
        for msg in messages:
            if msg.tool_result:
                openai_messages.append(self.parse_tool_call_result(msg.tool_result))
            elif msg.tool_call:
                openai_messages.append(self.parse_tool_call(msg.tool_call))
            else:
                if not msg.content:
                    raise ValueError("Message content is required")
                if msg.role == "system":
                    message_dict = {"role": "system", "content": msg.content}
                    # Add summary if not using conversation state (manual mode)
                    if not self.use_conversation_state:
                        message_dict["summary"] = (
                            msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                        )
                    openai_messages.append(message_dict)
                elif msg.role == "user":
                    message_dict = {"role": "user", "content": msg.content}
                    # Add summary if not using conversation state (manual mode)
                    if not self.use_conversation_state:
                        message_dict["summary"] = (
                            msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                        )
                    openai_messages.append(message_dict)
                elif msg.role == "assistant":
                    message_dict = {"role": "assistant", "content": msg.content}
                    # Add summary if not using conversation state (manual mode)
                    if not self.use_conversation_state:
                        message_dict["summary"] = (
                            msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
                        )
                    openai_messages.append(message_dict)
                else:
                    raise ValueError(f"Invalid message role: {msg.role}")
        return openai_messages

    def parse_tool_call(self, tool_call: ToolCall) -> ResponseFunctionToolCallParam:
        """Parse the tool call from the LLM response."""
        return ResponseFunctionToolCallParam(
            call_id=tool_call.call_id,
            name=tool_call.name,
            arguments=json.dumps(tool_call.arguments),
            type="function_call",
        )

    def parse_tool_call_result(self, tool_call_result: ToolResult) -> FunctionCallOutput:
        """Parse the tool call result from the LLM response to FunctionCallOutput format."""
        result_content: str = ""
        if tool_call_result.result is not None:
            result_content += str(tool_call_result.result)
        if tool_call_result.error:
            result_content += f"\nError: {tool_call_result.error}"
        result_content = result_content.strip()

        # Remove the function call from pending calls when we get the result
        call_id = tool_call_result.call_id
        if call_id in self.pending_function_calls:
            # If not using conversation state, add the pending function call to history
            # but only if it's not already there (avoid duplicates)
            if not self.use_conversation_state:
                pending_call = self.pending_function_calls[call_id]
                # Check if this function call is already in history
                call_already_in_history = any(
                    hasattr(msg, "call_id") and getattr(msg, "call_id", None) == call_id
                    for msg in self.message_history
                )
                if not call_already_in_history:
                    # Add reasoning block first if it exists (required by OpenAI)
                    if hasattr(pending_call, "get") and "id" in pending_call:
                        # Look for associated reasoning blocks
                        for reasoning_id, reasoning_block in list(
                            self.pending_reasoning_blocks.items()
                        ):
                            # Add the reasoning block before the function call
                            self.message_history.append(reasoning_block)
                            # Remove from pending reasoning blocks
                            del self.pending_reasoning_blocks[reasoning_id]
                            break  # Only add one reasoning block per function call

                    self.message_history.append(pending_call)
            del self.pending_function_calls[call_id]

        return FunctionCallOutput(
            type="function_call_output",  # Explicitly set the type field
            call_id=tool_call_result.call_id,
            output=result_content,
        )
