# Firestore indexes

All commands are run by `infra/gcp_setup.sh`. Listed here so they can be re-run by hand.

## Vector index on `chunks` (required for retrieval)

Pre-filters `country` and `status` (equality), then nearest-neighbour on `embedding`.
Dimension must equal `EMBEDDING_DIM` in `.env` (768 for `gemini-embedding-001` with
`output_dimensionality=768`; 384 for the local sentence-transformers fallback).

```bash
gcloud firestore indexes composite create \
  --project="$GCP_PROJECT" \
  --collection-group=chunks \
  --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=country \
  --field-config=order=ASCENDING,field-path=status \
  --field-config=vector-config='{"dimension":"768","flat":"{}"}',field-path=embedding
```

## Composite indexes on `questions`

`GET /questions` (own questions, newest first):

```bash
gcloud firestore indexes composite create --project="$GCP_PROJECT" \
  --collection-group=questions --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=asked_by \
  --field-config=order=DESCENDING,field-path=created_at
```

`GET /expert/inbox` (assigned to me and escalated, newest first):

```bash
gcloud firestore indexes composite create --project="$GCP_PROJECT" \
  --collection-group=questions --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=assigned_expert_id \
  --field-config=order=ASCENDING,field-path=status \
  --field-config=order=DESCENDING,field-path=created_at
```

`GET /sources` uses `country in [X, ALL]` on `knowledge_items`, which needs no composite index.

Check status: `gcloud firestore indexes composite list --project="$GCP_PROJECT"`.
