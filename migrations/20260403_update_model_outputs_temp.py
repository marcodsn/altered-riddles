import argparse
import json
import logging
import re
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def extract_temperature(filename: str) -> float:
    """
    Extract temperature from filename.
    Example: 'model_cot_temp0.7.jsonl' -> 0.7
    Example: 'model_cot.jsonl' -> 0.0
    """
    match = re.search(r"_temp(\d+\.?\d*)", filename)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return 0.0
    return 0.0


def update_file_temperature(file_path: Path):
    """Reads a jsonl file and adds/updates the temperature field based on filename."""
    temp = extract_temperature(file_path.name)

    updated_lines = []
    changed = False

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                data = json.loads(line)
                if data.get("temperature") != temp:
                    data["temperature"] = temp
                    changed = True
                updated_lines.append(json.dumps(data, ensure_ascii=False))

        if changed:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("\n".join(updated_lines) + "\n")
            logger.info(f"Updated {file_path} with temperature {temp}")
        else:
            logger.info(f"No changes needed for {file_path}")

    except Exception as e:
        logger.error(f"Failed to process {file_path}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Update model output .jsonl files by adding temperature from filename."
    )
    parser.add_argument(
        "output_dir",
        type=str,
        help="Path to the output directory containing benchmark results",
    )

    args = parser.parse_args()
    root_dir = Path(args.output_dir)

    if not root_dir.is_dir():
        logger.error(f"Directory not found: {root_dir}")
        return

    # Find all .jsonl files recursively
    jsonl_files = list(root_dir.rglob("*.jsonl"))

    if not jsonl_files:
        logger.info("No .jsonl files found in the specified directory.")
        return

    logger.info(f"Found {len(jsonl_files)} .jsonl files. Processing...")

    for file_path in jsonl_files:
        update_file_temperature(file_path)

    logger.info("Done.")


if __name__ == "__main__":
    main()
