from __future__ import annotations

import os
from typing import List, Dict, Any

import weaviate
from google.oauth2 import service_account
from dotenv import load_dotenv
from vertexai import init as vertexai_init
from vertexai.preview.language_models import TextEmbeddingModel  

from utils import get_env

load_dotenv()

_VERTEX_CLIENT_INITIALIZED = False


def init_vertex_client() -> None:
    global _VERTEX_CLIENT_INITIALIZED
    if _VERTEX_CLIENT_INITIALIZED:
        return

    project_id = get_env("VERTEX_PROJECT_ID")
    location = get_env("VERTEX_LOCATION")
    credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

    if credentials_path and os.path.exists(credentials_path):
        creds = service_account.Credentials.from_service_account_file(credentials_path)
        vertexai_init(project=project_id, location=location, credentials=creds)
    else:
        vertexai_init(project=project_id, location=location)

    _VERTEX_CLIENT_INITIALIZED = True


def build_embeddings(texts: List[str]) -> List[List[float]]:
    init_vertex_client()
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    embeddings = model.get_embeddings(texts)
    return [record.values for record in embeddings]


def init_weaviate_client() -> weaviate.Client:
    endpoint = get_env("WEAVIATE_ENDPOINT")
    api_key = get_env("WEAVIATE_API_KEY")
    return weaviate.Client(
        url=endpoint,
        auth_client_secret=weaviate.AuthApiKey(api_key=api_key),
        additional_headers={"X-OpenAI-Api-Key": api_key},
    )


def ensure_schema(client: weaviate.Client) -> None:
    class_name = "StripeDocPage"
    if client.schema.exists(class_name):
        return

    schema = {
        "class": class_name,
        "description": "Stripe billing documentation chunks",
        "vectorizer": "none",
        "properties": [
            {"name": "title", "dataType": ["text"]},
            {"name": "url", "dataType": ["text"]},
            {"name": "content", "dataType": ["text"]},
            {"name": "section", "dataType": ["text"]},
            {"name": "chunk_index", "dataType": ["int"]},
        ],
    }
    client.schema.create_class(schema)


def upsert_documents(documents: List[Dict[str, Any]]) -> None:
    if not documents:
        return

    client = init_weaviate_client()
    ensure_schema(client)

    contents = [doc["content"] for doc in documents]
    embeddings = build_embeddings(contents)

    batch_size = 20
    with client.batch.configure(batch_size=batch_size, dynamic=True):
        for doc, vector in zip(documents, embeddings):
            client.batch.add_data_object(
                data_object={
                    "title": doc["title"],
                    "url": doc["url"],
                    "content": doc["content"],
                    "section": doc["section"],
                    "chunk_index": doc["chunk_index"],
                },
                class_name="StripeDocPage",
                uuid=doc["id"],
                vector=vector,
            )