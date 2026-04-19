import argparse
import json

KEEP_COLUMNS = {
    "id",
    "original_riddle",
    "original_answer",
    "original_accepted_answers",
    "original_reasoning",
    "altered_riddle",
    "altered_answer",
    "altered_accepted_answers",
    "altered_competing_answers",
    "altered_reasoning",
    "type",
    "source",
}


def clean_benchmark(input_path: str, output_path: str):
    cleaned = []
    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                item = json.loads(line)
                cleaned.append({k: v for k, v in item.items() if k in KEEP_COLUMNS})

    with open(output_path, "w", encoding="utf-8") as f:
        for item in cleaned:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Cleaned {len(cleaned)} items → {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Clean the Altered Riddles benchmark.")
    parser.add_argument(
        "input",
        nargs="?",
        default="data/benchmark.jsonl",
        help="Path to the raw benchmark JSONL file",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default="hf/benchmark.jsonl",
        help="Path to write the cleaned JSONL file",
    )
    args = parser.parse_args()

    clean_benchmark(args.input, args.output)
