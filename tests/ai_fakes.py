"""Offline fake chat models for AI-layer tests.

``fake_llm`` returns plain scripted text (for ``prompt | llm | StrOutputParser``
chains). ``StructuredFakeChatModel`` additionally drives
``llm.with_structured_output(Schema)`` deterministically by returning preset
objects in sequence — no tool-calling, no network — so grading, reranking,
extraction and judge verdicts are all testable offline.
"""

from typing import Any, List

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda
from pydantic import PrivateAttr


def fake_llm(*responses: str) -> FakeListChatModel:
    """A chat model that returns the given strings in order (cycling)."""
    return FakeListChatModel(responses=list(responses) or [""])


class StructuredFakeChatModel(FakeListChatModel):
    """FakeListChatModel whose ``with_structured_output`` yields preset objects.

    ``structured_outputs`` are returned one per call (the last repeats), so a
    test can script e.g. ``[Grade(relevant=False), Grade(relevant=True)]`` for a
    grade→rewrite→grade loop.
    """

    structured_outputs: List[Any] = []
    # Shared cursor across with_structured_output() calls, so successive
    # structured calls within one graph run consume outputs in order.
    _cursor: List[int] = PrivateAttr(default_factory=lambda: [0])

    def with_structured_output(self, schema: Any = None, **kwargs: Any):  # noqa: D401
        outputs = list(self.structured_outputs)
        cursor = self._cursor

        def _invoke(_input: Any) -> Any:
            i = cursor[0]
            cursor[0] = i + 1
            if not outputs:
                return None
            return outputs[min(i, len(outputs) - 1)]

        return RunnableLambda(_invoke)


class ToolCallingFakeChatModel(FakeListChatModel):
    """Emits one tool call, then answers from the tool result.

    Drives ``create_react_agent`` offline: first turn returns an AIMessage with a
    tool call; once a ToolMessage is present it returns a final text answer.
    """

    responses: List[str] = [""]
    tool_name: str = "search_policies"
    tool_args: dict = {"query": "policy"}
    final_prefix: str = "Answer:"

    @property
    def _llm_type(self) -> str:
        return "tool-calling-fake"

    def bind_tools(self, tools: Any = None, **kwargs: Any):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        from langchain_core.messages import AIMessage, ToolMessage
        from langchain_core.outputs import ChatGeneration, ChatResult

        tool_msgs = [m for m in messages if isinstance(m, ToolMessage)]
        if not tool_msgs:
            msg = AIMessage(
                content="",
                tool_calls=[{"name": self.tool_name, "args": dict(self.tool_args), "id": "call_1"}],
            )
        else:
            msg = AIMessage(content=f"{self.final_prefix} {tool_msgs[-1].content}")
        return ChatResult(generations=[ChatGeneration(message=msg)])


class BoomLLM(FakeListChatModel):
    """A chat model that always raises — exercises graceful-fallback paths."""

    responses: List[str] = [""]

    def _generate(self, *args: Any, **kwargs: Any):
        raise RuntimeError("LLM unreachable")

    def with_structured_output(self, schema: Any = None, **kwargs: Any):
        def _invoke(_input: Any) -> Any:
            raise RuntimeError("LLM unreachable")

        return RunnableLambda(_invoke)
