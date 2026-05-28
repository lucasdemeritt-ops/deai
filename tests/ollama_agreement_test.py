"""
Two-node Ollama agreement test.

Fires a batch of prompts across three categories (factual, explanatory,
creative/ambiguous) with --verify-sample-rate 1.0 active on the orchestrator.
Reports per-category pass rate. Agreement scores appear in the orchestrator
logs (look for "VERIFY OK" / "VERIFY MISMATCH" lines).

Usage:
    # Terminal 1 — orchestrator (embedding comparator on)
    python protocol/orchestrator.py \\
        --verify-sample-rate 1.0 \\
        --verify-threshold 0.85 \\
        --embedding-url http://localhost:11434

    # Terminals 2 & 3 — two real Ollama nodes
    python compute/node.py --ollama --models qwen3:8b
    python compute/node.py --ollama --models qwen3:8b

    # Terminal 4 — this script
    python tests/ollama_agreement_test.py
    python tests/ollama_agreement_test.py --threshold 0.80   # if 0.85 is too tight
    python tests/ollama_agreement_test.py --model llama3
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error

# ── Prompt bank ──────────────────────────────────────────────────────────────

PROMPTS = {
    "factual": [
        ("capital of France",
         [{"role": "user", "content": "What is the capital of France? Answer in one word."}]),
        ("7 × 8",
         [{"role": "user", "content": "What is 7 multiplied by 8? Answer with just the number."}]),
        ("WW2 end year",
         [{"role": "user", "content": "What year did World War II end? Answer with just the year."}]),
        ("boiling point water",
         [{"role": "user", "content": "What is the boiling point of water in Celsius? Answer with just the number."}]),
        ("speed of light unit",
         [{"role": "user", "content": "What unit is the speed of light measured in? Answer in three words or fewer."}]),
    ],
    "explanatory": [
        ("TCP handshake",
         [{"role": "user", "content": "Explain how a TCP three-way handshake works. Keep it under 100 words."}]),
        ("list vs tuple",
         [{"role": "user", "content": "What are the main differences between Python lists and tuples? Keep it under 80 words."}]),
        ("HTTPS encryption",
         [{"role": "user", "content": "Describe how HTTPS encrypts web traffic. Keep it under 100 words."}]),
        ("RAM vs storage",
         [{"role": "user", "content": "What is the difference between RAM and storage? Keep it under 80 words."}]),
        ("git rebase vs merge",
         [{"role": "user", "content": "What is the difference between git rebase and git merge? Keep it under 80 words."}]),
    ],
    "creative": [
        ("robot story",
         [{"role": "user", "content": "Write exactly two sentences: a short story about a robot who learns to cook."}]),
        ("meaning of life",
         [{"role": "user", "content": "What is the meaning of life? Answer in one sentence."}]),
        ("productivity tips",
         [{"role": "user", "content": "Give exactly three short bullet points: tips for staying focused while coding."}]),
        ("describe blue",
         [{"role": "user", "content": "Describe the color blue to someone who has never seen it. One sentence only."}]),
        ("haiku about Python",
         [{"role": "user", "content": "Write a haiku about the Python programming language."}]),
    ],
}


# ── HTTP helper ───────────────────────────────────────────────────────────────

def post_chat(url: str, model: str, messages: list, timeout: int) -> tuple[int, str]:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "max_tokens": 512,
        "temperature": 0.0,
    }).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            content = data["choices"][0]["message"]["content"]
            return 200, content
    except urllib.error.HTTPError as e:
        return e.code, e.reason
    except Exception as e:
        return 0, str(e)


# ── Main ──────────────────────────────────────────────────────────────────────

def run(args):
    url = args.orchestrator.rstrip("/") + "/v1/chat/completions"
    delay = args.delay

    results = {}  # category -> list of (name, status_code, passed)

    print(f"\nDAI two-node Ollama agreement test")
    print(f"  orchestrator : {args.orchestrator}")
    print(f"  model        : {args.model}")
    print(f"  threshold    : {args.threshold}  (set on orchestrator — not enforced here)")
    print(f"  timeout/req  : {args.timeout}s\n")
    print("  Scores appear in orchestrator logs: grep 'VERIFY' orchestrator output\n")
    print(f"{'Category':<14} {'Prompt':<22} {'Status':>6}  {'Result'}")
    print("-" * 70)

    total_pass = total_fail = total_err = 0

    for category, prompts in PROMPTS.items():
        cat_results = []
        for name, messages in prompts:
            code, text = post_chat(url, args.model, messages, args.timeout)

            if code == 200:
                status_str = "200 OK"
                passed = True
                total_pass += 1
                detail = text[:60].replace("\n", " ") + ("..." if len(text) > 60 else "")
            elif code == 502:
                status_str = "502 MISMATCH"
                passed = False
                total_fail += 1
                detail = "(nodes disagreed — see orchestrator logs)"
            elif code == 503:
                status_str = "503 NO NODE"
                passed = False
                total_err += 1
                detail = "(no node available)"
            elif code == 504:
                status_str = "504 TIMEOUT"
                passed = False
                total_err += 1
                detail = "(node timed out)"
            else:
                status_str = f"{code} ERR"
                passed = False
                total_err += 1
                detail = text[:60]

            mark = "✓" if passed else "✗"
            print(f"{category:<14} {name:<22} {status_str:>12}  {mark}  {detail}")
            cat_results.append((name, code, passed))

            if delay > 0:
                time.sleep(delay)

        results[category] = cat_results
        print()

    # Per-category summary
    print("=" * 70)
    print(f"{'Category':<14}  {'Pass':>4}  {'Fail':>4}  {'Err':>4}  {'Rate':>6}")
    print("-" * 70)
    for category, cat_results in results.items():
        p = sum(1 for _, _, ok in cat_results if ok)
        f = sum(1 for _, c, ok in cat_results if not ok and c in (502,))
        e = sum(1 for _, c, ok in cat_results if not ok and c not in (200, 502))
        n = len(cat_results)
        rate = f"{p/n*100:.0f}%" if n else "-"
        print(f"{category:<14}  {p:>4}  {f:>4}  {e:>4}  {rate:>6}")
    print("-" * 70)
    total = total_pass + total_fail + total_err
    rate = f"{total_pass/total*100:.0f}%" if total else "-"
    print(f"{'TOTAL':<14}  {total_pass:>4}  {total_fail:>4}  {total_err:>4}  {rate:>6}")
    print()

    if total_err > 0:
        print("ERR rows = orchestrator unreachable or no nodes connected.")
        print("Make sure two `node.py --ollama` clients are running.\n")

    if total_fail > 0:
        print("MISMATCH rows (502): two nodes returned semantically different answers.")
        print("Check orchestrator logs for agreement scores — the threshold may need")
        print(f"lowering (current: {args.threshold}). Re-run with --threshold 0.75 to see")
        print("if the score is close to the boundary.\n")

    return 0 if total_err == 0 and total_fail == 0 else 1


def parse_args():
    p = argparse.ArgumentParser(description="Two-node Ollama agreement stress test")
    p.add_argument("--orchestrator", default="http://localhost:8000",
                   help="Orchestrator base URL (default: http://localhost:8000)")
    p.add_argument("--model", default="any",
                   help="Model to request (default: any)")
    p.add_argument("--threshold", type=float, default=0.85,
                   help="Threshold set on orchestrator — printed for reference only (default: 0.85)")
    p.add_argument("--timeout", type=int, default=120,
                   help="Per-request timeout in seconds (default: 120)")
    p.add_argument("--delay", type=float, default=1.0,
                   help="Seconds between requests (default: 1.0)")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(run(parse_args()))
