try:
    import markdown
except Exception as ex:
    from django_forms.utils import object_not_imported
    markdown = object_not_imported("markdown",ex)

from django.utils.html import mark_safe
from django.utils.encoding import force_text

from .widgets import DisplayWidget

class Markdownify(DisplayWidget):
    def render(self,name,value,attrs=None,renderer=None):
        extensions = ["nl2br"]
        return mark_safe(markdown.markdown(force_text(value), extensions=extensions,output_format='html'))

