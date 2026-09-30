#!/usr/bin/env bash
# One-time Google Cloud setup for CallSight. Everything in europe-west1. Idempotent: safe to re-run.
# Run in Cloud Shell (gcloud is preinstalled) from the repo root:
#   GCP_PROJECT=my-project ELEVENLABS_WEBHOOK_SECRET=wsec_... ./infra/gcp_setup.sh
# ELEVENLABS_WEBHOOK_SECRET is optional here; add it later with the command printed at the end.
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
REGION=europe-west1
AR_REPO=callsight
RUNTIME_SA=callsight-backend
DEPLOY_SA=callsight-deployer
SECRET=elevenlabs-webhook-secret
EMBEDDING_DIM="${EMBEDDING_DIM:-768}"
RUNTIME="${RUNTIME_SA}@${GCP_PROJECT}.iam.gserviceaccount.com"
DEPLOYER="${DEPLOY_SA}@${GCP_PROJECT}.iam.gserviceaccount.com"

say() { printf '\n==> %s\n' "$*"; }

gcloud config set project "$GCP_PROJECT" >/dev/null

say "Enabling APIs"
gcloud services enable \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  iam.googleapis.com

say "Firestore (Native mode) in $REGION"
gcloud firestore databases create --location="$REGION" --type=firestore-native 2>/dev/null \
  || echo "   database already exists"

say "Artifact Registry repo $AR_REPO"
gcloud artifacts repositories create "$AR_REPO" --repository-format=docker --location="$REGION" \
  --description="CallSight images" 2>/dev/null || echo "   repo already exists"

say "Service accounts"
gcloud iam service-accounts create "$RUNTIME_SA" --display-name="CallSight backend (Cloud Run runtime)" 2>/dev/null \
  || echo "   $RUNTIME_SA exists"
gcloud iam service-accounts create "$DEPLOY_SA" --display-name="CallSight deployer (Cloud Build)" 2>/dev/null \
  || echo "   $DEPLOY_SA exists"
sleep 5  # IAM propagation

# runtime: read/write Firestore, call Vertex embeddings
for role in roles/datastore.user roles/aiplatform.user; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$RUNTIME" \
    --role="$role" --condition=None --quiet >/dev/null
done
# deployer: push images, deploy Cloud Run, write build logs, act as the runtime SA
for role in roles/run.admin roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT" --member="serviceAccount:$DEPLOYER" \
    --role="$role" --condition=None --quiet >/dev/null
done
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME" \
  --member="serviceAccount:$DEPLOYER" --role=roles/iam.serviceAccountUser --quiet >/dev/null

say "Secret $SECRET"
if ! gcloud secrets describe "$SECRET" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET" --replication-policy=user-managed --locations="$REGION"
  # placeholder keeps the webhook closed (every signature fails) until the real secret is added
  printf '%s' "${ELEVENLABS_WEBHOOK_SECRET:-not-configured-yet}" | gcloud secrets versions add "$SECRET" --data-file=-
elif [ -n "${ELEVENLABS_WEBHOOK_SECRET:-}" ]; then
  printf '%s' "$ELEVENLABS_WEBHOOK_SECRET" | gcloud secrets versions add "$SECRET" --data-file=-
fi
gcloud secrets add-iam-policy-binding "$SECRET" --member="serviceAccount:$RUNTIME" \
  --role=roles/secretmanager.secretAccessor --quiet >/dev/null

say "Firestore indexes (vector indexes take a few minutes to build)"
VECTOR_CONFIG="{\"dimension\":\"${EMBEDDING_DIM}\",\"flat\":\"{}\"}"
gcloud firestore indexes composite create --collection-group=solutions --query-scope=COLLECTION \
  --field-config=field-path=problem_embedding,vector-config="$VECTOR_CONFIG" --async \
  || echo "   (solutions vector index: already exists, or see the error above)"
gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
  --field-config=field-path=problem_embedding,vector-config="$VECTOR_CONFIG" --async \
  || echo "   (calls vector index: already exists, or see the error above)"
# for the dashboard's realtime history queries (where caller_id/company_id == x orderBy started_at desc)
for f in caller_id company_id; do
  gcloud firestore indexes composite create --collection-group=calls --query-scope=COLLECTION \
    --field-config=order=ASCENDING,field-path="$f" \
    --field-config=order=DESCENDING,field-path=started_at --async \
    || echo "   (calls($f, started_at) index: already exists, or see the error above)"
done

say "Done"
cat <<EOF
Next:
  1. Connect GitHub and create the trigger: docs/backend.md, step 3.
  2. Add the real ElevenLabs webhook secret when A has it:
       printf '%s' 'wsec_...' | gcloud secrets versions add $SECRET --data-file=-
     then re-run the trigger so a new revision picks it up.
  3. Index status: gcloud firestore indexes composite list
EOF
