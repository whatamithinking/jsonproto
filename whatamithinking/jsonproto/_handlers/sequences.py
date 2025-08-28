from typing import (
    Any,
    TYPE_CHECKING,
    Iterable,
)
from itertools import cycle
from functools import partial
from collections import deque

if TYPE_CHECKING:
    from .._codec import Config

from .._constraints import Length
from .._errors import MissingGenericsError
from .._pointers import JsonPointer
from .._common import MISSING_TYPE, MISSING
from .._issues import (
    JsonTypeIssue,
    BaseIssue,
    PythonTypeIssue,
    LengthIssue,
)
from .._common import cached_get_args
from .base import TypeHandler, register_default_type_handler

__all__ = [
    "ListHandler",
    "SetHandler",
    "FrozenSetHandler",
    "DequeHandler",
    "TupleHandler",
]


class SequenceHandler(TypeHandler):
    data_type = "array"
    media_type = "application/json"
    structure_class = None
    destructure_class = list

    def _validate_length_eq(
        self,
        limit: int,
        value: str,
        pointer: JsonPointer,
    ) -> list[BaseIssue]:
        if len(value) == limit:
            return ()
        return [
            LengthIssue(
                comparator="eq",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_gt(
        self,
        limit: int,
        value: str,
        pointer: JsonPointer,
    ) -> list[BaseIssue]:
        if len(value) > limit:
            return ()
        return [
            LengthIssue(
                comparator="gt",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_ge(
        self,
        limit: int,
        value: str,
        pointer: JsonPointer,
    ) -> list[BaseIssue]:
        if len(value) >= limit:
            return ()
        return [
            LengthIssue(
                comparator="ge",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_le(
        self,
        limit: int,
        value: str,
        pointer: JsonPointer,
    ) -> list[BaseIssue]:
        if len(value) <= limit:
            return ()
        return [
            LengthIssue(
                comparator="le",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def _validate_length_lt(
        self,
        limit: int,
        value: str,
        pointer: JsonPointer,
    ) -> list[BaseIssue]:
        if len(value) < limit:
            return ()
        return [
            LengthIssue(
                comparator="lt",
                value=value,
                pointer=pointer,
                limit=limit,
            )
        ]

    def build(self) -> None:
        item_types = cached_get_args(self.type_hint)
        if len(item_types) <= 0:
            raise MissingGenericsError(
                f"Generic arg(s) required but not given for {self.type_hint!r}",
            )
        elif len(item_types) == 1:
            self._item_type_handlers = cycle((
                self.get_type_handler(type_hint=item_types[0]),
            ))
        else:
            self._item_type_handlers = tuple(map(self.get_type_handler, item_types))
        self._validators = []
        if not self.constraints:
            return
        len_min_inc = len_min_exc = len_max_inc = len_max_exc = len_eq = None
        seen = set[str]()
        for constraint in self.constraints:
            if constraint.constraint_id in seen:
                continue
            seen.add(constraint.constraint_id)
            match constraint.constraint_id:
                case "length_eq":
                    len_eq = constraint
                    break
                case "length_gt":
                    len_min_exc = constraint
                case "length_ge":
                    len_min_inc = constraint
                case "length_le":
                    len_max_inc = constraint
                case "length_lt":
                    len_max_exc = constraint

        if len_eq is not None:
            self._validators.append(
                partial(self._validate_length_eq, limit=len_eq.value)
            )
        else:
            if len_min_inc is not None and len_min_exc is not None:
                if len_min_inc.value > len_min_exc.value:
                    len_min_exc = None
                else:
                    len_min_inc = None
            if len_min_inc is not None:
                self._validators.append(
                    partial(self._validate_length_ge, limit=len_min_inc.value)
                )
            elif len_min_exc is not None:
                self._validators.append(
                    partial(self._validate_length_gt, limit=len_min_exc.value)
                )
            if len_max_inc is not None and len_max_exc is not None:
                if len_max_inc.value < len_max_exc.value:
                    len_min_exc = None
                else:
                    len_min_inc = None
            if len_max_inc is not None:
                self._validators.append(
                    partial(self._validate_length_le, limit=len_max_inc.value)
                )
            elif len_max_exc is not None:
                self._validators.append(
                    partial(self._validate_length_lt, limit=len_max_exc.value)
                )

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | MISSING_TYPE, list[BaseIssue]]:
        issues = []
        cvalue = value
        if config.source == "json":
            if cvalue.__class__ is not self.destructure_class:
                return cvalue, [
                    JsonTypeIssue(
                        value=cvalue,
                        pointer=pointer,
                        expected_type="array",
                    )
                ]
        else:
            # if coercion enabled and we were given an iterable, we can skip validation here
            # as we will create an instance of the sequence below anyway. if coercion not allowed
            # or we were not given an iterable, we have to check the type here and maybe fail
            # here so we enforce strict types and dont let the bad input type reach the loop below
            if config.coerce and hasattr(cvalue, "__iter__"):
                pass
            elif cvalue.__class__ is not self.structure_class:
                return cvalue, [
                    PythonTypeIssue(
                        value=cvalue,
                        pointer=pointer,
                        expected_type=(
                            Iterable if config.coerce else self.structure_class
                        ),
                    )
                ]
        source_patches = config.patches.have_for("source", "value")
        target_patches = config.patches.have_for("target", "value")
        sequence_class = self.destructure_class if config.target == "json" else self.structure_class
        cvalue = sequence_class(
            item_value
            for i, (type_handler, vv) in enumerate(
                zip(self._item_type_handlers, cvalue)
            )
            if (item_pointer := pointer.join(i))
            and ((item_excluded := config.exclude.matches(item_pointer)) is not True)
            and ((item_value := vv) is not MISSING)
            and (
                not source_patches
                or (
                    item_value := config.patches.patch(
                        "source", "value", item_pointer, item_value
                    )
                )
                is not MISSING
            )
            and (
                item_results := type_handler.handle(
                    value=item_value,
                    pointer=item_pointer,
                    included=included or config.include.matches(item_pointer),
                    excluded=item_excluded,
                    config=config,
                )
            )
            and ((item_value := item_results[0]) is not MISSING)
            and (issues.extend(item_results[1]) is None)
            and (
                not target_patches
                or (
                    item_value := config.patches.patch(
                        "target", "value", item_pointer, item_value
                    )
                )
                is not MISSING
            )
        )
        if config.validate and self._validators:
            issues.extend(
                issue
                for validator in self._validators
                for issue in validator(value=cvalue, pointer=pointer)
            )
        if (included and not excluded) or cvalue:
            if config.convert or config.coerce:
                return cvalue, issues
            else:
                return value, issues
        return MISSING, issues


@register_default_type_handler(list)
class ListHandler(SequenceHandler):
    structure_class = list


@register_default_type_handler(set)
class SetHandler(SequenceHandler):
    structure_class = set


@register_default_type_handler(frozenset)
class FrozenSetHandler(SequenceHandler):
    structure_class = frozenset


@register_default_type_handler(deque)
class DequeHandler(SequenceHandler):
    structure_class = deque


@register_default_type_handler(tuple)
class TupleHandler(SequenceHandler):
    structure_class = tuple

    def build(self):
        # there is an implicit constraint on length of a tuple based on type hint
        # needed to prevent caller from providing too few or too many args returning
        # too short/long a tuple without realizing
        self.constraints.append(Length("eq", len(cached_get_args(self.type_hint))))
        return super().build()
