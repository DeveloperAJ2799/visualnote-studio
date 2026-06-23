#!/bin/bash
# Run the pipeline service locally

cd "$(dirname "$0")"

# Load env vars from .env.example template
export $(grep -v '^#' .env.example | xargs) 2>/dev/null

echo "Starting FastAPI server on http://localhost:8080"
echo "Health check: http://localhost:8080/health"
echo "POST endpoint: http://localhost:8080/generate-manifest"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8080 --reload