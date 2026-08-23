"""Tests for listing_utils discovery helpers."""

from lambdas.match import listing_utils as lu


def listing(
    canonical_id,
    employment_type="Internship",
    min_pow=10,
    skills=None,
    status="ACTIVE",
    **overrides,
):
    item = {
        "canonical_id": canonical_id,
        "title": f"Role {canonical_id}",
        "company": "Acme",
        "location": "Remote",
        "apply_url": f"https://example.com/{canonical_id}",
        "min_pow_score": min_pow,
        "employment_type": employment_type,
        "required_skills": skills or ["Python"],
        "status": status,
        "display_status": "Active",
    }
    item.update(overrides)
    return item


def test_partition_matches_and_almost_there_pow_gap():
    items = [
        listing("qualified", min_pow=20),
        listing("almost-pow", min_pow=35, skills=["Python"]),
    ]
    result = lu.partition_matches(items, "Python", "Engineering", 32)
    assert len(result["internships"]) == 1
    assert result["internships"][0]["canonical_id"] == "qualified"
    assert len(result["almostThere"]["internships"]) == 1
    assert result["almostThere"]["internships"][0]["gapType"] == "pow"


def test_skill_gap_report_missing_skills():
    matched = [listing("a", skills=["Python", "Docker"])]
    almost = [listing("b", min_pow=40, skills=["Python", "Kubernetes"])]
    report = lu.build_skill_gap_report(
        [lu.public_listing(matched[0])],
        [lu.public_listing(almost[0])],
        "Python",
        "Engineering",
    )
    assert report["summary"]
    missing = {row["skill"] for row in report["missingSkills"]}
    assert "Kubernetes" in missing or "Docker" in missing


def test_expand_skill_needles_tokenizes_subdomain_labels():
    needles = lu.expand_skill_needles("Engineering", "Machine Learning / AI")
    assert "machine learning / ai" in needles
    assert "machine" in needles
    assert "learning" in needles


def test_subdomain_skill_matches_via_tokens_and_harvest_skill():
    """Portal subdomain labels rarely appear verbatim on job tags."""
    items = [
        listing(
            "ml-role",
            employment_type="Job",
            min_pow=10,
            skills=["Python", "TensorFlow"],
            harvest_skill="Machine Learning",
            title="Junior ML Engineer",
        ),
        listing(
            "fullstack",
            employment_type="Internship",
            min_pow=10,
            skills=["React", "Node"],
            harvest_skill="Full Stack Development",
        ),
        listing(
            "unrelated",
            employment_type="Job",
            min_pow=10,
            skills=["Accounting"],
            harvest_skill="Corporate Finance",
        ),
    ]

    ml = lu.partition_matches(items, "Machine Learning / AI", "Engineering", 40)
    assert [row["canonical_id"] for row in ml["jobs"]] == ["ml-role"]

    fs = lu.partition_matches(items, "Full Stack Development", "Engineering", 40)
    assert [row["canonical_id"] for row in fs["internships"]] == ["fullstack"]
    assert fs["jobs"] == []
