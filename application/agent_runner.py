"""
DeAI Persistent Agent Runner
-----------------------------
Runs a long-lived AI agent funded by a DEAI token budget. The agent
keeps sending tasks to the network and processing responses until the
budget runs out, then pauses and waits for a top-up.

Use cases:
  - Research crawlers that process URLs one by one
  - Continuous summarisation pipelines
  - Automated assistants that stay running as long as they're funded
  - Community-funded agents (anyone can top up the wallet to extend runtime)

Run:
    python application/agent_runner.py --prompt "Summarize today's AI news"
    python application/agent_runner.py --prompt-file prompts.txt --budget 100
    python application/agent_runner.py --help

Budget:
    --budget N sets a max spend in DEAI tokens (in-memory estimate).
    Without --budget the agent runs until stopped with Ctrl+C.

    In on-chain mode, the orchestrator mints real DEAI to the miner —
    the budget here tracks the agent's spend estimate, not a wallet balance.
    A full on-chain spend gate (reading the user's wallet balance before each
    task) is a Phase 3 feature once user wallets are integrated.
"""

import argparse
import json
import sys
import time
import os
import httpx

# Cost estimate — mirrors ledger.py BASE_REWARD so the budget is meaningful
ESTIMATED_COST_PER_TASK = 10.0  # DEAI tokens per task (conservative)


def send_task(endpoint: str, model: str, prompt: str, api_key: str | None) -> dict:
    """Send one inference request and return the response dict."""
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 2048,
    }

    with httpx.Client(timeout=90.0) as client:
        resp = client.post(f"{endpoint}/v1/chat/completions", json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


def load_prompts(prompt_file: str) -> list[str]:
    with open(prompt_file) as f:
        return [line.strip() for line in f if line.strip()]


def run(args):
    endpoint  = args.endpoint.rstrip("/")
    model     = args.model
    budget    = args.budget      # None = unlimited
    interval  = args.interval
    api_key   = args.api_key or os.getenv("DEAI_API_KEY")
    loop      = args.loop

    # Build prompt sequence
    if args.prompt_file:
        prompts = load_prompts(args.prompt_file)
        print(f"Loaded {len(prompts)} prompts from {args.prompt_file}")
    elif args.prompt:
        prompts = [args.prompt]
    else:
        print("ERROR: provide --prompt or --prompt-file")
        sys.exit(1)

    spent        = 0.0
    tasks_run    = 0
    prompt_index = 0

    print(f"\nDeAI Agent Runner")
    print(f"  Endpoint : {endpoint}")
    print(f"  Model    : {model}")
    print(f"  Budget   : {budget} DEAI" if budget else "  Budget   : unlimited")
    print(f"  Loop     : {'yes' if loop else 'once per prompt'}")
    print(f"  Interval : {interval}s between tasks")
    print()

    try:
        while True:
            # Budget check
            if budget is not None and spent >= budget:
                print(f"\n[paused] Budget exhausted ({spent:.1f} / {budget} DEAI).")
                print("Top up your wallet or increase --budget to continue.")
                print("Waiting 60s then checking again...")
                time.sleep(60)
                continue

            # Pick next prompt
            if prompt_index >= len(prompts):
                if loop:
                    prompt_index = 0
                else:
                    print("\nAll prompts completed.")
                    break

            prompt = prompts[prompt_index]
            prompt_index += 1
            tasks_run += 1

            print(f"[task {tasks_run}] {prompt[:80]}{'...' if len(prompt) > 80 else ''}")

            try:
                start   = time.time()
                result  = send_task(endpoint, model, prompt, api_key)
                elapsed = time.time() - start

                content = result["choices"][0]["message"]["content"]
                tokens  = result.get("usage", {}).get("total_tokens", 0)
                spent  += ESTIMATED_COST_PER_TASK

                print(f"  -> {content[:120]}{'...' if len(content) > 120 else ''}")
                print(f"     tokens={tokens}  elapsed={elapsed:.1f}s  spent={spent:.1f} DEAI")

                if args.output_file:
                    with open(args.output_file, "a") as f:
                        f.write(json.dumps({
                            "task": tasks_run,
                            "prompt": prompt,
                            "response": content,
                            "tokens": tokens,
                            "elapsed": round(elapsed, 2),
                        }) + "\n")

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 503:
                    print(f"  [no nodes available] waiting {interval}s...")
                else:
                    print(f"  [error] {e}")

            except Exception as e:
                print(f"  [error] {e}")

            if interval > 0:
                time.sleep(interval)

    except KeyboardInterrupt:
        pass

    print(f"\nStopped. Tasks completed: {tasks_run}  Estimated spend: {spent:.1f} DEAI")


def main():
    parser = argparse.ArgumentParser(
        description="DeAI Persistent Agent Runner — runs a funded AI agent on the network."
    )
    parser.add_argument("--prompt", help="Single prompt to run (loops if --loop is set)")
    parser.add_argument("--prompt-file", help="File with one prompt per line")
    parser.add_argument("--model", default="any", help="Model to request (default: any)")
    parser.add_argument("--endpoint", default="http://localhost:8000",
                        help="Orchestrator HTTP endpoint (default: localhost)")
    parser.add_argument("--budget", type=float, default=None,
                        help="Max DEAI tokens to spend before pausing (default: unlimited)")
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Seconds between tasks (default: 2)")
    parser.add_argument("--loop", action="store_true",
                        help="Loop through prompts repeatedly until budget is exhausted")
    parser.add_argument("--output-file", help="Append results as JSON lines to this file")
    parser.add_argument("--api-key", default=None,
                        help="API key if the orchestrator requires one (or set DEAI_API_KEY)")

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
