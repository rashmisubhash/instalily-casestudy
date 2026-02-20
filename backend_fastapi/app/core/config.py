import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
ARTIFACTS_DIR = os.path.join(BASE_DIR, "artifacts")
SCRIPTS_DIR = os.path.join(ARTIFACTS_DIR, "scrape/data")

PART_ID_MAP_PATH = os.path.join(SCRIPTS_DIR, "part_id_map.json")
MODEL_TO_PARTS_MAP_PATH = os.path.join(SCRIPTS_DIR, "model_to_parts_map.json")
MODEL_ID_TO_PARTS_MAP_PATH = os.path.join(SCRIPTS_DIR, "model_id_to_parts_map.json")
CHROMA_DIR = os.path.join(ARTIFACTS_DIR, "chroma_appliance_parts")

CHROMA_COLLECTION = "partselect_parts"

AWS_REGION = os.getenv("AWS_REGION", "us-east-1")
BEDROCK_MODEL_ID = os.getenv(
    "BEDROCK_MODEL_ID",
    "anthropic.claude-3-sonnet-20240229-v1:0"
)
