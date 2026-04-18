from __future__ import annotations

from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError, model_validator


Severity = Literal["low", "medium", "high", "critical"]


class SecurityEvidenceModel(BaseModel):
    match: str
    start: int = Field(ge=0)
    end: int = Field(ge=0)


class SecurityHitModel(BaseModel):
    rule_id: str
    title: str
    severity: Severity
    evidence: SecurityEvidenceModel


class ComplexityFunctionModel(BaseModel):
    name: str
    lineno: int
    endline: int | None = None
    complexity: int = Field(ge=0)
    type: str


class ComplexityResultModel(BaseModel):
    language: str
    supported: bool
    reason: str | None = None
    cyclomatic_avg: float | None = None
    cyclomatic_max: int | None = None
    cyclomatic_functions: list[ComplexityFunctionModel] = Field(default_factory=list)
    halstead_total: dict[str, Any] | None = None

    @model_validator(mode="after")
    def ensure_supported_shape(self) -> "ComplexityResultModel":
        if self.supported and self.cyclomatic_max is None:
            raise ValueError("Supported complexity results must include cyclomatic_max.")
        return self


class QualityIssueModel(BaseModel):
    title: str
    severity: Literal["low", "medium", "high"]
    details: str
    recommendation: str


class QualityResponseModel(BaseModel):
    issues: list[QualityIssueModel] = Field(default_factory=list)


class SecurityRiskModel(BaseModel):
    title: str
    severity: Severity
    mitigation: str


class SecurityResponseModel(BaseModel):
    risks: list[SecurityRiskModel] = Field(default_factory=list)


class RefactorPlanItemModel(BaseModel):
    file: str
    steps: list[str] = Field(default_factory=list)
    risk: Literal["low", "medium", "high"]


class RefactorResponseModel(BaseModel):
    plan: list[RefactorPlanItemModel] = Field(default_factory=list)


class RefactorSuggestionSummaryModel(BaseModel):
    files_with_suggestions: int = Field(ge=0)
    suggestion_count: int = Field(ge=0)


class RefactorSuggestionsModel(BaseModel):
    files: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    summary: RefactorSuggestionSummaryModel


TModel = TypeVar("TModel", bound=BaseModel)


def safe_validate(model_cls: type[TModel], payload: Any) -> TModel | None:
    try:
        return model_cls.model_validate(payload)
    except ValidationError:
        return None


def normalize_quality_response(payload: Any) -> dict[str, Any]:
    """Normalize common LLM response variants into {'issues': [...]}."""
    if isinstance(payload, list):
        return {"issues": payload}
    if isinstance(payload, dict):
        if isinstance(payload.get("issues"), list):
            return payload
        if isinstance(payload.get("issue"), list):
            return {"issues": payload.get("issue")}
        if all(k in payload for k in ("title", "severity", "details", "recommendation")):
            return {"issues": [payload]}
    return {"issues": []}


def normalize_security_response(payload: Any) -> dict[str, Any]:
    """Normalize common LLM response variants into {'risks': [...]}."""
    if isinstance(payload, list):
        return {"risks": payload}
    if isinstance(payload, dict):
        if isinstance(payload.get("risks"), list):
            return payload
        if isinstance(payload.get("risk"), list):
            return {"risks": payload.get("risk")}
        if all(k in payload for k in ("title", "severity", "mitigation")):
            return {"risks": [payload]}
    return {"risks": []}


def normalize_refactor_response(payload: Any) -> dict[str, Any]:
    """Normalize common LLM response variants into {'plan': [...]}."""
    if isinstance(payload, list):
        return {"plan": payload}
    if isinstance(payload, dict):
        if isinstance(payload.get("plan"), list):
            return payload
        if isinstance(payload.get("plans"), list):
            return {"plan": payload.get("plans")}
        if all(k in payload for k in ("file", "steps", "risk")):
            return {"plan": [payload]}
    return {"plan": []}
