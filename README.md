# Stripe RAG Demo

This repository contains a Retrieval-Augmented Generation (RAG) proof of concept built on Google Cloud Functions. It ingests sections of Stripe documentation, stores the embeddings in a vector store, and serves a question-answering endpoint that generates context-aware answers with the help of a large language model (LLM).

---

## Architecture

1. **Embedding ingestion (`functions/embed-texts`)**
   - Fetches or receives plaintext Stripe docs.
   - Splits documents into chunks.
   - Generates embeddings for each chunk.
   - Persists embeddings and associated metadata in the configured vector store.

2. **RAG inference (`rag_poc_function`)**
   - Accepts a natural-language question.
  - Converts the question into an embedding.
  - Retrieves the most relevant document chunks.
  - Builds a prompt that combines the retrieved context with the user query.
  - Calls the LLM to produce a grounded answer.

Both Cloud Functions are designed for stateless execution and rely on environment configuration to connect to external services (LLMs, vector databases, storage buckets, etc.).

---

## Repository Structure

<pre>
.
├── .gitignore
├── env.sample.yaml
├── functions
│   └── embed-texts
│       ├── main.py
│       └── requirements.txt
└── rag_poc_function
    ├── .gcloudignore
    ├── main.py
    ├── requirements.txt
    ├── utils.py
    └── vectorstore.py
</pre>

- `env.sample.yaml`: Template for environment variables required by the Cloud Functions.
- `functions/embed-texts`: Cloud Function code for embedding ingestion.
- `rag_poc_function`: Cloud Function code for query-time retrieval and response generation.

---

## Prerequisites

- Python 3.10+
- Google Cloud SDK (`gcloud`) authenticated and configured with the correct project.
- Access credentials for the chosen LLM provider (e.g., OpenAI, Vertex AI) and vector store (e.g., Pinecone, Vertex Matching Engine, Weaviate).

---

## Environment Configuration

1. Copy the sample environment file and fill in real values:

   ```bash
   cp env.sample.yaml env.yaml

2. Populate env.yaml with the secrets specific to your deployment (API keys, project IDs, region, vector store identifiers, etc.). Do not commit env.yaml or any file containing real secrets.

3. If you prefer .env files for local testing, keep them out of version control (already covered by .gitignore).

## Local Development

1. Install dependencies for the function you want to test:

   ```bash
   cd rag_poc_function
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Export required environment variables (match the keys in env.sample.yaml).

3. Run unit or integration tests (add your own test suite as needed).

## Deployment (Google Cloud Functions)

**Deploy the embedding function**

    gcloud functions deploy embed-texts \
      --runtime python310 \
      --region YOUR_REGION \
      --entry-point main \
      --trigger-http \
      --allow-unauthenticated \
      --env-vars-file env.yaml \
      --source functions/embed-texts  

**Deploy the RAG function**
   
    gcloud functions deploy rag-poc-function \
      --runtime python310 \
      --region YOUR_REGION \
      --entry-point main \
      --trigger-http \
      --allow-unauthenticated \
      --env-vars-file env.yaml \
      --source rag_poc_function

Adjust flags (authentication, VPC connector, memory, timeout, etc.) to fit your security and performance requirements.

## Usage Workflow

**Embed documents**

Trigger embed-texts with the document payload or ingestion request. This populates the vector store.

**Ask questions**

Send an HTTP request to rag-poc-function with a JSON body such as:
    
    {
      "question": "How do I create a Stripe checkout session?"
    }

The response includes the model’s answer plus any additional metadata you decide to return (e.g., retrieved chunk references).

## Operational Notes

- Secret management: Prefer Google Secret Manager or environment variables set at deploy time. Rotate keys if they were ever exposed.

- Logging & monitoring: Use Cloud Logging to inspect function output and errors. Set up alerts if needed.

- Vector store cleanup: Implement lifecycle policies or maintenance scripts to remove outdated embeddings.

## Roadmap Ideas

- Add automated tests and CI/CD pipelines (GitHub Actions + Cloud Build).

- Introduce caching for repeated queries.

- Support multiple document sources and incremental updates.

- Integrate authentication for the HTTP endpoints.

- Provide a simple frontend or CLI client for demonstration purposes.

## Contributing

1. Fork the repository.

2. Create a feature branch (git checkout -b feature/my-feature).

3. Commit your changes with clear messages.

4. Push the branch and open a pull request.

For questions or suggestions, open an issue or reach out to the maintainers. Happy building!
   
