#!/bin/bash
# Test the /generate-manifest endpoint locally

curl -X POST http://localhost:8080/generate-manifest \
  -H "Content-Type: application/json" \
  -d '{
    "job_id": "test-job-123",
    "pdf_url": "https://www.w3.org/WAI/WCAG21/Techniques/pdf/img/table-word.jpg"
  }'