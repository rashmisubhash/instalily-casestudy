import json
import re
from collections import defaultdict
from pathlib import Path

INPUT_FILE = "artifacts/scrape/data/parts.json"
OUTPUT_DIR = Path("artifacts/scrape/data")

def normalize_model_id(model: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", model.strip().upper())


def build_indexes(parts):

    part_id_map = {}
    model_id_to_parts_map = defaultdict(list)
    model_metadata = {}

    for part in parts:

        part_id = part["part_id"].upper()
        part_id_map[part_id] = part

        appliance_type = part.get("appliance_type")

        for model in part.get("compatible_models", []):
            clean_model = normalize_model_id(model)

            model_id_to_parts_map[clean_model].append(part_id)

            # Only store metadata once
            if clean_model not in model_metadata:
                model_metadata[clean_model] = {
                    "appliance_type": appliance_type
                }

    # Deduplicate part lists
    model_id_to_parts_map = {
        k: list(set(v)) for k, v in model_id_to_parts_map.items()
    }

    return part_id_map, model_id_to_parts_map, model_metadata


def run():

    with open(INPUT_FILE) as f:
        parts = json.load(f)

    part_id_map, model_map, metadata = build_indexes(parts)

    with open(OUTPUT_DIR / "part_id_map.json", "w") as f:
        json.dump(part_id_map, f, indent=2)

    with open(OUTPUT_DIR / "model_id_to_parts_map.json", "w") as f:
        json.dump(model_map, f, indent=2)

    with open(OUTPUT_DIR / "model_metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)

    print("Indexes built successfully.")


if __name__ == "__main__":
    run()
