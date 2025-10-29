from tkinter import N
from typing import Any, TYPE_CHECKING
from types import NoneType
import datetime
import re
import ipaddress
import uuid
import operator
import enum
from inspect import isclass
from contextlib import suppress
from pathlib import Path, WindowsPath, PosixPath, PurePosixPath, PureWindowsPath

if TYPE_CHECKING:
    from .._codec import Config

from .._pointers import JsonPointer
from .._common import Empty
from .._issues import (
    JsonTypeIssue,
    BaseIssue,
    PythonTypeIssue,
    EnumOptionIssue,
)
from .._errors import ValidationError
from .._types import Email, Url

from .base import TypeHandler, register_default_type_handler
from .strings import StringHandler
from .bytes import BytesHandler

__all__ = [
    "BoolHandler",
    "NoneHandler",
    "EnumHandler",
    "DateTimeHandler",
    "DateHandler",
    "TimeHandler",
    "DurationHandler",
    "IPv4AddressHandler",
    "IPv6AddressHandler",
    "EmailHandler",
    "UrlHandler",
    "PatternHandler",
    "UuidHandler",
    "PathHandler",
]


@register_default_type_handler(bool)
class BoolHandler(TypeHandler):
    data_type = "boolean"
    media_type = "text/plain"

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | Empty, list[BaseIssue]]:
        if not included or excluded or value is Empty:
            return Empty, []
        issues = []
        if value.__class__ is not bool:
            if config.source == "json":
                issues.append(
                    JsonTypeIssue(
                        value=value, pointer=pointer, expected_type="boolean"
                    )
                )
            else:
                issues.append(
                    PythonTypeIssue(
                        value=value, pointer=pointer, expected_type=bool
                    )
                )
        return value, issues


@register_default_type_handler(NoneType)
@register_default_type_handler(None)
class NoneHandler(TypeHandler):
    data_type = "null"
    media_type = "text/plain"

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | Empty, list[BaseIssue]]:
        if not included or excluded or value is Empty:
            return Empty, []
        issues = []
        if value.__class__ not in (None, NoneType):
            if config.source == "json":
                issues.append(
                    JsonTypeIssue(
                        value=value, pointer=pointer, expected_type="null"
                    )
                )
            else:
                issues.append(
                    PythonTypeIssue(
                        value=value, pointer=pointer, expected_type=None
                    )
                )
        return value, issues


def is_enum(cls):
    return isclass(cls) and issubclass(cls, enum.Enum)


@register_default_type_handler(callback=is_enum)
class EnumHandler(TypeHandler):
    type_hint: enum.Enum

    def build(self):
        from .._codec import Config
        
        # unravel types, handling StrEnum and IntEnum which bury the type of the values in the enum
        base_type = self.type_hint.__bases__[0]
        while issubclass(base_type, enum.Enum):
            base_type = base_type.__bases__[0]
        
        self._type_handler = self.get_type_handler(
            type_hint=base_type, constraints=self.constraints
        )
        self.python_options = frozenset(_.value for _ in self.type_hint)
        self.json_options = set()
        issues = []
        for enum_val in self.python_options:
            enum_json_val, ejissues = self._type_handler.handle(
                value=enum_val,
                pointer=JsonPointer.root,
                included=True,
                excluded=False,
                config=Config(target="json", convert=True),
            )
            issues.extend(ejissues)
            self.json_options.add(enum_json_val)
        if issues:
            raise ValidationError(issues)

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | Empty, list[BaseIssue]]:
        issues = []
        if not included or excluded or value is Empty:
            return Empty, issues
        cvalue = value
        if config.source == "json":
            cvalue, cissues = self._type_handler.handle(
                value=cvalue,
                pointer=pointer,
                included=included,
                excluded=excluded,
                config=config,
            )
            issues.extend(cissues)
            if config.validate or config.convert:
                if config.target == "json":
                    if cvalue not in self.json_options:
                        issues.append(
                            EnumOptionIssue(
                                value=cvalue,
                                pointer=pointer,
                                options=self.json_options,
                            )
                        )
                else:
                    try:
                        cvalue = self.type_hint(cvalue)
                    except ValueError:
                        issues.append(
                            EnumOptionIssue(
                                value=cvalue,
                                pointer=pointer,
                                options=self.python_options,
                            )
                        )
        else:
            if config.coerce and cvalue.__class__ is not self.type_hint:
                with suppress(ValueError):
                    cvalue = self.type_hint(cvalue)
            if cvalue.__class__ is not self.type_hint:
                return cvalue, [
                    PythonTypeIssue(
                        value=cvalue, pointer=pointer, expected_type=self.type_hint
                    )
                ]
            if config.convert and config.target == "json":
                try:
                    cvalue = cvalue.value
                except AttributeError:
                    issues.append(
                        PythonTypeIssue(
                            value=cvalue, pointer=pointer, expected_type=self.type_hint
                        )
                    )
                else:
                    cvalue, cissues = self._type_handler.handle(
                        value=cvalue,
                        pointer=pointer,
                        included=included,
                        excluded=excluded,
                        config=config,
                    )
                    issues.extend(cissues)
        if config.convert or config.coerce:
            return cvalue, issues
        return value, issues


@register_default_type_handler(datetime.datetime)
class DateTimeHandler(StringHandler):
    format = "date-time"
    structure_class = datetime.datetime
    structure = staticmethod(datetime.datetime.fromisoformat)
    destructure = staticmethod(datetime.datetime.isoformat)


@register_default_type_handler(datetime.date)
class DateHandler(StringHandler):
    format = "date"
    structure_class = datetime.date
    structure = staticmethod(datetime.date.fromisoformat)
    destructure = staticmethod(datetime.date.isoformat)


@register_default_type_handler(datetime.time)
class TimeHandler(StringHandler):
    format = "time"
    structure_class = datetime.time
    structure = staticmethod(datetime.time.fromisoformat)
    destructure = staticmethod(datetime.time.isoformat)


duration_regex = re.compile(
    r"^(?P<sign>-)?P"
    r"(?:(?P<days>\d*)D)?"
    r"(?:T"
    r"(?:(?P<hours>\d*)H)?"
    r"(?:(?P<minutes>\d*)M)?"
    r"(?:(?P<seconds>\d*)\.?(?P<fractional_seconds>\d*)S)?"
    r")?$"
)


def structure_duration(value: str) -> datetime.timedelta:
    match = duration_regex.match(value)
    if match is None:
        raise ValueError("invalid duration format given")
    mdict = match.groupdict()
    return (-1 if mdict["sign"] == "-" else +1) * datetime.timedelta(
        days=int(mdict["days"] or 0),
        hours=int(mdict["hours"] or 0),
        minutes=int(mdict["minutes"] or 0),
        seconds=int(mdict["seconds"] or 0),
        microseconds=float(f'0.{mdict["fractional_seconds"]}') * 10**6,
    )


def destructure_datetime(value: datetime.timedelta) -> str:
    try:
        microseconds = int(
            (value.days * 86400 + value.seconds) * 10**6 + value.microseconds
        )
    except AttributeError:
        raise TypeError
    sign = ""
    if microseconds < 0:
        microseconds = abs(microseconds)
        sign = "-"
    days, days_rem = divmod(microseconds, 86_400_000_000)
    hours, hours_rem = divmod(days_rem, 3_600_000_000)
    minutes, minutes_rem = divmod(hours_rem, 60_000_000)
    seconds, microseconds = divmod(minutes_rem, 1_000_000)
    parts = [f"{sign}P"]
    if days:
        parts.append(f"{days}D")
    if hours or minutes or seconds or microseconds:
        parts.append("T")
        if hours:
            parts.append(f"{hours:d}H")
        if minutes:
            parts.append(f"{minutes:d}M")
        if seconds and microseconds:
            parts.append(f"{seconds:d}.{microseconds:06d}S")
        elif seconds:
            parts.append(f"{seconds:d}S")
        elif microseconds:
            parts.append(f"0.{microseconds:06d}S")
    return "".join(parts)


@register_default_type_handler(datetime.timedelta)
class DurationHandler(StringHandler):
    format = "duration"
    structure_class = datetime.timedelta
    structure = staticmethod(structure_duration)
    destructure = staticmethod(destructure_datetime)


@register_default_type_handler(ipaddress.IPv4Address)
class IPv4AddressHandler(StringHandler):
    format = "ipv4"
    structure_class = ipaddress.IPv4Address
    structure = structure_class
    destructure = staticmethod(structure_class.__str__)


@register_default_type_handler(ipaddress.IPv6Address)
class IPv6AddressHandler(StringHandler):
    format = "ipv6"
    structure_class = ipaddress.IPv6Address
    structure = structure_class
    destructure = staticmethod(structure_class.__str__)


@register_default_type_handler(Email)
class EmailHandler(StringHandler):
    format = "email"
    structure_class = Email
    structure = structure_class
    destructure = staticmethod(structure_class.__str__)


@register_default_type_handler(Url)
class UrlHandler(StringHandler):
    format = "uri"
    structure_class = Url
    structure = structure_class
    destructure = staticmethod(structure_class.__str__)


@register_default_type_handler(re.Pattern)
class PatternHandler(StringHandler):
    format = "regex"
    structure_class = re.Pattern
    structure = staticmethod(re.compile)
    destructure = staticmethod(operator.attrgetter("pattern"))


def structure_uuid(value: bytes) -> uuid.UUID:
    return uuid.UUID(bytes=value)


def destructure_uuid(value: uuid.UUID) -> bytes:
    return value.bytes


@register_default_type_handler(uuid.UUID)
class UuidHandler(BytesHandler):
    encoding = "base32hex"
    format = "uuid"
    structure_class = uuid.UUID
    structure = staticmethod(structure_uuid)
    destructure = staticmethod(destructure_uuid)

    def coerce(self, value: Any, pointer: JsonPointer, config: "Config"):
        if config.source != "json":
            with suppress(ValueError):
                match value:
                    case str():
                        return self.structure_class(hex=value)
                    case int():
                        return self.structure_class(int=value)
                    case bytes():
                        return self.structure_class(bytes=value)
        return value


def is_path_structure_class(self, obj) -> bool:
    return obj.__class__ in (Path, WindowsPath, PosixPath)


@register_default_type_handler(Path)
class PathHandler(StringHandler):
    structure_class = Path
    is_structure_class = is_path_structure_class
    structure = staticmethod(Path)


@register_default_type_handler(PurePosixPath)
class PurePosixPathHandler(StringHandler):
    structure_class = PurePosixPath
    structure = staticmethod(PurePosixPath)


@register_default_type_handler(PureWindowsPath)
class PureWindowsPathHandler(StringHandler):
    structure_class = PureWindowsPath
    structure = staticmethod(PureWindowsPath)
