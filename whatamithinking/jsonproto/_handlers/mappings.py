from typing import (
    Any,
    TYPE_CHECKING,
    Mapping,
    Callable,
    MappingView,
)
from collections import OrderedDict, defaultdict
from types import MappingProxyType

if TYPE_CHECKING:
    from .._codec import Config

from .._common import Empty, cached_get_args
from .._errors import MissingGenericsError
from .._pointers import JsonPointer
from .._issues import (
    JsonTypeIssue,
    BaseIssue,
    PythonTypeIssue,
)

from .base import TypeHandler, register_default_type_handler

__all__ = [
    "DictHandler",
    "OrderedDictHandler",
    "DefaultDictHandler",
    "MappingProxyTypeHandler",
    "MappingViewHandler",
]


class MappingHandler(TypeHandler):
    data_type = "object"
    media_type = "application/json"
    structure_class: type
    structure: Callable[[Mapping], Any]
    destructure_class: Mapping = dict
    destructure: Callable[[Any], Mapping] = dict

    def build(self) -> None:
        args = cached_get_args(self.type_hint)
        if len(args) != 2:
            raise MissingGenericsError(
                f"Generic arg(s) required but not given for {self.type_hint!r}",
            )
        key_type_hint, value_type_hint = args
        self._key_type_handler = self.get_type_handler(type_hint=key_type_hint)
        self._value_type_handler = self.get_type_handler(type_hint=value_type_hint)

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | Empty, list[BaseIssue]]:
        issues = []
        cvalue = value
        if config.source == "json":
            if cvalue.__class__ is not self.destructure_class:
                return cvalue, [
                    JsonTypeIssue(
                        value=cvalue,
                        pointer=pointer,
                        expected_type="object",
                    )
                ]
        else:
            # if coerce enabled and we were given some sort of mapping we can skip validating the exact type
            # so long as we can iterate over the items in the mapping, we dont have to worry about the exact type
            # can also support sequence of some kind so long as when we iterate over it we will get two objects
            # to use for key/value pair
            if config.coerce and (
                hasattr(cvalue, "items")
                or (hasattr(cvalue, "__iter__") and cvalue and len(cvalue[0]) == 2)
            ):
                pass
            elif cvalue.__class__ is not self.structure_class:
                return cvalue, [
                    PythonTypeIssue(
                        value=cvalue,
                        pointer=pointer,
                        expected_type=(
                            Mapping if config.coerce else self.structure_class
                        ),
                    )
                ]
        source_key_patches = config.patches.have_for("source", "key")
        source_value_patches = config.patches.have_for("source", "value")
        target_key_patches = config.patches.have_for("target", "key")
        target_value_patches = config.patches.have_for("target", "value")
        mapping = self.destructure if config.target == "json" else self.structure
        cvalue = mapping(
            (key, val)
            for k, v in getattr(cvalue, 'items', getattr(cvalue, "__iter__"))()
            if ((key := k) is not Empty)
            and ((val := v) is not Empty)
            and (not config.exclude_none or val is not None)
            and (key_pointer := pointer.join(key))
            and ((key_excluded := config.exclude.matches(key_pointer)) is not True)
            and (
                not source_key_patches
                or (key := config.patches.patch("source", "key", key_pointer, key))
                is not Empty
            )
            and (
                not source_value_patches
                or (val := config.patches.patch("source", "value", key_pointer, val))
                is not Empty
            )
            and (
                (
                    key_results := self._key_type_handler.handle(
                        value=key,
                        pointer=key_pointer,
                        included=included or config.include.matches(key_pointer),
                        excluded=key_excluded,
                        config=config,
                    )
                )
                is not Empty
            )
            and ((key := key_results[0]) is not Empty)
            and (issues.extend(key_results[1]) is None)
            and (
                (
                    val_results := self._value_type_handler.handle(
                        value=val,
                        pointer=key_pointer,
                        included=included or config.include.matches(key_pointer),
                        excluded=key_excluded,
                        config=config,
                    )
                )
                is not Empty
            )
            and ((val := val_results[0]) is not Empty)
            and (issues.extend(val_results[1]) is None)
            and (
                not target_key_patches
                or (key := config.patches.patch("target", "key", key_pointer, key))
                is not Empty
            )
            and (
                not target_value_patches
                or (val := config.patches.patch("target", "value", key_pointer, val))
                is not Empty
            )
        )
        if (included and not excluded) or cvalue:
            if config.convert or config.coerce:
                return cvalue, issues
            else:
                return value, issues
        return Empty, issues


@register_default_type_handler(dict)
class DictHandler(MappingHandler):
    structure_class = dict
    structure = structure_class


@register_default_type_handler(OrderedDict)
class OrderedDictHandler(MappingHandler):
    structure_class = OrderedDict
    structure = structure_class


@register_default_type_handler(defaultdict)
class DefaultDictHandler(MappingHandler):
    structure_class = defaultdict

    def build(self):
        super().build()
        # dynamically create constructor using the value type hint
        # should work in simple cases but might fall apart for things like union values
        self.structure = self.structure_class(cached_get_args(self.type_hint)[1])


@register_default_type_handler(MappingProxyType)
class MappingProxyTypeHandler(MappingHandler):
    structure_class = MappingProxyType
    structure = structure_class


@register_default_type_handler(MappingView)
class MappingViewHandler(MappingHandler):
    structure_class = MappingView
    structure = structure_class
