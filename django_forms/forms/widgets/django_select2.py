try:
    from django_select2.forms import Select2MultipleWidget as DjangoSelect2MultipleWidget
except Exception as ex:
    from django_forms.utils import class_not_imported
    DjangoSelect2MultipleWidget = class_not_imported("django_select2.forms.Select2MultipleWidget",ex)

class Select2MultipleWidget(DjangoSelect2MultipleWidget):
    def render(self,name,value,attrs=None,renderer=None):
        return """
        {}
        <script type="text/javascript">
        $("#{}").djangoSelect2();
        </script>
        """.format(super().render(name,value,attrs,renderer),attrs["id"])

