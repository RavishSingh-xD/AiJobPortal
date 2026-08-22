"""
Backend Lambda package root.

Makes `backend/` importable as `lambdas.*` for local pytest and scripts.
Individual handlers live in subpackages (auth, jobs, match, verification)
or as top-level modules (applications, profile, saved_jobs).
"""
