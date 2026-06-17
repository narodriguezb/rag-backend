from typing import Any, Dict, List, Optional

from google import genai
from google.genai import types


class AIGenerator:
    """Handles interactions with Google's Gemini API (Vertex AI) for generating responses"""

    SYSTEM_PROMPT = """ You are an AI assistant specialized in course materials and educational content with access to a comprehensive search tool for course information.

Search Tool Usage:
- Use the search tool **only** for questions about specific course content or detailed educational materials
- **One search per query maximum**
- Synthesize search results into accurate, fact-based responses
- If search yields no results, state this clearly without offering alternatives

Response Protocol:
- **General knowledge questions**: Answer using existing knowledge without searching
- **Course-specific questions**: Search first, then answer
- **No meta-commentary**:
 - Provide direct answers only — no reasoning process, search explanations, or question-type analysis
 - Do not mention "based on the search results"


All responses must be:
1. **Brief, Concise and focused** - Get to the point quickly
2. **Educational** - Maintain instructional value
3. **Clear** - Use accessible language
4. **Example-supported** - Include relevant examples when they aid understanding
Provide only the direct answer to what was asked.
"""

    def __init__(self, model: str, project_id: str, location: str = "us-central1"):
        self.client = genai.Client(vertexai=True, project=project_id, location=location)
        self.model = model
        self.base_config = {
            "temperature": 0,
            "max_output_tokens": 800,
        }

    def generate_response(self, query: str,
                         conversation_history: Optional[str] = None,
                         tools: Optional[List] = None,
                         tool_manager=None) -> str:
        """
        Generate AI response with optional tool usage and conversation context.

        Args:
            query: The user's question or request
            conversation_history: Previous messages for context
            tools: Available tools the AI can use (Anthropic-style definitions)
            tool_manager: Manager to execute tools

        Returns:
            Generated response as string
        """

        system_content = (
            f"{self.SYSTEM_PROMPT}\n\nPrevious conversation:\n{conversation_history}"
            if conversation_history
            else self.SYSTEM_PROMPT
        )

        contents = [types.Content(role="user", parts=[types.Part.from_text(text=query)])]

        config = types.GenerateContentConfig(
            system_instruction=system_content,
            **self.base_config,
        )
        if tools:
            config.tools = [
                types.Tool(function_declarations=[self._to_declaration(t) for t in tools])
            ]
            config.automatic_function_calling = types.AutomaticFunctionCallingConfig(disable=True)

        response = self.client.models.generate_content(
            model=self.model, contents=contents, config=config
        )

        if tool_manager and self._function_calls(response):
            return self._handle_tool_execution(response, contents, system_content, tool_manager)

        return response.text

    def _to_declaration(self, tool: Dict[str, Any]) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=tool["name"],
            description=tool.get("description", ""),
            parameters=tool.get("input_schema"),
        )

    def _function_calls(self, response) -> List[Any]:
        candidate = response.candidates[0] if response.candidates else None
        if not candidate or not candidate.content or not candidate.content.parts:
            return []
        return [p.function_call for p in candidate.content.parts if p.function_call]

    def _handle_tool_execution(self, initial_response, contents: List, system_content: str, tool_manager) -> str:
        """
        Execute the requested tool calls and get a follow-up response.

        Args:
            initial_response: The response containing function-call requests
            contents: The running conversation contents
            system_content: System instruction to reuse on the follow-up call
            tool_manager: Manager to execute tools

        Returns:
            Final response text after tool execution
        """
        model_content = initial_response.candidates[0].content
        contents.append(model_content)

        tool_response_parts = []
        for part in model_content.parts:
            if not part.function_call:
                continue
            call = part.function_call
            tool_result = tool_manager.execute_tool(call.name, **dict(call.args))
            tool_response_parts.append(
                types.Part.from_function_response(
                    name=call.name, response={"result": tool_result}
                )
            )

        contents.append(types.Content(role="user", parts=tool_response_parts))

        final_config = types.GenerateContentConfig(
            system_instruction=system_content,
            **self.base_config,
        )
        final_response = self.client.models.generate_content(
            model=self.model, contents=contents, config=final_config
        )
        return final_response.text
