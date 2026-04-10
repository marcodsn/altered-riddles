import json
import os
import shutil
from collections import defaultdict


def main():
    # The project root is where this script is likely called from,
    # but we'll use a path relative to the project root.
    output_root = "data/model_outputs"

    if not os.path.exists(output_root):
        print(f"Error: Directory {output_root} not found.")
        return

    model_files = defaultdict(list)

    print("Scanning for model output files...")
    # Find all .jsonl files and group them by the 'model' field inside the file
    for root, _, files in os.walk(output_root):
        for file in files:
            if file.endswith(".jsonl") and not file.endswith(".bak"):
                path = os.path.join(root, file)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        first_line = f.readline()
                        if first_line:
                            data = json.loads(first_line)
                            model_name = data.get("model", "unknown")
                            model_files[model_name].append(path)
                except Exception as e:
                    print(f"Error reading {path}: {e}")

    if not model_files:
        print("No .jsonl files found to update.")
        return

    print(f"Found {len(model_files)} unique models.")

    # For each unique model, ask the user for provider and quantization
    model_info = {}
    for model in sorted(model_files.keys()):
        print(f"\n--- Model: {model} ---")
        provider = input("Enter provider (e.g., 'together', 'local', 'hf'): ").strip()
        quantization = input("Enter quantization type (leave empty if none): ").strip()
        model_info[model] = {"provider": provider, "quantization": quantization}

    # Process files
    print("\nUpdating files...")
    for model, paths in model_files.items():
        info = model_info[model]
        for path in paths:
            # 1. Backup the file
            bak_path = path + ".bak"
            try:
                shutil.copy2(path, bak_path)
            except Exception as e:
                print(f"Failed to backup {path}: {e}")
                continue

            # 2. Read and update the content
            updated_lines = []
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            data["provider"] = info["provider"]
                            data["quantization"] = info["quantization"]
                            updated_lines.append(json.dumps(data))
                        except json.JSONDecodeError as e:
                            print(f"Skipping malformed line in {path}: {e}")

                # Write back to the file
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(updated_lines) + "\n")
                print(f"Successfully updated: {path}")
            except Exception as e:
                print(f"Error updating {path}: {e}")

    print("\nFinished updating model outputs.")


if __name__ == "__main__":
    main()
