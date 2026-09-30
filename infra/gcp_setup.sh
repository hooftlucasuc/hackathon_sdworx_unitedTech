#!/usr/bin/env bash
# One-time Google Cloud setup for TrustCard. Everything in europe-west1.
# Usage: GCP_PROJECT=my-project ./infra/gcp_setup.sh
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
REGION=europe-west1
EMBEDDING_DIM="${EMBEDDING_DIM:-768}"

gcloud config set project "$GCP_PROJECT"
gcloud services enable \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  secretmanager.googleapis.com

gcloud firestore databases create --location="$REGION" --type=firestore-native || true
gcloud storage buckets create "gs://${GCP_PROJECT}-trustcard-raw" \
  --location="$REGION" --uniform-bucket-level-access || true

gcloud iam service-accounts create trustcard-backend --display-name="TrustCard backend" || true
SA="trustcard-backend@${GCP_PROJECT}.iam.gserviceaccount.com"
for role in roles/datastore.user roles/storage.objectAdmin roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" \
    --member="serviceAccount:$SA" --role="$role" --quiet
done

# Local dev key. Gitignored. Delete after the hackathon:
#   gcloud iam service-accounts keys delete <KEY_ID> --iam-account="$SA"
if [ ! -f ./sa-key.json ]; then
  gcloud iam service-accounts keys create ./sa-key.json --iam-account="$SA"
fi

# Vector index on chunks (see infra/firestore.indexes.md). Takes a few minutes to build.
gcloud firestore indexes composite create \
  --project="$GCP_PROJECT" \
  --collection-group=chunks \
  --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=country \
  --field-config=order=ASCENDING,field-path=status \
  --field-config=vector-config="{\"dimension\":\"${EMBEDDING_DIM}\",\"flat\":\"{}\"}",field-path=embedding \
  || true

# Composite indexes for the question queries used by the API.
gcloud firestore indexes composite create --project="$GCP_PROJECT" \
  --collection-group=questions --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=asked_by \
  --field-config=order=DESCENDING,field-path=created_at || true
gcloud firestore indexes composite create --project="$GCP_PROJECT" \
  --collection-group=questions --query-scope=COLLECTION \
  --field-config=order=ASCENDING,field-path=assigned_expert_id \
  --field-config=order=ASCENDING,field-path=status \
  --field-config=order=DESCENDING,field-path=created_at || true

echo "Done. Now: cp .env.example .env and fill GCP_PROJECT=$GCP_PROJECT"
