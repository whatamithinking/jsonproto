from typing import Any, cast, TYPE_CHECKING, Callable
from numbers import Number
from decimal import Decimal
from functools import partial
from contextlib import suppress

if TYPE_CHECKING:
    from .._codec import Config

from .._pointers import JsonPointer
from .._common import Empty
from .._issues import (
    JsonTypeIssue,
    BaseIssue,
    StructTypeIssue,
    FormatIssue,
    NumberIssue,
)
from .._constraints import (
    Format,
    Value,
)
from .._registry import default_type_handler_registry

from .base import BaseTypeHandler

__all__ = [
    "IntHandler",
    "FloatHandler",
    "DecimalHandler",
]


class NumberLikeHandler(BaseTypeHandler):
    media_type = "text/plain"
    structure_class: type
    structure: Callable[[Any], Any]
    destructure_class: type
    destructure: Callable[[Any], Any]

    def _validate_32_bit(
        self,
        value: int,
        pointer: JsonPointer,
    ) -> list[BaseIssue]:
        if value.bit_length() > 32:
            return [
                FormatIssue(
                    value=value,
                    pointer=pointer,
                    format="int32",
                )
            ]
        return []

    def _validate_64_bit(
        self,
        value: int,
        pointer: JsonPointer,
    ) -> list[BaseIssue]:
        if value.bit_length() > 64:
            return [
                FormatIssue(
                    value=value,
                    pointer=pointer,
                    format="int64",
                )
            ]
        return []

    def _validate_eq(
        self, limit: Number, value: int, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if value == limit:
            return ()
        return [
            NumberIssue(
                value=value,
                pointer=pointer,
                comparator="eq",
                limit=limit,
            )
        ]

    def _validate_gt(
        self, limit: Number, value: int, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if value > limit:
            return ()
        return [
            NumberIssue(
                value=value,
                pointer=pointer,
                comparator="gt",
                limit=limit,
            )
        ]

    def _validate_ge(
        self, limit: Number, value: int, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if value >= limit:
            return ()
        return [
            NumberIssue(
                value=value,
                pointer=pointer,
                comparator="ge",
                limit=limit,
            )
        ]

    def _validate_le(
        self, limit: Number, value: int, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if value <= limit:
            return ()
        return [
            NumberIssue(
                value=value,
                pointer=pointer,
                comparator="le",
                limit=limit,
            )
        ]

    def _validate_lt(
        self, limit: Number, value: int, pointer: JsonPointer
    ) -> list[BaseIssue]:
        if value < limit:
            return ()
        return [
            NumberIssue(
                value=value,
                pointer=pointer,
                comparator="lt",
                limit=limit,
            )
        ]

    def build(self) -> None:
        self._is_destructure_class_number = issubclass(self.destructure_class, Number)
        self._validators = []
        if not self.constraints:
            return
        min_inc = min_exc = max_inc = max_exc = eq = None
        for constraint in self.constraints:
            match constraint.constraint_type:
                case "format":
                    constraint = cast(Format, constraint)
                    match constraint.value:
                        case "int32":
                            self._validators.append(self._validate_32_bit)
                        case "int64":
                            self._validators.append(self._validate_64_bit)
                case "value":
                    constraint = cast(Value, constraint)
                    match constraint.comparator:
                        case "eq":
                            eq = constraint
                        case "gt":
                            min_exc = constraint
                        case "ge":
                            min_inc = constraint
                        case "le":
                            max_inc = constraint
                        case "lt":
                            max_exc = constraint
        if eq is not None:
            self._validators.append(partial(self._validate_eq, limit=eq.value))
        else:
            if min_inc is not None and min_exc is not None:
                if min_inc.value > min_exc.value:  # type: ignore
                    min_exc = None
                else:
                    min_inc = None
            if min_inc is not None:
                self._validators.append(partial(self._validate_ge, limit=min_inc.value))
            elif min_exc is not None:
                self._validators.append(partial(self._validate_gt, limit=min_exc.value))
            if max_inc is not None and max_exc is not None:
                if max_inc.value < max_exc.value:  # type: ignore
                    min_exc = None
                else:
                    min_inc = None
            if max_inc is not None:
                self._validators.append(partial(self._validate_le, limit=max_inc.value))
            elif max_exc is not None:
                self._validators.append(partial(self._validate_lt, limit=max_exc.value))

    def coerce(self, value: Any, pointer: JsonPointer, config: "Config") -> Any:
        return value

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
        converted = coerced = value
        if config.coerce:
            converted = coerced = self.coerce(
                value=value, pointer=pointer, config=config
            )
        if config.source == "json":
            is_json_type = True
            if converted.__class__ is not self.destructure_class:
                is_json_type = False
                issues.append(
                    JsonTypeIssue(
                        value=converted,
                        pointer=pointer,
                        expected_type=self.data_type,
                    )
                )
            if is_json_type:
                if (
                    not self._is_destructure_class_number
                    or config.validate
                    or (config.convert and config.target != "json")
                ):
                    try:
                        converted = self.structure(converted)
                    except ValueError:
                        issues.append(
                            FormatIssue(
                                value=converted, pointer=pointer, format=self.format
                            )
                        )
                    except TypeError:
                        issues.append(
                            JsonTypeIssue(
                                value=converted, pointer=pointer, expected_type="string"
                            )
                        )
                if (
                    config.validate and self._validators
                ):  # do validation after conversion to handle numbers destructured to non-numbers like Decimal
                    issues.extend(
                        issue
                        for validator in self._validators
                        for issue in validator(value=converted, pointer=pointer)
                    )
        else:
            is_struct_type = True
            if converted.__class__ is not self.structure_class:
                is_struct_type = False
                issues.append(
                    StructTypeIssue(
                        value=converted,
                        pointer=pointer,
                        expected_type=self.structure_class,
                    )
                )
            if config.validate:
                if self._validators:
                    issues.extend(
                        issue
                        for validator in self._validators
                        for issue in validator(value=converted, pointer=pointer)
                    )
            if is_struct_type and config.convert:
                if config.target == "json":
                    if converted.__class__ is not self.destructure_class:
                        try:
                            converted = self.destructure(converted)
                        except TypeError:
                            issues.append(
                                StructTypeIssue(
                                    value=converted,
                                    pointer=pointer,
                                    expected_type=self.structure_class,
                                )
                            )
        if config.convert:
            return converted, issues
        elif config.coerce:
            return coerced, issues
        else:
            return value, issues


@default_type_handler_registry.register(type_hint=int)
class IntHandler(NumberLikeHandler):
    data_type = "integer"
    structure_class = int
    structure = structure_class
    destructure_class = structure_class
    destructure = structure_class

    def coerce(self, value, pointer, config):
        if isinstance(value, self.structure_class):
            return value
        match value:
            case float():
                if value.is_integer():
                    value = self.structure(value)
            case str():
                if value.isdigit():
                    value = self.structure(value)
            case Decimal():
                if value == value.to_integral_value():
                    value = self.structure(value)
        return value


@default_type_handler_registry.register(type_hint=float)
class FloatHandler(NumberLikeHandler):
    data_type = "number"
    structure_class = float
    structure = structure_class
    destructure_class = structure_class
    destructure = structure_class

    def coerce(self, value, pointer, config):
        if isinstance(value, self.structure_class):
            return value
        match value:
            case int():
                value = self.structure(value)
            case str():
                with suppress(ValueError):
                    value = self.structure(value)
            case Decimal():
                fvalue = float(value)
                if fvalue == value:
                    value = fvalue
        return value


@default_type_handler_registry.register(type_hint=Decimal)
class DecimalHandler(NumberLikeHandler):
    data_type = "string"
    structure_class = Decimal
    structure = structure_class
    destructure_class = str
    destructure = staticmethod(structure_class.__str__)

    def coerce(self, value, pointer, config):
        if isinstance(value, self.structure_class):
            return value
        if config.source != "json":
            match value:
                case int() | float():
                    value = self.structure(value)
                case str():
                    with suppress(ValueError):
                        value = self.structure(value)
        return value
