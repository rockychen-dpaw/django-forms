from django.conf import settings
from django.shortcuts import resolve_url
from django import template
from django.utils.html import mark_safe


register = template.Library()


@register.simple_tag
def page_background():
    """
    Usage:
        Set a image as html page's background to indicate the runtime environment (dev or uat)
    """
    if settings.ENV_TYPE == "PROD":
        return ""
    elif settings.ENV_TYPE == "LOCAL":
        return "background-image:url('/static/dbca/img/local.png')"
    elif settings.ENV_TYPE == "DEV":
        return "background-image:url('/static/dbca/img/dev.png')"
    elif settings.ENV_TYPE == "UAT":
        return "background-image:url('/static/dbca/img/uat.png')"
    elif settings.ENV_TYPE == "TEST":
        return "background-image:url('/static/dbca/img/test.png')"
    elif settings.ENV_TYPE == "TRAINING":
        return "background-image:url('/static/dbca/img/training.png')"
    else:
        return "background-image:url('/static/dbca/img/dev.png')"


@register.simple_tag
def call_method(obj,method_name,*args,**kwargs):
    return getattr(obj,method_name)(*args,**kwargs)

@register.simple_tag
def call_method_escape(obj,method_name,*args,**kwargs):
    return mark_safe(getattr(obj,method_name)(*args,**kwargs).replace("</script>","</\script>"))

@register.simple_tag
def setvar(*args):
    if len(args) == 0:
        return None
    elif len(args) == 1:
        return args[0]
    else:
        return "".join([str(o) for o in args])

class Index(object):
    def __init__(self,index = 0,step = 1):
        self._index = index
        self._step = step

    @property
    def index(self):
        return self._index

    @property
    def nextindex(self):
        self._index += self._step
        return self._index

@register.simple_tag
def setindex(index):
    return Index(index)

@register.simple_tag
def nextindex(index):
    index.nextindex;
    return ""


@register.simple_tag
def addurlparameter(url,name,value):
    if "?" in url:
        return "{}&{}={}".format(url,name,value)
    else:
        return "{}?{}={}".format(url,name,value)
    

@register.simple_tag
def debug(obj,*args):
    import ipdb;ipdb.set_trace()
    return ""

