from django import forms
from django.dispatch import receiver

from .. import widgets
from ..utils import hashvalue
from .fields import (class_id,field_classes)
from .. import boundfield

from django_mvc.signals import formfields_inited,formsetfields_inited
from django_mvc.utils import get_class

class FormSetField(forms.Field):
    widget = widgets.TextDisplay()

    _formset_class = None
    _formset_class_name = None
    _is_display = True

    boundfield_class = boundfield.FormSetBoundField

    def __init__(self, *args,**kwargs):
        kwargs["widget"] = widgets.TextDisplay()
        kwargs["initial"] = None
        initial = None
        super(FormSetField,self).__init__(*args,**kwargs)

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

def FormSetFieldFactory(formset_class_name):
    global class_id

    class_key = "FormSetField<{}>".format(hashvalue("FormSetField<{}>".format(formset_class_name)))
    if class_key not in field_classes:
        class_id += 1
        class_name = "FormSetField_{}".format(class_id)
        field_classes[class_key] = type(class_name,(FormSetField,),{"_formset_class_name":formset_class_name})
    return field_classes[class_key]


@receiver(formfields_inited)
def init_formsetfields(sender,**kwargs):
    for key,cls in field_classes.items():
        if key.startswith("FormSetField<"):
            cls._formset_class = get_class(cls._formset_class_name)

    for key,cls in field_classes.items():
        if key.startswith("FormSetField<"):
            cls._is_display = not cls._formset_class.form.can_edit()

    formsetfields_inited.send(sender="formsetfields")



