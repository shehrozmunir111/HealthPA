import os
import shutil
import subprocess
from typing import Any, List, Optional

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ChatClaudeCLI(BaseChatModel):
    """Minimal text chat model backed by the `claude` CLI."""

    model: str = "haiku"
    command: str = "claude"
    disable_thinking: bool = True
    timeout: float = 120.0

    @property
    def _llm_type(self) -> str:
        return "claude_cli"

    @staticmethod
    def _role(message: BaseMessage) -> str:
        if isinstance(message, SystemMessage):
            return "System"
        if isinstance(message, AIMessage):
            return "Assistant"
        return "User"

    def _flatten(self, messages: List[BaseMessage]) -> str:
        parts = []
        for message in messages:
            content = message.content
            if isinstance(content, list):  # multimodal blocks -> text only
                content = " ".join(str(block) for block in content)
            parts.append(f"{self._role(message)}: {content}")
        return "\n\n".join(parts)

    def _call_cli(self, prompt: str) -> str:
        exe = shutil.which(self.command) or self.command
        # --strict-mcp-config skips MCP servers; small model + MAX_THINKING_TOKENS=0 keep calls fast.
        args = [exe, "-p", "--output-format", "text", "--strict-mcp-config"]
        if self.model:
            args += ["--model", self.model]
        env = dict(os.environ)
        if self.disable_thinking:
            env["MAX_THINKING_TOKENS"] = "0"
        try:
            proc = subprocess.run(
                args,
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                encoding="utf-8",
                errors="ignore",
                env=env,
            )
        except FileNotFoundError as exc:
            raise RuntimeError(
                "Claude CLI not found. Install Claude Code and ensure `claude` is on "
                "PATH, or set CHAT_LLM_PROVIDER to a cloud/local endpoint."
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(f"Claude CLI timed out after {self.timeout}s") from exc

        if proc.returncode != 0:
            raise RuntimeError(
                f"Claude CLI failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}"
            )
        return (proc.stdout or "").strip()

    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        text = self._call_cli(self._flatten(messages))
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=text))])
