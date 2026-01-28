from typing import Any, TYPE_CHECKING, ClassVar, Final, Literal

if TYPE_CHECKING:
    from .._codec import Config

from .._pointers import JsonPointer
from .._issues import (
    BaseIssue,
    ConstantIssue,
    EnumOptionIssue,
)
from .._errors import MissingGenericsError, ValidationError
from .._common import cached_get_args, Empty
from .._registry import default_type_registry

from .base import BaseTypeHandler

__all__ = [
    "ClassVarHandler",
    "FinalHandler",
    "LiteralHandler",
]


@default_type_registry.register_type_handler(type_hint=ClassVar)
class ClassVarHandler(BaseTypeHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.type_hint_value is Empty:
            raise ValueError("type_hint_value must not be Empty")

    def build(self):
        from .._codec import Config

        args = cached_get_args(self.type_hint)
        if len(args) != 1:
            raise MissingGenericsError(
                f"Generic arg required but not given for {self.type_hint!r}",
            )
        self._type_handler = self.type_handler_registry.get_type_handler(
            type_hint=args[0], constraints=self.constraints
        )
        self.python_value = self.type_hint_value
        self.json_value, issues = self._type_handler.handle(
            value=self.type_hint_value,
            pointer=JsonPointer.root,
            included=True,
            excluded=False,
            config=Config(target="json", convert=True),
        )
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
        cvalue, cissues = self._type_handler.handle(
            value=value,
            pointer=pointer,
            included=included,
            excluded=excluded,
            config=config,
        )
        issues.extend(cissues)
        format = config.target if config.convert else config.source
        if format == "json":
            if cvalue != self.json_value:
                issues.append(
                    ConstantIssue(
                        value=cvalue,
                        pointer=pointer,
                        expected_value=self.json_value,
                    )
                )
        else:
            if cvalue != self.python_value:
                issues.extend(
                    ConstantIssue(
                        value=cvalue,
                        pointer=pointer,
                        expected_value=self.python_value,
                    )
                )
        if config.convert or config.coerce:
            return cvalue, issues
        return value, issues


@default_type_registry.register_type_handler(type_hint=Final)
class FinalHandler(ClassVarHandler): ...


@default_type_registry.register_type_handler(type_hint=Literal)
class LiteralHandler(BaseTypeHandler):
    def build(self):
        from .._codec import Config

        args = cached_get_args(self.type_hint)
        if len(args) < 1:
            raise MissingGenericsError(
                f"Generic arg(s) required but not given for {self.type_hint!r}",
            )
        self._struct_type_handlers = dict(
            (
                arg,
                self.type_handler_registry.get_type_handler(
                    type_hint=arg.__class__, constraints=self.constraints
                ),
            )
            for arg in args
        )
        self._python_options = frozenset(self._struct_type_handlers)
        issues = []
        self._json_type_handlers = {}
        for pyval, type_handler in self._struct_type_handlers.items():
            jsonval, jissues = type_handler.handle(
                value=pyval,
                pointer=JsonPointer.root,
                included=True,
                excluded=False,
                config=Config(target="json", convert=True),
            )
            issues.extend(jissues)
            self._json_type_handlers[jsonval] = type_handler
        self._json_options = frozenset(self._json_type_handlers.keys())
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
            try:
                type_handler = self._json_type_handlers[cvalue]
            except KeyError:
                return cvalue, [
                    EnumOptionIssue(
                        value=cvalue,
                        pointer=pointer,
                        options=self._json_options,
                    )
                ]
            cvalue, cissues = type_handler.handle(
                value=cvalue,
                pointer=pointer,
                included=included,
                excluded=excluded,
                config=config,
            )
            issues.extend(cissues)
        else:
            try:
                type_handler = self._struct_type_handlers[cvalue]
            except KeyError:
                return cvalue, [
                    EnumOptionIssue(
                        value=cvalue,
                        pointer=pointer,
                        options=self._python_options,
                    )
                ]
            cvalue, cissues = type_handler.handle(
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
