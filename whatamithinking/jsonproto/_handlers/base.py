from typing import Any, Callable, TypeVar, ParamSpec, TYPE_CHECKING, Self, overload
import inspect
from types import MethodType
import weakref

if TYPE_CHECKING:
    from .._codec import Codec, Config

from .._errors import TypeHandlerMissingError
from .._pointers import JsonPointer
from .._issues import BaseIssue
from .._constraints import T_Encoding, T_DataType, T_MediaType, T_Format
from .._common import (
    TypeHintValue,
    ResolvedTypeHint,
    IsTypeCallback,
    Constraints,
    Empty,
)
from .._resolver import resolve_type_hint, TypeHintResolution, FuzzyTypeHint

__all__ = [
    "TypeHandlerRegistry",
    "default_type_handler_registry",
    "TypeHandler",
]


T_DataPointer = TypeVar("T_DataPointer")
T_Value = TypeVar("T_Value")
P = ParamSpec("P")
R = TypeVar("R")
T = TypeVar("T")
T_TypeHandlerRegisterCallback = Callable[
    [type["TypeHandler"], ResolvedTypeHint | Empty, IsTypeCallback | Empty], None
]


class TypeHandlerRegistry:

    def __init__(self, *registries: "TypeHandlerRegistry") -> None:
        self._cache_handler_classes: dict[FuzzyTypeHint, type["TypeHandler"]] = {}
        self._type_hint_handler_classes: dict[ResolvedTypeHint, type["TypeHandler"]] = (
            {}
        )
        self._callback_handler_classes: dict[IsTypeCallback, type["TypeHandler"]] = {}
        self._register_callbacks = list[weakref.ref[T_TypeHandlerRegisterCallback]]()
        # clear cache so we return the latest type handler class registered
        # unlikely to really be a problem in practice but because we are caching we are now
        # open late registrations potentially changing things up after the fact
        self.add_register_callback(self._cache_handler_classes.clear)
        self._registries = registries
        for registry in self._registries:
            registry.add_register_callback(self._cache_handler_classes.clear)

    def add_register_callback(self, callback: T_TypeHandlerRegisterCallback, /) -> None:
        if inspect.ismethod(callback):
            register_callback_ref = weakref.WeakMethod(callback)
        else:
            register_callback_ref = weakref.ref(callback)
        self._register_callbacks.append(register_callback_ref)

    def call_register_callbacks(
        self,
        type_handler_class: type[T] | Empty,
        type_hint: ResolvedTypeHint | Empty,
        callback: IsTypeCallback | Empty,
    ) -> None:
        for i in range(len(self._register_callbacks) - 1, -1, -1):
            register_callback = self._register_callbacks[i]()
            if register_callback is None:
                del self._register_callbacks[i]
            else:
                register_callback(
                    type_handler_class=type_handler_class,
                    type_hint=type_hint,
                    callback=callback,
                )

    @overload
    def register(
        self,
        type_handler_class: type[T],
        /,
        *,
        type_hint: ResolvedTypeHint | Empty = Empty,
        callback: IsTypeCallback | Empty = Empty,
    ) -> type[T]: ...

    @overload
    def register(
        self,
        type_handler_class: Empty = Empty,
        /,
        *,
        type_hint: ResolvedTypeHint | Empty = Empty,
        callback: IsTypeCallback | Empty = Empty,
    ) -> Callable[[type[T]], type[T]]: ...

    def register(
        self,
        type_handler_class: type[T] | Empty = Empty,
        /,
        *,
        type_hint: ResolvedTypeHint | Empty = Empty,
        callback: IsTypeCallback | Empty = Empty,
    ) -> type[T] | Callable[[type[T]], type[T]]:
        if type_hint is Empty and callback is Empty:
            raise ValueError("one of type_hint or callback must be given")
        elif type_hint is not Empty and callback is not Empty:
            raise ValueError("either type_hint or callback must be given, not both")

        def register_type_handler_wrapper(type_handler_class: type[T], /) -> type[T]:
            if type_hint is not Empty:
                thr = resolve_type_hint(type_hint=type_hint)
                if thr.is_partial:
                    raise TypeError(
                        "stringified types not supported during type handler registration"
                    )
                self._type_hint_handler_classes[thr.type_hint] = type_handler_class
            else:
                self._callback_handler_classes[callback] = type_handler_class
            self.call_register_callbacks()
            return type_handler_class

        # if called like a function with type handler class given
        if type_handler_class is not Empty:
            return register_type_handler_wrapper(type_handler_class)
        else:  # if used as decorator, where type handler class will be empty
            return register_type_handler_wrapper

    def get(self, type_hint_resolution: TypeHintResolution) -> type["TypeHandler"]:
        try:
            return self._cache_handler_classes[type_hint_resolution.type_hint]
        except KeyError:
            # note that we start by looking for handlers of the more specific type hint
            # and fallback to the less specific without the generic types, since
            # these shell types usually themselves call in this method to handle
            # generic types handling
            type_hint_options = [
                type_hint_resolution.original_type_hint,
                type_hint_resolution.type_hint,
            ]
            if (origin := type_hint_resolution.origin) is not None:
                type_hint_options.append(origin)
            type_hint_class = None
            for type_hint_option in type_hint_options:
                if type_hint_class := self._type_hint_handler_classes.get(
                    type_hint_option
                ):
                    break
                for is_type, thc in self._callback_handler_classes.items():
                    if not is_type(type_hint_option):
                        continue
                    type_hint_class = thc
                    break
                if type_hint_class:
                    break
            else:
                # we cache results from other registries as well so we can avoid searching through them
                # each time. don't think this should generally create problems as i don't see any need
                # to be changing type handlers returned on the fly from one call to the next
                for registry in self._registries:
                    try:
                        type_hint_class = registry.get(
                            type_hint_resolution=type_hint_resolution
                        )
                        break
                    except TypeHandlerMissingError:
                        continue
                else:
                    raise TypeHandlerMissingError(
                        f"No type handler class found supporting {type_hint_resolution.original_type_hint!r}"
                    )
            self._cache_handler_classes[type_hint_resolution.original_type_hint] = (
                type_hint_class
            )
            self._cache_handler_classes[type_hint_option] = type_hint_class
            return type_hint_class


default_type_handler_registry = TypeHandlerRegistry()


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
        type_hint_value: TypeHintValue = Empty,
    ) -> None:
        self._codec = weakref.ref(codec)
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

    @property
    def codec(self) -> "Codec":
        return self._codec()

    def get_type_handler(
        self,
        type_hint: type,
        constraints: Constraints = Constraints.empty,
        type_hint_value: TypeHintValue = Empty,
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
    ) -> tuple[Any | Empty, list[BaseIssue]]:
        raise NotImplementedError
