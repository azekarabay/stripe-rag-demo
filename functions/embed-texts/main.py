import os
from typing import Any, Dict, List

from flask import Request, jsonify

from vertexai import init as vertexai_init
from vertexai.preview.language_models import TextEmbeddingModel


vertex_client_initialized = False
embedding_model: TextEmbeddingModel | None = None


def init_vertex_client() -> None:
    global vertex_client_initialized, embedding_model

    if vertex_client_initialized:
        return

    project_id = os.environ["VERTEX_PROJECT_ID"]
    location = os.environ["VERTEX_LOCATION"]

    vertexai_init(project=project_id, location=location)
    embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")

    vertex_client_initialized = True


def embed(request: Request):
    init_vertex_client()

    token = request.headers.get("X-Internal-Token")
    expected = os.environ.get("EMBED_FUNCTION_TOKEN")
    if expected and token != expected:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        payload: Dict[str, Any] = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON payload"}), 400

    texts: List[str] | None = payload.get("texts")
    if not texts or not isinstance(texts, list):
        return jsonify({"error": "Missing 'texts' array"}), 400

    embeddings = embedding_model.get_embeddings(texts)
    vectors = [record.values for record in embeddings]

    return jsonify({"embeddings": vectors})