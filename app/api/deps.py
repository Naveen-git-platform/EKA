"""FastAPI dependencies that expose the service container to routes."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.core.container import Container


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise HTTPException(status_code=503, detail="Service is starting up")
    return container


ContainerDep = Annotated[Container, Depends(get_container)]
