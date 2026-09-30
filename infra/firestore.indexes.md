# Firestore indexes (CallSight)

`infra/gcp_setup.sh` creates all of these. Listed here to re-run by hand. Dimension must equal
`EMBEDDING_DIM` (768 for `gemini-embedding-001` with `output_dimensionality=768`).

## Vector index on `solutions` (required: the backend's solution search)

```bash
gcloud firestore indexes composite create --collection-group=solutions --query-scope=COLLECTION \
  --field-config=field-path=problem_embedding,vector-config='{"dimension":"768","flat":"{}"}'
```

Without it, calls are still stored but `suggestions_status` is `search_error`. After the index is
ready, recompute an affected call with `python -m app.cli rescore <call_id>`.

## Vector index on `calls` (reserved for "similar past calls")

```bash
gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
  --field-config=field-path=problem_embedding,vector-config='{"dimension":"768","flat":"{}"}'
```

## Composite indexes on `calls` (for the dashboard's realtime queries)

The backend API sorts history in Python and does not need these. The dashboard's
`where('caller_id','==',x).orderBy('started_at','desc')` with `onSnapshot` does.

```bash
for f in caller_id company_id; do
  gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
    --field-config=order=ASCENDING,field-path=$f \
    --field-config=order=DESCENDING,field-path=started_at
done
```

`orderBy('started_at','desc').limit(1)` on `calls` (the live screen) uses the automatic single-field index.

Check status: `gcloud firestore indexes composite list`.
