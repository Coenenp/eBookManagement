"""Findings and report model for the epub_check package."""

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Finding:
    code: str
    severity: Severity
    message: str
    location: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "location": self.location,
        }


@dataclass
class Report:
    file: str
    findings: List[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.findings) == 0

    def to_dict(self) -> dict:
        return {
            "file": self.file,
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)
