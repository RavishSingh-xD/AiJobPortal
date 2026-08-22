"""
Shared job-listing helpers for match discovery: filtering, overlap,
almost-there roles, and structured skill gap reports.
"""

from __future__ import annotations

from decimal import Decimal
from urllib.parse import quote_plus

EMPLOYMENT_INTERNSHIP = "Internship"
EMPLOYMENT_JOB = "Job"
CLOSED_STATUSES = {"closed", "expired", "inactive"}

DOMAIN_TABLE_MAP = {
    "Engineering": "jobs_engineering",
    "Business": "jobs_business",
    "Healthcare": "jobs_healthcare",
}

LISTING_FIELDS = (
    "canonical_id",
    "title",
    "company",
    "location",
    "apply_url",
    "min_pow_score",
    "is_fallback",
    "employment_type",
    "required_skills",
    "source",
)

ALMOST_THERE_POW_GAP = 5
ALMOST_THERE_MIN_SKILL_OVERLAP = 0.4
SCAN_LIMIT = 100


def as_number(value, default=0):
    if value is None or isinstance(value, bool):
        return default
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    if isinstance(value, (int, float)):
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def is_open_listing(item: dict) -> bool:
    status = item.get("status") or item.get("display_status") or ""
    return str(status).strip().lower() not in CLOSED_STATUSES


def normalize_required_skills(required_skills):
    if isinstance(required_skills, str):
        required_skills = [required_skills]
    if not isinstance(required_skills, list):
        return []
    return [str(skill).strip() for skill in required_skills if skill and str(skill).strip()]


def skill_matches(required_skills, skill_query: str) -> bool:
    if not skill_query:
        return True
    if isinstance(required_skills, str):
        required_skills = [required_skills]
    if not required_skills:
        return False
    needle = skill_query.strip().lower()
    if not needle:
        return True
    for skill in required_skills:
        if skill is None:
            continue
        if needle in str(skill).lower():
            return True
    return False


def skill_overlap(required_skills, skill: str, domain: str) -> float:
    tags = normalize_required_skills(required_skills)
    if not tags:
        return 0.0
    hits = 0
    for tag in tags:
        if skill_matches([tag], skill) or skill_matches([tag], domain):
            hits += 1
            continue
        lower = tag.lower()
        if (skill and lower in skill.strip().lower()) or (
            domain and lower in domain.strip().lower()
        ):
            hits += 1
    return hits / len(tags)


def employment_type_key(employment_type):
    if not employment_type:
        return None
    needle = str(employment_type).strip().lower()
    if needle == EMPLOYMENT_INTERNSHIP.lower():
        return "internships"
    if needle == EMPLOYMENT_JOB.lower():
        return "jobs"
    return None


def public_listing(item: dict) -> dict:
    listing = {}
    for field in LISTING_FIELDS:
        if field in item:
            listing[field] = item[field]
    listing["required_skills"] = normalize_required_skills(item.get("required_skills"))
    return listing


def learn_url(skill: str) -> str:
    query = quote_plus(f"learn {skill} free course")
    return f"https://www.google.com/search?q={query}"


def tag_matches_user(tag: str, skill: str, domain: str) -> bool:
    return skill_matches([tag], skill) or skill_matches([tag], domain)


def missing_skills_for_user(required_skills, skill: str, domain: str) -> list[str]:
    tags = normalize_required_skills(required_skills)
    return [tag for tag in tags if not tag_matches_user(tag, skill, domain)]


def qualifies_for_match(item: dict, skill: str, pow_score: float) -> bool:
    if not is_open_listing(item):
        return False
    if employment_type_key(item.get("employment_type")) is None:
        return False
    if not skill_matches(item.get("required_skills"), skill):
        return False
    min_pow = as_number(item.get("min_pow_score"), default=0)
    return min_pow <= pow_score


def build_almost_there_entry(item: dict, skill: str, domain: str, pow_score: float) -> dict | None:
    if not is_open_listing(item):
        return None
    group = employment_type_key(item.get("employment_type"))
    if group is None:
        return None

    if qualifies_for_match(item, skill, pow_score):
        return None

    required = item.get("required_skills")
    min_pow = as_number(item.get("min_pow_score"), default=0)
    overlap = skill_overlap(required, skill, domain)
    skill_match = skill_matches(required, skill)
    upgrade_steps = []

    if skill_match and min_pow > pow_score:
        gap = round(min_pow - pow_score, 2)
        if gap <= ALMOST_THERE_POW_GAP:
            upgrade_steps.append(
                {
                    "type": "pow",
                    "message": (
                        f"Raise your PoW score by {gap:g} points "
                        f"(this role asks for {min_pow:g}, you have {pow_score:g})."
                    ),
                    "powGap": gap,
                    "targetPowScore": min_pow,
                }
            )

    if min_pow <= pow_score and not skill_match and overlap >= ALMOST_THERE_MIN_SKILL_OVERLAP:
        missing = missing_skills_for_user(required, skill, domain)
        if missing:
            preview = ", ".join(missing[:3])
            upgrade_steps.append(
                {
                    "type": "skill",
                    "message": f"Build these skills: {preview}.",
                    "missingSkills": missing,
                }
            )

    if not upgrade_steps:
        return None

    entry = public_listing(item)
    entry["upgradeSteps"] = upgrade_steps
    entry["gapType"] = upgrade_steps[0]["type"]
    return entry


def build_skill_gap_report(
    matched_listings: list[dict],
    almost_there_listings: list[dict],
    skill: str,
    domain: str,
) -> dict:
    target_listings = matched_listings + almost_there_listings
    if not target_listings:
        return {
            "strongSkills": [],
            "weakSkills": [],
            "missingSkills": [],
            "summary": "No target roles yet — complete matching to see skill insights.",
        }

    skill_stats: dict[str, dict] = {}

    for listing in target_listings:
        tags = normalize_required_skills(listing.get("required_skills"))
        is_matched = listing in matched_listings
        for tag in tags:
            key = tag.lower()
            if key not in skill_stats:
                skill_stats[key] = {
                    "skill": tag,
                    "roleCount": 0,
                    "matchedRoleCount": 0,
                    "userMatches": tag_matches_user(tag, skill, domain),
                }
            skill_stats[key]["roleCount"] += 1
            if is_matched:
                skill_stats[key]["matchedRoleCount"] += 1

    strong_skills = []
    weak_skills = []
    missing_skills = []

    for stats in skill_stats.values():
        entry = {
            "skill": stats["skill"],
            "roleCount": stats["roleCount"],
            "matchedRoleCount": stats["matchedRoleCount"],
            "learnUrl": learn_url(stats["skill"]),
        }
        if stats["userMatches"] and stats["matchedRoleCount"] >= 1:
            strong_skills.append(entry)
        elif stats["userMatches"]:
            weak_skills.append(entry)
        else:
            entry["priority"] = "high" if stats["roleCount"] >= 2 else "medium"
            missing_skills.append(entry)

    strong_skills.sort(key=lambda row: (-row["matchedRoleCount"], -row["roleCount"], row["skill"]))
    weak_skills.sort(key=lambda row: (-row["roleCount"], row["skill"]))
    missing_skills.sort(key=lambda row: (-row["roleCount"], row["skill"]))

    if missing_skills:
        top = missing_skills[0]["skill"]
        summary = (
            f"Focus on {top} first — it appears in {missing_skills[0]['roleCount']} "
            f"roles you're targeting."
        )
    elif strong_skills:
        summary = (
            f"You're strong on {strong_skills[0]['skill']} across "
            f"{strong_skills[0]['matchedRoleCount']} matched roles."
        )
    else:
        summary = "Keep building domain depth to unlock more matches."

    return {
        "strongSkills": strong_skills[:12],
        "weakSkills": weak_skills[:8],
        "missingSkills": missing_skills[:12],
        "summary": summary,
    }


def partition_matches(
    items: list[dict],
    skill: str,
    domain: str,
    pow_score: float,
    group_cap: int = 20,
    almost_cap: int = 10,
) -> dict:
    internships = []
    jobs = []
    almost_internships = []
    almost_jobs = []
    matched_flat = []

    for item in items:
        if not isinstance(item, dict):
            continue
        if qualifies_for_match(item, skill, pow_score):
            listing = public_listing(item)
            matched_flat.append(listing)
            group = employment_type_key(item.get("employment_type"))
            if group == "internships":
                internships.append(listing)
            elif group == "jobs":
                jobs.append(listing)
        else:
            almost = build_almost_there_entry(item, skill, domain, pow_score)
            if almost is None:
                continue
            group = employment_type_key(item.get("employment_type"))
            if group == "internships":
                almost_internships.append(almost)
            elif group == "jobs":
                almost_jobs.append(almost)

    internships.sort(key=lambda row: as_number(row.get("min_pow_score"), 0), reverse=True)
    jobs.sort(key=lambda row: as_number(row.get("min_pow_score"), 0), reverse=True)
    almost_internships.sort(
        key=lambda row: as_number(row.get("min_pow_score"), 0), reverse=True
    )
    almost_jobs.sort(key=lambda row: as_number(row.get("min_pow_score"), 0), reverse=True)

    almost_flat = almost_internships[:almost_cap] + almost_jobs[:almost_cap]

    return {
        "internships": internships[:group_cap],
        "jobs": jobs[:group_cap],
        "almostThere": {
            "internships": almost_internships[:almost_cap],
            "jobs": almost_jobs[:almost_cap],
        },
        "matched_flat": matched_flat[:group_cap * 2],
        "almost_flat": almost_flat,
    }
