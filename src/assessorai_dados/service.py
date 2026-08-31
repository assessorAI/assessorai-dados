from functools import lru_cache

from .database import LegislativeRepository, create_repository


@lru_cache
def get_repository() -> LegislativeRepository:
    return create_repository()
