import json
import inspect

from django import forms
from django.dispatch import receiver

from django_mvc.signals import actions_inited,fields_inited
from django_mvc.utils import ConditionalChoice,getallargs
from .. import widgets
from ..utils import hashvalue,JSONEncoder
from .coerces import *
from ..boundfield import (CompoundBoundField,)

class_id = 0
field_classes = {}

DIRECTION_CHOICES = (
    ("","---"),
    ("N","N"),
    ("NNE","NNE"),
    ("NE","NE"),
    ("ENE","ENE"),
    ("E","E"),
    ("ESE","ESE"),
    ("SE","SE"),
    ("SSE","SSE"),
    ("S","S"),
    ("SSW","SSW"),
    ("SW","SW"),
    ("WSW","WSW"),
    ("W","W"),
    ("WNW","WNW"),
    ("NW","NW"),
    ("NNW","NNW")
)

class ObjectField(forms.Field):
    def __init__(self,*args,**kwargs):
        super(ObjectField,self).__init__(*args,**kwargs)

    def clean(self,value):
        return value
    

class NullDirectionField(forms.ChoiceField):
    def __init__(self,**kwargs):
        super(NullDirectionField,self).__init__(choices=DIRECTION_CHOICES,**kwargs)

class FieldParametersMixin(object):
    """
    A mixin to inject some parameters into field instance.
    field_kwargs: the kwargs are the keywords supported by the field class or its base classes
    extra_fields: the kwargs are not supported by the field class and its base classes
        widget_attrs: the attrs will pass to the widget during creating widget instance.
    """
    field_kwargs = None
    extra_fields = None

    def __init__(self,*args,**kwargs):
        #delete unwanted kwargs
        #if self.__class__.__name__ == "TypedMultipleChoiceField_18":
        #    import ipdb;ipdb.set_trace()
        field_class = None
        for cls in self.__class__.__bases__:
            if issubclass(cls,forms.Field):
                field_class = cls
                break
        method_args,method_kwargs = getallargs(field_class.__init__)
        invalid_args = None
        for k in kwargs.keys():
            if k not in method_kwargs and k not in method_args:
                if invalid_args is None:
                    invalid_args = [k]
                else:
                    invalid_args.append(k)

        #print("invalid args = {} {} {} {}".format(self.__class__,method_args,method_kwargs,invalid_args))
        if invalid_args:
            for k in invalid_args:
                del kwargs[k]
        
        if self.field_kwargs:
            for k,v in self.field_kwargs.items():
                kwargs[k] = v
        super(FieldParametersMixin,self).__init__(*args,**kwargs)
        if self.extra_fields:
            for k,v in self.extra_fields.items():
                setattr(self,k,v)

    def widget_attrs(self,widget):
        attrs = super(FieldParametersMixin,self).widget_attrs(widget)
        if self.extra_fields and "widget_attrs" in self.extra_fields:
            attrs.update(self.extra_fields["widget_attrs"])

        return attrs



def init_field_params(field_class,field_params):
    field_kwargs = {}
    extra_fields = {}
    method_args,method_kwargs = getallargs(field_class.__init__)
    for k,v in (field_params or {}).items():
        if k in method_args:
            field_kwargs[k] = v
        elif k in method_kwargs:
            field_kwargs[k] = v
        else:
            extra_fields[k] = v

    return (field_kwargs,extra_fields)


def OverrideFieldFactory(model,field_name,field_class=None,**field_params):
    """
    A factory method to create a compoundfield class
    """
    global class_id

    field_params = field_params or {}
    field_class = field_class or (model._meta.get_field(field_name).formfield().__class__ if model else None)
    if not field_class:
        raise Exception("Missing field class")
    class_key = hashvalue("OverrideField<{}.{}.{}.{}.{}.{}>".format(model.__module__ if model else "global",model.__name__ if model else "default",field_name,field_class.__module__,field_class.__name__,json.dumps(field_params,cls=JSONEncoder)))
    if class_key not in field_classes:
        class_id += 1
        field_kwargs = {}
        class_name = "{}_{}".format(field_class.__name__,class_id)
        field_kwargs,extra_fields = init_field_params(field_class,field_params)
        #print("classname = {}, extra fields = {},field_kwargs = {}".format(class_name,extra_fields,field_kwargs))
        field_classes[class_key] = type(class_name,(FieldParametersMixin,field_class),{"field_name":field_name,"field_kwargs":field_kwargs,"extra_fields":extra_fields})
        #print("{}.{}={}".format(field_name,field_classes[class_key],field_classes[class_key].get_layout))
    return field_classes[class_key]

class AliasFieldMixin(object):
    field_name = None

def AliasFieldFactory(model,field_name,field_class=None,field_params=None):
    global class_id
    field_class = field_class or model._meta.get_field(field_name).formfield().__class__
    if field_params:
        class_key = hashvalue("AliasField<{}.{}{}{}{}>".format(model.__module__,model.__name__,field_name,field_class,json.dumps(field_params,cls=JSONEncoder)))
    else:
        class_key = hashvalue("AliasField<{}.{}{}{}>".format(model.__module__,model.__name__,field_name,field_class))

    if class_key not in field_classes:
        class_id += 1
        class_name = "{}_{}".format(field_class.__name__,class_id)
        if field_params:
            field_kwargs,extra_fields = init_field_params(field_class,field_params)
            field_classes[class_key] = type(class_name,(FieldParametersMixin,AliasFieldMixin,field_class),{"field_name":field_name,"field_kwargs":field_kwargs,"extra_fields":extra_fields})
        else:
            field_classes[class_key] = type(class_name,(AliasFieldMixin,field_class),{"field_name":field_name})
    return field_classes[class_key]

class HtmlStringField(forms.Field):
    def __init__(self,html,*args,**kwargs):
        kwargs["widget"] = widgets.HtmlString
        super(HtmlStringField,self).__init__(*args,**kwargs)
        self.html = html

class CompoundField(AliasFieldMixin,FieldParametersMixin):
    """
    A base class of compund field which consists of multiple form fields
    """
    field_prefix = None
    related_field_names = []
    hidden_layout = None
    editmode = None

    def  get_layout(self,f):
        if self.editmode == True:
            return self._edit_layout(f)
        elif isinstance(self.widget,widgets.DisplayWidget):
            return self._view_layout(f)
        else:
            return self._edit_layout(f)

    def _view_layout(self,f):
        raise Exception("Not implemented")

    def _edit_layout(self,f):
        raise Exception("Not implemented")

def CompoundFieldFactory(compoundfield_class,model,field_name,related_field_names=None,field_class=None,**kwargs):
    """
    A factory method to create a compoundfield class
    """
    global class_id

    kwargs = kwargs or {}
    if not related_field_names:
        related_field_names = compoundfield_class.related_field_names
    if hasattr(compoundfield_class,"init_kwargs") and callable(compoundfield_class.init_kwargs):
        kwargs = compoundfield_class.init_kwargs(model,field_name,related_field_names,kwargs)

    hidden_layout="{}" * (len(related_field_names) + 1)
    field_class = field_class or model._meta.get_field(field_name).formfield().__class__
    class_key = hashvalue("CompoundField<{}.{}.{}.{}.{}.{}.{}.{}>".format(compoundfield_class.__name__,model.__module__,model.__name__,field_name,field_class.__module__,field_class.__name__,json.dumps(related_field_names),json.dumps(kwargs,cls=JSONEncoder)))
    if class_key not in field_classes:
        class_id += 1
        class_name = "{}_{}".format(field_class.__name__,class_id)
        kwargs.update({"field_name":field_name,"related_field_names":related_field_names,"hidden_layout":hidden_layout})
        if "field_params" in kwargs:
            field_params = kwargs["field_params"]
            field_kwargs,extra_fields = init_field_params(field_class,field_params)
            kwargs["field_kwargs"] = field_kwargs
            kwargs["extra_fields"] = extra_fields
            del kwargs["field_params"]
        field_classes[class_key] = type(class_name,(compoundfield_class,field_class),kwargs)
        #print("{}.{}={}".format(field_name,field_classes[class_key],field_classes[class_key].get_layout))
    return field_classes[class_key]

def SwitchFieldFactory(model,field_name,related_field_names,field_class=None,**kwargs):
    return CompoundFieldFactory(SwitchField,model,field_name,related_field_names,field_class,**kwargs)

def OtherOptionFieldFactory(model,field_name,related_field_names,field_class=None,**kwargs):
    return CompoundFieldFactory(OtherOptionField,model,field_name,related_field_names,field_class,**kwargs)

def MultipleFieldFactory(model,field_name,related_field_names,field_class=None,**kwargs):
    return CompoundFieldFactory(MultipleField,model,field_name,related_field_names,field_class,**kwargs)

def ConditionalMultipleFieldFactory(model,field_name,related_field_names,field_class=None,**kwargs):
    return CompoundFieldFactory(ConditionalMultipleField,model,field_name,related_field_names,field_class,**kwargs)

class ChoiceFieldMixin(object):
    def __init__(self,*args,**kwargs):
        kwargs["choices"] = self.CHOICES
        for key in ("min_value","max_value","max_length","limit_choices_to","to_field_name","queryset"):
            if key in kwargs:
                del kwargs[key]
        super(ChoiceFieldMixin,self).__init__(*args,**kwargs)

def ChoiceFieldFactory(choices,choice_class=forms.TypedChoiceField,field_params=None,type_name=None):
    global class_id
    if type_name:
        class_key = hashvalue("ChoiceField<{}.{}{}{}>".format(choice_class.__module__,choice_class.__name__,type_name,json.dumps(field_params,cls=JSONEncoder)))
    else:
        class_key = hashvalue("ChoiceField<{}.{}{}{}>".format(choice_class.__module__,choice_class.__name__,json.dumps(choices),json.dumps(field_params,cls=JSONEncoder)))
    if class_key not in field_classes:
        class_id += 1
        class_name = "{}_{}".format(choice_class.__name__,class_id)
        field_kwargs,extra_fields = init_field_params(choice_class,field_params)
        field_classes[class_key] = type(class_name,(FieldParametersMixin,ChoiceFieldMixin,choice_class),{"CHOICES":choices,"field_kwargs":field_kwargs,"extra_fields":extra_fields})
    return field_classes[class_key]


NOT_NONE=1
HAS_DATA=2
ALWAYS=3
DATA_MAP=4
class SwitchField(CompoundField):
    """
    suitable for compound fields which include a boolean primary field and one or more related field or a html section
    normally, when the primary feild is false, all related field will be disabled; when primary field is true, all related field will be enabled

    policy: the policy to view the related field when primary field if false.
    reverse: if reverse is true; the behaviour will be reversed; that means: all related field will be disabled when the primary field is true
    on_layout: the view layout when the primary field is true
    off_layout: the view layout when the primary field is false
    edit_layout: the edit layout
    """
    policy = HAS_DATA
    reverse = False
    on_layout = None
    off_layout = None
    edit_layout = None
    true_value = 'True'

    @classmethod
    def init_kwargs(cls,model,field_name,related_field_names,kwargs):
        if not kwargs.get("on_layout"):
            kwargs["on_layout"] = u"{{}}{}".format("<br>{}" * len(related_field_names))

        if not kwargs.get("off_layout"):
            kwargs["off_layout"] = None

        if not kwargs.get("edit_layout"):
            kwargs["edit_layout"] = u"{{0}}<div id='id_{}_body'>{{1}}{}</div>".format(
                "{{{}}}".format(len(related_field_names) + 1),
                "".join(["<br>{{{}}}".format(i) for i in range(2,len(related_field_names) + 1)])
            )

        kwargs["true_value"] = (str(kwargs['true_value']) if kwargs['true_value'] is not None else "" ) if "true_value" in kwargs else 'True'

        return kwargs

    def _view_layout(self,f):
        """
        return a tuple(layout,enable related field list) for view
        """
        val1 = f.value()
        val1_str = str(val1) if val1 is not None else ""
        if (not self.reverse and val1_str == self.true_value) or (self.reverse and not val1_str == self.true_value):
            if self.policy == ALWAYS:
                return (self.off_layout if self.reverse else self.on_layout,f.field.related_field_names,True)
            else:
                val2 = f.related_fields[0].value()
                if self.policy == NOT_NONE and val2 is not None:
                    return (self.off_layout if self.reverse else self.on_layout,f.field.related_field_names,True)
                elif self.policy == HAS_DATA and val2:
                    return (self.off_layout if self.reverse else self.on_layout,f.field.related_field_names,True)
                
        return (self.on_layout if self.reverse else self.off_layout,None,True)

        
    def _edit_layout(self,f):
        """
        return a tuple(layout,enable related field list) for edit
        """
        val1 = f.value()
        val1_str = str(val1) if val1 is not None else ""
            
        attrs = {}
        show_fields = "$('#id_{}_body').show();{}".format(f.auto_id,";".join(["$('#{0}').prop('disabled',false)".format(field.auto_id) for field in f.related_fields]))
        hide_fields = "$('#id_{}_body').hide();{}".format(f.auto_id,";".join(["$('#{0}').prop('disabled',true)".format(field.auto_id) for field in f.related_fields]))

        condition = None

        if isinstance(f.field.widget,forms.widgets.RadioSelect):
            condition ="document.getElementById('{0}').value === '{1}'".format(f.auto_id,str(self.true_value))
            attrs["onclick"]="show_{}()".format(f.auto_id)
        elif isinstance(f.field.widget,forms.widgets.CheckboxInput):
            condition ="document.getElementById('{0}').checked".format(f.auto_id)
            attrs["onclick"]="show_{}()".format(f.auto_id)
        elif isinstance(f.field.widget,forms.widgets.Select):
            condition ="document.getElementById('{0}').value === '{1}'".format(f.auto_id,str(self.true_value))
            attrs["onchange"]="show_{}()".format(f.auto_id)
        else:
            raise Exception("Not implemented")

        js_script ="""
            <script type="text/javascript">
                function show_{0}() {{{{
                    if ({1}) {{{{
                      {2}
                    }}}} else {{{{
                        {3}
                    }}}}
                }}}}
                $(document).ready(show_{0})
            </script>
        """.format(f.auto_id,condition,hide_fields if self.reverse else show_fields,show_fields if self.reverse else hide_fields)

        return ((u"{}{}".format(self.edit_layout,js_script),attrs),self.related_field_names,True)
    
class OtherOptionField(CompoundField):
    """
    suitable for compound fields which include a choice primary field with other options and one or more related field

    other_layout: is used when other option is chosen
    layout: is used when other option is not chosen
    edit_layout: is used for editing
    """
    policy = HAS_DATA
    other_layout = None
    layout = None
    edit_layout = None

    is_other_value = None
    is_other_value_js = None
    is_other_option = None

    @classmethod
    def _initialize_other_option(cls,other_option,edit=True):
        if isinstance(other_option,(list,tuple)):
            if len(other_option) == 0:
                other_option = None
            elif len(other_option) == 1:
                other_option = other_option[0]

        is_other_value_js = None
        if other_option is None:
            if edit:
                is_other_value = None
                is_other_value_js = None
            else:
                is_other_value = None
        elif isinstance(other_option,(list,tuple)):
            if edit:
                other_value = [o.id for o in other_option] if hasattr(other_option[0],"id") else other_option
                is_other_value = (lambda other_value:lambda val: val in other_value)(other_value)
                is_other_value_js = (lambda other_value:"['{}'].indexOf(this.value) >= 0".format("','".join([str(o) for o in other_value])))(other_value)
            else:
                is_other_value = (lambda other_value:lambda val: val in other_value)(other_option)
        else:
            if edit:
                other_value = other_option.id if hasattr(other_option,"id") else other_option
                is_other_value = (lambda other_value:lambda val: val == other_value)(other_value)
                is_other_value_js = (lambda other_value:"this.value === '{}'".format(other_value))(other_value)
            else:
                is_other_value = (lambda other_value:lambda val: val == other_value)(other_option)

        return is_other_value,is_other_value_js

    @classmethod
    def _init_class(cls):
        if cls.other_option and callable(cls.other_option):
            other_option = cls.other_option()
            if callable(other_option):
                cls.other_option = staticmethod(other_option)
            else:
                cls.other_option = other_option
                is_other_value,is_other_value_js = cls._initialize_other_option(cls.other_option,edit=True)
                is_other_option = cls._initialize_other_option(cls.other_option,edit=False)[0]
                cls.is_other_value = staticmethod(is_other_value) if is_other_value else is_other_value
                cls.is_other_value_js = staticmethod(is_other_value_js) if is_other_value_js else is_other_value_js
                cls.is_other_option = staticmethod(is_other_option) if is_other_option else is_other_option


    @classmethod
    def init_kwargs(cls,model,field_name,related_field_names,kwargs):
        if not kwargs.get("other_option"):
            raise Exception("Missing 'other_option' keyword parameter")

        if not kwargs.get("other_layout"):
            kwargs["other_layout"] = u"{{}}{}".format("<br>{}" * len(related_field_names))

        if not kwargs.get("layout"):
            kwargs["layout"] = None

        if not kwargs.get("edit_layout"):
            kwargs["edit_layout"] = u"{{0}}<div id='id_{}_body'>{{1}}{}</div>".format(
                "{{{}}}".format(len(related_field_names) + 1),
                "".join(["<br>{{{}}}".format(i) for i in range(2,len(related_field_names) + 1)])
            )

        return kwargs

    def _view_layout(self,f):
        val1 = f.value()
        if callable(self.other_option):
            try:
                is_other_option = self._initialize_other_option(self.other_option(val1),edit=False)[0]
            except:
                is_other_option = None

        else:
            is_other_option = self.is_other_option

        if not is_other_option:
            return (self.layout,None,True)

        if is_other_option(val1):
            val2 = f.related_fields[0].value()
            if self.policy == ALWAYS:
                return (self.other_layout,f.field.related_field_names,True)
            elif self.policy == NOT_NONE and val2 is not None:
                return (self.other_layout,f.field.related_field_names,True)
            elif self.policy == HAS_DATA and val2:
                return (self.other_layout,f.field.related_field_names,True)
            elif self.policy == DATA_MAP and val2 in self.other_layout:
                return (self.other_layout[val2],f.field.related_field_names,True)
                
        return (self.layout,None,True)

    def _edit_layout(self,f):
        """
        return a tuple(layout,enable related field list) for edit
        """
        val1 = f.value()
        if isinstance(val1,basestring):
            val1 = int(val1) if val1 else None
        #if f.name == "field_officer":
        #    import ipdb;ipdb.set_trace()
        if callable(self.other_option):
            try:
                is_other_value,is_other_value_js = self._initialize_other_option(self.other_option(val1),edit=True)
            except:
                is_other_value = None
                is_other_value_js = None
        else:
            is_other_value = self.is_other_value
            is_other_value_js = self.is_other_value_js

        if is_other_value is None:
            #no other option
            return (None,None,True)

        attrs = {}
        show_fields = "$('#id_{}_body').show();{}".format(f.auto_id,";".join(["$('#{0}').prop('disabled',false)".format(field.auto_id) for field in f.related_fields]))
        hide_fields = "$('#id_{}_body').hide();{}".format(f.auto_id,";".join(["$('#{0}').prop('disabled',true)".format(field.auto_id) for field in f.related_fields]))

        if isinstance(f.field.widget,forms.widgets.RadioSelect):
            attrs["onclick"]="""
                if ({0}) {{
                    {1}
                }} else {{
                    {2}
                }}
            """.format(is_other_value_js,show_fields,hide_fields)
        elif isinstance(f.field.widget,forms.widgets.Select):
            attrs["onchange"]="""
                if ({0}) {{
                    {1}
                }} else {{
                    {2}
                }}
            """.format(is_other_value_js,show_fields,hide_fields)
        else:
            raise Exception("Not  implemented")

        if is_other_value(val1):
            return ((u"{}<script type='text/javascript'>{}</script>".format(self.edit_layout,hide_fields),attrs),self.related_field_names,True)
        else:
            return ((self.edit_layout,attrs),self.related_field_names,True)
        
    
class MultipleField(CompoundField):
    """
    just combine multiple fields

    view_layout: is used for view
    edit_layout: is used for editing
    """
    @classmethod
    def init_kwargs(cls,model,field_name,related_field_names,kwargs):
        if not kwargs.get("view_layout"):
            if kwargs.get("layout"):
                kwargs["view_layout"] = kwargs.get("layout")
            else:
                kwargs["view_layout"] = u"{{0}} {}".format("".join(["<br>{{{}}}".format(i) for i in range(1,len(related_field_names) + 1)]))

        if not kwargs.get("edit_layout"):
            if kwargs.get("layout"):
                kwargs["edit_layout"] = kwargs.get("layout")
            else:
                kwargs["edit_layout"] = u"{{0}} {}".format("".join(["<br>{{{}}}".format(i) for i in range(1,len(related_field_names) + 1)]))

        if "layout" in kwargs:
            del kwargs["layout"]

        return kwargs

    def _view_layout(self,f):
        return (self.view_layout,f.field.related_field_names,True)

    def _edit_layout(self,f):
        """
        return a tuple(layout,enable related field list) for edit
        """
        return (self.edit_layout,f.field.related_field_names,True)
        
class ConditionalMultipleField(CompoundField):
    """
    view/edit multiple fields with condition

    """
    view_layouts = None
    edit_layouts = None

    @classmethod
    def init_kwargs(cls,model,field_name,related_field_names,kwargs):
        if kwargs.get("view_layouts"):
            kwargs["view_layouts"] = ConditionalChoice(kwargs["view_layouts"])
        else:
            kwargs["view_layouts"] = ConditionalChoice([(lambda f:True,u"{{0}} {}".format("".join(["<br>{{{}}}".format(i) for i in range(1,len(related_field_names) + 1)])))])

        if kwargs.get("edit_layouts"):
            kwargs["edit_layouts"] = ConditionalChoice(kwargs["edit_layouts"])
        else:
            kwargs["edit_layouts"] = ConditionalChoice([(lambda f:True,u"{{0}} {}".format("".join(["<br>{{{}}}".format(i) for i in range(1,len(related_field_names) + 1)])))])

        return kwargs

    def _view_layout(self,f):
        return self.view_layouts[f]

    def _edit_layout(self,f):
        return self.edit_layouts[f]

class ModelChoiceFilterIterator(forms.models.ModelChoiceIterator):

    def __iter__(self):
        if self.field.empty_label is not None:
            yield ("", self.field.empty_label,None)
        queryset = self.queryset
        # Can't use iterator() when queryset uses prefetch_related()
        if not queryset._prefetch_related_lookups:
            queryset = queryset.iterator()
        for obj in queryset:
            yield self.choice(obj)

    def choice(self,obj):
        return (self.field.prepare_value(obj), self.field.label_from_instance(obj),obj)

class ChoiceFilterMixin(object):
    iterator = ModelChoiceFilterIterator

class ModelChoiceFilterField(ChoiceFilterMixin,forms.ModelChoiceField):
    widget = widgets.FilteredSelect


BooleanChoiceField = ChoiceFieldFactory([
    (True,"Yes"),
    (False,"No")
],field_params={"coerce":coerce_TrueFalse,'empty_value':None},type_name="BooleanChoiceField")

BooleanChoiceFilter = ChoiceFieldFactory([
    (True,"Yes"),
    (False,"No")
    ],choice_class=forms.TypedMultipleChoiceField ,field_params={"coerce":coerce_TrueFalse,'empty_value':None,'required':False},type_name="BooleanChoiceFilter")

NullBooleanChoiceFilter = ChoiceFieldFactory([
    ('',"Unknown"),
    (True,"Yes"),
    (False,"No")
    ],choice_class=forms.TypedMultipleChoiceField ,field_params={"coerce":coerce_TrueFalse,'empty_value':None,'required':False},type_name="NullBooleanChoiceFilter")


@receiver(actions_inited)
def init_actions(sender,**kwargs):
    for key,cls in field_classes.items():
        #print("{}={}".format(key,cls))
        if hasattr(cls,"__init_class"):
            #initialize the class, and remove the class initialize method
            cls.__init_class()

    fields_inited.send(sender="fields")

