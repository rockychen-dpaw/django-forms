
from django import forms
from django.dispatch import receiver

from .. import widgets
from ..utils import hashvalue
from .fields import (class_id,field_classes)
from .. import boundfield

from django_mvc.signals import formsetfields_inited,listformfields_inited
from django_mvc.utils import get_class

class ListFormField(forms.Field):
    _listform_class = None
    _listform_class_name = None
    widget = widgets.TextDisplay()

    boundfield_class = boundfield.ListFormBoundField
    listboundfield_class = boundfield.ListFormListBoundField

    def __init__(self, *args,**kwargs):
        kwargs["widget"] = widgets.ListFormWidget(self)
        kwargs["initial"] = None
        initial = None
        super(ListFormField,self).__init__(*args,**kwargs)

    @property
    def listform_class(self):
        return self._listform_class

    @property
    def model(self):
        return self._listform_class._meta.model

def ListFormFieldFactory(listform_class_name):
    global class_id

    class_key = "ListFormField<{}>".format(hashvalue("ListFormField<{}>".format(listform_class_name)))
    if class_key not in field_classes:
        class_id += 1
        class_name = "ListFormField_{}".format(class_id)
        field_classes[class_key] = type(class_name,(ListFormField,),{"_listform_class_name":listform_class_name})
    return field_classes[class_key]


@receiver(formsetfields_inited)
def init_listformfields(sender,**kwargs):
    for key,cls in field_classes.items():
        if key.startswith("ListFormField<"):
            cls._listform_class = get_class(cls._listform_class_name)

    listformfields_inited.send(sender="listformfields")



