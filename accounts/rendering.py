from urllib.parse import urlparse

from django.http import QueryDict
from django.shortcuts import render
from django.urls import NoReverseMatch, Resolver404, resolve, reverse


def render_route(request, to, *args, fallback_template='accounts/login.html', **kwargs):
    """
    Render the view that a redirect target would have reached, without returning
    an HTTP redirect response. POST targets are re-opened as GET to keep the
    existing post-action landing pages.
    """
    path = _target_to_path(to, args, kwargs)
    if not path:
        return render(request, fallback_template)

    parsed = urlparse(path)
    route_path = parsed.path or path
    query_string = parsed.query

    try:
        match = resolve(route_path)
    except Resolver404:
        return render(request, fallback_template)

    request.method = 'GET'
    request.path = route_path
    request.path_info = route_path
    request.META['QUERY_STRING'] = query_string
    request.GET = QueryDict(query_string)
    request.resolver_match = match

    return match.func(request, *match.args, **match.kwargs)


def _target_to_path(to, args, kwargs):
    if not to:
        return ''

    to = str(to)
    if to.startswith(('http://', 'https://')):
        parsed = urlparse(to)
        return parsed.path + (f'?{parsed.query}' if parsed.query else '')

    if to.startswith('/'):
        return to

    try:
        return reverse(to, args=args, kwargs=kwargs)
    except NoReverseMatch:
        return to
