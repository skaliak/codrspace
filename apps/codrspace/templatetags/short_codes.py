"""Custom filters to grab code from the web via short codes"""


import requests
import mimetypes
import re
import os
import markdown
import urlparse
from hashlib import md5

from django.utils import simplejson
from django import template
from django.utils.safestring import mark_safe
from settings import MEDIA_ROOT

from codrspace.templatetags.syntax_color import _colorize_table

register = template.Library()


@register.filter(name='explosivo')
def explosivo(value):
    """
    Search text for any references to supported short codes and explode them
    """

    # Round-robin through all functions as if they are filter methods so we
    # don't have to update some silly list of available ones when they are
    # added
    import sys
    import types
    module = sys.modules[__name__]
    all_replacements = []

    # get the replacement values and content with replacement hashes
    for name, var in vars(module).items():
        if type(var) == types.FunctionType and name.startswith('filter_'):
            replacements, value, match = var(value)
            if match:
                all_replacements.extend(replacements)

    # convert to markdown
    value = markdown.markdown(value)

    # replace the hash values with the replacement values
    for r in all_replacements:
        _hash, text = r
        value = value.replace(_hash, text)

    return mark_safe(value)


def filter_inline(value):
    replacements = []
    pattern = re.compile('\\[code\\](.*?)\\[/code\\]', re.I | re.S | re.M)

    inlines = re.findall(pattern, value)
    if not len(inlines):
        return (replacements, value, None,)

    for inline_code in inlines:
        text = _colorize_table(inline_code, None)
        text_hash = md5(text).hexdigest()

        replacements.append([text_hash, text])
        value = re.sub(pattern, text_hash, value, count=1)

    return (replacements, value, True,)


def filter_gist(value):
    gist_base_url = 'https://api.github.com/gists/'
    replacements = []
    pattern = re.compile('\[gist (\d+) *\]', flags=re.IGNORECASE)

    ids = re.findall(pattern, value)
    if not len(ids):
        return (replacements, value, None,)

    for gist_id in ids:
        gist_text = ""
        resp = requests.get('%s%d' % (gist_base_url, int(gist_id)))

        if resp.status_code != 200:
            return value

        content = simplejson.loads(resp.content)

        # Go through all files in gist and smash 'em together
        for name in content['files']:
            gist_text += "%s" % (
                _colorize_table(content['files'][name]['content'], None))

        if content['comments'] > 0:
            gist_text += '<hr><p class="github_convo">Join the conversation on ' + \
                            '<a href="%s#comments">github</a> (%d comments)</p>' % (
                                content['html_url'], content['comments'])

        text_hash = md5(gist_text).hexdigest()

        replacements.append([text_hash, gist_text])
        value = re.sub(pattern, text_hash, value, count=1)

    return (replacements, value, True,)


def filter_upload(value):
    replacements = []
    pattern = re.compile('\[local (\S+) *\]', flags=re.IGNORECASE)

    files = re.findall(pattern, value)
    if not len(files):
        return (replacements, value, None,)

    for file_path in files:
        file_path = os.path.join(MEDIA_ROOT, file_path)
        (file_type, encoding) = mimetypes.guess_type(file_path)

        if file_type is None:
            return (replacements, value, None,)

        # FIXME: Can we trust the 'guessed' mimetype?
        if not file_type.startswith('text'):
            return (replacements, value, None,)

        # FIXME: Limit to 1MB right now
        try:
            f = open(file_path)
        except IOError:
            return (replacements, value, None,)

        text = f.read(1048576)
        f.close()

        text = _colorize_table(text, None)
        text_hash = md5(text).hexdigest()

        replacements.append([text_hash, text])
        value = re.sub(pattern, text_hash, value, count=1)

    return (replacements, value, True,)
