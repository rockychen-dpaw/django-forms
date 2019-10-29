from django.contrib.admin import widgets
from django import forms

class FilteredSelectMultiple(widgets.FilteredSelectMultiple):
    """
    A SelectMultiple with a JavaScript filter interface.

    Note that the resulting JavaScript assumes that the jsi18n
    catalog has been loaded in the page
    """
    @property
    def media(self):
        js = [
            'js/jsi18n.js',
            'js/jquery.init.js',
            'admin/js/core.js',
            'admin/js/SelectBox.js',
            'django/js/SelectFilter2.js',
        ]
        css = {
            "all":['admin/css/widgets.css']
        }
        return forms.Media(js=js,css=css)

    def render(self,name,value,attrs=None,renderer=None):
        html = super().render(name,value,attrs=attrs,renderer=renderer)
        if "id" in attrs:
            html = """
            {0}
            <script type="text/javascript">
                var data = $("#{1}").data();
                SelectFilter.init("{1}", data.fieldName, parseInt(data.isStacked, 10));
            </script>
            """.format(html,attrs["id"])
        return html
