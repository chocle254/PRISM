/**
 * PRISM - Google Cloud Infrastructure
 * Terraform configuration for Cloud Run, Firestore, Storage, and Pub/Sub
 */

terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  required_version = ">= 1.5.0"
}

variable "project_id" {
  description = "GCP Project ID"
  type        = string
}

variable "region" {
  description = "GCP Region"
  type        = string
  default     = "us-central1"
}

variable "gemini_api_key" {
  description = "Google Gemini API Key"
  type        = string
  sensitive   = true
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# ── Enable Required APIs ──────────────────────────────────────────────────────
resource "google_project_service" "services" {
  for_each = toset([
    "run.googleapis.com",
    "firestore.googleapis.com",
    "storage.googleapis.com",
    "pubsub.googleapis.com",
    "aiplatform.googleapis.com",
    "cloudbuild.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
  ])
  service            = each.value
  disable_on_destroy = false
}

# ── Artifact Registry ─────────────────────────────────────────────────────────
resource "google_artifact_registry_repository" "prism_repo" {
  location      = var.region
  repository_id = "prism"
  format        = "DOCKER"
  description   = "PRISM Docker images"
  depends_on    = [google_project_service.services]
}

# ── Secret Manager: Gemini API Key ────────────────────────────────────────────
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = "gemini-api-key"
  replication { auto {} }
  depends_on = [google_project_service.services]
}

resource "google_secret_manager_secret_version" "gemini_api_key_version" {
  secret      = google_secret_manager_secret.gemini_api_key.id
  secret_data = var.gemini_api_key
}

# ── Service Account for PRISM ─────────────────────────────────────────────────
resource "google_service_account" "prism_sa" {
  account_id   = "prism-service-account"
  display_name = "PRISM Service Account"
}

resource "google_project_iam_member" "prism_sa_roles" {
  for_each = toset([
    "roles/datastore.user",
    "roles/storage.objectAdmin",
    "roles/pubsub.publisher",
    "roles/pubsub.subscriber",
    "roles/aiplatform.user",
    "roles/secretmanager.secretAccessor",
    "roles/run.invoker",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.prism_sa.email}"
}

# ── Cloud Storage: Generated Assets ──────────────────────────────────────────
resource "google_storage_bucket" "prism_assets" {
  name          = "${var.project_id}-prism-assets"
  location      = var.region
  force_destroy = false

  uniform_bucket_level_access = true

  lifecycle_rule {
    condition { age = 7 }
    action { type = "Delete" }
  }

  cors {
    origin          = ["*"]
    method          = ["GET", "HEAD"]
    response_header = ["*"]
    max_age_seconds = 3600
  }
}

# ── Firestore Database ────────────────────────────────────────────────────────
resource "google_firestore_database" "prism_db" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"
  depends_on  = [google_project_service.services]
}

# ── Pub/Sub: Agent Messaging ──────────────────────────────────────────────────
resource "google_pubsub_topic" "prism_events" {
  name = "prism-agent-events"
  message_retention_duration = "600s"
}

resource "google_pubsub_subscription" "prism_events_sub" {
  name  = "prism-agent-events-sub"
  topic = google_pubsub_topic.prism_events.name
  ack_deadline_seconds = 20
  retain_acked_messages = false
}

# ── Cloud Run: PRISM Backend ──────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "prism_backend" {
  name     = "prism-backend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    service_account = google_service_account.prism_sa.email

    scaling {
      min_instance_count = 0
      max_instance_count = 10
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/prism/backend:latest"

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
        startup_cpu_boost = true
      }

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_REGION"
        value = var.region
      }
      env {
        name  = "USE_FIRESTORE"
        value = "true"
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.prism_assets.name
      }
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      ports {
        container_port = 8080
      }

      startup_probe {
        http_get { path = "/health" }
        initial_delay_seconds = 5
        period_seconds        = 10
        failure_threshold     = 3
      }

      liveness_probe {
        http_get { path = "/health" }
        period_seconds    = 30
        failure_threshold = 3
      }
    }
  }

  depends_on = [
    google_project_service.services,
    google_secret_manager_secret_version.gemini_api_key_version,
  ]
}

# ── Allow Public Access to Cloud Run ─────────────────────────────────────────
resource "google_cloud_run_v2_service_iam_member" "public_access" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.prism_backend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Cloud Run: PRISM Frontend ─────────────────────────────────────────────────
resource "google_cloud_run_v2_service" "prism_frontend" {
  name     = "prism-frontend"
  location = var.region
  ingress  = "INGRESS_TRAFFIC_ALL"

  template {
    scaling {
      min_instance_count = 0
      max_instance_count = 5
    }

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/prism/frontend:latest"

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "REACT_APP_BACKEND_URL"
        value = google_cloud_run_v2_service.prism_backend.uri
      }
      env {
        name  = "REACT_APP_WS_URL"
        value = replace(google_cloud_run_v2_service.prism_backend.uri, "https://", "wss://")
      }

      ports { container_port = 3000 }
    }
  }

  depends_on = [google_cloud_run_v2_service.prism_backend]
}

resource "google_cloud_run_v2_service_iam_member" "frontend_public" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.prism_frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "backend_url" {
  value       = google_cloud_run_v2_service.prism_backend.uri
  description = "PRISM Backend URL"
}

output "frontend_url" {
  value       = google_cloud_run_v2_service.prism_frontend.uri
  description = "PRISM Frontend URL"
}

output "storage_bucket" {
  value = google_storage_bucket.prism_assets.name
}
