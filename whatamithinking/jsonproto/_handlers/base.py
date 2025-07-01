from typing import (
    Any,
    Callable,
    TypeVar,
    ParamSpec,
    TYPE_CHECKING,
    Self,
)
from types import MappingProxyType, MethodType
import weakref

if TYPE_CHECKING:
    from .._codec import Codec, Config

from .._pointers import JsonPointer
from .._issues import BaseIssue
from .._constraints import T_Encoding, T_DataType, T_MediaType, T_Format
from .._common import (
    T_TypeHintValue,
    T_ResolvedTypeHint,
    T_IsTypeCallback,
    Constraints,
    MISSING,
    MISSING_TYPE,
)
from .._resolver import resolve_type_hint

__all__ = [
    "TypeHandler",
    "default_type_hint_handler_classes",
    "default_callback_handler_classes",
]


T_DataPointer = TypeVar("T_DataPointer")
T_Value = TypeVar("T_Value")
P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")


_default_type_hint_handler_classes: dict[T_ResolvedTypeHint, type["TypeHandler"]] = {}
_default_callback_handler_classes: dict[T_IsTypeCallback, type["TypeHandler"]] = {}


def default_type_hint_handler_classes():
    return MappingProxyType(_default_type_hint_handler_classes)


def default_callback_handler_classes():
    return MappingProxyType(_default_callback_handler_classes)


def register_default_type_handler(
    type_hint: T_ResolvedTypeHint | MISSING_TYPE = MISSING,
    callback: T_IsTypeCallback | MISSING_TYPE = MISSING,
) -> Callable[[type[T]], type[T]]:
    if type_hint is MISSING and callback is MISSING:
        raise ValueError("one of type_hint or callback must be given")
    elif type_hint is not MISSING and callback is not MISSING:
        raise ValueError("either type_hint or callback must be given, not both")

    def register_default_type_handler_wrapper(type_handler_class: type[T]) -> type[T]:
        if type_hint is not MISSING:
            thr = resolve_type_hint(type_hint=type_hint)
            if thr.is_partial:
                raise TypeError(
                    "stringified types not supported during type handler registration"
                )
            _default_type_hint_handler_classes[thr.type_hint] = type_handler_class
        else:
            _default_callback_handler_classes[callback] = type_handler_class
        return type_handler_class

    return register_default_type_handler_wrapper


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


class TypeHandler:
    # schema info for use in generating the open api spec
    data_type: T_DataType
    media_type: T_MediaType | None = None
    format: T_Format | None = None
    encoding: T_Encoding | None = None

    def __init__(
        self,
        codec: "Codec",
        type_hint: type,
        constraints: Constraints,
        type_hint_value: T_TypeHintValue = MISSING,
    ) -> None:
        self._codec = weakref.ref(codec)
        self.type_hint = type_hint
        self.constraints = constraints
        self.type_hint_value = type_hint_value

    def __init_subclass__(cls) -> None:
        method = getattr(cls, "handle", None)
        if method is not None:
            setattr(cls, "handle", prebuild(cls, method))

    @property
    def codec(self) -> "Codec":
        return self._codec()

    def get_type_handler(
        self,
        type_hint: type,
        constraints: Constraints = Constraints.empty,
        type_hint_value: T_TypeHintValue = MISSING,
    ) -> Self:
        return self.codec.get_type_handler(
            type_hint=type_hint,
            constraints=constraints,
            type_hint_value=type_hint_value,
        )

    def build(self) -> None: ...

    def handle(
        self,
        value: Any,
        pointer: JsonPointer,
        included: bool,
        excluded: bool,
        config: "Config",
    ) -> tuple[Any | MISSING_TYPE, list[BaseIssue]]:
        raise NotImplementedError
