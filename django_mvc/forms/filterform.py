from types import MethodType

from django.core.exceptions import ValidationError
from django.forms.fields import FileField

from . import forms 

class FilterForm(forms.ModelForm):
    def __init__(self, *args,**kwargs):
        if "instance" in kwargs:
            del kwargs["instance"]
    
        if "auto_id" not in kwargs:
            kwargs["auto_id"] = "id_filter_%s"

        super(FilterForm,self).__init__(*args,**kwargs)

    def _clean_fields(self):
        """
        Don't set the field value in cleaned_data, if it doesn't exist in data dict
        """
        for name, field in self.fields.items():
            # value_from_datadict() gets the data from the data dictionaries.
            # Each widget type knows how to retrieve its own data, because some
            # widgets split data over several HTML fields.
            if field.disabled:
                value = self.get_initial_for_field(field, name)
            else:
                formname = self.add_prefix(name)
                if formname not in self.data:
                    continue;
                value = field.widget.value_from_datadict(self.data, self.files, formname)
            try:
                if isinstance(field, FileField):
                    initial = self.get_initial_for_field(field, name)
                    value = field.clean(value, initial)
                else:
                    value = field.clean(value)
                self.cleaned_data[name] = value
                if hasattr(self, 'clean_%s' % name):
                    value = getattr(self, 'clean_%s' % name)()
                    self.cleaned_data[name] = value
            except ValidationError as e:
                self.add_error(name, e)

    def save(self, commit=True):
        raise NotImplementedError()

    def _post_clean(self):
        pass

    def validate_unique(self):
        pass
        
    class Meta:
        pass
