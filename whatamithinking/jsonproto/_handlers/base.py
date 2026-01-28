from typing import Any, TYPE_CHECKING
import inspect
from types import MethodType

if TYPE_CHECKING:
    from .._codec import Config
    from .._registry import TypeRegistry

from .._pointers import JsonPointer
from .._issues import BaseIssue
from .._constraints import Encoding, DataTypeName, MediaTypeName, FormatName
from .._common import (
    TypeHintValue,
    Constraints,
    Empty,
)

__all__ = [
    "BaseTypeHandler",
]


class prebuild:
    # HACK: don't hate me ;(
    # wanted to lazily trigger build step at last possible second. this hacky solution
    # works great when super() is not used but gets a bit messy when it is. maybe circle
    # back and reconsider lazy build and instead build when type handler created?

    def __init__(self, owner, method) -> None:
        self._owner = owner
        self._method = method
        self._key = hash((owner, "handle"))

    def __get__(self, instance, owner):
        if instance is None:
            return self._method
        else:
            try:
                return instance.__dict__[self._key]
            except KeyError:
                # track if prepare has already been done for this method in this hierarchy
                # so calls to super().method() do not trigger prepare as well. should only be
                # done on the leaf node of the hierarchy.
                if not hasattr(instance, "_prebuilt"):
                    instance.build()
                    setattr(instance, "_prebuilt", True)
                method = MethodType(self._method, instance)
                # ASSUMPTION: TypeHandler.handle does nothing and is a template but exists in MRO
                # all direct children of it will not call super(). subsequent children may
                # we can unwrap this decorator permanently if super is never called, cutting runtime overhead
                if len([cls for cls in owner.__mro__ if "handle" in cls.__dict__]) <= 2:
                    instance.__dict__["handle"] = method
                # if more than one handle method we have to keep the descriptor and every call to the
                # method will pass through it doing a dictionary lookup
                else:
                    instance.__dict__[self._key] = method
                return method


class BaseTypeHandler:
    # schema info for use in generating the open api spec
    data_type: DataTypeName
    media_type: MediaTypeName | None = None
    format: FormatName | None = None
    encoding: Encoding | None = None

    def __init__(
        self,
        type_handler_registry: TypeRegistry,
        type_hint: type,
        constraints: Constraints,
        type_hint_value: TypeHintValue = Empty,
    ) -> None:
        self.type_handler_registry = type_handler_registry
        self.type_hint = type_hint
        self.constraints = constraints
        self.type_hint_value = type_hint_value

    def __repr__(self) -> str:
        thstr = (
            self.type_hint.__name__
            if inspect.isclass(self.type_hint)
            else str(self.type_hint)
        )
        return (
            f"{self.__class__.__name__}(codec={self.codec!r}, type_hint={thstr}, "
            f"constraints={self.constraints!r}, type_hint_value={self.type_hint_value!r})"
        )

    def __init_subclass__(cls) -> None:
        method = getattr(cls, "handle", None)
        if method is not None:
            setattr(cls, "handle", prebuild(cls, method))

    def build(self) -> None: ...

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | Empty, list[BaseIssue]]:
        raise NotImplementedError
