"""
Scout mode — investigate a URL and produce a draft scraping instruction.
Does NOT extract or save company data.
Hard limit: 6 tool calls total.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.prompts import SCOUT_PROMPT
from agent.tools import TOOL_DEFINITIONS, dispatch_tool

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_TOOL_CALLS = 6
MODEL = "claude-sonnet-4-6"
MAX_RETRIES = 3
RETRY_WAIT = 10  # seconds


def _create_message(client: anthropic.Anthropic, **kwargs) -> anthropic.types.Message:
    """Call client.messages.create() with retry on 529 OverloadedError."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return client.messages.create(**kwargs)
        except anthropic.APIStatusError as e:
            if e.status_code == 529 and attempt < MAX_RETRIES:
                print(f"[scout] API overloaded (529), retrying in {RETRY_WAIT}s (attempt {attempt}/{MAX_RETRIES}) ...")
                time.sleep(RETRY_WAIT)
            else:
                raise


def run_scout(url: str) -> dict:
    """
    Investigate a URL and return a draft scraping instruction entry.

    Hard limit: MAX_TOOL_CALLS tool calls. After that the loop stops
    regardless of model state — this is enforced by a counter, not a prompt.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY not set"}

    client = anthropic.Anthropic(api_key=api_key)

    messages = [{"role": "user", "content": f"Scout this URL: {url}"}]
    tool_call_count = 0
    all_tool_calls = []

    print(f"[scout] Starting scout for: {url}")
    print(f"[scout] Model: {MODEL}, max tool calls: {MAX_TOOL_CALLS}")

    while True:
        response = _create_message(
            client,
            model=MODEL,
            max_tokens=4096,
            system=SCOUT_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        print(f"[scout] Response stop_reason: {response.stop_reason}")

        # Add assistant response to message history
        messages.append({"role": "assistant", "content": response.content})

        # If no tool calls, we're done
        if response.stop_reason == "end_turn":
            break

        # Process tool calls
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            # Hard limit check — stop before executing if already at limit
            if tool_call_count >= MAX_TOOL_CALLS:
                print(f"[scout] Hard limit reached ({MAX_TOOL_CALLS} tool calls). Stopping.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({"error": f"Hard limit of {MAX_TOOL_CALLS} tool calls reached. Stopping."}),
                })
                break

            print(f"[scout] Tool call {tool_call_count + 1}/{MAX_TOOL_CALLS}: {block.name}({json.dumps(block.input)[:120]})")
            result_str = dispatch_tool(block.name, block.input)
            tool_call_count += 1

            all_tool_calls.append({
                "tool": block.name,
                "input": block.input,
                "result": json.loads(result_str),
            })

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result_str,
            })

        messages.append({"role": "user", "content": tool_results})

        # Enforce hard limit — break loop after processing any limit-exceeded results
        if tool_call_count >= MAX_TOOL_CALLS and response.stop_reason != "end_turn":
            # Give the model one more turn to produce a final response
            final_response = _create_message(
                client,
                model=MODEL,
                max_tokens=2048,
                system=SCOUT_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": final_response.content})
            break

    # Extract final text response
    final_text = ""
    for block in messages[-1]["content"] if isinstance(messages[-1]["content"], list) else []:
        if hasattr(block, "type") and block.type == "text":
            final_text = block.text
            break
    if not final_text and isinstance(messages[-1]["content"], list):
        for block in messages[-1]["content"]:
            if isinstance(block, dict) and block.get("type") == "text":
                final_text = block.get("text", "")
                break

    # Try to parse structured JSON result from final text
    structured_result = _extract_json(final_text)

    result = {
        "success": True,
        "mode": "scout",
        "url": url,
        "tool_calls_used": tool_call_count,
        "structured_result": structured_result,
        "raw_response": final_text,
        "tool_call_log": all_tool_calls,
    }

    # Write log
    _write_log("scout", url, result)

    return result


def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from the model's text response."""
    import re
    # Look for a JSON block (fenced or bare)
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
    # Try parsing the whole text as JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    return None


def _write_log(mode: str, url: str, result: dict) -> None:
    """Write the full result to a timestamped log file."""
    LOGS_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_domain = url.replace("https://", "").replace("http://", "").split("/")[0].replace(".", "_")
    log_path = LOGS_DIR / f"{mode}_{safe_domain}_{timestamp}.json"
    with open(log_path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"[scout] Log written to {log_path}")
