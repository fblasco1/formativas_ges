"""
Conexión a PostgreSQL vía SQLAlchemy. Reutilizable para análisis y API FastAPI.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _default_config_path() -> str:
    """Ruta por defecto a config.json en la raíz del proyecto."""
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "config.json")


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    """Carga la configuración desde JSON. Si path es None, usa CONFIG_PATH o raíz del proyecto."""
    if path is None:
        path = os.environ.get("CONFIG_PATH", _default_config_path())
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_url(cfg: Optional[Dict[str, Any]] = None, config_path: Optional[str] = None) -> str:
    """
    Construye la URL de conexión PostgreSQL para SQLAlchemy.
    Si cfg es None, se carga desde config_path (o por defecto).
    """
    if cfg is None:
        cfg = load_config(config_path)
    db = cfg.get("db", {})
    host = db.get("host", "localhost")
    port = db.get("port", 5432)
    user = db.get("user")
    password = db.get("password")
    name = db.get("name")
    if not user or not password or not name:
        raise ValueError(
            "Config incompleta: se requieren db.user, db.password y db.name"
        )
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


def get_engine(
    url: Optional[str] = None,
    config_path: Optional[str] = None,
    cfg: Optional[Dict[str, Any]] = None,
    **engine_kwargs: Any,
) -> Engine:
    """
    Crea el motor SQLAlchemy.

    - Si se pasa `url`, se usa directamente.
    - Si no, se construye desde `cfg` o desde `config_path` / config por defecto.
    - `engine_kwargs` se pasan a create_engine (ej. pool_pre_ping=True).
    """
    if url is None:
        url = build_url(cfg=cfg, config_path=config_path)
    kwargs: Dict[str, Any] = {"pool_pre_ping": True}
    kwargs.update(engine_kwargs)
    return create_engine(url, **kwargs)


def get_session_factory(engine: Optional[Engine] = None, **engine_kwargs: Any):
    """
    Retorna un sessionmaker. Útil para inyectar en FastAPI con yield.

    Si engine es None, se crea uno con get_engine(**engine_kwargs).
    """
    if engine is None:
        engine = get_engine(**engine_kwargs)
    return sessionmaker(engine, autocommit=False, autoflush=False, class_=Session)


def get_session(
    engine: Optional[Engine] = None,
    session_factory: Optional[sessionmaker] = None,
    **engine_kwargs: Any,
) -> Session:
    """
    Retorna una sesión nueva. El llamador debe cerrarla o usar context manager.

    Prioridad: session_factory > engine > get_engine(**engine_kwargs).
    """
    if session_factory is not None:
        return session_factory()
    if engine is None:
        engine = get_engine(**engine_kwargs)
    return Session(engine)
