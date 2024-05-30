from odmantic import EmbeddedModel, ObjectId
from odmantic.bson import BaseBSONModel


class Type(EmbeddedModel):
    source: str | None = None
    type: str | None = None


class Updated(EmbeddedModel):
    time: int | None = None
    source: str | None = None

class Identifier(EmbeddedModel):
    COD_RH: str

class ExternalId(EmbeddedModel):
    id: str | int | list[str] | Identifier = None
    source: str | None = None
    provenance: str | None = None


class ExternalURL(EmbeddedModel):
    url: str | int | None = None
    source: str | None = None


class Name(BaseBSONModel):
    name: str | None = None
    lang: str | None = None


class Status(BaseBSONModel):
    source: str | None = None
    status: str | None = None
