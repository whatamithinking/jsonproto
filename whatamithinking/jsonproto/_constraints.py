from typing import Literal, Any, ClassVar, Callable
from decimal import Decimal
import re

from ._struct import struct, field
from ._common import BaseConstraint, make_cache_key, cached_get_args


__all__ = [
    "MediaTypeName",
    "EncodingName",
    "FormatName",
    "DataTypeName",
    "Value",
    "Length",
    "Alias",
    "Title",
    "Summary",
    "Description",
    "Pattern",
    "Discriminator",
    "Encoding",
    "Format",
    "Deprecated",
    "Example",
    "Status",
    "Default",
    "DefaultFactory",
    "MediaType",
    "DataType",
    "Contact",
    "Server",
    "Interface",
    "Disjoint",
    "Dependent",
    "Required",
]


ConstraintType = Literal[
    "value",
    "length",
    "alias",
    "title",
    "summary",
    "description",
    "pattern",
    "discriminator",
    "encoding",
    "format",
    "deprecated",
    "example",
    "status",
    "default",
    "default_factory",
    "media_type",
    "data_type",
    "contact",
    "server",
    "interface",
    "disjoint",
    "dependent",
    "required",
]
ConstraintId = Literal[
    "value_eq",
    "value_gt",
    "value_ge",
    "value_le",
    "value_lt",
    "length_eq",
    "length_gt",
    "length_ge",
    "length_le",
    "length_lt",
    "alias",
    "title",
    "summary",
    "description",
    "pattern",
    "discriminator",
    "encoding_base64",
    "encoding_base32",
    "encoding_base32hex",
    "encoding_base16",
    "format_date_time",
    "format_date",
    "format_time",
    "format_duration",
    "format_email",
    "format_hostname",
    "format_ipv4",
    "format_ipv6",
    "format_uri",
    "format_uri_reference",
    "format_uuid",
    "format_regex",
    "format_int32",
    "format_int64",
    "format_float",
    "format_double",
    "format_password",
    "deprecated",
    "example",
    "status",
    "default",
    "default_factory",
    "media_type_text_plain",
    "media_type_application_json",
    "media_type_application_octet_stream",
    "media_type_multipart_form_data",
    "data_type_integer",
    "data_type_number",
    "data_type_string",
    "data_type_boolean",
    "data_type_null",
    "data_type_array",
    "data_type_object",
    "contact",
    "server",
    "interface",
    "disjoint",
    "dependent",
    "required",
]


ValueComparator = Literal["eq", "gt", "ge", "le", "lt"]
ValueConstraintId = Literal[
    "value_eq",
    "value_gt",
    "value_ge",
    "value_le",
    "value_lt",
]
_value_comparators = dict(
    zip(cached_get_args(ValueComparator), cached_get_args(ValueConstraintId))
)


# NOTE: originally had a metaclass for Value and Length so i could use syntax like Value >= 0
# but there was performance hit of ~20-30us per instantiation, roughly, chewing through a lot of
# the gains made by lazy building classes, so decided to go back to the slightly less awesome
# syntax where we just pass in the comparator and value to the class instance instead


@struct(kw_only=False)
class Value(BaseConstraint):
    comparator: ValueComparator
    value: int | float | Decimal
    constraint_type: ClassVar[str] = "value"

    def _post_init_(self) -> None:
        if not isinstance(self.value, (int, float, Decimal)):
            raise TypeError(
                f"Value constraint value must be int/float/Decimal, not {self.value.__class__.__name__}"
            )

    @field(cache=True)
    def constraint_id(self) -> ValueConstraintId:
        return _value_comparators[self.comparator]


LengthComparator = Literal["eq", "gt", "ge", "le", "lt"]
LengthConstraintId = Literal[
    "length_eq",
    "length_gt",
    "length_ge",
    "length_le",
    "length_lt",
]
_length_comparators = dict(
    zip(cached_get_args(LengthComparator), cached_get_args(LengthConstraintId))
)


@struct(kw_only=False)
class Length(BaseConstraint):
    comparator: LengthComparator
    value: int
    constraint_type: ClassVar[str] = "length"

    def _post_init_(self) -> None:
        if not isinstance(self.value, int):
            raise TypeError(
                f"Length constraint value must be int, not {self.value.__class__.__name__}"
            )
        if self.value < 0:
            raise ValueError(
                f"Length constraint value must be greater than or equal to zero, not {self.value}"
            )

    @field(cache=True)
    def constraint_id(self) -> LengthConstraintId:
        return _length_comparators[self.comparator]


@struct(kw_only=False)
class Alias(BaseConstraint):
    value: str
    constraint_type: ClassVar[str] = "alias"
    constraint_id: ClassVar[str] = "alias"


@struct(kw_only=False)
class Title(BaseConstraint):
    value: str
    constraint_type: ClassVar[str] = "title"
    constraint_id: ClassVar[str] = "title"


@struct(kw_only=False)
class Summary(BaseConstraint):
    value: str
    constraint_type: ClassVar[str] = "summary"
    constraint_id: ClassVar[str] = "summary"


@struct(kw_only=False)  # type: ignore
class Description(BaseConstraint):  # type: ignore
    value: str  # type: ignore
    constraint_type: ClassVar[str] = "description"
    constraint_id: ClassVar[str] = "description"


@struct(kw_only=False)
class Pattern(BaseConstraint):
    """Constrain the value to matching a specific regular expression pattern, per jsonschema
    regex subset.

    There are both different regex features supported as well as slight meaning changes between
    python and jsonschema regex. This makes trustworthy validation of patterns used
    challenging without a compiler supporting just this subset, which does not currently seem
    to exist in python. Please follow the [docs](https://json-schema.org/understanding-json-schema/reference/regular_expressions#regular-expressions) to ensure your regex is compliant and works the
    same across languages.
    """

    value: str
    constraint_type: ClassVar[str] = "pattern"
    constraint_id: ClassVar[str] = "pattern"

    @field(cache=True)
    def pattern(self) -> re.Pattern:
        return re.compile(self.value)  # type: ignore


# NOTE: there is no constant constraint because Literal/ClassVar/Final can be used instead
# NOTE: there is no unique constraint because the same can be accomplished with a set


@struct(kw_only=False)
class Discriminator(BaseConstraint):
    field_name: str
    constraint_type: ClassVar[str] = "discriminator"
    constraint_id: ClassVar[str] = "discriminator"

    def _post_init_(self) -> None:
        # possible someone might try to use mapping option for this, which is defined in spec
        # but not supported here at the moment. make sure they dont.
        if not isinstance(self.field_name, str):
            raise TypeError("Discriminator must be string")


# per https://www.rfc-editor.org/rfc/rfc4648
# non-exhaustive. add more as needed
EncodingName = Literal[
    "base64",
    "base32",
    "base32hex",
    "base16",
]
EncodingConstraintId = Literal[
    "encoding_base64",
    "encoding_base32",
    "encoding_base32hex",
    "encoding_base16",
]
_encodings = dict(
    zip(cached_get_args(EncodingName), cached_get_args(EncodingConstraintId))
)


@struct(kw_only=False)
class Encoding(BaseConstraint):
    value: EncodingName
    constraint_type: ClassVar[str] = "encoding"

    @field(cache=True)
    def constraint_id(self) -> EncodingConstraintId:
        return _encodings[self.value]


# per https://datatracker.ietf.org/doc/html/draft-bhutton-json-schema-validation-00#section-7.3
# some options are omitted if they are not yet supported by this implementation
DateTimeFormatName = Literal["date-time", "date", "time", "duration"]
EmailFormatName = Literal["email"]
HostnameFormatName = Literal["hostname"]
IpAddressFormatName = Literal[
    "ipv4",
    "ipv6",
]
UriFormatName = Literal[
    "uri",
    "uri-reference",
]
UuidFormatName = Literal["uuid"]
RegexFormatName = Literal["regex"]
# per OAS https://spec.openapis.org/oas/v3.1.0#dataTypeFormat
NumberFormatName = Literal[
    "int32",
    "int64",
    "float",
    "double",
]
# per OAS https://spec.openapis.org/oas/v3.1.0#dataTypeFormat
PasswordFormatName = Literal["password"]
FormatName = (
    DateTimeFormatName
    | EmailFormatName
    | HostnameFormatName
    | IpAddressFormatName
    | UriFormatName
    | UuidFormatName
    | RegexFormatName
    | NumberFormatName
    | PasswordFormatName
)
FormatConstraintId = Literal[
    "format_date_time",
    "format_date",
    "format_time",
    "format_duration",
    "format_email",
    "format_hostname",
    "format_ipv4",
    "format_ipv6",
    "format_uri",
    "format_uri_reference",
    "format_uuid",
    "format_regex",
    "format_int32",
    "format_int64",
    "format_float",
    "format_double",
    "format_password",
]
_formats = dict(
    (fval, f"format_{fval.replace('-', '_')}")
    for t_format in cached_get_args(FormatName)
    for fval in cached_get_args(t_format)
)


@struct(kw_only=False)
class Format(BaseConstraint):
    value: FormatName
    constraint_type: ClassVar[str] = "format"

    def _post_init_(self) -> None:
        if self.value not in _formats:
            raise ValueError(f"Format, {self.value}, not valid")

    @field(cache=True)
    def constraint_id(self) -> FormatConstraintId:
        return _formats[self.value]


# need deprecated constraint in addition to @deprecated decorator in order
# to handle deprecation of individual parameters as well as entire operations
@struct(kw_only=False)
class Deprecated(BaseConstraint):
    value: bool = True
    constraint_type: ClassVar[str] = "deprecated"
    constraint_id: ClassVar[str] = "deprecated"


@struct(kw_only=False)
class Example(BaseConstraint):
    value: Any
    name: str | None = None
    summary: str | None = None
    description: str | None = None
    constraint_type: ClassVar[str] = "example"
    constraint_id: ClassVar[str] = "example"


@struct(kw_only=False)
class Status(BaseConstraint):
    status: int
    constraint_type: ClassVar[str] = "status"
    constraint_id: ClassVar[str] = "status"

    def _post_init_(self) -> None:
        from http.client import responses as http_codes

        try:
            http_codes[self.status]
        except KeyError:
            raise ValueError(f"Http status code, {self.status}, is not valid")


@struct(kw_only=False)
class Default(BaseConstraint):
    value: Any
    constraint_type: ClassVar[str] = "default"
    constraint_id: ClassVar[str] = "default"


@struct(kw_only=False)
class DefaultFactory(BaseConstraint):
    value: Callable[[], Any]
    constraint_type: ClassVar[str] = "default_factory"
    constraint_id: ClassVar[str] = "default_factory"


# https://developer.mozilla.org/en-US/docs/Web/HTTP/Basics_of_HTTP/MIME_types/Common_types
# non-exhaustive list, but if we need more we can add them. if problematic, can allow generic str type
MediaTypeName = Literal[
    "text/plain", "application/json", "application/octet-stream", "multipart/form-data"
]
MediaTypeConstraintId = Literal[
    "media_type_text_plain",
    "media_type_application_json",
    "media_type_application_octet_stream",
    "media_type_multipart_form_data",
]
_media_types = dict(
    (mt, f"media_type_{mt.replace("/", "_").replace("-", "_")}")
    for mt in cached_get_args(MediaTypeName)
)


@struct(kw_only=False)
class MediaType(BaseConstraint):
    value: MediaTypeName
    constraint_type: ClassVar[str] = "media_type"

    def _post_init_(self) -> None:
        if self.value not in _media_types:
            raise ValueError(f"Media type, {self.value!r}, is not valid")

    @field(cache=True)
    def constraint_id(self) -> MediaTypeConstraintId:
        return _media_types[self.value]


DataTypeName = Literal[
    "integer", "number", "string", "boolean", "null", "array", "object"
]
DataTypeConstraintId = Literal[
    "data_type_integer",
    "data_type_number",
    "data_type_string",
    "data_type_boolean",
    "data_type_null",
    "data_type_array",
    "data_type_object",
]
_data_types = dict(zip(cached_get_args(DataTypeName), DataTypeConstraintId))


@struct(kw_only=False)
class DataType(BaseConstraint):
    value: DataTypeName
    constraint_type: ClassVar[str] = "data_type"

    def _post_init_(self) -> None:
        if self.value not in _data_types:
            raise ValueError(
                f"The given value, {self.value!r}, was not a valid OpenAPI data type"
            )

    @field(cache=True)
    def constraint_id(self) -> DataTypeConstraintId:
        return _data_types[self.value]


@struct(kw_only=False)
class Contact(BaseConstraint):
    name: str
    url: str | None = None
    email: str | None = None
    constraint_type: ClassVar[str] = "contact"
    constraint_id: ClassVar[str] = "contact"


@struct(kw_only=False)
class Server(BaseConstraint):
    url: str
    description: str | None = None
    constraint_type: ClassVar[str] = "server"
    constraint_id: ClassVar[str] = "server"


@struct(kw_only=False)
class Interface(BaseConstraint):
    title: str
    version: str
    summary: str | None = None
    description: str | None = None
    constraint_type: ClassVar[str] = "interface"
    constraint_id: ClassVar[str] = "interface"


# model-level constraint only!
# only one of these fields may be given at the same time when constructing the model
# ex: user is performing a search and has two fields to key off of, route_id and route_name,
# we will only use on them to perform the search so we need to make sure only one at a time
# is allowed to avoid confusion of user in results returned when both are given
@struct(kw_only=False, init=False)
class Disjoint(BaseConstraint):
    field_names: frozenset[str]
    constraint_type: ClassVar[str] = "disjoint"
    constraint_id: ClassVar[str] = "disjoint"

    def __init__(self, *field_names: str) -> None:
        object.__setattr__(self, "field_names", frozenset(field_names))
        if len(self.field_names) <= 1:
            raise ValueError("At least two field names must be given")


# dependent events where if one event happens the other must happen
# allow the current model field to depend on other fields being given if it is given
# this allows us to avoid having to create a submodel and keep a flat structure
# ex: someone is performing a search and gives me their street address but to complete
# the search i also need their zip code/state/country, so i need to make sure they
# have filled in those other fields
@struct(kw_only=False, init=False)
class Dependent(BaseConstraint):
    field_names: frozenset[str]
    constraint_type: ClassVar[str] = "dependent"
    constraint_id: ClassVar[str] = "dependent"

    def __init__(self, *field_names: str) -> None:
        object.__setattr__(self, "field_names", frozenset(field_names))
        if len(self.field_names) <= 1:
            raise ValueError("At least two field names must be given")


@struct(kw_only=False)
class Required(BaseConstraint):
    value: bool
    constraint_type: ClassVar[str] = "required"
    constraint_id: ClassVar[str] = "required"
