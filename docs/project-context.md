# Project context — AiJobPortal / Avyukt

## Product flow
1. User signs up/logs in via Cognito (email OTP).
2. Optional ID verification (S3 upload + Rekognition face match).
3. Find Roles (`listJobs`) reads domain DynamoDB tables; empty tables trigger SSM harvest on EC2.
4. Get Matched wizard: resume upload → domain MCQ → PoW/match → recommendations → apply/save.

## Domain tables
`jobs_engineering`, `jobs_business`, `jobs_healthcare`, `jobs_design`

## Harvester
- Code lives outside this repo: `~/Documents/Projects/jobsniper` (Blackhole-2), deployed to EC2 `/home/ubuntu/blackhole`.
- Portal trigger: `harvester.py -d "{Domain}" -s "{Skill}" --exclude-fallbacks`
- `listJobs` Lambda env must set `HARVESTER_INSTANCE_ID`.

## Logo
Brand asset is PNG only: `frontend/public/avyukt-logo.png` (nav, home, favicon).
