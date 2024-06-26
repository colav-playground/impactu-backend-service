from math import nan
from typing import Any, Callable

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING

from infraestructure.mongo.utils.session import client
from infraestructure.mongo.repositories.work import WorkRepository
from infraestructure.mongo.repositories.affiliation import (
    AffiliationRepository,
    affiliation_repository,
)
from core.config import settings
from utils.bars import bars
from utils.maps import maps
from utils.pies import pies
from schemas.affiliation import AffiliationRelatedInfo


class AffiliationAppService:
    def __init__(self):
        self.colav_db = client[settings.MONGO_INITDB_DATABASE]
        self.impactu_db = client[settings.MONGO_IMPACTU_DB]
        self.bars = bars()
        self.pies = pies()
        self.maps = maps()

    def get_info(self, idx, typ, start_year=None, end_year=None):

        pipeline = [
            {"$match": {"_id": ObjectId(idx)}},
            {
                "$project": {
                    "_id": 1,
                    "names": 1,
                    "citations": 1,
                    "external_urls": 1,
                    "types": 1,
                    "external_ids": 1,
                    "addresses": 1,
                    "relations": 1,
                }
            },
        ]

        affiliation = next(self.colav_db["affiliations"].aggregate(pipeline), None)
        if affiliation:
            name = ""
            for n in affiliation["names"]:
                if n["lang"] == "es":
                    name = n["name"]
                    break
                elif n["lang"] == "en":
                    name = n["name"]
            logo = ""
            for ext in affiliation["external_urls"]:
                if ext["source"] == "logo":
                    logo = ext["url"]

            entry = {
                "id": affiliation["_id"],
                "name": name,
                "citations_count": WorkRepository.count_citations(
                    affiliation_id=affiliation["_id"],
                    affiliation_type=affiliation["types"][0]["type"],
                ),
                "products_count": WorkRepository.count_papers(
                    affiliation_id=affiliation["_id"],
                    affiliation_type=affiliation["types"][0]["type"],
                ),
                "external_urls": [
                    ext
                    for ext in affiliation["external_urls"]
                    if ext["source"] != "logo"
                ],
                "external_ids": affiliation["external_ids"],
                "types": affiliation["types"],
                "addresses": affiliation["addresses"],
                "logo": logo,
            }
            
            entry.update({"affiliations": AffiliationRepository.upside_relations(affiliation["relations"], typ)})

            return {"data": entry}
        else:
            return None

    def get_affiliations(self, idx, typ=None, aff_type: str | None = None) -> dict[str, list[Any]]:
        data = {}
        if typ == "institution":
            data["faculties"] = affiliation_repository.get_affiliations_related_type(idx, "faculty", typ)
        if typ in ["faculty", "institution"]:
            data["departments"] = affiliation_repository.get_affiliations_related_type(idx, "department", typ)
        if typ in ["department", "faculty", "institution"]:
            data["groups"] = affiliation_repository.get_affiliations_related_type(idx, "group", typ)
        if typ in ["group", "department", "faculty"]:
            data["authors"] = affiliation_repository.get_authors_by_affiliation(idx, typ)
        

        result = AffiliationRelatedInfo.model_validate(data, from_attributes=True)
        
        return result.model_dump(exclude_none=True)

    def process_work(self, work):
        paper = {
            "id": work["_id"],
            "title": "",
            "authors": [],
            "source": {},
            "year_published": (
                work["year_published"] if "year_published" in work.keys() else None
            ),
            "citations_count": work["citations_count"],
            "open_access_status": (
                work["bibliographic_info"]["open_access_status"]
                if "open_access_status" in work["bibliographic_info"]
                else ""
            ),
            "subjects": [],
            "external_ids": work["external_ids"]
        }

        paper["title"] = work["titles"][0]["title"] if "titles" in work.keys() else ""
        for w in work["titles"]:
            if w["lang"] in ["es", "en"]:
                paper["title"] = w["title"]
                break

        if "source" in work.keys():
            if "id" in work["source"].keys():
                if "name" in work["source"].keys() and isinstance(
                    work["source"].get("name", ""), str
                ):
                    paper["source"] = {
                        "name": work["source"].get("name", ""),
                        "id": work["source"]["id"],
                    }
                elif "names" in paper["source"].keys():
                    paper["source"] = {
                        "name": work["source"]["names"][0].get("name", ""),
                        "id": work["source"]["id"],
                    }

        for subs in work["subjects"]:
            if subs["source"] == "openalex":
                for sub in subs["subjects"]:
                    name = sub.get("name", "no subject name founded in db")
                    paper["subjects"].append({"name": name, "id": sub["id"]})
                break

        authors = []
        for author in work["authors"]:
            au_entry = author.copy()
            if not "affiliations" in au_entry.keys():
                au_entry["affiliations"] = []
            author_db = None
            if "id" in author.keys():
                if author["id"] == "":
                    continue
                author_db = self.colav_db["person"].find_one({"_id": author["id"]})
            else:
                continue
            if author_db:
                au_entry = {
                    "id": author_db["_id"],
                    "full_name": author_db["full_name"],
                    "external_ids": [
                        ext
                        for ext in author_db["external_ids"]
                        if not ext["source"]
                        in ["Cédula de Ciudadanía", "Cédula de Extranjería", "Passport"]
                    ],
                }
            affiliations = []
            aff_ids = []
            aff_types = []
            for aff in author["affiliations"]:
                if "id" in aff.keys():
                    if aff["id"]:
                        aff_db = self.colav_db["affiliations"].find_one(
                            {"_id": aff["id"]}
                        )
                        if aff_db:
                            aff_ids.append(aff["id"])
                            aff_entry = {"id": aff_db["_id"], "name": ""}
                            if author_db:
                                for aff_au in author_db["affiliations"]:
                                    if aff_au["id"] == aff["id"]:
                                        if "start_date" in aff_au.keys():
                                            aff_entry["start_date"] = aff_au[
                                                "start_date"
                                            ]
                                        if "end_date" in aff_au.keys():
                                            aff_entry["end_date"] = aff_au["end_date"]
                                        break
                            name = aff_db["names"][0]["name"]
                            lang = ""
                            for n in aff_db["names"]:
                                if "lang" in n.keys():
                                    if n["lang"] == "es":
                                        name = n["name"]
                                        lang = n["lang"]
                                        break
                                    elif n["lang"] == "en":
                                        name = n["name"]
                                        lang = n["lang"]
                            aff["name"] = name
                            if "types" in aff.keys():
                                for typ in aff["types"]:
                                    if "type" in typ.keys():
                                        if not typ["type"] in aff_types:
                                            aff_types.append(typ["type"])
                            affiliations.append(aff)
            if author_db:
                for aff in author_db["affiliations"]:
                    if aff["id"] in aff_ids:
                        continue
                    if aff["id"]:
                        aff_db = self.colav_db["affiliations"].find_one(
                            {"_id": aff["id"]}
                        )
                        inst_already = False
                        if aff_db:
                            if "types" in aff_db.keys():
                                for typ in aff_db["types"]:
                                    if "type" in typ.keys():
                                        if typ["type"] in aff_types:
                                            inst_already = True
                            if inst_already:
                                continue
                            aff_ids.append(aff["id"])
                            aff_entry = {"id": aff_db["_id"], "name": ""}
                            name = aff_db["names"][0]["name"]
                            lang = ""
                            for n in aff_db["names"]:
                                if "lang" in n.keys():
                                    if n["lang"] == "es":
                                        name = n["name"]
                                        lang = n["lang"]
                                        break
                                    elif n["lang"] == "en":
                                        name = n["name"]
                                        lang = n["lang"]
                            aff["name"] = name
                            affiliations.append(aff)
            au_entry["affiliations"] = affiliations
            authors.append(au_entry)
        paper["authors"] = authors

        return paper

    def get_research_products(
        self,
        idx,
        typ=None,
        start_year=None,
        end_year=None,
        page=None,
        max_results=None,
        sort=None,
        direction="descending",
    ):
        papers = []
        total = 0
        open_access = []

        if start_year:
            try:
                start_year = int(start_year)
            except:
                print("Could not convert start year to int")
                return None
        if end_year:
            try:
                end_year = int(end_year)
            except:
                print("Could not convert end year to int")
                return None

        if not page:
            page = 1
        else:
            try:
                page = int(page)
            except:
                print("Could not convert end page to int")
                return None
        if not max_results:
            max_results = 100
        else:
            try:
                max_results = int(max_results)
            except:
                print("Could not convert option max to int")
                return None
        if max_results > 250:
            max_results = 250

        if typ:
            if typ != "institution":
                work_ids = []
                match_works = {}
                if start_year or end_year:
                    match_works["works.year_published"] = {}
                if start_year:
                    match_works["works.year_published"]["$gte"] = start_year
                if end_year:
                    match_works["works.year_published"]["$lte"] = end_year
                search_pipeline = [
                    {"$match": {"affiliations.id": ObjectId(idx)}},
                    {"$project": {"affiliations": 1, "full_name": 1, "_id": 1}},
                    {
                        "$lookup": {
                            "from": "works",
                            "localField": "_id",
                            "foreignField": "authors.id",
                            "as": "works",
                        }
                    },
                    {"$unwind": "$works"},
                    {"$match": match_works},
                    {"$group": {"_id": "$works._id", "works": {"$first": "$works"}}},
                    {
                        "$project": {
                            "works._id": 1,
                            "works.citations_count": 1,
                            "works.year_published": 1,
                            "works.titles": 1,
                            "works.source": 1,
                            "works.authors": 1,
                            "works.subjects": 1,
                            "works.bibliographic_info": 1,
                            "works.external_ids": 1
                        }
                    },
                    {
                        "$sort": "works.titles.title"
                    }
                ]

                if sort == "citations" and direction == "ascending":
                    search_pipeline.append(
                        {"$sort": {"works.citations_count.count": ASCENDING}}
                    )
                elif sort == "citations" and direction == "descending":
                    search_pipeline.append(
                        {"$sort": {"works.citations_count.count": DESCENDING}}
                    )
                elif sort == "year" and direction == "ascending":
                    search_pipeline.append(
                        {"$sort": {"works.year_published": ASCENDING}}
                    )
                elif sort == "year" and direction == "descending":
                    search_pipeline.append(
                        {"$sort": {"works.year_published": DESCENDING}}
                    )
                elif not sort:
                    search_pipeline.append(
                        {"$sort": {"works.citations_count.count": DESCENDING}}
                    )

                total_pipeline = search_pipeline.copy()
                total_pipeline.append({"$count": "total"})
                total = list(self.colav_db["person"].aggregate(total_pipeline))[0][
                    "total"
                ]

                search_pipeline.append({"$skip": max_results * (page - 1)})
                search_pipeline.append({"$limit": max_results})

                for work in self.colav_db["person"].aggregate(search_pipeline):
                    w = work["works"]
                    for i, author in enumerate(w["authors"]):
                        if author["id"] == work["_id"]:
                            w["authors"][i] = author
                            break
                    if len(w["authors"]) >= 10:
                        if i >= 10:
                            w["authors"] = w["authors"][i - 9 : i + 1]
                        else:
                            w["authors"] = w["authors"][0:10]
                    if w["_id"] not in work_ids:
                        papers.append(self.process_work(w))
                        work_ids.append(w["_id"])

            elif typ == "institution":
                search_dict = {}
                if start_year or end_year:
                    search_dict["year_published"] = {}
                if start_year:
                    search_dict["year_published"]["$gte"] = start_year
                if end_year:
                    search_dict["year_published"]["$lte"] = end_year
                if idx:
                    search_dict = {"authors.affiliations.id": ObjectId(idx)}
                search_dict["types.type"] = {"$nin": ["department", "faculty", "group"]}
                total = self.colav_db["works"].count_documents(search_dict)
                cursor = self.colav_db["works"].find(search_dict)

                if sort == "citations" and direction == "ascending":
                    cursor.sort([("citations_count.count", ASCENDING)])
                if sort == "citations" and direction == "descending":
                    cursor.sort([("citations_count.count", DESCENDING)])
                if sort == "year" and direction == "ascending":
                    cursor.sort([("year_published", ASCENDING)])
                if sort == "year" and direction == "descending":
                    cursor.sort([("year_published", DESCENDING)])

                cursor = cursor.skip(max_results * (page - 1)).limit(max_results)
                for work in cursor:
                    papers.append(self.process_work(work))

            return {
                "data": papers,
                "count": len(papers),
                "page": page,
                "total_results": total,
            }
        else:
            return None

    def get_products_by_year_by_type(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {"authors.id": author["_id"], "year_published": {"$exists": 1}},
                    {"year_published": 1, "types": 1},
                ):
                    data.append(work)
        else:
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "year_published": {"$exists": 1},
                },
                {"year_published": 1, "types": 1},
            ):
                data.append(work)
        result = self.bars.products_by_year_by_type(data)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_products_by_affiliation_by_type(
        self, idx, typ, aff_type: str | None = None
    ):
        if not typ in ["group", "department", "faculty"]:
            return None
        pipeline = [
            {
                "$match": {
                    "affiliations.types.type": typ,
                    "affiliations.id": ObjectId(idx),
                }
            },
            {"$unwind": "$affiliations"},
            {"$match": {"affiliations.types.type": typ}},
            {"$project": {"authorIds": "$_id", "_id": 0, "affiliations": 1}},
            {
                "$lookup": {
                    "from": "works",
                    "localField": "authorIds",
                    "foreignField": "authors.id",
                    "as": "works",
                }
            },
            {"$unwind": "$works"},
            {"$match": {"works.types": {"$ne": []}}},
            {
                "$project": {
                    "name": "$affiliations.name",
                    "work": {"types": "$works.types"},
                }
            },
        ]
        data = {}
        for _data in self.colav_db["person"].aggregate(pipeline):
            if not data.get(_data["name"], False):
                data[_data["name"]] = []
            data[_data["name"]].append(_data["work"])

        return {"plot": self.bars.products_by_affiliation_by_type(data)}

    def get_citations_by_year(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {
                        "authors.id": author["_id"],
                        "citations_by_year": {"$ne": []},
                        "year_published": {"$exists": 1},
                    },
                    {"year_published": 1, "citations_by_year": 1},
                ):
                    data.append(work)
        else:
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "citations_by_year": {"$ne": []},
                    "year_published": {"$exists": 1},
                },
                {"year_published": 1, "citations_by_year": 1},
            ):
                data.append(work)
        result = self.bars.citations_by_year(data)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_apc_by_year(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {
                        "authors.id": author["_id"],
                        "year_published": {"$exists": 1},
                        "source.id": {"$exists": 1},
                    },
                    {"year_published": 1, "source": 1},
                ):
                    if not "source" in work.keys():
                        continue
                    if not "id" in work["source"].keys():
                        continue
                    source_db = self.colav_db["sources"].find_one(
                        {"_id": work["source"]["id"]}
                    )
                    if source_db:
                        if source_db["apc"]:
                            data.append(
                                {
                                    "year_published": work["year_published"] or 2020,
                                    "apc": source_db["apc"],
                                }
                            )
        else:
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "year_published": {"$exists": 1},
                    "source.id": {"$exists": 1},
                },
                {"year_published": 1, "source": 1},
            ):
                if not "source" in work.keys():
                    continue
                if not "id" in work["source"].keys():
                    continue
                source_db = self.colav_db["sources"].find_one(
                    {"_id": work["source"]["id"]}
                )
                if source_db:
                    if source_db["apc"]:
                        data.append(
                            {
                                "year_published": work["year_published"] or 2020,
                                "apc": source_db["apc"],
                            }
                        )
        result = self.bars.apc_by_year(data, 2022)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_oa_by_year(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {
                        "authors.id": author["_id"],
                        "bibliographic_info.is_open_access": {"$ne": None},
                        "year_published": {"$ne": None},
                    },
                    {"year_published": 1, "bibliographic_info.is_open_access": 1},
                ):
                    data.append(work)
        else:
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "bibliographic_info.is_open_access": {"$ne": None},
                    "year_published": {"$ne": None},
                },
                {"year_published": 1, "bibliographic_info.is_open_access": 1},
            ):
                data.append(work)

        result = self.bars.oa_by_year(data)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_products_by_year_by_publisher(
        self, idx, typ=None, aff_type: str | None = None
    ):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {
                        "authors.id": author["_id"],
                        "year_published": {"$exists": 1},
                        "source.id": {"$exists": 1},
                    },
                    {"year_published": 1, "source.id": 1},
                ):
                    if not "source" in work.keys():
                        continue
                    if not "id" in work["source"].keys():
                        continue
                    source_db = self.colav_db["sources"].find_one(
                        {"_id": work["source"]["id"]}
                    )
                    if source_db:
                        if source_db["publisher"]:
                            data.append(
                                {
                                    "year_published": work["year_published"],
                                    "publisher": source_db["publisher"],
                                }
                            )
        else:
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "year_published": {"$exists": 1},
                    "source.id": {"$exists": 1},
                },
                {"year_published": 1, "source.id": 1},
            ):
                if not "source" in work.keys():
                    continue
                if not "id" in work["source"].keys():
                    continue
                source_db = self.colav_db["sources"].find_one(
                    {"_id": work["source"]["id"]}
                )
                if source_db:
                    if source_db["publisher"]:
                        data.append(
                            {
                                "year_published": work["year_published"],
                                "publisher": source_db["publisher"],
                            }
                        )

        result = self.bars.products_by_year_by_publisher(data)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_h_by_year(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {"authors.id": author["_id"], "citations_by_year": {"$ne": []}},
                    {"citations_by_year": 1},
                ):
                    data.append(work)
        else:
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "citations_by_year": {"$ne": []},
                },
                {"citations_by_year": 1},
            ):
                data.append(work)
        result = self.bars.h_index_by_year(data)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_products_by_year_by_researcher_category(
        self, idx, typ=None, aff_type: str | None = None
    ):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                pipeline = [
                    {
                        "$match": {
                            "authors.id": author["_id"],
                            "year_published": {"$ne": None},
                        }
                    },
                    {"$project": {"year_published": 1, "authors": 1}},
                    {"$unwind": "$authors"},
                    {
                        "$lookup": {
                            "from": "person",
                            "localField": "authors.id",
                            "foreignField": "_id",
                            "as": "researcher",
                        }
                    },
                    {
                        "$project": {
                            "year_published": 1,
                            "researcher.ranking": 1,
                            "researcher._id": 1,
                        }
                    },
                    {"$match": {"researcher.ranking.source": "scienti"}},
                ]
                for work in self.colav_db["works"].aggregate(pipeline):
                    for researcher in work["researcher"]:
                        for rank in researcher["ranking"]:
                            if rank["source"] == "scienti":
                                data.append(
                                    {
                                        "year_published": work["year_published"],
                                        "rank": rank["rank"],
                                    }
                                )
        else:
            pipeline = [
                {
                    "$match": {
                        "authors.affiliations.id": ObjectId(idx),
                        "year_published": {"$ne": None},
                    }
                },
                {"$project": {"year_published": 1, "authors": 1}},
                {"$unwind": "$authors"},
                {"$match": {"authors.affiliations.id": ObjectId(idx)}},
                {
                    "$lookup": {
                        "from": "person",
                        "localField": "authors.id",
                        "foreignField": "_id",
                        "as": "researcher",
                    }
                },
                {"$project": {"year_published": 1, "researcher.ranking": 1}},
                {"$match": {"researcher.ranking.source": "scienti"}},
            ]
            for work in self.colav_db["works"].aggregate(pipeline):
                for researcher in work["researcher"]:
                    for rank in researcher["ranking"]:
                        if rank["source"] == "scienti":
                            data.append(
                                {
                                    "year_published": work["year_published"],
                                    "rank": rank["rank"],
                                }
                            )
        result = self.bars.products_by_year_by_researcher_category(data)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_products_by_year_by_group_category(
        self, idx, typ=None, aff_type: str | None = None
    ):
        data = []
        info_db = self.colav_db["affiliations"].find_one(
            {"_id": ObjectId(idx)}, {"types": 1, "relations": 1, "ranking": 1}
        )
        db_type = ""
        for typ in info_db["types"]:
            if typ["type"] == "group":
                db_type = typ["type"]
                break
            elif typ["type"] == "department":
                db_type = typ["type"]
                break
            elif typ["type"] == "faculty":
                db_type = typ["type"]
                break
            else:
                db_type = "institution"
                break

        if db_type == "group":
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "year_published": {"$exists": 1},
                },
                {"year_published": 1},
            ):
                work["ranking"] = info_db["ranking"]
                data.append(work)
        else:
            groups = self.colav_db["affiliations"].find(
                {"relations.id": ObjectId(idx), "types.type": "group"},
                {"_id": 1, "ranking": 1},
            )
            for group in groups:
                authors = self.colav_db["person"].find(
                    {"affiliations.id": group["_id"]}, {"affiliations": 1}
                )
                for author in authors:
                    aff_start_date = None
                    aff_end_date = None
                    for aff in author["affiliations"]:
                        if aff["id"] == group["_id"]:
                            aff_start_date = (
                                aff["start_date"]
                                if aff["start_date"] != -1
                                else 9999999999
                            )
                            aff_end_date = (
                                aff["end_date"] if aff["end_date"] != -1 else 9999999999
                            )
                            break
                    query_dict = {
                        "authors.id": author["_id"],
                        "ranking": {"$ne": []},
                        "$and": [
                            {"date_published": {"$lte": aff_end_date}},
                            {"date_published": {"$gte": aff_start_date}},
                        ],
                    }
                    for work in self.colav_db["works"].find(
                        query_dict, {"year_published": 1, "date_published": 1}
                    ):
                        work["ranking"] = group["ranking"]
                        data.append(work)
        # print(data)
        result = self.bars.products_by_year_by_group_category(data)
        return {"plot": result}

    def get_title_words(self, idx, typ=None, aff_type: str | None = None):
        data = self.impactu_db["affiliations"].find_one(
            {"_id": ObjectId(idx)}, {"top_words": 1}
        )
        if data:
            if not "top_words" in data.keys():
                return {"plot": None}
            data = data["top_words"]
            return {"plot": data}
        else:
            return {"plot": None}

    def get_citations_by_affiliations(self, idx, typ, aff_type: str | None = None):
        if not typ in ["group", "department", "faculty"]:
            return None
        affiliations = affiliation_repository.get_affiliations_related_type(idx, typ, aff_type)

        data = {}
        for aff in affiliations:
            aff_id = aff.id
            name = aff.name
            data[name] = []
            for author in self.colav_db["person"].find({"affiliations.id": ObjectId(aff_id)}):
                aff_start_date = None
                aff_end_date = None
                for aff in author["affiliations"]:
                    if aff["id"] == aff_id:
                        aff_start_date = (
                            aff["start_date"] if aff["start_date"] != -1 else 9999999999
                        )
                        aff_end_date = (
                            aff["end_date"] if aff["end_date"] != -1 else 9999999999
                        )
                        break
                query_dict = {
                    "authors.id": author["_id"],
                    "citations_count": {"$ne": []},
                    "$and": [
                        {"date_published": {"$lte": aff_end_date}},
                        {"date_published": {"$gte": aff_start_date}},
                    ],
                }

                for work in self.colav_db["works"].find(
                    query_dict, {"citations_count": 1}
                ):
                    data[name].append(work)

        return self.pies.citations_by_affiliation(data)

    def get_products_by_affiliations(self, idx, typ, aff_type: str | None = None):
        affiliations = affiliation_repository.get_affiliations_related_type(idx, typ, aff_type)

        data = {}
        for aff in affiliations:
            aff_id = aff.id
            name = aff.name
            data[name] = 0
            for author in self.colav_db["person"].find({"affiliations.id": ObjectId(aff_id)}):
                aff_start_date = None
                aff_end_date = None
                for aff in author["affiliations"]:
                    if aff["id"] == aff_id:
                        aff_start_date = (
                            aff["start_date"] if aff["start_date"] != -1 else 9999999999
                        )
                        aff_end_date = (
                            aff["end_date"] if aff["end_date"] != -1 else 9999999999
                        )
                        break
                query_dict = {
                    "authors.id": author["_id"],
                    "$and": [
                        {"date_published": {"$lte": aff_end_date}},
                        {"date_published": {"$gte": aff_start_date}},
                    ],
                }

                data[name] += self.colav_db["works"].count_documents(query_dict)

        return self.pies.products_by_affiliation(data)

    def get_apc_by_affiliations(self, idx, typ, aff_type: str | None = None):
        affiliations = affiliation_repository.get_affiliations_related_type(idx, typ, aff_type)

        data = {}
        for aff in affiliations:
            aff_id = aff.id
            name = aff.name
            data[name] = []
            for author in self.colav_db["person"].find({"affiliations.id": ObjectId(aff_id)}):
                aff_start_date = None
                aff_end_date = None
                for aff in author["affiliations"]:
                    if aff["id"] == aff_id:
                        aff_start_date = (
                            aff["start_date"] if aff["start_date"] != -1 else 9999999999
                        )
                        aff_end_date = (
                            aff["end_date"] if aff["end_date"] != -1 else 9999999999
                        )
                        break
                query_dict = {
                    "authors.id": author["_id"],
                    "source": {"$ne": []},
                    "$and": [
                        {"date_published": {"$lte": aff_end_date}},
                        {"date_published": {"$gte": aff_start_date}},
                    ],
                }

                for work in self.colav_db["works"].find(
                    query_dict, {"source": 1, "year_published": 1}
                ):
                    if not "id" in work["source"].keys():
                        continue
                    source_db = self.colav_db["sources"].find_one(
                        {"_id": work["source"]["id"]}
                    )
                    if source_db:
                        if source_db["apc"]:
                            source_db["apc"]["year_published"] = work["year_published"]
                            data[name].append(source_db["apc"])

        return self.pies.apc_by_affiliation(data, 2022)

    def get_h_by_affiliations(self, idx, typ, aff_type: str | None = None):
        affiliations = affiliation_repository.get_affiliations_related_type(idx, typ, aff_type)

        data = {}
        for aff in affiliations:
            aff_id = aff.id
            name = aff.name
            data[name] = []
            for author in self.colav_db["person"].find({"affiliations.id": ObjectId(aff_id)}):
                aff_start_date = None
                aff_end_date = None
                for aff in author["affiliations"]:
                    if aff["id"] == aff_id:
                        aff_start_date = (
                            aff["start_date"] if aff["start_date"] != -1 else 9999999999
                        )
                        aff_end_date = (
                            aff["end_date"] if aff["end_date"] != -1 else 9999999999
                        )
                        break
                query_dict = {
                    "authors.id": author["_id"],
                    "citation_count": {"$ne": []},
                    "$and": [
                        {"date_published": {"$lte": aff_end_date}},
                        {"date_published": {"$gte": aff_start_date}},
                    ],
                }

                for work in self.colav_db["works"].find(
                    query_dict, {"citations_count": 1}
                ):
                    citations = 0
                    for count in work["citations_count"]:
                        if count["source"] == "scholar":
                            citations = count["count"]
                            break
                        elif count["source"] == "openalex":
                            citations = count["count"]
                            break
                    if citations == 0:
                        continue
                    data[name].append(citations)

        return self.pies.hindex_by_affiliation(data)

    def get_products_by_publisher(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {"authors.id": author["_id"], "source.id": {"$exists": 1}},
                    {"source.id": 1},
                ):
                    if not "source" in work.keys():
                        continue
                    if not "id" in work["source"].keys():
                        continue
                    source_db = self.colav_db["sources"].find_one(
                        {"_id": work["source"]["id"], "publisher.name": {"$ne": nan}}
                    )
                    if source_db:
                        if source_db["publisher"]:
                            data.append({"publisher": source_db["publisher"]})
        else:
            for work in self.colav_db["works"].find(
                {"authors.affiliations.id": ObjectId(idx), "source.id": {"$exists": 1}},
                {"source.id": 1},
            ):
                if not "source" in work.keys():
                    continue
                if not "id" in work["source"].keys():
                    continue
                source_db = self.colav_db["sources"].find_one(
                    {"_id": work["source"]["id"], "publisher.name": {"$ne": nan}}
                )
                if source_db:
                    if source_db["publisher"]:
                        data.append({"publisher": source_db["publisher"]})

        result = self.pies.products_by_publisher(data)
        if result:
            return result
        else:
            return {"plot": None}

    def get_products_by_subject(
        self, idx, level: int = 0, typ: str = None, aff_type: str | None = None
    ):
        if not level:
            level = 0
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {"authors.id": author["_id"], "subjects": {"$exists": 1}},
                    {"subjects": 1},
                ):
                    if not "subjects" in work.keys():
                        continue
                    for subjects in work["subjects"]:
                        if subjects["source"] != "openalex":
                            continue
                        for subject in subjects["subjects"]:
                            if subject["level"] != level:
                                continue
                            name = subject.get("name", "No name specified")
                            data.append({"subject": {"name": name}})
        else:
            for work in self.colav_db["works"].find(
                {"authors.affiliations.id": ObjectId(idx), "subjects": {"$exists": 1}},
                {"subjects": 1},
            ):
                if not "subjects" in work.keys():
                    continue
                for subjects in work["subjects"]:
                    if subjects["source"] != "openalex":
                        continue
                    for subject in subjects["subjects"]:
                        if subject["level"] != level:
                            continue
                        name = subject.get("name", "No name specified")
                        data.append({"subject": {"name": name}})

        result = self.pies.products_by_subject(data)
        if result:
            return result
        else:
            return {"plot": None}

    def get_products_by_database(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {"authors.id": author["_id"]}, {"updated": 1}
                ):
                    data.append(work["updated"])
        else:
            for work in self.colav_db["works"].find(
                {"authors.affiliations.id": ObjectId(idx)}, {"updated": 1}
            ):
                data.append(work["updated"])

        result = self.pies.products_by_database(data)
        if result:
            return result
        else:
            return {"plot": None}

    def get_products_by_open_access_status(
        self, idx, typ=None, aff_type: str | None = None
    ):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {
                        "authors.id": author["_id"],
                        "bibliographic_info.open_access_status": {
                            "$exists": 1,
                            "$ne": None,
                        },
                    },
                    {"bibliographic_info.open_access_status": 1},
                ):
                    data.append(work["bibliographic_info"]["open_access_status"])
        else:
            for work in self.colav_db["works"].find(
                {
                    "authors.affiliations.id": ObjectId(idx),
                    "bibliographic_info.open_access_status": {
                        "$exists": 1,
                        "$ne": None,
                    },
                },
                {"bibliographic_info.open_access_status": 1},
            ):
                data.append(work["bibliographic_info"]["open_access_status"])

        result = self.pies.products_by_open_access_status(data)
        return result

    def get_products_by_author_sex(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                pipeline = [
                    {"$match": {"authors.id": author["_id"]}},
                    {"$project": {"authors": 1}},
                    {"$unwind": "$authors"},
                    {
                        "$lookup": {
                            "from": "person",
                            "localField": "authors.id",
                            "foreignField": "_id",
                            "as": "author",
                        }
                    },
                    {"$project": {"author.sex": 1}},
                    {"$match": {"author.sex": {"$ne": "", "$exists": 1}}},
                ]
                for work in self.colav_db["works"].aggregate(pipeline):
                    data.append(work)
        else:
            pipeline = [
                {"$match": {"authors.affiliations.id": ObjectId(idx)}},
                {"$project": {"authors": 1}},
                {"$unwind": "$authors"},
                {
                    "$lookup": {
                        "from": "person",
                        "localField": "authors.id",
                        "foreignField": "_id",
                        "as": "author",
                    }
                },
                {"$project": {"author.sex": 1}},
                {"$match": {"author.sex": {"$ne": "", "$exists": 1}}},
            ]
            for work in self.colav_db["works"].aggregate(pipeline):
                data.append(work)

        result = self.pies.products_by_sex(data)
        if result:
            return result
        else:
            return {"plot": None}

    def get_products_by_author_age(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                pipeline = [
                    {
                        "$match": {
                            "authors.id": author["_id"],
                            "date_published": {"$ne": None},
                        },
                    },
                    {
                        "$project": {
                            "authors": 1,
                            "date_published": 1,
                            "year_published": 1,
                        }
                    },
                    {"$unwind": "$authors"},
                    # {"$match":{"authors.affiliations.id":ObjectId(idx)}},
                    {
                        "$lookup": {
                            "from": "person",
                            "localField": "authors.id",
                            "foreignField": "_id",
                            "as": "author",
                        }
                    },
                    {
                        "$project": {
                            "author.birthdate": 1,
                            "date_published": 1,
                            "year_published": 1,
                        }
                    },
                    {"$match": {"author.birthdate": {"$nin": [-1, ""], "$exists": 1}}},
                ]
                for work in self.colav_db["works"].aggregate(pipeline):
                    data.append(work)
        else:
            pipeline = [
                {
                    "$match": {
                        "authors.affiliations.id": ObjectId(idx),
                        "date_published": {"$ne": None},
                    }
                },
                {"$project": {"authors": 1, "date_published": 1, "year_published": 1}},
                {"$unwind": "$authors"},
                {"$match": {"authors.affiliations.id": ObjectId(idx)}},
                {
                    "$lookup": {
                        "from": "person",
                        "localField": "authors.id",
                        "foreignField": "_id",
                        "as": "author",
                    }
                },
                {
                    "$project": {
                        "author.birthdate": 1,
                        "date_published": 1,
                        "year_published": 1,
                    }
                },
                {"$match": {"author.birthdate": {"$nin": [-1, ""], "$exists": 1}}},
            ]
            for work in self.colav_db["works"].aggregate(pipeline):
                data.append(work)

        result = self.pies.products_by_age(data)
        if result:
            return result
        else:
            return {"plot": None}

    def get_products_by_scienti_rank(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                for work in self.colav_db["works"].find(
                    {"authors.id": author["_id"], "ranking": {"$ne": []}, "ranking.rank": {"$ne": None}},
                    {"ranking": 1},
                ):
                    data.append(work)
        else:
            for work in self.colav_db["works"].find(
                {"authors.affiliations.id": ObjectId(idx), "ranking": {"$ne": []}, "ranking.rank": {"$ne": None}},
                {"ranking": 1},
            ):
                data.append(work)
        result = self.pies.products_by_scienti_rank(data)
        if result:
            return result
        else:
            return {"plot": None}

    def get_products_by_scimago_rank(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                pipeline = [
                    {
                        "$match": {
                            "authors.id": author["_id"],
                            "date_published": {"$ne": None},
                        }
                    },
                    {"$project": {"source": 1, "date_published": 1}},
                    {
                        "$lookup": {
                            "from": "sources",
                            "localField": "source.id",
                            "foreignField": "_id",
                            "as": "source",
                        }
                    },
                    {"$unwind": "$source"},
                    {"$project": {"source.ranking": 1, "date_published": 1}},
                ]
                for work in self.colav_db["works"].aggregate(pipeline):
                    data.append(work)
        else:
            pipeline = [
                {
                    "$match": {
                        "authors.affiliations.id": ObjectId(idx),
                        "date_published": {"$ne": None},
                    }
                },
                {"$project": {"source": 1, "date_published": 1}},
                {
                    "$lookup": {
                        "from": "sources",
                        "localField": "source.id",
                        "foreignField": "_id",
                        "as": "source",
                    }
                },
                {"$unwind": "$source"},
                {"$project": {"source.ranking": 1, "date_published": 1}},
            ]
            for work in self.colav_db["works"].aggregate(pipeline):
                data.append(work)

        result = self.pies.products_by_scimago_rank(data)
        if result:
            return result
        else:
            return {"plot": None}

    def get_publisher_same_institution(
        self, idx, typ=None, aff_type: str | None = None
    ):
        data = []
        institution = self.colav_db["affiliations"].find_one(
            {"_id": ObjectId(idx)}, {"names": 1}
        )
        pipeline = [
            {
                '$match': {
                    'affiliations.id': ObjectId(idx)
                }
            }, {
                '$project': {
                    '_id': 1
                }
            }, {
                '$lookup': {
                    'from': 'works', 
                    'localField': '_id', 
                    'foreignField': 'authors.id', 
                    'as': 'work'
                }
            }, {
                '$unwind': '$work'
            }, {
                '$replaceRoot': {
                    'newRoot': '$work'
                }
            },
            {"$project": {"source": 1}},
            {
                "$lookup": {
                    "from": "sources",
                    "localField": "source.id",
                    "foreignField": "_id",
                    "as": "source",
                }
            },
            {"$unwind": "$source"},
            {"$project": {"source.publisher": 1}},
            {
                "$match": {
                    "source.publisher": {"$exists": 1, "$not": {"$type": "string"}},
                    "source.publisher.name": {"$type": "string"},
                }
            },
        ]
        for work in self.colav_db["person"].aggregate(pipeline):
            data.append(work)
        result = self.pies.products_editorial_same_institution(data, institution)
        if result:
            return result
        else:
            return {"plot": None}

    def get_coauthorships_worldmap(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                pipeline = [
                    {"$match": {"authors.id": author["_id"]}},
                    {"$unwind": "$authors"},
                    {
                        "$group": {
                            "_id": "$authors.affiliations.id",
                            "count": {"$sum": 1},
                        }
                    },
                    {"$unwind": "$_id"},
                    {
                        "$lookup": {
                            "from": "affiliations",
                            "localField": "_id",
                            "foreignField": "_id",
                            "as": "affiliation",
                        }
                    },
                    {
                        "$project": {
                            "count": 1,
                            "affiliation.addresses.country_code": 1,
                            "affiliation.addresses.country": 1,
                        }
                    },
                    {"$unwind": "$affiliation"},
                    {"$unwind": "$affiliation.addresses"},
                ]
                for work in self.colav_db["works"].aggregate(pipeline):
                    data.append(work)
        else:
            pipeline = [
                {"$match": {"authors.affiliations.id": ObjectId(idx)}},
                {"$unwind": "$authors"},
                {"$group": {"_id": "$authors.affiliations.id", "count": {"$sum": 1}}},
                {"$unwind": "$_id"},
                {
                    "$lookup": {
                        "from": "affiliations",
                        "localField": "_id",
                        "foreignField": "_id",
                        "as": "affiliation",
                    }
                },
                {
                    "$project": {
                        "count": 1,
                        "affiliation.addresses.country_code": 1,
                        "affiliation.addresses.country": 1,
                    }
                },
                {"$unwind": "$affiliation"},
                {"$unwind": "$affiliation.addresses"},
            ]
            for work in self.colav_db["works"].aggregate(pipeline):
                data.append(work)
        result = self.maps.get_coauthorship_world_map(data)
        if result:
            return {"plot": result}
        else:
            return {"plot": None}

    def get_coauthorships_colombiamap(self, idx, typ=None, aff_type: str | None = None):
        data = []
        if typ in ["group", "department", "faculty"]:
            for author in self.colav_db["person"].find(
                {"affiliations.id": ObjectId(idx)}, {"affiliations": 1}
            ):
                pipeline = [
                    {"$match": {"authors.id": author["_id"]}},
                    {"$unwind": "$authors"},
                    {
                        "$group": {
                            "_id": "$authors.affiliations.id",
                            "count": {"$sum": 1},
                        }
                    },
                    {"$unwind": "$_id"},
                    {
                        "$lookup": {
                            "from": "affiliations",
                            "localField": "_id",
                            "foreignField": "_id",
                            "as": "affiliation",
                        }
                    },
                    {
                        "$project": {
                            "count": 1,
                            "affiliation.addresses.country_code": 1,
                            "affiliation.addresses.city": 1,
                        }
                    },
                    {"$unwind": "$affiliation"},
                    {"$unwind": "$affiliation.addresses"},
                ]
                for work in self.colav_db["works"].aggregate(pipeline):
                    data.append(work)
        else:
            pipeline = [
                {"$match": {"authors.affiliations.id": ObjectId(idx)}},
                {"$unwind": "$authors"},
                {"$group": {"_id": "$authors.affiliations.id", "count": {"$sum": 1}}},
                {"$unwind": "$_id"},
                {
                    "$lookup": {
                        "from": "affiliations",
                        "localField": "_id",
                        "foreignField": "_id",
                        "as": "affiliation",
                    }
                },
                {
                    "$project": {
                        "count": 1,
                        "affiliation.addresses.country_code": 1,
                        "affiliation.addresses.city": 1,
                    }
                },
                {"$unwind": "$affiliation"},
                {"$unwind": "$affiliation.addresses"},
            ]
            for work in self.colav_db["works"].aggregate(pipeline):
                data.append(work)
        result = self.maps.get_coauthorship_colombia_map(data)
        return {"plot": result}

    def get_coauthorships_network(self, idx, typ=None, aff_type: str | None = None):
        if typ in ["group", "department", "faculty"]:
            return {"plot": None}
        data = self.impactu_db["affiliations"].find_one(
            {"_id": ObjectId(idx)}, {"coauthorship_network": 1}
        )
        if data:
            if "coauthorship_network" not in data.keys():
                return {"plot": None}
            data = data["coauthorship_network"]
            nodes = sorted(data["nodes"], key=lambda x: x["degree"], reverse=True)[:50]
            nodes_ids = [node["id"] for node in nodes]
            edges = []
            for edge in data["edges"]:
                if edge["source"] in nodes_ids and edge["target"] in nodes_ids:
                    edges.append(edge)
            return {"plot": {"nodes": nodes, "edges": edges}}
        else:
            return {"plot": None}

    @property
    def plot_mappings(self) -> dict[str, Callable[[Any, Any], dict[str, list] | None]]:
        return {
            "year_type": self.get_products_by_year_by_type,
            "type,faculty": self.get_products_by_affiliation_by_type,
            "type,department": self.get_products_by_affiliation_by_type,
            "type,group": self.get_products_by_affiliation_by_type,
            "year_citations": self.get_citations_by_year,
            "year_apc": self.get_apc_by_year,
            "year_oa": self.get_oa_by_year,
            "year_publisher": self.get_products_by_year_by_publisher,
            "year_h": self.get_h_by_year,
            "year_researcher": self.get_products_by_year_by_researcher_category,
            "year_group": self.get_products_by_year_by_group_category,
            "title_words": self.get_title_words,
            "citations,faculty": self.get_citations_by_affiliations,
            "citations,department": self.get_citations_by_affiliations,
            "citations,group": self.get_citations_by_affiliations,
            "products,faculty": self.get_products_by_affiliations,
            "products,department": self.get_products_by_affiliations,
            "products,group": self.get_products_by_affiliations,
            "apc,faculty": self.get_apc_by_affiliations,
            "apc,department": self.get_apc_by_affiliations,
            "apc,group": self.get_apc_by_affiliations,
            "h,faculty": self.get_h_by_affiliations,
            "h,department": self.get_h_by_affiliations,
            "h,group": self.get_h_by_affiliations,
            "products_publisher": self.get_products_by_publisher,
            "products_subject": self.get_products_by_subject,
            "products_database": self.get_products_by_database,
            "products_oa": self.get_products_by_open_access_status,
            "products_sex": self.get_products_by_author_sex,
            "products_age": self.get_products_by_author_age,
            "scienti_rank": self.get_products_by_scienti_rank,
            "scimago_rank": self.get_products_by_scimago_rank,
            "published_institution": self.get_publisher_same_institution,
            "collaboration_worldmap": self.get_coauthorships_worldmap,
            "collaboration_colombiamap": self.get_coauthorships_colombiamap,
            "collaboration_network": self.get_coauthorships_network,
        }


affiliation_app_service = AffiliationAppService()
