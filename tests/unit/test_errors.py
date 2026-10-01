from src.core.errors import (
    BadRequestError,
    ConflictError,
    DomainError,
    ForbiddenError,
    NotFoundError,
    ProblemDetails,
    UnauthorizedError,
    ValidationError,
)


def test_problem_details_model():
    p = ProblemDetails(
        type="https://errors.medisync.com/not-found",
        title="Not Found",
        status=404,
        detail="Patient not found",
        instance="/api/v1/patients/123",
        request_id="req-123",
    )
    d = p.model_dump(exclude_none=True)
    assert d["status"] == 404
    assert d["title"] == "Not Found"
    assert d["detail"] == "Patient not found"
    assert d["request_id"] == "req-123"


def test_domain_error_hierarchy():
    err = NotFoundError("Patient not found")
    assert isinstance(err, DomainError)
    assert err.status_code == 404
    assert err.title == "Not Found"
    assert err.detail == "Patient not found"

    err_conflict = ConflictError("Resource already locked")
    assert err_conflict.status_code == 409
    assert err_conflict.title == "Conflict"

    err_unauth = UnauthorizedError("Missing token")
    assert err_unauth.status_code == 401

    err_forbidden = ForbiddenError("Access denied")
    assert err_forbidden.status_code == 403

    err_bad = BadRequestError("Invalid parameter")
    assert err_bad.status_code == 400

    err_val = ValidationError("Invalid payload")
    assert err_val.status_code == 422


def test_domain_error_custom_attributes():
    err = DomainError(
        "Custom error occurred",
        status_code=418,
        title="I'm a teapot",
        error_type="https://errors.medisync.com/teapot",
        code="TEAPOT_ERROR",
    )
    assert err.status_code == 418
    assert err.title == "I'm a teapot"
    assert err.error_type == "https://errors.medisync.com/teapot"
    assert err.code == "TEAPOT_ERROR"
