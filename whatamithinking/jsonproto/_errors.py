from typing import TYPE_CHECKING, Union, Any
from itertools import groupby

if TYPE_CHECKING:
    from ._issues import BaseIssue
    from ._common import BaseConstraint
from ._struct import get_fields, get_names


__all__ = [
    "Error",
    "TypeHintError",
    "MissingGenericsError",
    "JsonPathError",
    "TypeHandlerMissingError",
    "DiscriminatorFieldMissingError",
    "DuplicateDiscriminatorError",
    "ValidationError",
    "ConstraintError",
]


class Error(Exception):
    """Base error for openapi package"""


class TypeHintError(Error):
    """Raised when a type hint is invalid/under specified"""

    def __init__(self, message: str) -> None:
        super().__init__(message)


class MissingGenericsError(TypeHintError):
    """Raised when the generic(s) for a class are not given in a type hint
    but are required for the codec to work"""


class JsonPathError(Error): ...


class TypeHandlerMissingError(Error): ...


class DiscriminatorFieldMissingError(Error):
    discriminator_name: str
    type_hint: type

    def __init__(self, message: str, discriminator_name: str, type_hint: type) -> None:
        self.type_hint = type_hint
        self.discriminator_name = discriminator_name
        super().__init__(message)


class DuplicateDiscriminatorError(Error):
    discriminator_name: str
    discriminator_value: Any
    type_hint: type

    def __init__(
        self,
        message: str,
        discriminator_name: str,
        discriminator_value: Any,
        type_hint: type,
    ) -> None:
        super().__init__(message)
        self.discriminator_name = discriminator_name
        self.discriminator_value = discriminator_value
        self.type_hint = type_hint


class ValidationError(Error):
    issues: list["BaseIssue"]

    def __init__(self, issues: list["BaseIssue"]) -> None:
        self.issues = issues
        super().__init__("One or more validation checks failed for the given data")

    def __str__(self) -> str:
        # pretty-print error in a hierarchy with pointer as top level, then issue type, then issue details
        # hopefully making it a bit easier to parse through to identify where the issues happened and why
        self.issues.sort(key=lambda _: (_.pointer, _.issue_type))
        parts = []
        for pointer, pissues in groupby(self.issues, key=lambda _: _.pointer):
            pointer_issues = "\n\n        ".join(
                "\n        ".join(
                    f"{'' if name == 'issue_type' else '    '}{name}={getattr(pissue, name)!r}"
                    for name in sorted(get_names(pissue), key=lambda _: 0 if _ == "issue_type" else 1)
                    if name not in ("pointer",)
                )
                for pissue in pissues
            )
            parts.append(f"pointer='{pointer}'\n        {pointer_issues}")
        issue_str = "\n\n    ".join(parts)
        return f"{self.args[0]}\n    {issue_str}"


class ConstraintError(Error):
    """Raised when a parameter for a constraint is invalid."""

    constraint: Union["BaseConstraint", None] = None

    def __init__(
        self,
        message: str,
        constraint: Union["BaseConstraint", None] = None,
    ) -> None:
        if constraint:
            self.constraint = constraint
        super().__init__(message)
