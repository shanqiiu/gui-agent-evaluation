"""
vLLM Inference Script for Qwen2.5-VL-7B UI-TARS Checkpoint

Usage:
    # Single image inference
    python inference.py --image path/to/image.jpg --prompt "Describe this UI"

    # Multi-image inference
    python inference.py --image img1.jpg img2.jpg --prompt "Compare these UIs"

    # Batch from JSON
    python inference.py --batch questions.json --output results.json

    # OpenAI-compatible API server
    python inference.py --serve --port 8000 --tp 1

Requirements:
    pip install vllm>=0.19.0 pillow
"""

import argparse
import json
import time
from pathlib import Path
from typing import Optional

from PIL import Image
from vllm import LLM, SamplingParams


MODEL_DIR = Path(__file__).parent
DEFAULT_MODEL = str(MODEL_DIR)


def build_sampling_params(
    temperature: float = 0.1,
    top_p: float = 0.001,
    top_k: int = 1,
    repetition_penalty: float = 1.05,
    max_tokens: int = 2048,
    stop_token_ids: Optional[list[int]] = None,
) -> SamplingParams:
    return SamplingParams(
        temperature=temperature,
        top_p=top_p,
        top_k=top_k,
        repetition_penalty=repetition_penalty,
        max_tokens=max_tokens,
        stop_token_ids=stop_token_ids or [151645, 151643],
    )


def build_messages(prompt: str, image_paths: list[str]) -> list[dict]:
    """Build conversation messages in Qwen2.5-VL format."""
    content = []
    for img_path in image_paths:
        content.append({"type": "image", "image": str(img_path)})
    content.append({"type": "text", "text": prompt})
    return [{"role": "user", "content": content}]


def chat(
    llm: LLM,
    prompt: str,
    image_paths: list[str],
    sampling_params: SamplingParams,
) -> str:
    """Single-turn chat with image input."""
    messages = build_messages(prompt, image_paths)
    outputs = llm.chat(messages=messages, sampling_params=sampling_params)
    return outputs[0].outputs[0].text


def run_batch(
    llm: LLM,
    batch: list[dict],
    sampling_params: SamplingParams,
) -> list[dict]:
    """
    Run a batch of inference requests.

    Each item in batch:
        {"prompt": "...", "images": ["img1.jpg", ...]}
    """
    results = []
    for item in batch:
        prompt = item["prompt"]
        images = item.get("images", [])
        start = time.time()
        response = chat(llm, prompt, images, sampling_params)
        elapsed = time.time() - start
        results.append({
            "prompt": prompt,
            "images": images,
            "response": response,
            "latency_s": round(elapsed, 3),
        })
    return results


def launch_server(args):
    """Launch OpenAI-compatible API server using vllm serve."""
    import sys
    import subprocess

    cmd = [
        sys.executable, "-m", "vllm.entrypoints.openai.api_server",
        "--model", args.model,
        "--dtype", args.dtype,
        "--tensor-parallel-size", str(args.tp),
        "--max-model-len", str(args.max_model_len),
        "--gpu-memory-utilization", str(args.gpu_memory),
        "--host", args.host,
        "--port", str(args.port),
    ]
    print(f"Launching vLLM server: {' '.join(cmd)}")
    try:
        subprocess.run(cmd)
    except KeyboardInterrupt:
        print("\nServer stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="Qwen2.5-VL-7B UI-TARS vLLM Inference"
    )
    parser.add_argument(
        "--model", type=str, default=DEFAULT_MODEL,
        help="Path to the model directory",
    )
    parser.add_argument(
        "--prompt", type=str, default="Describe this image.",
        help="Text prompt for the model",
    )
    parser.add_argument(
        "--image", nargs="+", type=str, default=[],
        help="Path(s) to input image(s)",
    )
    parser.add_argument(
        "--batch", type=str, default=None,
        help="Path to JSON file with batch of questions",
    )
    parser.add_argument(
        "--output", type=str, default="results.json",
        help="Output file for batch results",
    )

    # Serving mode
    parser.add_argument(
        "--serve", action="store_true",
        help="Launch OpenAI-compatible API server",
    )
    parser.add_argument(
        "--host", type=str, default="0.0.0.0",
        help="Server host",
    )
    parser.add_argument(
        "--port", type=int, default=8000,
        help="Server port",
    )

    # vLLM engine options
    parser.add_argument(
        "--tp", "--tensor-parallel-size", type=int, default=1,
        help="Tensor parallel size (number of GPUs)",
    )
    parser.add_argument(
        "--dtype", type=str, default="bfloat16",
        choices=["bfloat16", "float16", "auto"],
        help="Model data type",
    )
    parser.add_argument(
        "--max-model-len", type=int, default=32768,
        help="Maximum sequence length",
    )
    parser.add_argument(
        "--gpu-memory", type=float, default=0.9,
        help="GPU memory utilization ratio",
    )
    parser.add_argument(
        "--max-images", type=int, default=10,
        help="Max images per prompt",
    )

    # Generation options
    parser.add_argument(
        "--temperature", type=float, default=0.1,
        help="Sampling temperature",
    )
    parser.add_argument(
        "--top-p", type=float, default=0.001,
        help="Nucleus sampling top-p",
    )
    parser.add_argument(
        "--top-k", type=int, default=1,
        help="Top-k sampling",
    )
    parser.add_argument(
        "--repetition-penalty", type=float, default=1.05,
        help="Repetition penalty",
    )
    parser.add_argument(
        "--max-tokens", type=int, default=2048,
        help="Max generated tokens",
    )

    args = parser.parse_args()

    # Serve mode
    if args.serve:
        launch_server(args)
        return

    # Initialize engine
    print(f"Loading model: {args.model}")
    print(f"TP size: {args.tp}, dtype: {args.dtype}, max_len: {args.max_model_len}")

    llm = LLM(
        model=args.model,
        dtype=args.dtype,
        tensor_parallel_size=args.tp,
        max_model_len=args.max_model_len,
        gpu_memory_utilization=args.gpu_memory,
        limit_mm_per_prompt={"image": args.max_images},
    )

    sampling_params = build_sampling_params(
        temperature=args.temperature,
        top_p=args.top_p,
        top_k=args.top_k,
        repetition_penalty=args.repetition_penalty,
        max_tokens=args.max_tokens,
    )

    # Batch mode
    if args.batch:
        with open(args.batch, "r", encoding="utf-8") as f:
            batch = json.load(f)
        print(f"Running batch ({len(batch)} items) from {args.batch}")
        results = run_batch(llm, batch, sampling_params)
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"Results saved to {args.output}")
        for r in results:
            print(f"  Q: {r['prompt'][:60]}...")
            print(f"  A: {r['response'][:120]}...")
            print(f"  Latency: {r['latency_s']}s")
            print()
        return

    # Interactive chat mode
    if not args.image:
        print("No images provided. Enter interactive mode.")
        print("Type 'quit' to exit. Provide image paths with --image flag for vision input.\n")

    while True:
        try:
            if not args.image:
                prompt = input("Prompt: ").strip()
                if prompt.lower() in ("quit", "exit", "q"):
                    break
                images = []
            else:
                prompt = args.prompt
                images = args.image

            if not images and not prompt:
                continue

            start = time.time()
            response = chat(llm, prompt, images, sampling_params)
            elapsed = time.time() - start

            print(f"\n{response}")
            print(f"\n[Latency: {elapsed:.2f}s]")

            if args.image:
                break  # single-shot for CLI image mode

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"\nError: {e}")

    print("Done.")


if __name__ == "__main__":
    main()
