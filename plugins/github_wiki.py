"""
GitHub Wiki support for mistletoe.
"""

import re
from mistletoe.span_token import SpanToken, tokenize_inner
from mistletoe.html_renderer import HTMLRenderer, escape_url


__all__ = ['GithubWiki', 'GithubWikiRenderer']


class GithubWiki(SpanToken):
    pattern = re.compile(r"\[\[ *(.+?) *\| *(.+?) *\]\]")
    def __init__(self, match_obj):
        self.children = tokenize_inner(match_obj.group(1))
        self.target = match_obj.group(2)


class GithubWikiRenderer(HTMLRenderer):
    def __init__(self):
        super().__init__(GithubWiki)

    def render_github_wiki(self, token, footnotes):
        template = '<a href="{target}">{inner}</a>'
        target = escape_url(token.target)
        inner = self.render_inner(token, footnotes)
        return template.format(target=target, inner=inner)
