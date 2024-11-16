import inspect
import os
from functools import wraps
from typing import Optional

import fastapi
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
from starlette.routing import get_name

from fastapi_jinja.exceptions import FastAPIJinjaException

template_path: Optional[str] = None
__templates: Optional[Jinja2Templates] = None


def global_init(template_folder: str, auto_reload: bool = False, cache_init: bool = True):
    global __templates, template_path

    if __templates and cache_init:
        return

    if not template_folder:
        msg = f"The template_folder must be specified."
        raise FastAPIJinjaException(msg)

    if not os.path.isdir(template_folder):
        msg = f"The specified template folder must be a folder, it's not: {template_folder}"
        raise FastAPIJinjaException(msg)

    template_path = template_folder
    __templates = Jinja2Templates(directory=template_folder)
    __templates.env.auto_reload = auto_reload


def clear():
    global __templates, template_path
    template_path = None
    __templates = None


def render(template_file: str, **template_data):
    if not __templates:
        raise Exception("You must call global_init() before rendering templates.")

    rendered_page = __templates.TemplateResponse(template_file, template_data)
    return rendered_page


def response(template_file: str, mimetype: str = "text/html", status_code: int = 200, **template_data):
    html = render(template_file, **template_data)
    return fastapi.Response(content=html, media_type=mimetype, status_code=status_code)


def template(template_file: str, mimetype: str = "text/html"):
    """
    Decorate a FastAPI view method to render an HTML response.

    :param str template_file: The Chameleon template file (path relative to template folder, *.pt).
    :param str mimetype: The mimetype response (defaults to text/html).
    :return: Decorator to be consumed by FastAPI
    """
    if not template_file:
        raise FastAPIJinjaException("You must specify a template file.")

    def response_inner(f):
        name = get_name(f)
        signature = inspect.signature(f)
        if 'request' not in signature.parameters:
            raise FastAPIJinjaException(f"Template view {name} did not define a request argument")

        @wraps(f)
        def sync_view_method(*args, **kwargs):
            request = __get_request(*args, **kwargs)
            response_val = f(*args, **kwargs)
            return __render_response(template_file, response_val, request, mimetype)

        @wraps(f)
        async def async_view_method(*args, **kwargs):
            request = __get_request(*args, **kwargs)
            response_val = await f(*args, **kwargs)
            return __render_response(template_file, response_val, request, mimetype)

        if inspect.iscoroutinefunction(f):
            return async_view_method
        else:
            return sync_view_method

    return response_inner


def __get_request(*args, **kwargs):
    for arg in args:
        if isinstance(arg, Request):
            return arg
    else:
        return kwargs.get('request', None)


def __render_response(template_file: str, response_val: dict, request: Request, mimetype: str):

    if isinstance(response_val, fastapi.Response):
        return response_val

    model = dict(response_val)
    # Allow override from response
    model.setdefault('media_type', mimetype)

    if 'request' in model and not isinstance(model['request'], Request):
        msg = f"'request' in response is not an instance of {Request.__name__}"
        raise FastAPIJinjaException(msg)
    model.setdefault('request', request)

    if template_file and not isinstance(response_val, dict):
        msg = f"Invalid return type {type(response_val)}, we expected a dict as the return value."
        raise FastAPIJinjaException(msg)

    return render(template_file, **model)
