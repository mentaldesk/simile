from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import BaseRoute, Route

from simile.gallery.store import gallery_store_of


def painting(request: Request) -> Response:
    picture = gallery_store_of(request.app).picture(request.path_params["work_id"])
    if picture is None:
        return Response(status_code=404)
    return Response(
        picture, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"}
    )


routes: list[BaseRoute] = [Route("/api/gallery/{work_id}.png", painting)]
