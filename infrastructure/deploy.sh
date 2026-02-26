#!/bin/bash
# ╔══════════════════════════════════════════════════════════════════════════╗
# ║  PRISM - GCP Deployment Script                                          ║
# ║  Builds and deploys backend + frontend to Cloud Run                     ║
# ╚══════════════════════════════════════════════════════════════════════════╝

set -euo pipefail

# ── Config (edit these) ────────────────────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-your-gcp-project-id}"
REGION="${GCP_REGION:-us-central1}"
GEMINI_API_KEY="${GEMINI_API_KEY:-your-gemini-api-key}"

REPO="$REGION-docker.pkg.dev/$PROJECT_ID/prism"
BACKEND_IMAGE="$REPO/backend:latest"
FRONTEND_IMAGE="$REPO/frontend:latest"

echo "═══════════════════════════════════════════════"
echo "  🌈 PRISM Deployment"
echo "  Project: $PROJECT_ID"
echo "  Region:  $REGION"
echo "═══════════════════════════════════════════════"

# ── Prerequisites Check ─────────────────────────────────────────────────────────
check_tool() {
  if ! command -v "$1" &>/dev/null; then
    echo "❌ Required tool not found: $1"
    exit 1
  fi
}

check_tool gcloud
check_tool docker
check_tool terraform

echo "✅ Prerequisites OK"

# ── GCP Auth + Config ──────────────────────────────────────────────────────────
gcloud config set project "$PROJECT_ID"
gcloud config set run/region "$REGION"
gcloud auth configure-docker "$REGION-docker.pkg.dev" --quiet

echo "✅ GCP configured"

# ── Enable APIs ────────────────────────────────────────────────────────────────
echo "🔧 Enabling GCP APIs..."
gcloud services enable \
  run.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  aiplatform.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  --quiet

echo "✅ APIs enabled"

# ── Artifact Registry ──────────────────────────────────────────────────────────
echo "🏗️  Creating Artifact Registry..."
gcloud artifacts repositories create prism \
  --repository-format=docker \
  --location="$REGION" \
  --quiet 2>/dev/null || echo "  (already exists)"

# ── Build and Push Backend ─────────────────────────────────────────────────────
echo ""
echo "🐳 Building backend..."
docker build -t "$BACKEND_IMAGE" ./backend
docker push "$BACKEND_IMAGE"
echo "✅ Backend image pushed"

# ── Build and Push Frontend ────────────────────────────────────────────────────
echo ""
echo "🎨 Building frontend..."

# Get backend URL first (may already be deployed)
BACKEND_URL=$(gcloud run services describe prism-backend \
  --region="$REGION" \
  --format="value(status.url)" 2>/dev/null || echo "")

if [ -n "$BACKEND_URL" ]; then
  WS_URL=$(echo "$BACKEND_URL" | sed 's/https:/wss:/')
  export REACT_APP_BACKEND_URL="$BACKEND_URL"
  export REACT_APP_WS_URL="$WS_URL"
fi

cat > ./frontend/Dockerfile << 'DOCKERFILE'
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --quiet
COPY . .
ARG REACT_APP_BACKEND_URL
ARG REACT_APP_WS_URL
ENV REACT_APP_BACKEND_URL=$REACT_APP_BACKEND_URL
ENV REACT_APP_WS_URL=$REACT_APP_WS_URL
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]
DOCKERFILE

cat > ./frontend/nginx.conf << 'NGINX'
server {
    listen 3000;
    root /usr/share/nginx/html;
    index index.html;
    location / {
        try_files $uri $uri/ /index.html;
    }
    location /health { return 200 "ok"; add_header Content-Type text/plain; }
}
NGINX

docker build \
  --build-arg REACT_APP_BACKEND_URL="$BACKEND_URL" \
  --build-arg REACT_APP_WS_URL="${BACKEND_URL/https:/wss:}" \
  -t "$FRONTEND_IMAGE" \
  ./frontend

docker push "$FRONTEND_IMAGE"
echo "✅ Frontend image pushed"

# ── Store Gemini API Key in Secret Manager ─────────────────────────────────────
echo ""
echo "🔐 Storing API key..."
echo -n "$GEMINI_API_KEY" | gcloud secrets create gemini-api-key \
  --data-file=- \
  --quiet 2>/dev/null || \
  echo -n "$GEMINI_API_KEY" | gcloud secrets versions add gemini-api-key \
    --data-file=- --quiet

echo "✅ API key stored"

# ── Deploy Backend to Cloud Run ────────────────────────────────────────────────
echo ""
echo "🚀 Deploying backend to Cloud Run..."

gcloud run deploy prism-backend \
  --image="$BACKEND_IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=2Gi \
  --cpu=2 \
  --concurrency=100 \
  --min-instances=0 \
  --max-instances=10 \
  --set-env-vars="GCP_PROJECT_ID=$PROJECT_ID,GCP_REGION=$REGION,USE_FIRESTORE=true" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest" \
  --port=8080 \
  --quiet

BACKEND_URL=$(gcloud run services describe prism-backend \
  --region="$REGION" \
  --format="value(status.url)")

echo "✅ Backend deployed: $BACKEND_URL"

# ── Deploy Frontend to Cloud Run ───────────────────────────────────────────────
echo ""
echo "🎨 Deploying frontend to Cloud Run..."

gcloud run deploy prism-frontend \
  --image="$FRONTEND_IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --allow-unauthenticated \
  --memory=512Mi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=5 \
  --set-env-vars="REACT_APP_BACKEND_URL=$BACKEND_URL,REACT_APP_WS_URL=${BACKEND_URL/https:/wss:}" \
  --port=3000 \
  --quiet

FRONTEND_URL=$(gcloud run services describe prism-frontend \
  --region="$REGION" \
  --format="value(status.url)")

echo "✅ Frontend deployed: $FRONTEND_URL"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "════════════════════════════════════════════════"
echo "  ✨ PRISM Deployment Complete!"
echo ""
echo "  🌐 Frontend:  $FRONTEND_URL"
echo "  ⚙️  Backend:   $BACKEND_URL"
echo "  📊 Health:    $BACKEND_URL/health"
echo "  📖 API Docs:  $BACKEND_URL/docs"
echo ""
echo "  ☁️  GCP Console:"
echo "  https://console.cloud.google.com/run?project=$PROJECT_ID"
echo "════════════════════════════════════════════════"
