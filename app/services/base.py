from typing import Generic, TypeVar, Any, Type
from json import loads

from odmantic import Model
from pydantic import BaseModel

from infraestructure.mongo.repositories.base import RepositorieBase
from schemas.general import QueryBase, GeneralMultiResponse


ModelType = TypeVar("ModelType", bound=Model)
RepositoryType = TypeVar("RepositoryType", bound=RepositorieBase)
ParamsType = TypeVar("ParamsType", bound=QueryBase)
SearchType = TypeVar("SearchType", bound=BaseModel)


class ServiceBase(Generic[ModelType, RepositoryType, ParamsType, SearchType]):
    def __init__(self, repository: RepositoryType, search_class: SearchType):
        self.repository = repository
        self.search_class = search_class

    def get_all(self, *, params: ParamsType) -> dict[str, Any]:
        db_objs = self.repository.get_all(
            query={}, skip=params.skip, limit=params.limit, sort=params.sort
        )
        total_results = self.repository.count()
        results = GeneralMultiResponse(total_results=total_results)
        results.data = db_objs
        return loads(results.model_dump_json())

    def get_by_id(self, *, id: str) -> dict[str, Any]:
        db_obj = self.repository.get_by_id(id=id)
        return loads(db_obj.model_dump_json())

    def search(self, *, params: ParamsType) -> GeneralMultiResponse[Type[SearchType]]:
        db_objs, count = self.repository.search(
            keywords=params.keywords,
            skip=params.skip,
            limit=params.limit,
            sort=params.sort,
            search=params.get_search
        )
        results = GeneralMultiResponse[Type[SearchType]](total_results=count)
        results.data = [self.search_class(**obj) for obj in db_objs]
        return loads(results.model_dump_json(exclude_none=True))
