import pytest

from job_outreach.matching import Assessment, Evidence, cosine, validate_assessment


def test_cosine_ranking_and_invalid_vectors():
    assert cosine([1, 0], [1, 0]) > cosine([1, 0], [0, 1])
    with pytest.raises(ValueError):
        cosine([1, 0], [1])
    assert cosine([0, 0], [1, 0]) == 0


def test_assessment_rejects_invented_evidence():
    assessment = Assessment(
        skills=80,
        projects=50,
        role=80,
        domain=0,
        location=0,
        matched=[Evidence(fact_index=0, job_quote="Python")],
    )
    result = validate_assessment(assessment, ["Built Python services"], "Required Python skills")
    assert result["score"] == 56.5
    with pytest.raises(ValueError):
        validate_assessment(assessment, ["Built Python services"], "Required Java")
    assessment.matched[0].fact_index = 10
    with pytest.raises(ValueError):
        validate_assessment(assessment, ["Built Python services"], "Required Python skills")
