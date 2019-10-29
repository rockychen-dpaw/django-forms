from django import forms
from django.template import engines
from django.dispatch import receiver

from .. import widgets
from ..utils import hashvalue
from .fields import (class_id,field_classes)

from django_forms.signals import formfields_inited,formsetfields_inited
from django_forms.utils import get_class

django_engine = engines['django']
class FormSetField(forms.Field):
    _formset_class = None
    _formset_class_name = None
    _template = None
    _is_display = True
    def __init__(self, *args,**kwargs):
        kwargs["widget"] = kwargs["widget"] or TextDisplay()
        kwargs["initial"] = None
        initial = None
        super(FormSetField,self).__init__(*args,**kwargs)

    @property
    def template(self):
        return self._template

    @property
    def formset_class(self):
        return self._formset_class

    @property
    def model(self):
        return self._formset_class._meta.model

    @property
    def is_display(self):
        return self._is_display

    def get_initial(self):
        """
        guarantee a non-none value will be returned
        """
        if not self.initial:
            self.initial = self.formset_class.form._meta.model()
        return self.initial

def FormSetFieldFactory(formset_class_name,template):
    global class_id

    class_key = "FormSetField<{}>".format(hashvalue("FormSetField<{}>".format(formset_class_name)))
    if class_key not in field_classes:
        class_id += 1
        class_name = "FormSetField_{}".format(class_id)
        field_classes[class_key] = type(class_name,(FormSetField,),{"_formset_class_name":formset_class_name,"_template":django_engine.from_string(template)})
    return field_classes[class_key]


@receiver(formfields_inited)
def init_actions(sender,**kwargs):
    for key,cls in field_classes.items():
        if key.startswith("FormSetField<"):
            cls._formset_class = get_class(cls._formset_class_name)

    for key,cls in field_classes.items():
        if key.startswith("FormSetField<"):
            cls._is_display = not cls._formset_class.form.can_edit()

    formsetfields_inited.send(sender="formsetfields")



