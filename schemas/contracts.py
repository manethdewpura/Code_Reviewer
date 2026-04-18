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
