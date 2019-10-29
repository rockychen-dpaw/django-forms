from django import forms
from django.dispatch import receiver

from .. import widgets
from ..utils import hashvalue
from .fields import (class_id,field_classes)
from ..widgets import (TextDisplay,)

from django_mvc.signals import fields_inited,formfields_inited
from django_mvc.utils import get_class

class FormField(forms.Field):
    _form_class = None
    _form_class_name = None
    _is_display=True
    def __init__(self, *args,**kwargs):
        kwargs["widget"] = kwargs.get("widget") or TextDisplay()
        kwargs["initial"] = None
        initial = None
        super(FormField,self).__init__(*args,**kwargs)

    @property
    def form_class(self):
        return self._form_class

    @property
    def model(self):
        return self._form_class._meta.model

    @property
    def is_display(self):
        return self._is_display

    def get_initial(self):
        """
        guarantee a non-none value will be returned
        """
        if not self.initial:
            self.initial = self.form_class._meta.model()
        return self.initial



def FormFieldFactory(form_class_name):
    global class_id
    class_key = "FormField<{}>".format(hashvalue("FormField<{}>".format(form_class_name)))
    if class_key not in field_classes:
        class_id += 1
        class_name = "FormField_{}".format(class_id)
        field_classes[class_key] = type(class_name,(FormField,),{"_form_class_name":form_class_name})
    return field_classes[class_key]

@receiver(fields_inited)
def init_actions(sender,**kwargs):
    for key,cls in field_classes.items():
        if key.startswith("FormField<"):
            cls._form_class = get_class(cls._form_class_name)

    for key,cls in field_classes.items():
        if key.startswith("FormField<"):
            cls._is_display = not cls._form_class.can_edit()

    formfields_inited.send(sender="formfields")



