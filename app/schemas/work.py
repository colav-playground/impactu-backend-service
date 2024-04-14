from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas.general import Type, Updated, ExternalId, ExternalURL, QueryBase
from core.config import settings


class Title(BaseModel):
    title: str
    lang: str
    source: str


class BiblioGraphicInfo(BaseModel):
    bibtex: str | Any | None
    end_page: str | Any | None
    volume: str | int | None
    issue: str | Any | None
    open_access_status: str | Any | None
    pages: str | Any | None
    start_page: str | Any | None
    is_open_access: bool | Any | None
    open_access_status: str | None


class CitationsCount(BaseModel):
    source: str
    count: int


class Name(BaseModel):
    name: str
    lang: str


class Affiliation(BaseModel):
    id: str
    name: str
    types: list[Type] | None = Field(default_factory=list)


class Author(BaseModel):
    id: str
    full_name: str
    affiliations: list[Affiliation] | None = Field(default_affiliation=list)
    external_ids: list[ExternalId] | None = Field(default_factory=list)


class Source(BaseModel):
    id: str
    name: str | Any
    serials: Any | None = None


class SubjectEmbedded(BaseModel):
    id: str
    name: str | None
    level: int


class Subject(BaseModel):
    source: str
    subjects: list[SubjectEmbedded] | None = Field(default_factory=list)


class CitationByYear(BaseModel):
    cited_by_count: int | None
    year: int | None


class CitationsCount(BaseModel):
    source: str | None
    count: int | None


class WorkBase(BaseModel):
    id: str | None
    title: str | None = None
    authors: list[Author] = Field(default_factory=list)
    source: Source | None = Field(default_factory=dict)
    citations_count: list[CitationsCount]
    subjects: list[Subject] | list[dict[str, str]]


class WorkSearch(WorkBase):
    @field_validator("citations_count")
    @classmethod
    def sort_citations_count(cls, v: list[CitationsCount]):
        return list(sorted(v, key=lambda x: x.count, reverse=True))


class WorkProccessed(WorkSearch):
    abstract: str | None = ""
    year_published: int | None = None
    language: str | None = ""

    titles: list[Title] = Field(default_factory=list)

    @model_validator(mode="after")
    def get_title(self):
        self.title = next(
            filter(lambda x: x.lang == "en", self.titles), self.titles[0].title
        )
        return self

    year_published: int | None = None
    open_access_status: str | None = None
    bibliographic_info: BiblioGraphicInfo
    volume: str | int | None = None
    issue: str | None = None

    @model_validator(mode="after")
    def get_biblio_graphic_info(self):
        self.open_access_status = self.bibliographic_info.open_access_status
        self.volume = self.bibliographic_info.volume
        self.issue = self.bibliographic_info.issue
        self.bibliographic_info = None
        return self

    @field_validator("subjects")
    @classmethod
    def get_openalex_source(cls, v: list[Subject]):
        open_alex_subjects = list(filter(lambda x: x.source == "openalex", v))
        maped_embedded_subjects = list(map(lambda x: x.subjects, open_alex_subjects))
        return list(
            map(lambda x: {"name": x.name, "id": x.id}, *maped_embedded_subjects)
        )

    external_ids: list[ExternalId] | list[dict] | None = Field(default_factory=list)
    external_urls: list[ExternalURL] | None = Field(default_factory=list)
    openalex_url: str | None = None

    # Machete
    @model_validator(mode="before")
    @classmethod
    def get_openalex_url(cls, data: dict[str, Any]):
        openalex = next(
            filter(lambda x: x["source"] == "openalex", data["external_ids"]), None
        )
        if openalex:
            data["openalex_url"] = openalex["id"]
        return data

    @field_validator("external_ids")
    @classmethod
    def append_urls_external_ids(cls, v: list[ExternalId]):
        return list(
            map(
                lambda x: (
                    {
                        "id": x.id,
                        "source": x.source,
                        "url": settings.EXTERNAL_IDS_MAP.get(x.source, "").format(
                            id=x.id
                        ),
                    }
                ),
                filter(lambda x: x.source in settings.EXTERNAL_IDS_MAP, v),
            )
        )


class Work(BaseModel):
    updated: list[Updated] | None = Field(default_factory=list)
    subtitle: str
    abstract: str
    keywords: list[str] | None = Field(default_factory=list)
    types: list[Type] | None = Field(default_factory=list)
    external_ids: list[ExternalId] | None = Field(default_factory=list)
    external_urls: list[ExternalURL] | None = Field(default_factory=list)
    date_published: int
    year_published: int
    bibligraphic_info: list[BiblioGraphicInfo] | None = Field(default_factory=list)
    references_count: int | None
    references: list[Any] | None = Field(default_factory=list)
    citations: list[CitationsCount] | None = Field(default_factory=list)
    author_count: int

    citations_by_year: list[CitationByYear] | None = Field(default_factory=list)


class WorkQueryParams(QueryBase):
    start_year: int | None = None
    end_year: int | None = None
    institutions: str | None = None
    groups: str | None = None
    type: str | None = None
