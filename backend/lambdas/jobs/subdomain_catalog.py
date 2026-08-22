"""
Sub-domain / specialty catalog for portal job browsing and harvest coordination.

Stored in DynamoDB table ``subdomain_catalog`` (PK domain, SK slug) with a
static seed fallback when the table is empty or unavailable.
"""

from __future__ import annotations

import re
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

REGION = __import__("os").environ.get("AWS_REGION", "ap-south-1")
SUBDOMAIN_CATALOG_TABLE = __import__("os").environ.get(
    "SUBDOMAIN_CATALOG_TABLE", "subdomain_catalog"
)

_dynamodb = boto3.resource("dynamodb", region_name=REGION)
_catalog_table = _dynamodb.Table(SUBDOMAIN_CATALOG_TABLE)

# Canonical portal domains only.
STATIC_SUBDOMAINS: Dict[str, List[str]] = {
    "engineering": [
        "Full Stack Development",
        "Backend Development",
        "Frontend Development",
        "Mobile App Development (Android/iOS)",
        "Machine Learning / AI",
        "Data Engineering",
        "DevOps / Cloud Infrastructure",
        "Cybersecurity",
        "Game Development",
        "Embedded Systems",
        "Civil Engineering",
        "Electrical Engineering",
        "Mechanical Engineering",
        "Software Engineering",
    ],
    "healthcare": [
        "Cardiology",
        "Neurology",
        "Orthopedics",
        "Pediatrics",
        "Dermatology",
        "General Surgery",
        "Psychiatry",
        "Radiology",
        "Internal Medicine",
        "ICU / Critical Care",
        "Pediatric Nursing",
        "Community Health Nursing",
    ],
    "business": [
        "Digital Marketing",
        "SEO / Content Marketing",
        "Brand Management",
        "B2B Sales",
        "Financial Analysis",
        "Corporate Finance",
        "Business Analysis",
        "Operations Management",
        "Product Management",
        "Corporate Tax",
        "Investment Banking",
        "Strategy Consulting",
    ],
}


def skill_slug(skill: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (skill or "").lower()).strip("_")
    return slug[:80] if slug else "general"


def harvest_status_key(domain_key: str, skill: Optional[str] = None) -> str:
    domain_key = (domain_key or "").strip().lower()
    skill = (skill or "").strip()
    if skill:
        return f"{domain_key}#{skill_slug(skill)}"
    return domain_key


def _search_terms_for_label(label: str) -> List[str]:
    label = (label or "").strip()
    terms = {label.lower()}
    for part in re.split(r"[/,&]+", label):
        part = part.strip().lower()
        if part:
            terms.add(part)
    for token in re.findall(r"[a-z0-9]+", label.lower()):
        if len(token) >= 3:
            terms.add(token)
    return sorted(terms)


def _static_entries(domain_key: str) -> List[Dict[str, Any]]:
    labels = STATIC_SUBDOMAINS.get((domain_key or "").strip().lower(), [])
    entries = []
    for label in labels:
        slug = skill_slug(label)
        entries.append(
            {
                "domain": domain_key,
                "slug": slug,
                "label": label,
                "searchTerms": _search_terms_for_label(label),
                "active": True,
            }
        )
    return entries


def _normalize_entry(item: dict) -> Dict[str, Any]:
    label = str(item.get("label") or "").strip()
    slug = str(item.get("slug") or skill_slug(label)).strip()
    terms = item.get("searchTerms") or item.get("search_terms") or []
    if isinstance(terms, str):
        terms = [terms]
    search_terms = sorted(
        {str(t).strip().lower() for t in terms if t and str(t).strip()}
    )
    if label:
        search_terms = sorted(set(search_terms) | set(_search_terms_for_label(label)))
    return {
        "domain": str(item.get("domain") or "").strip().lower(),
        "slug": slug,
        "label": label,
        "searchTerms": search_terms,
        "active": bool(item.get("active", True)),
        "lastHarvestedAt": item.get("lastHarvestedAt"),
        "lastJobCount": item.get("lastJobCount"),
    }


def list_subdomains(domain_key: str) -> List[Dict[str, Any]]:
    """Return catalog entries for a domain (DynamoDB + static fallback)."""
    domain_key = (domain_key or "").strip().lower()
    if not domain_key:
        return []

    try:
        response = _catalog_table.query(KeyConditionExpression=Key("domain").eq(domain_key))
        items = response.get("Items") or []
        if items:
            return [_normalize_entry(item) for item in items if isinstance(item, dict)]
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code", "Unknown")
        if code != "ResourceNotFoundException":
            logger.warning("subdomain_catalog query failed domain=%s: %s", domain_key, code)

    return _static_entries(domain_key)


def seed_catalog_for_domain(domain_key: str) -> None:
    """Write static subdomains into DynamoDB (idempotent upsert)."""
    domain_key = (domain_key or "").strip().lower()
    for entry in _static_entries(domain_key):
        try:
            _catalog_table.put_item(
                Item={
                    "domain": domain_key,
                    "slug": entry["slug"],
                    "label": entry["label"],
                    "searchTerms": entry["searchTerms"],
                    "active": True,
                }
            )
        except ClientError as e:
            logger.warning(
                "subdomain_catalog seed failed domain=%s slug=%s: %s",
                domain_key,
                entry["slug"],
                e.response.get("Error", {}).get("Code", "Unknown"),
            )
            break


def record_harvest_result(domain_key: str, skill: str, job_count: int) -> None:
    """Upsert catalog row and stamp harvest metadata after a successful run."""
    domain_key = (domain_key or "").strip().lower()
    skill = (skill or "").strip()
    if not domain_key or not skill:
        return

    slug = skill_slug(skill)
    now = datetime.now(timezone.utc).isoformat()
    label = skill
    for entry in _static_entries(domain_key):
        if entry["slug"] == slug:
            label = entry["label"]
            break

    item = {
        "domain": domain_key,
        "slug": slug,
        "label": label,
        "searchTerms": _search_terms_for_label(label),
        "active": True,
        "lastHarvestedAt": now,
        "lastJobCount": int(job_count),
    }
    try:
        _catalog_table.put_item(Item=item)
    except ClientError as e:
        logger.warning(
            "subdomain_catalog record_harvest failed domain=%s skill=%s: %s",
            domain_key,
            skill,
            e.response.get("Error", {}).get("Code", "Unknown"),
        )


def expand_skill_needles(domain_key: str, skill_query: str) -> Set[str]:
    """Expand a user skill filter to all catalog match terms."""
    query = (skill_query or "").strip().lower()
    if not query:
        return set()

    needles: Set[str] = {query}
    for token in re.findall(r"[a-z0-9]+", query):
        if len(token) >= 3:
            needles.add(token)

    for entry in list_subdomains(domain_key):
        label = str(entry.get("label") or "").lower()
        slug = str(entry.get("slug") or "").lower()
        if query in label or label in query or query.replace(" ", "_") == slug:
            needles.add(label)
            needles.add(slug.replace("_", " "))
        for term in entry.get("searchTerms") or []:
            needles.add(str(term).lower())

    return needles
