"""
Task 5.2 - Real Assessment runner
--------------------------------
Run one real firm-year assessment through the project's existing integration
wrapper, real panel-backed tools, frozen v3 model adapter, and Task 5.3 verifier.

Run from the project root:
    pip install openai
    # Set OPENAI_API_KEY in your environment first.
    python run_task_5_2_real.py --gvkey 001004 --year 2018

The script deliberately does not implement or replace the project's data tools.
It imports src.task_5_2_integration, which should refuse placeholder/stub tools.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any

from openai import OpenAI

from src.task_5_2_integration import run_task_5_2


class OpenAIChatClient:
    """
    Adapter for the project's LLMClient.complete(messages, tools) interface.

    The project agent stores tool exchanges in a provider-neutral message
    format. This adapter converts those exchanges to OpenAI Chat Completions
    function-tool messages and converts the response back to the format
    expected by src.agent.run_agent.
    """

    def __init__(self, model: str):
        self.client = OpenAI()
        self.model = model

    @staticmethod
    def _to_openai_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        i = 0

        while i < len(messages):
            msg = messages[i]
            role = msg.get("role")

            # The project agent records an assistant tool call as JSON text,
            # followed by a tool message. Convert that pair to the OpenAI
            # assistant.tool_calls + tool.tool_call_id format.
            if role == "assistant" and i + 1 < len(messages):
                next_msg = messages[i + 1]
                content = msg.get("content")
                try:
                    parsed = json.loads(content) if isinstance(content, str) else {}
                except json.JSONDecodeError:
                    parsed = {}

                if (
                    isinstance(parsed, dict)
                    and "tool_call" in parsed
                    and next_msg.get("role") == "tool"
                ):
                    tool_call_id = f"call_project_{i}"
                    converted.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": tool_call_id,
                            "type": "function",
                            "function": {
                                "name": parsed["tool_call"],
                                "arguments": json.dumps(parsed.get("arguments", {})),
                            },
                        }],
                    })
                    converted.append({
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": next_msg.get("content", ""),
                    })
                    i += 2
                    continue

            # Normal system/user/assistant messages.
            if role in {"system", "user", "assistant"}:
                converted.append({
                    "role": role,
                    "content": msg.get("content") or "",
                })
            elif role == "tool":
                # A tool message without its preceding project tool-call
                # record indicates malformed history; fail rather than guess.
                raise ValueError("Found a tool result without a matching assistant tool call.")
            i += 1

        return converted

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        api_tools = []
        for item in tools:
            if item.get("type") == "function":
                api_tools.append(item)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": self._to_openai_messages(messages),
            "temperature": 0,
        }
        if api_tools:
            kwargs["tools"] = api_tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        message = response.choices[0].message

        if message.tool_calls:
            # The project agent executes one tool call per loop iteration.
            call = message.tool_calls[0]
            return {
                "type": "tool_call",
                "name": call.function.name,
                "arguments": json.loads(call.function.arguments or "{}"),
            }

        return {
            "type": "final",
            "content": message.content or "",
        }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run one Task 5.2 real-data firm assessment."
    )
    parser.add_argument("--gvkey", required=True, help="Six-character Compustat GVKEY.")
    parser.add_argument("--year", required=True, type=int, help="Feature/assessment fiscal year.")
    parser.add_argument(
        "--model",
        default=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        help="OpenAI model name; defaults to OPENAI_MODEL or gpt-4.1-mini.",
    )
    parser.add_argument(
        "--output-dir",
        default="task_outputs/real_assessments",
        help="Directory for the structured assessment and trace JSON.",
    )
    parser.add_argument(
        "--max-tool-calls",
        type=int,
        default=8,
        help="Maximum number of tool calls (project default: 8).",
    )
    args = parser.parse_args()

    if not os.getenv("OPENAI_API_KEY"):
        raise SystemExit(
            "OPENAI_API_KEY is not set. Set it in your terminal before running."
        )

    gvkey = str(args.gvkey).strip()
    if not re.fullmatch(r"\d{1,6}", gvkey):
        raise SystemExit("GVKEY must contain between 1 and 6 digits.")
    gvkey = gvkey.zfill(6)

    if args.year < 1900 or args.year > 2100:
        raise SystemExit("Please provide a valid fiscal year.")
    if args.max_tool_calls < 1 or args.max_tool_calls > 8:
        raise SystemExit("For this project, max-tool-calls must be between 1 and 8.")

    llm = OpenAIChatClient(args.model)

    question = (
        f"Assess {gvkey} using fiscal-year {args.year} information to estimate "
        f"the risk of an adverse ICFR opinion in fiscal year {args.year + 1}. "
        "Use only evidence returned by the available tools. Respect the fiscal-year "
        "cutoff: do not request or use information after the feature year. "
        "Include supporting evidence, contradictory evidence, uncertainty, and "
        "specific recommended checks. The filing-excerpt tool may be unavailable "
        "or gated; do not imply that a filing was reviewed unless it returns a passage."
    )

    result = run_task_5_2(
        firm_id=gvkey,
        feature_year=args.year,
        user_question=question,
        llm=llm,
        logger=None,
        max_tool_calls=args.max_tool_calls,
        output_dir=args.output_dir,
    )

    print("\nTASK 5.2 RUN")
    print(f"Firm (GVKEY):       {gvkey}")
    print(f"Feature year:       {args.year}")
    print(f"Outcome year:       {args.year + 1}")
    print(f"Agent status:       {result['agent_status']}")
    print(f"Tool calls used:    {result['tool_calls_used']}")
    print(f"Run ID:             {result['run_id']}")
    print(f"Saved JSON:         {result['saved_to']}")

    print("\nVERIFIED ASSESSMENT")
    print(json.dumps(result["verified_output"], indent=2, default=str))

    print("\nTASK 5.3 VERIFICATION")
    print(json.dumps(result["verification_report"], indent=2, default=str))


if __name__ == "__main__":
    main()
