# AiJobPortal (Avyukt)

Vite/React frontend + AWS Lambda/API Gateway backend + Cognito auth.
Job harvesting runs on EC2 (`/home/ubuntu/blackhole`, JobSniper/Blackhole).

## Layout

```
frontend/                 React app (Vercel)
  public/avyukt-logo.png
  src/pages/              routes (Home, auth, jobs, match, …)
  src/services/           apiClient + authService
backend/
  lambdas/
    auth/                 Cognito triggers
    verification/         ID upload + face match
    jobs/list_jobs.py     listings + on-demand harvest via SSM
    match/                match session / domain test / resume
    applications.py       apply records
    saved_jobs.py         saved listings
    profile.py            LinkedIn/GitHub profile
    common/               shared helpers (optional)
    tests/                pytest
```

## Local frontend

```bash
cd frontend && npm install && npm run dev
```

Requires `frontend/.env` with `VITE_API_URL`, Cognito pool/client IDs.
