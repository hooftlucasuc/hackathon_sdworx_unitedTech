# Firestore-indexen

`infra/gcp_setup.sh` maakt ze aan. Hier staan ze om met de hand opnieuw te draaien.
Status: `gcloud firestore indexes composite list`.

## Vector-index op `solutions` (vector search van rol B)

Geen prefilter: een andere category wordt niet uitgesloten (TEAMPLAN §1.5).
De dimensie moet gelijk zijn aan `EMBEDDING_DIM` (768 voor `gemini-embedding-001` met `output_dimensionality=768`).

```bash
gcloud firestore indexes composite create --collection-group=solutions --query-scope=COLLECTION \
  --field-config=vector-config='{"dimension":"768","flat":"{}"}',field-path=problem_embedding
```

Query aan de kant van B: `find_nearest(vector_field="problem_embedding", distance_measure=COSINE, limit=20)`,
daarna herrangschikken op de totaalscore en de top 5 bewaren.

## Historie-queries van het dashboard (rol C)

`calls where caller_id == X orderBy started_at desc`:

```bash
gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=caller_id \
  --field-config=order=DESCENDING,field-path=started_at
```

`calls where company_id == X orderBy started_at desc`:

```bash
gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=company_id \
  --field-config=order=DESCENDING,field-path=started_at
```

`calls orderBy started_at desc limit 1` (live-scherm) gebruikt de automatische single-field index.
