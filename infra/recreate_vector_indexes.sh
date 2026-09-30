#!/usr/bin/env bash
# Recreate the Firestore vector indexes on problem_embedding at a new dimension.
# Needed when you switch embedding model (e.g. Vertex 768 -> local sentence-transformers 384):
# a vector index is tied to one dimension, and a create on the same field is refused while the old one exists.
# The caller_id/company_id composite indexes are not vector indexes and are left untouched.
#
# Usage (Cloud Shell):
#   GCP_PROJECT=my-project EMBEDDING_DIM=384 ./infra/recreate_vector_indexes.sh
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
: "${EMBEDDING_DIM:?set EMBEDDING_DIM (384 for the local model, 768 for Vertex)}"
VCFG="{\"dimension\":\"${EMBEDDING_DIM}\",\"flat\":\"{}\"}"

echo "==> Deleting existing vector indexes on problem_embedding"
gcloud firestore indexes composite list --project="$GCP_PROJECT" --format=json \
  | jq -r '.[] | select(any(.fields[]?; .vectorConfig != null)) | .name' \
  | while read -r name; do
      id="${name##*/}"
      echo "    delete $id"
      gcloud firestore indexes composite delete "$id" --project="$GCP_PROJECT" --quiet || true
    done

echo "==> Creating vector indexes at ${EMBEDDING_DIM} dims (build takes a few minutes)"
for cg in solutions calls; do
  gcloud firestore indexes composite create --project="$GCP_PROJECT" \
    --collection-group="$cg" --query-scope=COLLECTION \
    --field-config=field-path=problem_embedding,vector-config="$VCFG" --async \
    || echo "    ($cg: already exists, or see the error above)"
done

echo "==> Done. Status: gcloud firestore indexes composite list --format='table(name.basename(), state)'"
