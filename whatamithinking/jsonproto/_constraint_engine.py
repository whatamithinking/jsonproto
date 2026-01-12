from ._issues import BaseIssue, LengthIssue, PatternIssue, DecodingIssue
from ._pointers import JsonPointer
from ._codec import Config
import re
from ._struct import struct
from typing import ClassVar
from ._common import JsonType
from base64 import b64decode
import binascii

def validate_length_eq(
    limit: int, value: str, pointer: JsonPointer
) -> list[BaseIssue]:
    if value.__len__() == limit:
        return []
    return [
        LengthIssue(
            comparator="eq",
            value=value,
            pointer=pointer,
            limit=limit,
        )
    ]


class ConstraintEngine:
    
    
    
    
    pass


@struct
class AnyOfIssue(BaseIssue):
    issue_type: ClassVar[str] = "any_of"
    value: JsonType
    pointer: JsonPointer
    issues: list[list[BaseIssue]]


# how would we handle allOf(Pattern("m-\d+"), anyOf(Length("eq", 10), allOf(Length("ge", 3), Length("le", 8))), Encoding("base64"))?
value = "m-123"
config = Config()
pointer: JsonPointer = JsonPointer.root
included: bool = True
excluded: bool = False

pattern_1 = re.compile(r"m-\d+")

issues = []
if config.source == "json":
    if not pattern_1.fullmatch(value):
        issues.append(PatternIssue(
            value=value,
            pointer=pointer,
            pattern=pattern_1,
        ))
    any_of_issues_1 = [[], []]
    if not(len(value) == 10):
        any_of_issues_1[0].append(LengthIssue(
            comparator="eq",
            value=value,
            pointer=pointer,
            limit=10,
        ))
    if any_of_issues_1[0]:
        if not(len(value) >= 3):
            any_of_issues_1[1].append(LengthIssue(
                comparator="ge",
                value=value,
                pointer=pointer,
                limit=3,
            ))
        if not(len(value) <= 8):
            any_of_issues_1[1].append(LengthIssue(
                comparator="le",
                value=value,
                pointer=pointer,
                limit=8,
            ))
        if any_of_issues_1[1]:
            issues.append(AnyOfIssue(
                value=value,
                pointer=pointer,
                issues=any_of_issues_1,
            ))
        else:
            issues.extend(any_of_issues_1[1])
    else:
        issues.extend(any_of_issues_1[0])
    try:
        value = b64decode(value).decode()
    except (ValueError, binascii.Error):
        issues.append(
            DecodingIssue(
                value=value,
                pointer=pointer,
                encoding="base64",
            )
        )


if value == 10:
    
    pass