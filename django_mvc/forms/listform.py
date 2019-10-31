import collections

from django import forms as django_mvc
from django.forms.utils import ErrorList
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.forms.renderers import get_default_renderer
from django.utils.html import mark_safe
from django.forms.utils import ErrorList,ErrorDict

from . import forms
from . import boundfield
from . import fields
from .utils import SubpropertyEnabledDict
from django_mvc.models import DictMixin,ModelDictWrapper


class ListDataForm(django_mvc.BaseForm,collections.Iterable):
    def __init__(self,listform, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=None,
                 empty_permitted=False, field_order=None, use_required_attribute=None, renderer=None):
        self.listform = listform
        self.is_bound = data is not None or files is not None
        self.files = {} if files is None else files
        self.auto_id = auto_id
        if prefix is not None:
            self.prefix = prefix
        self.error_class = error_class
        # Translators: This is the default suffix added to form field labels
        self.label_suffix = label_suffix if label_suffix is not None else _(':')
        self.empty_permitted = empty_permitted
        self._errors = None  # Stores the errors after clean() has been called.

        if use_required_attribute is not None:
            self.use_required_attribute = use_required_attribute

        # Initialize form renderer. Use a global default if not specified
        # either as an argument or as self.default_renderer.
        if renderer is None:
            if self.default_renderer is None:
                renderer = get_default_renderer()
            else:
                renderer = self.default_renderer
                if isinstance(self.default_renderer, type):
                    renderer = renderer()
        self.renderer = renderer

    @property
    def check(self):
        return self.listform.check

    @property
    def boundfields(self):
        return self.listform.boundfields

    @property
    def fields(self):
        return self.listform.fields

    @property
    def instance(self):
        return self.listform.instance

    @instance.setter
    def instance(self,value):
        pass

    @property
    def initial(self):
        return self.listform.initial

    @initial.setter
    def initial(self,value):
        pass

    @property
    def data(self):
        return self.listform.data

    @property
    def request(self):
        return self.listform.request

    @data.setter
    def data(self,value):
        pass

    @property
    def path(self):
        return self.listform.requesturl.path

    @property
    def fullpath(self):
        return self.listform.requesturl.fullpath

    @property
    def quotedfullpath(self):
        return self.listform.requesturl.quotedfullpath

    def querystring(self,ordering=None,page=None):
        return self.listform.requesturl.querystring(ordering,page)

    @property
    def querystring_without_ordering(self):
        return self.listform.requesturl.querystring_without_ordering

    @property
    def querystring_without_paging(self):
        return self.listform.requesturl.querystring_without_paging

    def get_querystring(self,paramname,paramvalue=None):
        return self.listform.requesturl.get_querystring(paramname,paramvalue)

    @property
    def pk(self):
        return self.initial.pk

    @property
    def is_bound(self):
        return self.listform.is_bound

    def __getitem__(self, name):
        return self.listform.__getitem__(name)

    @is_bound.setter
    def is_bound(self,value):
        pass

    def __iter__(self):
        self._index = -1
        return self

    def __next__(self):
        self._index += 1
        if self._index >= len(self.listform._meta.ordered_fields):
            raise StopIteration()
        else:
            return self.listform[self.listform._meta.ordered_fields[self._index]]

    def as_table(self):
        "Return this form rendered as HTML <tr>s -- excluding the <table></table>."
        return self._html_output(
            normal_row='<td %(html_class_attr)s>%(field)s</td>',
            error_row='',
            row_ender='</td>',
            help_text_html='<br /><span class="helptext">%s</span>',
            errors_on_separate_row=False)


def _model_to_dict(self,obj):
    try:
        self._dictwrapper.obj = obj
    except AttributeError as es:
        self._dictwrapper = ModelDictWrapper(obj)
    return self._dictwrapper


class ListModelFormMetaclass(forms.BaseModelFormMetaclass,collections.Iterable.__class__):
    """
    Support list reslated features
    1. toggleable_fields to declare toggleable fields
    2. default_toggled_fields to declare default toggled fields
    """
    
    def __new__(mcs, name, bases, attrs):
        if 'Meta' in attrs :
            for item,default_value in [('asc_sorting_html_class','headerSortUp'),('desc_sorting_html_class','headerSortDown'),('sorting_html_class','headerSortable'),
                    ('toggleable_fields',None),('default_toggled_fields',None),('sortable_fields',None),('listdataform',ListDataForm)]:
                if not hasattr(attrs['Meta'],item):
                    config = forms.BaseModelFormMetaclass.get_meta_property_from_base(bases,item)
                    if config:
                        setattr(attrs['Meta'],item,config)
                    else:
                        setattr(attrs['Meta'],item,default_value)

        new_class = super(ListModelFormMetaclass, mcs).__new__(mcs, name, bases, attrs)
        meta = getattr(new_class,"Meta") if hasattr(new_class,"Meta") else None
        opts = getattr(new_class,"_meta") if hasattr(new_class,"_meta") else None
        if not opts or not meta:
            return new_class

        for item in ['asc_sorting_html_class','desc_sorting_html_class','sorting_html_class','toggleable_fields','default_toggled_fields','sortable_fields','listdataform']:
            if hasattr(meta,item) :
                setattr(opts,item,getattr(meta,item))
            else:
                setattr(opts,item,None)

        model = opts.model
        model_field = None

        if opts.toggleable_fields:
            for field in opts.toggleable_fields:
                field = field.lower()
                classes = getattr(new_class.all_fields[field],"css_classes") if hasattr(new_class.all_fields[field],"css_classes") else []
                classes.append("{}".format(field))
                """
                if field not in classes:
                    classes.append(field)
                """
                if opts.default_toggled_fields and field not in opts.default_toggled_fields:
                    classes.append("hide")
                setattr(new_class.all_fields[field],"css_classes",classes)

        #if has a class initialization method, then call it
        if hasattr(new_class,"_init_class"):
            getattr(new_class,"_init_class")()
                
        #set different way to convert a model instance to dict object
        if hasattr(meta,"model"):
            model = getattr(meta,"model")
            if issubclass(model,(DictMixin,dict)):
                setattr(new_class,"model_to_dict",staticmethod(lambda obj:obj))
            else:
                setattr(new_class,"model_to_dict",_model_to_dict)

        return new_class

class ToggleableFieldIterator(collections.Iterable):
    def __init__(self,form):
        self.form = form
        self._index = None
        self._toggleable_fields = self.form._meta.toggleable_fields if hasattr(self.form._meta,"toggleable_fields") else None

    def __iter__(self):
        self._index = -1
        return self

    def __next__(self):
        self._index += 1
        if self._toggleable_fields and self._index < len(self._toggleable_fields):
            return self.form[self._toggleable_fields[self._index]]
        else:
            raise StopIteration()


class ListForm(forms.FormInitMixin,forms.ActionMixin,forms.RequestUrlMixin,forms.ModelFormMetaMixin,django_mvc.BaseForm,collections.Iterable,metaclass=ListModelFormMetaclass):
    """
    Use a form to display list data 
    used to display only
    """
    check = None
    error_title = None
    errors_title = None
    _errors = None
    cleaned_data = {}
    def __init__(self,instance_list=None,check=None,parent_instance=None,**kwargs):
        if check is not None:
            self.check = check
        kwargs["data"] = None
        super().__init__(**kwargs)
        self.fields = self.all_fields

        self.instance_list = instance_list
        #set index to one position before the start position. because we need to call next() before getting the first data 
        self.index = None
        self.parent_instance = parent_instance
        self.dataform = self._meta.listdataform(self)
        if self._meta.subproperty_enabled:
            self.current_instance = SubpropertyEnabledDict({})

    @property
    def boundfieldlength(self):
        return len(self._meta.ordered_fields)

    @property
    def tablecolumns(self):
        if self.has_actions:
            return len(self._meta.ordered_fields) + 1
        else:
            return len(self._meta.ordered_fields) + 1

    @property
    def boundfields(self):
        return boundfield.BoundFieldIterator(self)

    @property
    def haslistfooter(self):
        return True if self.listfooter else False

    @property
    def toggleablefields(self):
        if hasattr(self._meta,"toggleable_fields") and self._meta.toggleable_fields:
            return ToggleableFieldIterator(self)
        else:
            return None

    @property
    def model_name_lower(self):
        return self._meta.model.__name__.lower()

    @property
    def model_name(self):
        return self._meta.model.__name__

    @property
    def model_verbose_name(self):
        return self._meta.model._meta.verbose_name;

    @property
    def model_verbose_name_plural(self):
        return self._meta.model._meta.verbose_name_plural;

    @property
    def instance(self):
        if self.index < 0:
            return None
        elif self.instance_list and self.index < len(self.instance_list):
            return self.instance_list[self.index]
        else:
            return None

    @instance.setter
    def instance(self,value):
        pass

    @property
    def initial(self):
        if self.index < 0:
            return {}
        elif self.instance_list and self.index < len(self.instance_list):
            if self._meta.subproperty_enabled :
                self.current_instance.data = self.model_to_dict(self.instance_list[self.index])
                return self.current_instance
            else:
                return self.model_to_dict(self.instance_list[self.index])
        else:
            return {}

    @initial.setter
    def initial(self,value):
        pass

    @property
    def toggleable_fields(self):
        return self._meta.toggleable_fields
    
    def __len__(self):
        if self.instance_list:
            return len(self.instance_list)
        else:
            return 0

    @property
    def first(self):
        self.index = 0
        return self.dataform

    @property
    def errors(self):
        return self._errors


    def full_check(self):
        self._errors = ErrorDict()

        self._check_form()
        
        return False if self._errors else True

    def _check_form(self):
        try:
            self.check_form()
        except django_mvc.ValidationError as e:
            self.add_error(None, e)

    def check_form(self):
        pass

    def footerfield(self,name):
        return self[name].as_widget()

    def __iter__(self):
        self.index = -1
        return self

    def __next__(self):
        self.index += 1
        if self.instance_list:
            if self.index < len(self.instance_list):
                return self.dataform
            else:
                raise StopIteration()
        else:
            raise StopIteration()

    def get_initial_for_field(self, field, field_name):
        """
        Return initial data for field on form. Use initial data from the form
        or the field, in that order. Evaluate callable values.
        """
        value = self.initial.get(field_name, field.initial)
        if callable(value):
            if isinstance(value,models.manager.Manager):
                return value.all()
            else:
                value = value()
        return value


    def __getitem__(self, name):
        """Return a BoundField with the given name."""
        #if name == "planning_status":
        #    import ipdb;ipdb.set_trace()
        try:
            field = self.fields[name]
        except KeyError:
            try:
                field = self.listfooter_fields[name]
            except:
                raise KeyError(
                    "Key '%s' not found in '%s'. Choices are: %s." % (
                        name,
                        self.__class__.__name__,
                        ', '.join(sorted([f for f in self.fields] + [f for f in self.listfooter_fields])),
                    )
                )
        if name not in self._bound_fields_cache:
            if name == "loginuser":
                self._bound_fields_cache[name] = boundfield.LoginUserListBoundField(self,field,name)
            elif isinstance(field,fields.CompoundField):
                if field.field_name == 'loginuser':
                    self._bound_fields_cache[name] = boundfield.LoginUserCompoundListBoundField(self,field,name)
                else:
                    self._bound_fields_cache[name] = boundfield.CompoundListBoundField(self,field,name)
            elif isinstance(field,fields.AggregateField):
                self._bound_fields_cache[name] = boundfield.AggregateBoundField(self,field,name)
            elif isinstance(field,fields.HtmlStringField):
                self._bound_fields_cache[name] = boundfield.HtmlStringBoundField(self,field,name)
            else:
                self._bound_fields_cache[name] = boundfield.ListBoundField(self,field,name)
        return self._bound_fields_cache[name]

    def as_table(self):
        raise NotImplementedError()


            
