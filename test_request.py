"""
Quick test — send chat requests to the DAI network.

Usage:
    python test_request.py
    python test_request.py --message "Explain quantum computing"
    python test_request.py --count 5             # send 5 requests in parallel
    python test_request.py --model llama3
    python test_request.py --status              # just show network state
"""

import httpx
import argparse
import sys
import time
import threading


def send_request(model: str, message: str, url: str, index: int = 0) -> dict:
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "max_tokens": 2048,
    }
    t0 = time.time()
    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(f"{url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()
        elapsed = round(time.time() - t0, 2)
        return {"ok": True, "data": data, "elapsed": elapsed, "index": index}
    except httpx.HTTPStatusError as e:
        return {"ok": False, "error": e.response.json().get("detail", e.response.text), "index": index}
    except httpx.ConnectError:
        return {"ok": False, "error": f"Could not connect to {url}. Is the orchestrator running?", "index": index}


def check_status(url: str):
    try:
        resp = httpx.get(f"{url}/status", timeout=5.0)
        data = resp.json()
        print(f"\n  Network status  ({data['nodes_online']} node(s) online)")
        print(f"  Requests: {data['stats']['requests']}  Completed: {data['stats']['completed']}  Failed: {data['stats']['failed']}")
        if data["nodes"]:
            print()
            for node in data["nodes"]:
                score = node.get("score", "busy")
                last_task = f"{node['last_task_ago_s']}s ago" if node.get("last_task_ago_s") else "never"
                gpu_str = f"GPU {node['vram_gb']}GB VRAM" if node.get("gpu") and node.get("vram_gb") else ("GPU" if node.get("gpu") else "CPU")
                print(f"    [{node['status']:8}]  {node['node_id']}  models={node['models']}  {gpu_str}  tasks={node['tasks_completed']}  score={score}  last_task={last_task}")
        else:
            print("  No nodes connected. Start one with:  python compute/node.py")
    except Exception as e:
        print(f"  Status check failed: {e}")


def print_result(r: dict, model: str):
    if not r["ok"]:
        print(f"\n  [Request {r['index']+1}] ERROR: {r['error']}")
        return
    data = r["data"]
    content = data["choices"][0]["message"]["content"]
    usage = data["usage"]
    print(f"\n  [Request {r['index']+1}]  {r['elapsed']}s  tokens={usage['total_tokens']}")
    print(f"  {content}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="any", help="Model name to request (default: any)")
    parser.add_argument("--message", default="Hello! What is DAI?", help="Message to send")
    parser.add_argument("--count", type=int, default=1, help="Number of parallel requests to send (default: 1)")
    parser.add_argument("--url", default="http://localhost:8000", help="Orchestrator URL")
    parser.add_argument("--status", action="store_true", help="Just show network status")
    args = parser.parse_args()

    check_status(args.url)

    if args.status:
        sys.exit(0)

    print(f"\n  Sending {args.count} request(s)  model={args.model}")
    print(f"  Message: {args.message}\n")

    if args.count == 1:
        r = send_request(args.model, args.message, args.url, 0)
        print_result(r, args.model)
    else:
        results = [None] * args.count
        threads = []

        def worker(i):
            results[i] = send_request(args.model, args.message, args.url, i)

        t0 = time.time()
        for i in range(args.count):
            t = threading.Thread(target=worker, args=(i,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        elapsed = round(time.time() - t0, 2)
        print(f"  All {args.count} requests completed in {elapsed}s\n")
        for r in results:
            print_result(r, args.model)

    print()
    check_status(args.url)
