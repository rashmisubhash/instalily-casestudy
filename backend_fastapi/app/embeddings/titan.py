import boto3
import json
from app.core import config

class TitanEmbedder:
    def __init__(self):
        self.client = boto3.client(
            "bedrock-runtime",
            region_name=config.AWS_REGION
        )
        self.model_id = "amazon.titan-embed-text-v1"

    def embed(self, text: str):
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps({"inputText": text}),
            contentType="application/json",
            accept="application/json"
        )

        result = json.loads(response["body"].read())
        return result["embedding"]
