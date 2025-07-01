from typing import (
    Any,
    TYPE_CHECKING,
    Union,
)
from types import UnionType, NoneType
from collections import deque

if TYPE_CHECKING:
    from .._codec import Config

from .._errors import DiscriminatorFieldMissingError, DuplicateDiscriminatorError
from .._constraints import Discriminator
from .._common import get_alias, MISSING_TYPE, cached_get_args
from .._pointers import JsonPointer
from .._issues import (
    BaseIssue,
    MissingDiscriminatorIssue,
    InvalidDiscriminatorIssue,
)

from .base import TypeHandler, register_default_type_handler

__all__ = [
    "UnionHandler"
]


@register_default_type_handler(Union)
@register_default_type_handler(UnionType)
class UnionHandler(TypeHandler):
    data_type = "object"

    def build(self) -> None:
        discriminator: Discriminator | None = self.constraints.get("discriminator")
        if discriminator is not None:
            self._handle = self._discriminated_handle
            self._disc_name = disc_name = discriminator.field_name
            self._disc_alias = get_alias(disc_name)
            self._disc_type_handlers = {}
            # add checks to fool-proof since copy-pasting models and forgetting to change disc seems common
            # optimization: use getattr here instead of fields to avoid triggering build of all fields
            # for all models in union. should not be an issue as the discriminator is usually a constant
            # only edge case is if Field object is used instead of just a scalar value
            self._disc_type_hints = {}
            for type_hint in cached_get_args(self.type_hint):
                disc_value = getattr(type_hint, disc_name, None)
                if disc_value is None:
                    raise DiscriminatorFieldMissingError(
                        message="Discriminator field referenced by union missing from model class definition",
                        discriminator_name=disc_name,
                        type_hint=type_hint,
                    )
                disc_value = getattr(disc_value, "default", disc_value)
                if disc_value in self._disc_type_hints:
                    raise DuplicateDiscriminatorError(
                        message="Same discriminator value used for more than one model",
                        discriminator_name=disc_name,
                        discriminator_value=disc_value,
                        type_hint=type_hint,
                    )
                self._disc_type_hints[disc_value] = type_hint
        else:
            # Fast-path for Optional[T] (Union[T, NoneType] or Union[NoneType, T])
            args = cached_get_args(self.type_hint)
            if (
                len(args) == 2 and
                (args[0] is NoneType or args[1] is NoneType)
            ):
                # Find the non-None type
                non_none_type = args[1] if args[0] is NoneType else args[0]
                self._optional_type_handler = self.get_type_handler(type_hint=non_none_type)
                self._handle = self._optional_handle
            else:
                self._handle = self._left_to_right_handle
                self._type_hints = deque(cached_get_args(self.type_hint))
                self._type_handlers = [None] * len(self._type_hints)

    def _discriminated_handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | MISSING_TYPE, list[BaseIssue]]:
        try:
            match config.source:
                case "json":
                    disc_value = value[self._disc_alias]
                case "unstruct":
                    disc_value = value[self._disc_name]
                case "struct":
                    disc_value = getattr(value, self._disc_name)
        except (KeyError, AttributeError):
            raise MissingDiscriminatorIssue(
                value=value,
                pointer=pointer,
                discriminator=(
                    self._disc_alias
                    if config.source == "json"
                    else self._disc_name
                ),
            )
        try:
            type_handler = self._disc_type_handlers[disc_value]
        except KeyError:
            try:
                type_hint = self._disc_type_hints.pop(disc_value)
            except KeyError:
                raise InvalidDiscriminatorIssue(
                    value=value,
                    pointer=pointer,
                    discriminator=(
                        self._disc_alias
                        if config.source == "json"
                        else self._disc_name
                    ),
                )
            else:
                self._disc_type_handlers[disc_value] = type_handler = (
                    self.get_type_handler(type_hint=type_hint)
                )
        return type_handler.handle(
            value=value,
            pointer=pointer,
            included=included,
            excluded=excluded,
            config=config,
        )

    def _optional_handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | MISSING_TYPE, list[BaseIssue]]:
        # Fast-path for Optional[T]: if value is None, return it, else use the precomputed handler
        if value is None:
            return value, []
        return self._optional_type_handler.handle(
            value=value,
            pointer=pointer,
            included=included,
            excluded=excluded,
            config=config,
        )

    def _left_to_right_handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | MISSING_TYPE, list[BaseIssue]]:
        issues = []
        i = 0
        while i < len(self._type_handlers):
            type_handler = self._type_handlers[i]
            if type_handler is None:
                try:
                    type_hint = self._type_hints.popleft()
                except:
                    break
                else:
                    type_handler = self.get_type_handler(type_hint=type_hint)
                    self._type_handlers[i] = type_handler
            cvalue, cissues = type_handler.handle(
                value=value,
                pointer=pointer,
                included=included,
                excluded=excluded,
                config=config,
            )
            if not cissues:
                return cvalue, cissues
            issues.extend(cissues)
            i += 1
        return value, issues

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | MISSING_TYPE, list[BaseIssue]]:
        return self._handle(
            value=value,
            pointer=pointer,
            included=included,
            excluded=excluded,
            config=config,
        )
