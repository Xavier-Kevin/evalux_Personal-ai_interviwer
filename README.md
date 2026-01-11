# EvaV2 - AI Interview Platform

FastAPI backend with Aiven MySQL database.

## Setup

1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment variables (see .env.example)
4. Run: `uvicorn main:app --reload`

## Deployment

Deployed on Render with Aiven MySQL database.

## Environment Variables

Required environment variables:
- DATABASE_HOST
- DATABASE_PORT
- DATABASE_USER
- DATABASE_PASSWORD
- DATABASE_NAME
- API_KEY
- SECRET_KEY