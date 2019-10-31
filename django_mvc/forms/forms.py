from collections import OrderedDict
import re
import imp
import inspect
from itertools import chain

from django import forms
from django.utils import six,safestring
from django.utils.encoding import python_2_unicode_compatible
from django.utils.html import html_safe
from django.forms.utils import ErrorList,ErrorDict
from django.db import transaction,models
from django.template.defaultfilters import safe
from django.contrib import messages
from django.core.exceptions import ValidationError,ObjectDoesNotExist
from django.conf import settings
from django.core import validators
import django.db.models.fields
from django.dispatch import receiver

from . import widgets
from . import fields
from . import boundfield
from .fields import (CompoundField,FormField,FormSetField,AliasFieldMixin)

from .utils import FieldClassConfigDict,FieldWidgetConfigDict,FieldLabelConfigDict,SubpropertyEnabledDict,ChainDict,Media,NoneValueKey
from ..models import DictMixin,AuditMixin,ModelDictWrapper
from django_mvc.signals import widgets_inited,system_ready
from django_mvc.utils import load_module,is_equal


def create_boundfield(self,form,field,name):
    """
    This method will be assigned to form class as instance method to create bound field
    """
    return self.boundfield_class(form,field,name)
    

class EditableFieldsMixin(object):
    """
    A mixin to let the view set the editable fields per request
    """
    def __init__(self,editable_fields = None,*args,**kwargs):
        self._editable_fieldnames = editable_fields
        super(EditableFieldsMixin,self).__init__(*args,**kwargs)

    @property
    def editable_fieldnames(self):
        result = self._meta._editable_fields
        if self._editable_fieldnames is None:
            return result
        else:
            return [f for f in result if f in self._editable_fieldnames]

    @property
    def editable_formfieldnames(self):
        result = self._meta._editable_formfields
        if self._editable_fieldnames is None:
            return result
        else:
            return [f for f in result if f in self._editable_fieldnames]

    @property
    def editable_formsetfieldnames(self):
        result = self._meta._editable_formsetfields
        if self._editable_fieldnames is None:
            return result
        else:
            return [f for f in result if f in self._editable_fieldnames]

    @property
    def update_db_fields(self):
        result = self._meta.update_db_fields
        if self._editable_fieldnames is None:
            return result
        else:
            return [f for f in result if f in self._editable_fieldnames or f in self._meta.extra_update_fields]

class ActionMixin(object):
    """
    A mixin to iterate actions or buttons which are supported by this form instance and enabled for the current request user
    action is usually displayed as html select option, mostly used in list page
    button is usually displayed as html button, mostly used in form page

    Actions and buttons must be a list of Action instance
    """
    all_actions = []
    all_buttons = []

    class ActionIterator(object):
        def __init__(self,form,actions,is_valid_action=None):
            self._form = form
            self._actions = actions
            self._is_valid_action = is_valid_action
        
        def __iter__(self):
            self.index = -1
            return self

        def __next__(self):
            while self.index < len(self._actions) - 1:
                self.index += 1
                action = self._actions[self.index]
                #print("{}".format(action.tag_attrs))
                if self._is_valid_action and not self._is_valid_action(action):
                    continue
                if action.has_permission(self._form.request.user if self._form.request else None):
                    return action

            raise StopIteration()

    @property
    def actions(self):
        if not self.all_actions:
            return self.all_actions
        elif not self.request:
            return self.all_actions
        else:
            return self.ActionIterator(self,self.all_actions)

    @property
    def has_actions_or_submit_buttons(self):
        if hasattr(self,"_has_action_or_submit_buttons"): 
            return self._has_action_or_buttons
        else:
            self._has_action_or_buttons = self.has_actions or self.has_submit_buttons
            return self._has_action_or_buttons

    @property
    def has_actions(self):
        if not self.all_actions:
            return False
        elif not self.request:
            return True
        elif hasattr(self,"_has_action"): 
            return self._has_action
        else:
            for a in self.ActionIterator(self,self.all_actions,lambda action:action.action != ""):
                self._has_action = True
                return True
            self._has_action = False
            return False

    @property
    def buttons(self):
        if not self.all_buttons:
            return self.all_buttons
        elif not self.request:
            return self.all_buttons
        else:
            return self.ActionIterator(self,self.all_buttons)

    @property
    def has_buttons(self):
        if not self.all_buttons:
            return False
        elif not self.request:
            return True
        elif hasattr(self,"_has_button"): 
            return self._has_button
        else:
            for a in self.ActionIterator(self,self.all_buttons):
                self._has_button = True
                return True
            self._has_button = False
            return False

    @property
    def has_submit_buttons(self):
        if not self.all_buttons:
            return False
        elif not self.request:
            return True
        elif hasattr(self,"_has_submit_button"): 
            return self._has_submit_button
        else:
            for a in self.ActionIterator(self,self.all_buttons,lambda action:action.tag_attrs.get("type") == "submit"):
                self._has_submit_button = True
                return True
            self._has_submit_button = False
            return False


class RequestMixin(object):
    """
    A mixin to inject a request object into a form instance
    """
    def __init__(self,request=None,*args,**kwargs):
        self.request = request
        super(RequestMixin,self).__init__(*args,**kwargs)

class RequestUrlMixin(RequestMixin):
    """
    A mixin to inject a request url object into a form instance to provide some request url related properties and method
    """
    def __init__(self,requesturl=None,*args,**kwargs):
        self.requesturl = requesturl
        super(RequestUrlMixin,self).__init__(*args,**kwargs)

    @property
    def path(self):
        return self.requesturl.path

    @property
    def fullpath(self):
        return self.requesturl.fullpath

    @property
    def quotedfullpath(self):
        return self.requesturl.quotedfullpath

    @property
    def sorting(self):
        return self.requesturl.sorting

    @property
    def sorting_string(self):
        return self.requesturl.sorting_string

    def querystring(self,ordering=None,page=None):
        return self.requesturl.querystring(ordering,page)

    @property
    def querystring_without_ordering(self):
        return self.requesturl.querystring_without_ordering

    @property
    def querystring_without_paging(self):
        return self.requesturl.querystring_without_paging

    def get_querystring(self,paramname,paramvalue=None):
        return self.requesturl.get_querystring(paramname,paramvalue)

_formclasses = []

class BaseFormMetaclassMixin(object):
    """
    Extend django's ModelFormMetaclass to support the following features
    1. Inheritance the meta properties from super class
    2. automatically populate 'update_fields' when saving a model instance
    3. Unsupport the follwoing properties in subclass 'Meta'
        1. exclude: any configration for the property "excludes" in Meta class will be ignored
        2. fields: any configration for the property "fields" in Meta class will be ignored
        3. labels: any configuration for the property "labels" in Meta class will be ignored
    4. Support the following properties to subclass 'Meta'
        1. Model: the model class for the model form
        2. third_party_model: the model is from third party,default is False
        3. labels_config: config the field class for editing and view
        4. field_classes_config: config the field class for editing and view
        5. widgets_config: config widget for editing and view
        6. all_fields: list all the fields
        7. editable_fields: list all editable fields
        8. ordered_fields: support sort fields, default is 'all_fields'
        9. container_attrs: specify the attributes(including css) of the field's container element. mostly used in the list table.is a tuple with length 2; first is for header; second is for data
        10. listfooter_fields: the footer fields for the list. a 2 dimensions list. the first dimension is row, the second dimension is column.
            column can be.
            1. None: empty column
            2. string: a column with colspan=1.
            3. tuple. (field name,colspan): if field name is None, means empty column; if colspan is 0, means hidden column 
            for example
            [((None,0),"total",None,"total_area_treated","total_area_estimate","total_edging_length","total_edging_depth_estimate",None,None,None,None)]

        11. formfield_callback: a metod to provide some custom logic to create form field instance.
        12. extra_update_fields: add extra update fields to 'update_fields' when saving a model instance
        13: editable_fields: list all editable fields.
        14. purpose: a tupe with 2 length, it is used to choose right fields and widgets to create form field instance
            first member: a string or list of string, for editable fields; if it is None, editable_fields will be ignored, and no fields is editable
            second member: a string or list of string,  for display fields
        15. field_required_flag: add '*' to label of required edit field,default is True

    Add the following properties into _meta property of model instance
    1. subproperty_enabled: True if some form field is created for subproperty of a model field or model property
    2. update_db_fields: possible db fields which can be updated through the form instance
    3. update_m2m_fields: possible m2m fields which can be updated through the form instance
    4. update_model_properties: possible model properties or subproperties which can be updated through the form instance
    5. save_model_properties: True if model supports save properties;otherwise False
    6. _editable_fields: the editable fields
    7. _editable_formfields: the editable form fields
    8. _editable_formsetfields: the editable formset fields
    9. editable: True if editable;otherwise False
    10. _extra_update_nonaudit_fields: add extra update non audit fields 
    11. _extra_update_audit_fields: add extra update audit fields
    12. enhanced_form_fields: True if some form field is not originally supported by django form; otherwise False

    Change the following properties into form class
    1.base_fields: always be a empty list to avoid deep clone the fields in form instance.
        This framework disallow the form class change the field and it's widget in form instance, so no need to clone the fields
    2.listfooter_fields: a dict for footfield name and foot field instance
    3.listfooter: 2 dimension list, first list is row; second list is columns. each column is a tuple (field name,colspan)
    4.model_to_dict:a static method to convert a object to a dict like object
    5.all_fields: all fields
    6.total_fields: all_fields + listfooter_fields

    Add the follwing properties to all form field instance if required
    1. create_boundfield: a class method to create a bound field instance for this form field
    2. boundfield_class: a class property, set to a default class ''BoundField' if not present in field class,

    """
 
    @staticmethod
    def get_meta_property_from_base(bases,name):
        """
        Get meta property value from bases
        if not found, return None
        this method only supports direct bases.
        """
        for b in bases:
            if hasattr(b, 'Meta') and hasattr(b.Meta, name):
                return getattr(b.Meta,name)
        return None

    def __new__(mcs, name, bases, attrs):
        base_formfield_callback = None
        #inheritence some configuration from super class
        """
        if name == 'DateRangeFilterForm':
            import ipdb;ipdb.set_trace()
        """
        if 'Meta' in attrs :
            if not hasattr(attrs['Meta'],'model'):
                #can't find the model property in the subclass 'Meta', try to get it from bases
                config = BaseFormMetaclassMixin.get_meta_property_from_base(bases,'model')
                if config:
                    setattr(attrs["Meta"],"model",config)

            #check whether model is compatible with the model form
            if hasattr(attrs["Meta"],"model"):
                model = getattr(attrs["Meta"],"model")
                if not issubclass(model,DictMixin) and (not hasattr(attrs["Meta"],"third_party_model") or not attrs["Meta"].third_party_model):
                    #To improve the performance, the model of the model form must extend the DictMixin or be a third parth model which is flagged by the meta property 'third_party_model'
                    raise Exception("{}.{} does not extend from DictMixin".format(model.__module__,model.__name__))

            for item in ('exclude','fields','labels'):
                if hasattr(attrs['Meta'],item):
                    raise Exception("'{}' is not supported in the Meta class of the form class '{}'".format(item,name))

            #get the property value from Meta class of the base classes if not configured in the Meta class
            for item in ("all_fields","extra_update_fields","ordered_fields",'purpose',"localized_fields","help_texts"):
                if not hasattr(attrs['Meta'],item):
                    config = BaseFormMetaclassMixin.get_meta_property_from_base(bases,item)
                    if config:
                        setattr(attrs["Meta"],item,config)

            #set ordered_fields to all_fields if all_fields is declared, but ordered_fields is not declared.
            if hasattr(attrs['Meta'],"all_fields") and not hasattr(attrs['Meta'],"ordered_fields"):
                setattr(attrs['Meta'],"ordered_fields",getattr(attrs['Meta'],'all_fields'))

            for item in ("editable_fields","container_attrs","listfooter_fields"):
                if not hasattr(attrs['Meta'],item):
                    config = BaseFormMetaclassMixin.get_meta_property_from_base(bases,item)
                    if config:
                        setattr(attrs["Meta"],item,config)
                    else:
                        setattr(attrs["Meta"],item,None)


            #get the configuration from the base classes, and update it with the configration in the Meta class
            for item in ("labels_config","field_classes_config","widgets_config","error_messages"):
                config = BaseFormMetaclassMixin.get_meta_property_from_base(bases,item)
                if not hasattr(attrs['Meta'],item):
                    if config:
                        setattr(attrs["Meta"],item,config)
                    else:
                        setattr(attrs["Meta"],item,{})
                elif config:
                    config = dict(config)
                    config.update(getattr(attrs['Meta'],item))
                    setattr(attrs['Meta'],item, config)

            #get the formfield_callback from base classes if not have
            for item in ("formfield_callback",):
                if not hasattr(attrs['Meta'],item):
                    config = BaseFormMetaclassMixin.get_meta_property_from_base(bases,item)
                    if config:
                        if hasattr(config,"__func__"):
                            setattr(attrs["Meta"],item,staticmethod(config.__func__))
                        else:
                            setattr(attrs["Meta"],item,staticmethod(config))

            #get some helper method from base classes if not have
            for item in ("is_dbfield","innerest_model","is_editable_dbfield"):
                if not hasattr(attrs['Meta'],item):
                    config = BaseFormMetaclassMixin.get_meta_property_from_base(bases,item)
                    if config:
                        if hasattr(config,"__func__"):
                            setattr(attrs["Meta"],item,classmethod(config.__func__))
                        else:
                            setattr(attrs["Meta"],item,classmethod(config))

            #prevent the super class from processing the fields, set fields to empty list
            setattr(attrs['Meta'],"fields",[])

            setattr(attrs['Meta'],"field_classes",FieldClassConfigDict(attrs['Meta'],attrs['Meta'].field_classes_config))
            setattr(attrs['Meta'],"widgets",FieldWidgetConfigDict(attrs['Meta'],attrs['Meta'].widgets_config))
            setattr(attrs['Meta'],"labels",FieldLabelConfigDict(attrs['Meta'],attrs['Meta'].labels_config))

        new_class = super(BaseFormMetaclassMixin, mcs).__new__(mcs, name, bases, attrs)
        meta = getattr(new_class,"Meta") if hasattr(new_class,"Meta") else None
        for item in ("localized_fields","help_texts","error_messages"):
            if not hasattr(meta,item):
                setattr(meta,item,None)

        opts = getattr(new_class,"_meta") if hasattr(new_class,"_meta") else None
        if not meta or not hasattr(meta,"all_fields") or not getattr(meta,"all_fields"):
            # all_fields configured, return directly.
            return new_class

        if opts is None:
            class Opts(object):
                field_classes = meta.field_classes
                widgets = meta.widgets
                labels = meta.labels
                localized_fields = meta.localized_fields
                help_texts = meta.help_texts
                error_messages = meta.error_messages
                pass
            opts = Opts
            setattr(new_class,"_meta",Opts)

        #copy properties from Meta class to _meta class
        for item in ("all_fields","ordered_fields","labels_config","field_classes_config","widgets_config","container_attrs","editable_fields","purpose","listfooter_fields"):
            if hasattr(meta,item) :
                setattr(opts,item,getattr(meta,item))
            else:
                setattr(opts,item,None)

        for item in ("extra_update_fields",):
            if hasattr(meta,item) :
                setattr(opts,item,getattr(meta,item))
            else:
                setattr(opts,item,[])

        #get formfield_callback to create form field instance
        formfield_callback = meta.formfield_callback if meta and hasattr(meta,"formfield_callback") else None

        model = opts.model if hasattr(opts,"model") else None
        if model:
            #try to add AuditMixin related fields into extra_update_fields.
            if meta.editable_fields is None or meta.editable_fields:
                if issubclass(model,AuditMixin):
                    for f in ("modifier","modified"):
                        if f not in opts.extra_update_fields:
                            if not isinstance(opts.extra_update_fields,list):
                                opts.extra_update_fields = list(opts.extra_update_fields)
                            opts.extra_update_fields.append(f)

        opts.extra_update_nonaudit_fields = [f for f in opts.extra_update_fields if f not in ["modifier","modified","created","creator"]]
        opts.extra_update_audit_fields = [f for f in opts.extra_update_fields if f in ["modifier","modified","created","creator"]]

        field_list = []
        kwargs = {}
        #True if this form need to access sub property; otherwise is False
        subproperty_enabled = False
        
        #the model field object if the field_name is not a sub property and it is a model field in the model class; othterwise is None
        model_dbfield = None
        #for sub property, this is the toppest property which is a direct property/model field in the model class
        #for model field, it is None; otherwise it is the field name which should be a property in model class.
        #for form declared field, it is None
        property_name = None
        #True if field_name is a db field or nested db field;otherwise it is False
        db_field = False

        editable = False
        #True if form field is declared in form; otherwise is False which means it is based on a model property or model field
        form_declared = False
        #the following variables are used only if the complete field_name has a innerest moodel

        #a tuple it is a nested db field; otherwise is None
        # 0: innerst model
        # 1: the model field of the innerest model if it is a nested db field; otherwise it is None
        # 2: property name the toppest property in the innerest model if it is not a innerest db field; otherwise it is None
        # 3: field names a sub property(including the property name) in the innerest model if it is not a innerest db field; otherwise it is None
        innerest_model = None
        #the class name of the innerest model
        innerest_model_class_name = None
        #the module name of the model form class for the innerest model
        #can configure the module in settings "FORM_MODULE_MAPPING"; 
        #if not found, using the name "{}.forms.{}".format(".".join(innerest_model[0].__module__.split(".")[:-1]),innerest_model[0].__name__.lower())
        innerest_model_form_module_name = None
        #the module of the model form class for the innerest model
        innerest_model_form_module = None
        #the model form class for the innerest model, it's name is "[innerest_model_dbfield_name]BaseForm" in remote module
        innerest_model_formclass = None
        #the _meta class of the innerest model form class
        innerest_model_opts = None
        #the model field of the innerest model if the complete field_name is a nested db field
        innerest_model_dbfield = None
        #the property name  in the innerest model if the complete field_name is not a nested db field
        #the name of the model field in the innerest model if the complete field_name is a nested db field
        innerest_model_property_name = None
        #the name of the model field in the innerest model if the complete field_name is a nested db field
        #the field name(including property name) of the model field in the innerest  model
        innerest_model_dbfield_name = None

        for field_name in opts.all_fields or []:
            """
            if name == 'DateRangeFilterForm':
                import ipdb;ipdb.set_trace()
            """
            model_dbfield = None
            property_name = None
            db_field = False
            editable = False
            form_declared = False

            innerest_model = None
            innerest_model_class_name = None
            innerest_model_form_module_name = None
            innerest_model_form_module = None
            innerest_model_formclass = None
            innerest_model_dbfield_name = None
            innerest_model_opts = None
            innerest_model_dbfield = None
            innerest_model_property_name = None

            #if field_name == "prescription__maximum_risk":
            #    import ipdb;ipdb.set_trace()
            try:
                if not model:
                    raise Exception("Not a model field")
                if "__" in field_name:
                    #this field is a sub property
                    property_name = field_name.split("__",1)[0]
                    subproperty_enabled = True

                    innerest_model = meta.innerest_model(field_name)
                    if not innerest_model:
                        raise Exception("Not a model field")
                    elif opts.field_classes.keypurpose(field_name)[1]:
                        raise Exception("Nested field can't be editable")
                    innerest_model_class_name = "{}.{}".format(innerest_model[0].__module__,innerest_model[0].__name__)
                    
                    if hasattr(settings,"FORM_MODULE_MAPPING") and getattr(settings,"FORM_MODULE_MAPPING") and innerest_model_class_name in settings.FORM_MODULE_MAPPING:
                        innerest_model_form_module_name = settings.FORM_MODULE_MAPPING[innerest_model_class_name]
                    else:
                        innerest_model_form_module_name = "{}.forms.{}".format(".".join(innerest_model[0].__module__.split(".")[:-1]),innerest_model[0].__name__.lower())
                    innerest_model_form_module = load_module(innerest_model_form_module_name,settings.BASE_DIR)
                    try:
                        innerest_model_formclass = getattr(innerest_model_form_module,"{}BaseForm".format(innerest_model[0].__name__))
                        innerest_model_opts = getattr(innerest_model_formclass,"_meta") if hasattr(innerest_model_formclass,"_meta") else None
                    except:
                        innerest_model_opts = None
                    if innerest_model[1]:
                        #is a innerest db field
                        innerest_model_dbfield = innerest_model[1]
                        innerest_model_dbfield_name = innerest_model_dbfield.name
                        innerest_model_property_name = innerest_model_dbfield_name
                        db_field = True
                    else:
                        innerest_model_dbfield = None
                        db_field = False
                        innerest_model_property_name = innerest_model[2]
                        innerest_model_dbfield_name = "__".join(innerest_model[3])

                else:
                    try:
                        model_dbfield = model._meta.get_field(field_name)
                        db_field = True
                    except:
                        property_name = field_name
                        raise
            except:
                #not a model field, check whether it is a property 
                if innerest_model:
                    raise
                db_field = False
                if not model or not hasattr(model,property_name) or not isinstance(getattr(model,property_name),property):
                    #no corresponding property in model, it should be a form field declared in form
                    property_name = None
                    form_declared = True
                

            kwargs.clear()
            #try to get configured field_class
            editable = opts.field_classes.keypurpose(field_name)[1]
            field_class = None
            try:
                #try to get the field configuration from form's _meta class 
                field_class = opts.field_classes.get_config(field_name,enable_default_key=False if innerest_model else True)
            except NoneValueKey:
                pass
            except:
                #if field_name is a innerest dbfield, try to get field configuration from innerest model form's _meta class
                if innerest_model and innerest_model_opts:
                    try:
                        #has a innerest_model, try to get field_class from innerest model form using the current form's purpose
                        field_class = innerest_model_opts.field_classes.get_config(innerest_model_dbfield_name,(None,meta.purpose[1]) if hasattr(meta,"purpose") else (None,"view"))
                    except:
                        pass

            if field_class and isinstance(field_class,forms.Field):
                #already configure a form field instance, use it directly
                field_class.form_declared = form_declared
                #check whether widget requires subproperty support
                if not subproperty_enabled and isinstance(field_class.widget,widgets.DataPreparationMixin) and field_class.widget.subproperty_enabled :
                    subproperty_enabled = True

                field_list.append((field_name, field_class))
                continue

            #if field class is subclass of AliasFieldMixin, try to check whether it is a model field or not.
            if field_class and issubclass(field_class,AliasFieldMixin) and model:
                try:
                    if innerest_model:
                        innerest_model_dbfield = innerest_model[0]._meta.get_field(field_class.field_name)
                    else:
                        model_dbfield = model._meta.get_field(field_class.field_name)
                    db_field = True
                except:
                    pass

            if field_class:
                kwargs['form_class'] = field_class
            elif not db_field :
                raise Exception("Please cofigure form field for property '{}' in 'field_classs_config' option".format(field_name))

            #try to get configured widget
            field_widget = None
            try:
                field_widget = opts.widgets.get_config(field_name,enable_default_key=False if (innerest_model or (editable and db_field)) else True)
            except NoneValueKey:
                pass
            except:
                if innerest_model and innerest_model_opts:
                    try:
                        #is a innerest_model, try to get field_class from remote form
                        field_widget = innerest_model_opts.widgets.get_config(innerest_model_dbfield_name,(None,meta.purpose[1]) if hasattr(meta,"purpose") else (None,"view"))
                    except:
                        pass

            if field_widget:
                kwargs['widget'] = field_widget
            elif not db_field:
                raise Exception("Please configure widget for property '{}.{}' in 'widgets_config' option".format(name,field_name))

            if innerest_model and innerest_model_opts:
                kwargs['localize'] = innerest_model_opts.localized_fields == forms.models.ALL_FIELDS or (innerest_model_opts.localized_fields and innerest_model_dbfield_name in innerest_model_opts.localized_fields)
            else:
                kwargs['localize'] = opts.localized_fields == forms.models.ALL_FIELDS or (opts.localized_fields and field_name in opts.localized_fields)

            if opts.labels and field_name in opts.labels:
                kwargs['label'] = safe(opts.labels[field_name])
            elif innerest_model:
                #if field_name == "prescription__current_approval":
                #    import ipdb;ipdb.set_trace()
                if innerest_model_opts and innerest_model_opts.labels and innerest_model_dbfield_name in innerest_model_opts.labels:
                    kwargs['label'] = safe(innerest_model_opts.labels[innerest_model_dbfield_name])
                elif not db_field:
                    kwargs['label'] = safe(innerest_model_dbfield_name)
            elif not db_field:
                    kwargs['label'] = safe(field_name)

            if innerest_model:
                if innerest_model_opts and innerest_model_opts.help_texts and innerest_model_dbfield_name in innerest_model_opts.help_texts:
                    kwargs['help_text'] = innerest_model_opts.help_texts[innerest_model_dbfield_name]
            else:
                if opts.help_texts and field_name in opts.help_texts:
                    kwargs['help_text'] = opts.help_texts[field_name]

            if innerest_model:
                if innerest_model_opts and innerest_model_opts.error_messages and innerest_model_dbfield_name in innerest_model_opts.error_messages:
                    kwargs['error_messages'] = innerest_model_opts.error_messages[innerest_model_dbfield_name]
            else:
                if opts.error_messages and field_name in opts.error_messages:
                    kwargs['error_messages'] = opts.error_messages[field_name]

            #try to set some keywords parameters from db field's validator
            if db_field and editable:
                field = innerest_model_dbfield if innerest_model else model_dbfield
                for validator in field.validators or []:
                    if isinstance(validator,validators.MinValueValidator):
                        kwargs["min_value"] = validator.limit_value
                    elif isinstance(validator,validators.MaxValueValidator):
                        kwargs["max_value"] = validator.limit_value

            #set required to False for all non db field
            if not db_field:
                kwargs['required'] = False

            if not callable(formfield_callback):
                raise TypeError('formfield_callback must be a function or callable')
            elif innerest_model:
                formfield = formfield_callback(innerest_model_dbfield, **kwargs)
            else:
                formfield = formfield_callback(model_dbfield, **kwargs)

            #if this field is a nested field. change field to reflect the nested field
            if innerest_model:
                prefix = field_name[:-1 * len(innerest_model_property_name)]
                if isinstance(formfield,AliasFieldMixin):
                    formfield.field_name = "{}{}".format(prefix,formfield.field_name)
                if isinstance(formfield,CompoundField):
                    formfield.field_prefix = prefix
                    #formfield.related_field_names = ["{}{}".format(prefix,f) for f in formfield.related_field_names]

                if isinstance(formfield.widget,widgets.DataPreparationMixin):
                    #add prefix to ids and parameters 
                    if hasattr(formfield.widget,"ids") and formfield.widget.ids:
                        formfield.widget.ids = [("{}{}".format(prefix,k),v) for k,v in formfield.widget.ids]
                    if hasattr(formfield.widget,"parameters") and formfield.widget.parameters:
                        formfield.widget.ids = [(k if k in ["request_full_path","loginuser"] else "{}{}".format(prefix,k),v) for k,v in formfield.widget.parameters]

            #check whether AliasField is only declared for non editable field.
            if not isinstance(formfield.widget,widgets.DisplayMixin) and isinstance(formfield,AliasFieldMixin) and formfield.field_name != field_name:
                if model:
                    raise Exception("Can't declare alias({}) for editable field ({}) in model({}.{})".format(field_name,formfield.field_name,model.__module__,model.__name__))
                else:
                    raise Exception("Can't declare alias({}) for editable field ({})".format(field_name,formfield.field_name))

            #set the boundfield class if not set by field
            if not hasattr(formfield,"boundfield_class") or not getattr(formfield,"boundfield_class"):
                formfield.boundfield_class = boundfield.BoundField
            #create a instance method to create boundfild
            formfield.__class__.create_boundfield = create_boundfield

            field_list.append((field_name, formfield))
            #check whether widget requires subproperty support
            if not subproperty_enabled and isinstance(formfield.widget,widgets.DataPreparationMixin) and formfield.widget.subproperty_enabled :
                subproperty_enabled = True

            formfield.form_declared = form_declared
    
        """
        if name == 'DateRangeFilterForm':
            import ipdb;ipdb.set_trace()
        """
        setattr(opts,'subproperty_enabled',subproperty_enabled)

        #check whether AliasFields are only declared for non editable field.
        for field_name,formfield in new_class.base_fields.items():
            if not isinstance(formfield.widget,widgets.DisplayMixin) and isinstance(formfield,forms.AliasFieldMixin) and formfield.field_name != field_name:
                if model:
                    raise Exception("Can't declare alias({}) for editable field ({}) in model({}.{})".format(field_name,formfield.field_name,model.__module__,model.__name__))
                else:
                    raise Exception("Can't declare alias({}) for editable field ({})".format(field_name,formfield.field_name))

        if field_list:
            field_list = OrderedDict(field_list)
            new_class.base_fields.update(field_list)

        #######delcare footer fields
        listfooter = []
        listfooter_fields = {}
        row_field_list = None
        for row in opts.listfooter_fields or []:
            if not row:
                continue
            row_field_list = []
            listfooter.append(row_field_list)
            for column in row:
                if not column:
                    row_field_list.append((None,1))
                    continue
                elif isinstance(column,str):
                    field_name = column
                    colspan = 1
                else:
                    field_name = column[0]
                    colspan = column[1]
                    if colspan == 0:
                        row_field_list.append((None,0))
                        continue

                kwargs.clear()
                #try to get configured field_class
                field_class = opts.field_classes.get_config(field_name)
    
                if field_class and isinstance(field_class,forms.Field):
                    #already configure a form field instance, use it directly
                    field_class.form_declared = True
                    row_field_list.append((field_name, colspan))
                    listfooter_fields[field_name] = field_class
                    continue
                elif field_class:
                    kwargs['form_class'] = field_class
                else :
                    raise Exception("Please cofigure form footer field '{}' in 'field_classes_config' option".format(field_name))
    
                #try to get configured widget
                field_widget = opts.widgets.get_config(field_name)
    
                if field_widget:
                    kwargs['widget'] = field_widget
                else:
                    raise Exception("Please configure widget for footer field '{}.{}' in 'widgets_config' option".format(name,field_name))
    
                kwargs['localize'] = False
    
                kwargs['label'] = ""
                kwargs['help_text'] = ""
                kwargs['error_messages'] = ""
    
                kwargs['required'] = False
    
                formfield = formfield_callback(None, **kwargs)
    
                #set the boundfield class if not set by field
                if not hasattr(formfield,"boundfield_class") or not getattr(formfield,"boundfield_class"):
                    formfield.boundfield_class = BoundField
                #create a instance method to create boundfild
                formfield.__class__.create_boundfield = create_boundfield

                formfield.form_declared = True

                row_field_list.append((field_name, colspan))
                listfooter_fields[field_name] = field_class

        new_class.listfooter_fields = listfooter_fields
        new_class.listfooter = listfooter

        ##################
        #add '*' to required field's label
        #if name == 'PrescribedBurnBushfireCreateForm':
        #    import ipdb;ipdb.set_trace()
        if not hasattr(meta,"field_required_flag") or getattr(meta,"field_required_flag"):
            for field in new_class.base_fields.values():
                if isinstance(field.widget,widgets.DisplayMixin):
                    continue
                if not field.required:
                    continue
                if not field.label:
                    continue
    
                if field.label.endswith('*'):
                    continue
                field.label = "{} *".format(field.label)


        #if not opts.ordered_fields:
        #   opts.ordered_fields = [f for f in new_class.base_fields.keys()]

        #populate the aggregated media
        media = Media()

        for field in new_class.base_fields.values():
            if hasattr(field.widget,"media") and field.widget.media:
                media += field.widget.media

        setattr(opts,"media",media)
        setattr(new_class,"media",media)

        _formclasses.append(new_class)

        #set different way to convert a model instance to dict object
        if hasattr(meta,"model"):
            model = getattr(meta,"model")
            if issubclass(model,(DictMixin,dict)):
                setattr(new_class,"model_to_dict",staticmethod(lambda obj:obj))
            else:
                setattr(new_class,"model_to_dict",staticmethod(lambda obj:ModelDictWrapper(obj)))

        #assign base_fields to all_fields
        #empty the base_fields to avoid deep clone
        setattr(new_class,"all_fields",new_class.base_fields)
        new_class.base_fields = []
        if not hasattr(new_class,"listfooter_fields") or not getattr(new_class,"listfooter_fields"):
            total_fields = new_class.all_fields
        else:
            total_fields = dict(new_class.all_fields)
            total_fields.update(new_class.listfooter_fields)
        setattr(new_class,"total_fields",total_fields)

        return new_class

class ModelFormMetaMixin(object):
    """
    A mixin to provide a Meta class which includes some utility methods
    """
    class Meta:
        @staticmethod
        def formfield_callback(field,**kwargs):
            override_widget_property = None
            formfield = None
            if field and isinstance(field,models.Field) and field.editable and not field.primary_key:
                form_class = kwargs.get("form_class")
                if form_class:
                    if isinstance(form_class,forms.fields.Field):
                        return form_class
                    elif issubclass(form_class,fields.ChoiceFieldMixin):
                        return kwargs.pop("form_class")(**kwargs)
                    else:
                        kwargs["choices_form_class"] = form_class
                result = field.formfield(**kwargs)
                if form_class and not isinstance(result,form_class):
                    raise Exception("'{}' don't use the form class '{}' declared in field_classes".format(field.__class__.__name__,form_class.__name__))
                formfield =  result
            else:
                formfield = kwargs.pop("form_class")(**kwargs)

            return formfield

        @classmethod
        def is_dbfield(cls,field_name):
            """
            Return True if it is not a sub property and is a db field;otherwise return False
            """
            if "__" in field_name:
                return False

            try:
                model_dbfield = cls.model._meta.get_field(field_name)
                return True
            except:
                return False

        @classmethod
        def innerest_model(cls,field_name):
            """
            return None if it is not a remote field; otherwise return a array
             0: innerst remote model
             1: remote field if it is a remote db field; otherwise it is None
             2: property name the toppest property in the remote model if it is not a remote db field; otherwise it is None
             3: field names a sub property(including the property name) in the remote model if it is not a remote db field; otherwise it is None
            """
            if "__" not in field_name:
                return None
            
            field_name = field_name.split("__")
            index = -1
            try:
                remote_model = cls.model
                for name in field_name[:-1]:
                    index += 1
                    model_dbfield = remote_model._meta.get_field(name)
                    remote_model = model_dbfield.innerest_model.model
                index += 1
                return (remote_model,remote_model._meta.get_field(field_name[-1]),None,None)
            except:
                if index <= 0:
                    return None
                else:
                    return (remote_model,None,field_name[index],field_name[index:])

        @classmethod
        def is_editable_dbfield(cls,field_name):
            """
            Return True if it is not a sub property and is a editable db field;otherwise return False
            """
            if "__" in field_name:
                return False

            try:
                model_dbfield = cls.model._meta.get_field(field_name)
                return True if model_dbfield.editable and not model_dbfield.primary_key else False
            except:
                return False

class BaseFormMetaclass(BaseFormMetaclassMixin,forms.forms.DeclarativeFieldsMetaclass):
    pass

class BaseModelFormMetaclass(BaseFormMetaclassMixin,forms.models.ModelFormMetaclass):
    pass

class FormInitMixin(object):
    """
    A mixin to final initialize the form after all actions, fields, widgets are initialized.
    """
    @classmethod
    def can_edit(cls):
        if hasattr(cls,"_meta") and hasattr(cls._meta,"editable"):
            return cls._meta.editable

        for field in cls.all_fields.values():
            if isinstance(field,FormField):
                if field.form_class.can_edit():
                    return True
            elif isinstance(field,FormSetField):
                if field.formset_class.form.can_edit():
                    return True
            elif not isinstance(field.widget,widgets.DisplayMixin):
                return True

        return False


    @classmethod
    def post_init(cls):
        meta = cls.Meta
        opts = cls._meta
        model = opts.model if hasattr(opts,"model") else None
        #populate the update_db_fields, update_m2m_fields, and update_model_properties
        update_db_fields = list(opts.extra_update_fields)
        update_m2m_fields = []
        update_model_properties = ([],[])

        _editable_fields = []
        _editable_formfields = []
        _editable_formsetfields = []
        enhanced_form_fields = False
        for name,field in cls.all_fields.items():
            if isinstance(field.widget,widgets.DisplayMixin):
                enhanced_form_fields = True
                continue
            if isinstance(field,FormField):
                #it is a form field
                if not field.is_display:
                    _editable_formfields.append(name)
                enhanced_form_fields = True
                continue
            elif isinstance(field,FormSetField):
                #it is a formset field
                if not field.is_display:
                    _editable_formsetfields.append(name)
                enhanced_form_fields = True
                continue
            else:
                _editable_fields.append(name)

            if field.form_declared:
                #this is a form declared field 
                continue
            elif "__" in name:
                #editable sub properties
                update_model_properties[0].append(name)
                update_model_properties[1].append(name)
                continue
            try:
                dbfield = model._meta.get_field(name)
                #is a dbfield
                if not dbfield.primary_key:
                    if dbfield in model._meta.many_to_many :
                        #a many to many field
                        update_m2m_fields.append(name)
                    else:
                        #is a model field, and also it is not a many to many field
                        update_db_fields.append(name)
            except:
                #not a model field
                if hasattr(model,name) and isinstance(getattr(model,name),property):
                    #field is a property
                    update_model_properties[0].append(name)
                    update_model_properties[1].append(name)
                else:
                    if isinstance(field,CompoundField) and hasattr(model,field.field_name) and isinstance(getattr(model,field.field_name),property):
                        #it is a compound field, field_name is a property
                        update_model_properties[0].append(name)
                        update_model_properties[1].append(field.field_name)
                    else:
                        #it is a not a model property
                        pass

        save_model_properties = False
        if update_model_properties[0]:
            if hasattr(cls,"save_properties") and callable(getattr(cls, "save_properties")):
                save_model_properties = True
        else:
            update_model_properties = None

        setattr(opts,'_editable_fields',_editable_fields)
        setattr(opts,'_editable_formfields',_editable_formfields)
        setattr(opts,'_editable_formsetfields',_editable_formsetfields)
        setattr(opts,'enhanced_form_fields',enhanced_form_fields)
        setattr(opts,'update_db_fields',update_db_fields)
        setattr(opts,'update_m2m_fields',update_m2m_fields)
        setattr(opts,'update_model_properties',update_model_properties)
        setattr(opts,'save_model_properties',save_model_properties)
        setattr(opts,'editable',True if (_editable_fields or _editable_formfields or _editable_formsetfields) else False)

        setattr(meta,"fields",meta.all_fields)
        setattr(opts,"fields",meta.all_fields)
 
class Form(FormInitMixin,ModelFormMetaMixin,ActionMixin,RequestUrlMixin,forms.Form,metaclass=BaseFormMetaclass):
    """
    A enhanced form to provide the following:
    1. Extended from ActionMixin to provide action related properties and methods
    2. Extended from RequestMixin to provide a request instance 
    3. provide a specifial field "loginuser" which is the user object from request
    4. Provide different boundfield for different field type.
    """

    def __init__(self, *args,**kwargs):
        initial = kwargs.get("initial")
        if initial:
            object_data = initial
        else:
            object_data = {}

        if self._meta.subproperty_enabled:
            object_data = SubpropertyEnabledDict(object_data)

        kwargs["initial"] = object_data

        super().__init__(*args,**kwargs)
        #populate the fields property
        self.fields = self.all_fields


    def __getitem__(self, name):
        """Return a BoundField with the given name."""
        try:
            field = self.total_fields[name]
        except KeyError:
            raise KeyError(
                "Key '%s' not found in '%s'. Choices are: %s." % (
                    name,
                    self.__class__.__name__,
                    ', '.join(sorted([f for f in self.total_fields])),
                )
            )
        if name not in self._bound_fields_cache:
            self._bound_fields_cache[name] = field.create_boundfield(self,field,name)

        return self._bound_fields_cache[name]

class BaseModelForm(FormInitMixin,ModelFormMetaMixin,forms.models.BaseModelForm,metaclass=BaseModelFormMetaclass):
    """
    This class only support model class which extends DictMixin

    The following features are supported.
    1. is_editable: to check whether a field is editable or not.
    2. save_properties: called right after save() method in the same transaction if update_model_properties is not emtpy.
    3. set the value of model properties or model subproperties from form instance before seting the value of model fields
    """
    #check mode if it is not none, used by clean method to differentiate between check mode and save mode 
    check = None
    #error title displayed in html page
    error_title = None
    #errors title displayed in html page
    errors_title = None
    #the cleaned data from request
    cleaned_data = {}

    #changed db fields in model
    changed_db_fields = None
    #changed m2m db fields in model
    changed_m2m_fields = None
    #changed properties in model
    changed_model_properties = None

    #True if any data is changed;False if no data is changed;none if not check
    _is_changed = None
    #True for new model instance; False for existing model instance;none if not set
    created = None
    #contain all the changed data , for debug
    _changed_data = None

    def __init__(self, data=None, files=None, auto_id='id_%s', prefix=None,
                 initial=None, error_class=ErrorList, label_suffix=None,
                 empty_permitted=False, instance=None, use_required_attribute=None,
                 renderer=None,parent_instance=None,is_bound=None,check=None):
        """
        The reason to totally override initial method of BaseModelForm is using a more efficient way to populate object_data
        """
        if check is not None:
            self.check = check

        opts = self._meta
        if opts.model is None:
            raise ValueError('ModelForm has no model class specified.')
        if instance is None:
            # if we didn't get an instance, instantiate a new one
            self.instance = opts.model()
        else:
            self.instance = instance

        #To improved the performance, use the instance directly instead of converting it to a dict object
        if instance and initial:
            object_data = ChainDict([initial,self.model_to_dict(instance)])
        elif instance:
            object_data = self.model_to_dict(instance)
        elif initial:
            object_data = initial
        else:
            object_data = {}

        if self._meta.subproperty_enabled:
            object_data = SubpropertyEnabledDict(object_data)

        # self._validate_unique will be set to True by BaseModelForm.clean().
        # It is False by default so overriding self.clean() and failing to call
        # super will stop validate_unique from being called.
        self._validate_unique = False

        #normal base_fields always set to empty list to prevent the base class from cloning the fields
        forms.forms.BaseForm.__init__(self,
            data, files, auto_id, prefix, object_data, error_class,
            label_suffix, empty_permitted, use_required_attribute=use_required_attribute,
            renderer=renderer,
        )
        #populate the fields property
        self.fields = self.all_fields

        #give a chance to client to choose whether form is bound or not.
        if is_bound is not None:
            self.is_bound = is_bound

        for formfield in self.fields.values():
            forms.models.apply_limit_choices_to_to_formfield(formfield)

        if parent_instance:
            self.set_parent_instance(parent_instance)

    def set_parent_instance(self,parent_instace):
        """
        A hook to let the subclass to set its parent instance if have
        """
        pass

    @property
    def editable(self):
        """
        True if all fields and formfields and formsetfields are nont editalbe; otherwise False
        """
        return True if (self.editable_fieldnames or self.editable_formfieldnames or self.editable_formsetfieldnames) else False

    @property
    def editable_fieldnames(self):
        return self._meta._editable_fields

    @property
    def editable_formfieldnames(self):
        return self._meta._editable_formfields

    @property
    def editable_formsetfieldnames(self):
        return self._meta._editable_formsetfields

    @property
    def ordered_fields(self):
        return self._meta.ordered_fields

    @property
    def update_db_fields(self):
        return self._meta.update_db_fields

    @property
    def update_m2m_fields(self):
        return self._meta.update_m2m_fields

    @property
    def model_verbose_name(self):
        return self._meta.model._meta.verbose_name;

    @property
    def model_verbose_name_plural(self):
        return self._meta.model._meta.verbose_name_plural;

    @property
    def save_model_properties_enabled(self) :
        return self._meta.save_model_properties

    @property
    def boundfields(self):
        return boundfield.BoundFieldIterator(self)

    def get_initial_for_field(self, field, field_name):
        """
        Return initial data for field on form. Use initial data from the form
        or the field, in that order. Evaluate callable values.
        If the value is a Manager, return all datas
        """
        value = self.initial.get(field_name, field.initial)
        if callable(value):
            if isinstance(value,models.manager.Manager):
                return value.all()
            else:
                value = value()
        return value

    def is_editable(self,name):
        """
        Return True if the field is editable;otherwise return False
        """
        return self.editable_fieldnames is None or name in self.editable_fieldnames

    def _clean_formfields(self):
        """
        get and validate cleaned value of the form fields, and save them to cleaned_data. have two steps:
        1. call 'clean_field' on formfield's boundfiled to get the cleaned value, and also the boundfield will call the clean method to validate each field in the form; if validation is failed, add a ValidationError with empty message to indicate the form field is invalid.
        2. call 'clean_[fieldname]' to validate the cleaned form value as a whole if that method exists; if validation is failed, add the ValidationError with proper message to indicate that each form member is valid,but the form as a whole is invalid. 
        """
        for name in self.editable_formfieldnames:
            field = self[name]
            try:
                value = field.clean_field()
                self.cleaned_data[name] = value
                clean_funcname = "clean_{}".format(name)
                if hasattr(self,clean_funcname):
                    self.cleaned_data[name] = getattr(self,clean_funcname)()
            except ValidationError as e:
                self.add_error(name, e)

    def _save_forms(self):
        """
        Called by the save metho to save all formset data
        """
        for name in self.editable_formfieldnames:
            field = self[name]
            field.save()

    def _clean_formsetfields(self):
        """
        get and validate cleaned value of the formset fields, and save them to cleaned_data. have two steps:
        1. call 'clean_field' on formsetfield's boundfiled to get the cleaned value and also the boundfield call the clean method to validate each field in each formset form; if validation is failed, add a ValidationError with empty message to indicate the formset field is invalid.
        2. call 'clean_[fieldname]' to validate the cleaned formset value as a whole if that method exists; if validation is failed, add the ValidationError with proper message to indicate that each formset member is valid,but the formset as a whole is invalid. 
        """
        for name in self.editable_formsetfieldnames:
            field = self[name]
            try:
                value = field.clean_field()
                self.cleaned_data[name] = value
                clean_funcname = "clean_{}".format(name)
                if hasattr(self,clean_funcname):
                    self.cleaned_data[name] = getattr(self,clean_funcname)()
            except ValidationError as e:
                self.add_error(name, e)

    def _save_formsets(self):
        """
        Called by the save method to save all formset data
        the formset bound field will check whehter the formset is changed or not in the save method.
        """
        for name in self.editable_formsetfieldnames:
            field = self[name]
            field.save()

    def _post_clean(self):
        """
        Provide enhanced logic
        1. call clean method to clean formset fields
        2. call clean metod to clean form fields
        3. save the property data to model
        4. After clean, the following properties will be set
            A. changed_db_fields
            B. changed_m2m_fields
            C. changed_model_properties

        """
        #save the value of model properties

        #for debug
        self._changed_data = {}

        extra_update_fields_data = None
        if self.instance.pk:
            #save the value of extra update non audit fields, and compare with the value after post_clean
            extra_update_fields_data = {}
            if self._meta.extra_update_nonaudit_fields:
                for f in self._meta.extra_update_nonaudit_fields:
                    extra_update_fields_data[f] = getattr(self.instance,f)

        #save the model properties into model if chaned
        #get the changed model properties for existing model instance
        if self._meta.update_model_properties:
            if self.instance.pk:
                #will contain all modified model properties
                self.changed_model_properties = []
            index = 0
            while index < len(self._meta.update_model_properties[0]):
                name = self._meta.update_model_properties[0][index]
                propertyname = self._meta.update_model_properties[1][index]
                index += 1
                if name not in self.cleaned_data:
                    continue
                try:
                    if "__" in name:
                        props = name.split("__")
                        result = getattr(self.instance,props[0])
                        for prop in props[1:-1]:
                            try:
                                result = result[prop]
                            except KeyError as ex:
                                result[prop] = {}
                                result = result[prop]
                        if self.instance.pk:
                            if not is_equal(result.get(props[-1]), self.cleaned_data[name]):
                                self.changed_model_properties.append(propertyname)
                                #for debug
                                self._changed_data[name] = (result.get(props[-1]), self.cleaned_data[name])
    
                                #update model property's value
                                result[props[-1]] = self.cleaned_data[name]
                        else:
                            result[props[-1]] = self.cleaned_data[name]
                    else:
                        if self.instance.pk:
                            if not hasattr(self.instance,propertyname) or (not is_equal(getattr(self.instance,propertyname), self.cleaned_data[name])):
                                self.changed_model_properties.append(propertyname)
    
                                #for debug
                                self._changed_data[name] = (getattr(self.instance,propertyname), self.cleaned_data[name])
    
                                #update model property's value
                                setattr(self.instance,propertyname,self.cleaned_data[name])
                        else:
                            setattr(self.instance,propertyname,self.cleaned_data[name])
                except Exception as ex:
                    raise Exception("Failed to check whether the model property({}.{}.{}) is equal with the post data({}).{} ".format(self._meta.model.__module__,self._meta.model.__class__.__name__,propertyname,name,str(ex)))
 
        if self.instance.pk:
            #get all changed db fields and m2m fields
            self.changed_db_fields = []
            self.changed_m2m_fields = []
            for key in self.fields.keys():
                try:
                    if not is_equal(self.cleaned_data.get(key),getattr(self.instance,key)):
                        if key in self.update_db_fields:
                            self.changed_db_fields.append(key)
                            #for debug
                            self._changed_data[key] = (getattr(self.instance,key), self.cleaned_data.get(key))
                        else:
                            self.changed_m2m_fields.append(key)
                            #for debug
                            self._changed_data[key] = (getattr(self.instance,key).all(), self.cleaned_data.get(key))
                except Exception as ex:
                    raise Exception("Failed to check whether the model field({}.{}.{}) is equal with the post data.{} ".format(self._meta.model.__module__,self._meta.model.__class__.__name__,key,str(ex)))

            self.created = False
        else:
            self.created = True


        #call clean_ method for m2m fields on model instance
        #if self.instance.pk and self.changed_m2m_fields:
        if self.changed_m2m_fields:
            for f in self.changed_m2m_fields:
                if hasattr(self.instance, "clean_%s" % f):
                    try:
                        getattr(self.instance, "clean_%s" % f)(self.cleaned_data.get(f))
                    except ValidationError as e:
                        self.add_error(f, e)

        #call the parent method to perform the basice cleaning.
        if self.fields:
            super(BaseModelForm,self)._post_clean()


        #clean formset fields and form fields
        #The formset fields and form fields are removed from self.fields in full_clean method, so we must restore all the fields before cleaning. 
        fields = self.fields
        try:
            self.fields = self.all_fields
            self._clean_formsetfields()
            self._clean_formfields()
        finally:
            self.fields = fields

        #check whether some extra update fields are changed or not after post clean
        #add the chaged extra update fields into changed db fields
        if extra_update_fields_data:
            for f,v in extra_update_fields_data.items():
                if getattr(self.instance,f) != v:
                    self.changed_db_fields.append(f)
                    self._changed_data[f] = (v,getattr(self.instance,f))

    @property
    def is_changed(self):
        """
        must called after full_clean
        Return true if any db field,m2m field,model property,formset field or form field is modified;otherwise return False
        """
        if self._is_changed is None:
            try:
                changed = False
                if self.created is None:
                    raise Exception("Please call full_clean first")
                elif self.created:
                    #new model instance
                    changed = True
                else:
                    #update existing instance
                    if (self.changed_db_fields or self.changed_m2m_fields or self.changed_model_properties):
                        changed = True
                    else:
                        for name in self.editable_formsetfieldnames:
                            field = self[name]
                            if field.is_changed:
                                changed = True
                                break
        
                        if not changed:
                            for name in self.editable_formfieldnames:
                                field = self[name]
                                if field.is_changed:
                                    changed = True
                                    break
        
                if not changed:
                    print("{}({}) was not changed".format(self.instance.__class__.__name__,self.instance.pk))
                self._is_changed = changed
            finally:
                pass
                #print the changed data for debug
                if (self.created):
                    print("create a {} instance".format(self.instance.__class__.__name__))
                elif self._changed_data:
                    if (self.changed_db_fields or self.changed_m2m_fields or self.changed_model_properties):
                        print("{}({}) was changed. {}{}{}".format(
                            self.instance.__class__.__name__,self.instance.pk,
                            "changed db fields:{}".format(["{}({} => {})".format(f,*self._changed_data.get(f,("!Err","!Err"))) for f in self.changed_db_fields]) if self.changed_db_fields else "", 
                            "  changed properties:{}".format(["{}({} => {})".format(p,*self._changed_data.get(p,["!Err","!Err"])) for p in self.changed_model_properties]) if self.changed_model_properties else "",
                            "  changed m2m fields:{}".format(["{}({} => {})".format(f,*self._changed_data.get(f,("!Err","!Err"))) for f in self.changed_m2m_fields]) if self.changed_m2m_fields else ""
    
                    ))
                    for name in self.editable_formsetfieldnames:
                        field = self[name]
                        if field.is_changed:
                            print("Formset field ({}) was changed".format(name))
        
                    for name in self.editable_formfieldnames:
                        field = self[name]
                        if field.is_changed:
                            print("Form field ({}) was changed".format(name))
                else:
                    if (self.changed_db_fields or self.changed_m2m_fields or self.changed_model_properties):
                        print("{}({}) was changed. {}{}{}".format(
                            self.instance.__class__.__name__,self.instance.pk,
                            "changed db fields:{}".format(self.changed_db_fields) if self.changed_db_fields else "", 
                            "  changed properties:{}".format(self.changed_model_properties) if self.changed_model_properties else "",
                            "  changed m2m fields:{}".format(self.changed_m2m_fields) if self.changed_m2m_fields else ""
    
                    ))
                    for name in self.editable_formsetfieldnames:
                        field = self[name]
                        if field.is_changed:
                            print("Formset field ({}) was changed".format(name))
        
                    for name in self.editable_formfieldnames:
                        field = self[name]
                        if field.is_changed:
                            print("Form field ({}) was changed".format(name))


        return self._is_changed
    

    def get_success_message(self) :
        """
        Return update success message to show in the next page
        """
        if not self.is_changed:
            return "{}({} - {}) wasn't changed".format(self.model_verbose_name,instance.pk,instance)
        elif self.is_created:
            return "Create {}({}) successfully".format(self.model_verbose_name,instance)
        else :
            return "Update {}({} - {}) successfully".format(self.model_verbose_name,instance.pk,instance)

    def add_message(self,message,level=messages.SUCCESS):
        """
        add message, the message will be shown in the next page.
        message can be
        1. string, 
        2. tuple (level,message)
        3. [string,string]
        4. [(level,message),string]
        """
        if not message:
            return
        if isinstance(message,str):
            messages.add_message(self.request,level,message)
        elif isinstance(message,tuple):
            messages.add_message(self.request,message[0],message[1])
        else:
            for m in message:
                if isinstance(m,str):
                    messages.add_message(self.request,level,m)
                else:
                    messages.add_message(self.request,m[0],m[1])


    def _save_m2m(self):
        """
        Compare the original logic, the only difference is this method only save changed m2m fields.
        """
        cleaned_data = self.cleaned_data
        exclude = self._meta.exclude
        fields = self._meta.fields
        opts = self.instance._meta
        # Note that for historical reasons we want to include also
        # private_fields here. (GenericRelation was previously a fake
        # m2m field).
        for f in chain(opts.many_to_many, opts.private_fields):
            if not hasattr(f, 'save_form_data'):
                continue
            if fields and f.name not in fields:
                continue
            if exclude and f.name in exclude:
                continue
            if f.name not in self.changed_m2m_fields:
                #data is not changed, ignore
                continue
            if f.name in cleaned_data:
                f.save_form_data(self.instance, cleaned_data[f.name])

    def save(self, commit=True,savemessage = True):
        """
        Save this form's self.instance object if commit=True. Otherwise, add
        a save_m2m() method to the form which can be called after the instance
        is saved manually at a later time. Return the model instance.
        """
        if self.errors:
            raise ValueError(
                "The %s could not be %s because the data didn't validate." % (
                    self.instance._meta.object_name,
                    'created' if self.instance._state.adding else 'changed',
                )
            )
        if not self.is_changed:
            #data not changed
            if savemessage and commit and self.request:
                message = self.get_success_message()
                self.add_message(message,messages.INFO)
            return self.instance

        #data is changed
        if self.instance.pk:
            #update a model instance
            if commit:
                # save the instance and the m2m data immediately.
                #assign the current user to modifier if have
                if hasattr(self.instance,"modifier") and self.request:
                    self.instance.modifier = self.request.user
                if self.changed_db_fields:
                    #add the audit fields into changed_db_fields
                    for f in self._meta.extra_update_audit_fields:
                        self.changed_db_fields.append(f)

                with transaction.atomic():
                    if  self.changed_db_fields:
                        #some db fields has been changed,save to database
                        self.instance.save(update_fields=self.changed_db_fields)

                    if self.changed_model_properties and self.save_model_properties_enabled:
                        #some model properties are changed, save it
                        self.instance.save_properties(update_fields=self.changed_model_properties)

                    if self.changed_m2m_fields:
                        #save m2m data
                        self._save_m2m()
                    #save inner formset data
                    self._save_formsets()
                    #save inner form data
                    self._save_forms()
            else:
                # If not committing, add a method to the form to allow deferred saving of m2m data.
                self.save_m2m = self._save_m2m
                # If not committing, add a method to the form to allow deferred saving inner formset data
                self.save_formsets = self._save_formsets
                # If not committing, add a method to the form to allow deferred saving inner form data
                self.save_forms = self._save_forms
        elif commit:
            #create a model instance
            if self.request:
                if hasattr(self.instance,"modifier"):
                    self.instance.modifier = self.request.user
                if hasattr(self.instance,"creator"):
                    self.instance.creator = self.request.user
            with transaction.atomic():
                super(BaseModelForm,self).save(commit)
                if self.save_model_properties_enabled:
                    self.instance.save_properties()
                self._save_formsets()
                self._save_forms()

        else:
            # If not committing, add a method to the form to allow deferred saving of m2m data.
            self.save_m2m = self._save_m2m
            # If not committing, add a method to the form to allow deferred saving inner formset data
            self.save_formsets = self._save_formsets
            # If not committing, add a method to the form to allow deferred saving inner form data
            self.save_forms = self._save_forms

        if savemessage and commit and self.request:
            message = self.get_success_message()
            self.add_message(message)

        return self.instance

    def full_check(self):
        """
        Check whether the model instance data is valid or not.
        Use the form clean logic and error message displaying to check the model instance in different scenario which is identified by property 'check'
        The form clean logic is to check the cleaned data, in order to use the same clean logic, this method to set cleaned_data to model instance and also guarantee only reading the data from cleaned_data
        """
        self.cleaned_data = self.instance
        self._errors = ErrorDict()


        #first check all the editable fields except formset fields and form fields
        try:

            if self._meta.enhanced_form_fields:
                opt_fields = self._meta.fields
                self._meta.fields = self.editable_fieldnames
                #only include the normal editable fields from db model and dynamically added fields
                self._editable_fields = self._editable_fields if hasattr(self,'_editable_fields') else OrderedDict([(n,f) for n,f in self.fields.items() if (n in self._meta.fields or n not in self.all_fields) ])
                self.fields = self._editable_fields

            #call clean_ method in form to validate the field data
            for name, field in self.fields.items():
                # value_from_datadict() gets the data from the data dictionaries.
                # Each widget type knows how to retrieve its own data, because some
                # widgets split data over several HTML fields.
                try:
                    if hasattr(self, 'clean_%s' % name):
                        getattr(self, 'clean_%s' % name)()
                except ValidationError as e:
                    self.add_error(name, e)

            #clean clean_form method to clean form data
            self._clean_form()
            #post clean

            exclude = self._get_validation_exclusions()
    
            # Foreign Keys being used to represent inline relationships
            # are excluded from basic field value validation. This is for two
            # reasons: firstly, the value may not be supplied (#12507; the
            # case of providing new values to the admin); secondly the
            # object being referred to may not yet fully exist (#12749).
            # However, these fields *must* be included in uniqueness checks,
            # so this can't be part of _get_validation_exclusions().
            for name, field in self.fields.items():
                if isinstance(field, forms.models.InlineForeignKeyField):
                    exclude.append(name)

            try:
                self.instance.full_clean(exclude=exclude, validate_unique=False)
            except ValidationError as e:
                self._update_errors(e)
    
            # Validate uniqueness if needed.
            if self._validate_unique:
                self.validate_unique()

        finally:
            if self._meta.enhanced_form_fields:
                self._meta.fields = opt_fields
                self.fields = self.all_fields

        #check formset field data
        for name in self.editable_formsetfieldnames:
            field = self[name]
            #call clean method on formset fields to check formset field data
            if not field.full_check():
                self.add_error(name, ValidationError(""))
            #call clean method on current form to check formset field data as a whole
            clean_funcname = "clean_{}".format(name)
            if hasattr(self,clean_funcname):
                try:
                    getattr(self,clean_funcname)()
                except ValidationError as e:
                    self.add_error(name, e)

        #check form field data
        for name in self.editable_formfieldnames:
            field = self[name]
            #call clean method on bound form fields to check form field data
            if not field.full_check():
                self.add_error(name, ValidationError(""))
            #call clean method on current form to check form field data as a whole
            clean_funcname = "clean_{}".format(name)
            if hasattr(self,clean_funcname):
                try:
                    getattr(self,clean_funcname)()
                except ValidationError as e:
                    self.add_error(name, e)

        return False if self._errors else True


    def full_clean(self):
        if not self.is_bound or not self._meta.enhanced_form_fields:
            super(BaseModelForm,self).full_clean()
            return

        opt_fields = self._meta.fields
        try:
            self._meta.fields = self.editable_fieldnames
            #only include the normal editable fields from db model and dynamically added fields
            self._editable_fields = self._editable_fields if hasattr(self,'_editable_fields') else OrderedDict([(n,f) for n,f in self.fields.items() if (n in self._meta.fields or n not in self.all_fields) ])
            self.fields = self._editable_fields
            super(BaseModelForm,self).full_clean()
        finally:
            self._meta.fields = opt_fields
            self.fields = self.all_fields

    def __getitem__(self, name):
        """Return a BoundField with the given name."""
        try:
            field = self.total_fields[name]
        except KeyError:
            raise KeyError(
                "Key '%s' not found in '%s'. Choices are: %s." % (
                    name,
                    self.__class__.__name__,
                    ', '.join(sorted([f for f in self.total_fields])),
                )
            )
        if name not in self._bound_fields_cache:
            self._bound_fields_cache[name] = field.create_boundfield(self,field,name)

        return self._bound_fields_cache[name]
    
            
class ModelForm(ActionMixin,RequestUrlMixin,BaseModelForm):
    pass

@receiver(widgets_inited)
def init_actions(sender,**kwargs):
    for cls in _formclasses:
        cls.post_init()
    system_ready.send(sender="forms")



