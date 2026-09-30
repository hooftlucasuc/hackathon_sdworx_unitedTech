#!/usr/bin/env bash
# Firebase voor het dashboard (rol D): project koppelen, web-app registreren, Firestore rules uitrollen.
# Draai dit ná infra/gcp_setup.sh (rol B). Idempotent: veilig om opnieuw te draaien.
#
#   gcloud auth login && firebase login
#   GCP_PROJECT=<project-id> ./infra/firebase_setup.sh
#
# Schrijft niets naar de repo. De web-config (VITE_FIREBASE_*) wordt getoond; C zet die in frontend/.env.local.
set -euo pipefail
: "${GCP_PROJECT:?set GCP_PROJECT}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_NAME=callsight-dashboard

say() { printf '\n==> %s\n' "$*"; }
command -v firebase >/dev/null || { echo "firebase CLI ontbreekt: npm install -g firebase-tools"; exit 1; }

say "API's"
gcloud services enable firebase.googleapis.com identitytoolkit.googleapis.com firebaserules.googleapis.com \
  firebasehosting.googleapis.com --project "$GCP_PROJECT"

say "Firebase koppelen aan $GCP_PROJECT"
if firebase projects:list 2>/dev/null | grep -q "$GCP_PROJECT"; then
  echo "   al gekoppeld"
else
  firebase projects:addfirebase "$GCP_PROJECT"
fi

say "Web-app $APP_NAME"
if ! firebase apps:list WEB --project "$GCP_PROJECT" 2>/dev/null | grep -q "$APP_NAME"; then
  firebase apps:create WEB "$APP_NAME" --project "$GCP_PROJECT"
fi
APP_ID="$(firebase apps:list WEB --project "$GCP_PROJECT" | grep "$APP_NAME" | grep -oE '1:[0-9]+:web:[a-z0-9]+' | head -1)"
CONFIG="$(firebase apps:sdkconfig WEB "$APP_ID" --project "$GCP_PROJECT")"
echo "   Voor frontend/.env.local (niet committen; staat in .gitignore):"
for pair in apiKey:API_KEY authDomain:AUTH_DOMAIN projectId:PROJECT_ID appId:APP_ID; do
  key="${pair%%:*}"; var="${pair##*:}"
  value="$(printf '%s' "$CONFIG" | grep -oE "\"?${key}\"?: *\"[^\"]+\"" | head -1 | sed -E 's/.*: *"([^"]+)"/\1/')"
  echo "   VITE_FIREBASE_${var}=${value}"
done

say "Firestore security rules (infra/firestore.rules)"
firebase deploy --only firestore:rules --project "$GCP_PROJECT" --config "$ROOT/firebase.json"

say "Klaar"
cat <<EOF
Nog met de hand, eenmalig:
  1. Google-login aanzetten: https://console.firebase.google.com/project/${GCP_PROJECT}/authentication/providers
     (Add new provider > Google > Enable). Anonieme login blijft uit: de rules laten die toch niet toe.
  2. Elk teamlid logt één keer in op het dashboard, daarna geef je toegang:
       python scripts/grant_access.py grant <e-mail> [<e-mail> ...]
     De persoon logt daarna opnieuw in, zodat de claim in het token zit.
  3. Dashboard publiceren (na C's build):
       cd frontend && npm run build && cd .. && firebase deploy --only hosting --project ${GCP_PROJECT} --config firebase.json
     en zet https://${GCP_PROJECT}.web.app in de trigger-substitutie _FRONTEND_ORIGIN van de backend (docs/backend.md).
EOF
