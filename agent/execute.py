"""
Execute mode — run an approved scraping instruction for a known site.
Hard limit: 3 tool calls total.
Will not run if no approved entry exists in the instruction library.
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from agent.prompts import EXECUTE_PROMPT
from agent.tools import TOOL_DEFINITIONS, dispatch_tool, read_instruction_library

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
MAX_TOOL_CALLS = 3
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
                print(f"[execute] API overloaded (529), retrying in {RETRY_WAIT}s (attempt {attempt}/{MAX_RETRIES}) ...")
                time.sleep(RETRY_WAIT)
            else:
                raise


def run_execute(url: str, source_name: str) -> dict:
    """
    Execute an approved scraping instruction for a known site.

    Checks the instruction library first — if no approved entry exists,
    returns an error immediately without calling the model.

    Hard limit: MAX_TOOL_CALLS tool calls enforced by a counter.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"success": False, "error": "ANTHROPIC_API_KEY not set"}

    # Pre-flight check: must have an approved entry before spending any API calls
    domain = url.replace("https://", "").replace("http://", "").split("/")[0]
    library_check = read_instruction_library(domain)

    if not library_check["found"]:
        return {
            "success": False,
            "mode": "execute",
            "url": url,
            "error": f"No instruction library entry found for '{domain}'. Run scout mode first.",
            "tool_calls_used": 0,
        }

    approved = [e for e in library_check["entries"] if e.get("status") == "approved"]
    if not approved:
        flagged = [e for e in library_check["entries"] if e.get("status") == "flagged"]
        reason = flagged[0]["notes"] if flagged else "Entry exists but is not approved."
        return {
            "success": False,
            "mode": "execute",
            "url": url,
            "error": f"No approved entry for '{domain}'. Reason: {reason}",
            "tool_calls_used": 0,
        }

    # If entry points to a specific scraper script, report that — don't re-implement
    entry = approved[0]
    if entry.get("scraper"):
        print(f"[execute] Approved scraper script exists: {entry['scraper']}")
        print(f"[execute] For best results, run: python {entry['scraper']}")
        # Still run the agent — it will report this in its response

    client = anthropic.Anthropic(api_key=api_key)

    messages = [
        {
            "role": "user",
            "content": (
                f"Execute scraping for: {url}\n"
                f"Source name: {source_name}\n"
                f"Domain: {domain}"
            ),
        }
    ]
    tool_call_count = 0
    all_tool_calls = []

    print(f"[execute] Starting execute for: {url}")
    print(f"[execute] Model: {MODEL}, max tool calls: {MAX_TOOL_CALLS}")

    while True:
        response = _create_message(
            client,
            model=MODEL,
            max_tokens=4096,
            system=EXECUTE_PROMPT,
            tools=TOOL_DEFINITIONS,
            messages=messages,
        )

        print(f"[execute] Response stop_reason: {response.stop_reason}")

        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "end_turn":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue

            if tool_call_count >= MAX_TOOL_CALLS:
                print(f"[execute] Hard limit reached ({MAX_TOOL_CALLS} tool calls). Stopping.")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps({"error": f"Hard limit of {MAX_TOOL_CALLS} tool calls reached. Stopping."}),
                })
                break

            print(f"[execute] Tool call {tool_call_count + 1}/{MAX_TOOL_CALLS}: {block.name}({json.dumps(block.input)[:120]})")
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

        if tool_call_count >= MAX_TOOL_CALLS and response.stop_reason != "end_turn":
            final_response = _create_message(
                client,
                model=MODEL,
                max_tokens=2048,
                system=EXECUTE_PROMPT,
                tools=TOOL_DEFINITIONS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": final_response.content})
            break

    # Extract final text response
    final_text = ""
    last_content = messages[-1]["content"]
    items = last_content if isinstance(last_content, list) else []
    for block in items:
        if hasattr(block, "type") and block.type == "text":
            final_text = block.text
            break
        if isinstance(block, dict) and block.get("type") == "text":
            final_text = block.get("text", "")
            break

    structured_result = _extract_json(final_text)

    result = {
        "success": True,
        "mode": "execute",
        "url": url,
        "source_name": source_name,
        "tool_calls_used": tool_call_count,
        "structured_result": structured_result,
        "raw_response": final_text,
        "tool_call_log": all_tool_calls,
    }

    _write_log("execute", url, result)

    return result


def _extract_json(text: str) -> dict | None:
    """Try to extract a JSON object from the model's text response."""
    import re
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
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
    print(f"[execute] Log written to {log_path}")
