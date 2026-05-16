"""
Quick test — send a chat request to the DeAI network.

Usage:
    python test_request.py
    python test_request.py --model llama3 --message "Explain quantum computing simply"
"""

import httpx
import json
import argparse
import sys


def send_request(model: str, message: str, url: str = "http://localhost:8000"):
    print(f"\n  Sending request to DeAI network...")
    print(f"  Model:   {model}")
    print(f"  Message: {message}\n")

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": message}
        ],
        "max_tokens": 256,
    }

    try:
        with httpx.Client(timeout=90.0) as client:
            resp = client.post(f"{url}/v1/chat/completions", json=payload)
            resp.raise_for_status()
            data = resp.json()

        content = data["choices"][0]["message"]["content"]
        usage = data["usage"]

        print("  Response from network:")
        print("  " + "-" * 60)
        print(f"  {content}")
        print("  " + "-" * 60)
        print(f"\n  Tokens — prompt: {usage['prompt_tokens']}  completion: {usage['completion_tokens']}  total: {usage['total_tokens']}")
        print(f"  Model served: {data['model']}\n")

    except httpx.HTTPStatusError as e:
        print(f"\n  Error {e.response.status_code}: {e.response.json().get('detail', e.response.text)}")
        sys.exit(1)
    except httpx.ConnectError:
        print(f"\n  Could not connect to {url}")
        print("  Is the orchestrator running? Start it with:  python protocol/orchestrator.py")
        sys.exit(1)


def check_status(url: str = "http://localhost:8000"):
    try:
        resp = httpx.get(f"{url}/status", timeout=5.0)
        data = resp.json()
        print(f"\n  Network status:")
        print(f"  Nodes online:  {data['nodes_online']}")
        print(f"  Total requests: {data['stats']['requests']}")
        print(f"  Completed:      {data['stats']['completed']}")
        for node in data["nodes"]:
            print(f"    Node {node['node_id']}  models={node['models']}  gpu={node['gpu']}  status={node['status']}  tasks={node['tasks_completed']}")
    except Exception as e:
        print(f"  Status check failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="any", help="Model name to request")
    parser.add_argument("--message", default="Hello! What is DeAI?", help="Message to send")
    parser.add_argument("--url", default="http://localhost:8000", help="Orchestrator URL")
    parser.add_argument("--status", action="store_true", help="Just check network status")
    args = parser.parse_args()

    if args.status:
        check_status(args.url)
    else:
        check_status(args.url)
        send_request(args.model, args.message, args.url)
