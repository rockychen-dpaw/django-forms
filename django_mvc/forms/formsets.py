from django.forms import formsets
from django.core.exceptions import ObjectDoesNotExist,ValidationError,NON_FIELD_ERRORS
from django.forms.formsets import DELETION_FIELD_NAME
from django.db import transaction
from django.template import (Template,Context)
from django.utils.html import mark_safe

from . import forms
from .listform import (ToggleableFieldIterator,ListModelFormMetaclass)
from . import boundfield
from . import fields
from .utils import Media

class FormSetMedia(Media):
    """
    Provide the media required by the formset
    """
    def __init__(self,formcls):
        self.can_add = formcls.can_add
        self.can_delete = formcls.can_delete
        if not formcls.can_add and not formcls.can_delete:
            super(FormSetMedia,self).__init__(js=None,statements=None)
            return

        js = ["/static/js/jquery.formset.enhanced.js"]

        statements = []
        if formcls.can_delete:
            statements.append("""
            function delete_{0}(ev,prefix){{
                var row = $(ev.srcElement).parents('.{0}_fs')
                var index = null;
                $.each(row.find("input"),function(i,element){{
                    if ($(element).prop('name').startsWith(prefix + '-')) {{
                        index = parseInt($(element).prop('name').substring(prefix.length + 1))
                        return false
                    }}
                }})
                idElement = $("#id_" + prefix + "-" + index + "-{1}")
                if (idElement.length && idElement.val()) {{
                    row.find("#delete").click()
                    ev.stopPropagation()
                }}
            }}
            """.format(formcls.model_name_lower,formcls.model_primary_key))

        if formcls.can_add:
            row_template = formcls.row_template.render(Context({"listform":formcls}))
        else:
            row_template = ""

        statements.append("var {}_row_template = `{}`".format(formcls.model_name_lower,row_template))
    
        init_formset = None
        if formcls.can_add and formcls.can_delete:
            init_formset = """
            function init_{0}_formset(prefix) {{
                var quoted_prefix = '"' + prefix + '"'
                $("#" + prefix + "_result_list > tbody > tr").formset({{
                    prefix: prefix,
                    formCssClass: "{0}_fs",
                    addText: '<i class="icon-plus"></i> Add Another {1}',
                    deleteText: "<img onclick='delete_{0}(event," + quoted_prefix + ");' src='/static/img/delete.png' style='width:16px;height:16px;'></img>",
                    deleteCssClass: 'delete-row' + '-' + prefix,
                    formTemplate:{0}_row_template
                }})
            }};
            """.format(formcls.model_name_lower,formcls.model_verbose_name)
        elif formcls.can_add:
            init_formset = """
            function init_{0}_formset(prefix) {{
                $("#" + prefix + "_result_list > tbody > tr").formset({{
                    prefix: prefix,
                    formCssClass: "{0}_fs",
                    addText: '<i class="icon-plus"></i> Add Another {1}',
                    formTemplate:{0}_row_template
                }})
            }};
            """.format(formcls.model_name_lower,formcls.model_verbose_name)
        elif formcls.can_delete:
            init_formset = """
            function init_{0}_formset(prefix) {{
                var quoted_prefix = '"' + prefix + '"'
                $("#" + prefix + "_result_list > tbody > tr").formset({{
                    prefix: prefix,
                    formCssClass: "{0}_fs",
                    addText: '',
                    deleteText: "<img onclick='delete_{0}(event," + quoted_prefix + ");' src='/static/img/delete.png' style='width:16px;height:16px;'></img>",
                    deleteCssClass: 'delete-row' + '-' + prefix,
                    formTemplate:{0}_row_template
                }})
                $(".{0}_fs-add").hide();
            }};
            """.format(formcls.model_name_lower,formcls.model_verbose_name)

        if init_formset:
            statements.append(init_formset)

        super(FormSetMedia,self).__init__(js=js,statements=statements)

    
    def init_formset(self,form):
        return mark_safe("""
        <script type="text/javascript">
            var {1}_formset = init_{0}_formset("{1}");
        </script>
        """.format(form.model_name_lower,form.prefix))
    
class FormSet(forms.ActionMixin,forms.RequestUrlMixin,forms.RequestMixin,formsets.BaseFormSet):
    check = None
    _errors = None
    error_title = None
    errors_title = None
    can_delete = False
    cleaned_data = {}

    model_name_lower=None
    model_primary_key = "id"
    _bound_footerfields_cache = None

    def __init__(self,parent_instance=None,instance_list=None,check=None,*args,**kwargs):
        if check is not None:
            self.check = check

        if "prefix" not in kwargs:
            kwargs["prefix"] = self.__class__.default_prefix
        kwargs['initial']=instance_list
        super(FormSet,self).__init__(*args,**kwargs)
        self.instance_list = instance_list
        self.parent_instance = parent_instance

        self._bound_footerfields_cache = {}

    @property
    def form_instance(self):
        if len(self) > 0:
            self[0].requesturl = self.requesturl
            return self[0]
        elif not hasattr(self,"_form_instance"):
            self._form_instance = self.form()
            self._form_instance.requesturl = self.requesturl
        return self._form_instance

    @property
    def toggleablefields(self):
        obj = self.form_instance
        if hasattr(obj._meta,"toggleable_fields") and obj._meta.toggleable_fields:
            return ToggleableFieldIterator(obj)
        else:
            return None

    @property
    def boundfields(self):
        return boundfield.BoundFieldIterator(self.form_instance)

    @property
    def init_formset_statements(self):
        if self.form_media:
            return self.form_media.init_formset(self)
        else:
            return ""

    @property
    def haslistfooter(self):
        return True if self.form_instance.listfooter else False

    @property
    def boundfieldlength(self):
        return len(self.form_instance._meta.ordered_fields)

    @property
    def use_required_attribute(self):
        return False

    @property
    def renderer(self):
        return None

    def _should_delete_form(self,form):
        return False

    def get_form_kwargs(self, index):
        kwargs = super(FormSet,self).get_form_kwargs(index)
        if self.instance_list and index < len(self.instance_list):
            if self.is_bound:
                kwargs["instance"] = self.get_instance(index)
            else:
                kwargs["instance"] = self.instance_list[index]
        if self.parent_instance:
            kwargs["parent_instance"] = self.parent_instance
        if self.check is not None:
            kwargs["check"] = self.check
        kwargs["request"] = self.request
        kwargs["requesturl"] = self.requesturl
        return kwargs

    def get_form_field_name(self,index,field_name):
        prefix = self.add_prefix(index)
        return '{}-{}'.format(prefix, field_name) 

    def get_instance(self,index):
        if self.primary_field:
            name = self.get_form_field_name(index,self.primary_field)
            value = self.data.get(name)
            value = self.form.all_fields[self.primary_field].clean(value)
            if value:
                for instance in self.instance_list:
                    if value == getattr(instance,self.primary_field):
                        return instance
                raise ObjectDoesNotExist("{}({}) doesn't exist".format(self.form.model_verbose_name,value))
            else:
                return None
        elif index < len(self.instance_list):
            return self.instance_list[index]
        else:
            return None

    def full_check(self):
        if self._errors is None:
            self._errors = {}
            for i in range(0, self.total_form_count()):
                form = self.forms[i]
                if not form.instance.pk:
                    #new instance,ignore
                    continue
                if not form.full_check():
                    self._errors[str(form.instance)] = form.errors
            try:
                self.clean()
            except ValidationError as e:
                self._non_form_errors = self.error_class(e.error_list)
                self._errors[NON_FIELD_ERRORS] = self._non_form_errors

        return False if self._errors else True


    def full_clean(self):
        if self._errors is None:
            if not self.is_bound:
                self._errors = {}
                return
            errors = {}
            super().full_clean()
            for i in range(0, self.total_form_count()):
                form = self.forms[i]
                if self.is_bound and self.can_delete and self._should_delete_form(form):
                    #this form was removed by the user,ignore
                    continue
                if form.errors:
                    errors[str(form.instance)] = form.errors
            if self._non_form_errors:
                errors[NON_FIELD_ERRORS] = self._non_form_errors
            self._errors = errors
        


    def _should_delete_form(self,form):
        """Return whether or not the form was marked for deletion."""
        should_delete = super(FormSet,self)._should_delete_form(form)
        if not should_delete and hasattr(form,"can_delete"):
            should_delete = form.can_delete
        form.cleaned_data[DELETION_FIELD_NAME] = should_delete
        return should_delete

    def listfooter(self):
        return self.form_instance.listfooter

    def footerfield(self,name):
        if self._bound_footerfields_cache is None:
            self._bound_footerfields_cache = {}
        try:
            bound_field = self._bound_footerfields_cache[name]
        except:
            if self._bound_footerfields_cache is None:
                self._bound_footerfields_cache = {}
            try:
                field = self.form_instance.listfooter_fields[name]
            except:
                raise KeyError(
                    "Key '%s' not found in '%s'. Choices are: %s." % (
                        name,
                        self.__class__.__name__,
                        ', '.join(sorted(f for f in self.form_instance.listfooter_fields)),
                    )
                )
            if isinstance(field,fields.AggregateField):
                bound_field = boundfield.AggregateBoundField(self,field,name)
            elif isinstance(field,fields.HtmlStringField):
                bound_field = boundfield.HtmlStringBoundField(self,field,name)
            else:
                raise NotImplementedError("Not Implemented")
            self._bound_footerfields_cache[name] = bound_field

        return bound_field.as_widget()

    def add_initial_prefix(self,name):
        return ""

    def save(self):
        if not self.is_bound:  # Stop further processing.
            return
        with transaction.atomic():
            for i in range(0, self.total_form_count()):
                form = self.forms[i]
                if self.can_delete and self._should_delete_form(form):
                    if form.instance.pk:
                        form.instance.delete()
                    continue
                form.save()


class TemplateFormsetMixin(object):
    def add_prefix(self, index):
        return '%s-__prefix__' % (self.prefix)


class FormSetMemberForm(forms.ModelForm,metaclass=ListModelFormMetaclass):
    def __init__(self,parent_instance=None,*args,**kwargs):
        super(FormSetMemberForm,self).__init__(*args,**kwargs)
        if parent_instance:
            self.set_parent_instance(parent_instance)

    def set_parent_instance(self,parent_instace):
        pass

    def __getitem__(self, name):
        """Return a BoundField with the given name."""
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
            if isinstance(field,fields.CompoundField):
                self._bound_fields_cache[name] = boundfield.CompoundListBoundField(self,field,name)
            elif isinstance(field,fields.AggregateField):
                self._bound_fields_cache[name] = boundfield.AggregateBoundField(self,field,name)
            elif isinstance(field,fields.HtmlStringField):
                self._bound_fields_cache[name] = boundfield.HtmlStringBoundField(self,field,name)
            else:
                self._bound_fields_cache[name] = boundfield.ListBoundField(self,field,name)
        return self._bound_fields_cache[name]

    @property
    def boundfields(self):
        return boundfield.BoundFieldIterator(self)

template_formset_classes = {}
def TemplateFormsetFactory(form,formset):
    key = "{}.{}".format(formset.__module__,formset.__name__)
    cls = template_formset_classes.get(key)
    if not cls:
        class_name = "{}.{}_template".format(formset.__module__,formset.__name__)
        cls = type(class_name,(TemplateFormsetMixin,formset),{"can_add":False,"can_delete":False})
        form_obj = form()
        cls.model_name = form_obj.model_name
        cls.model_name_lower = form_obj.model_name_lower
        cls.model_verbose_name = form_obj.model_verbose_name
        cls.model_verbose_name_plural = form_obj.model_verbose_name_plural
        template_formset_classes[key] = cls
    return cls

def formset_factory(form, formset=FormSet, extra=1, can_order=False,
                    can_delete=False, max_num=None, validate_max=False,can_add=True,
                    min_num=None, validate_min=False,primary_field=None,all_actions=None,all_buttons=None,row_template=None,template=None):

    cls = formsets.formset_factory(form,formset=formset,extra=extra,can_order=can_order,can_delete=can_delete,max_num=max_num,validate_max=validate_max,min_num=min_num,validate_min=validate_min)
    cls.primary_field = primary_field or form._meta.model._meta.pk.name
    cls.default_prefix = form._meta.model.__name__.lower()
    form_obj = form()
    cls.default_prefix = form_obj.model_name_lower
    cls.model_name_lower = form_obj.model_name_lower
    cls.model_name = form_obj.model_name
    cls.model_verbose_name = form_obj.model_verbose_name
    cls.model_verbose_name_plural = form_obj.model_verbose_name_plural

    if not template:
        template = """
        {{% load pbs_utils %}}
        <table id="{0}_result_list" class="table table-striped table-condensed table-hober table-fixed-header">
            <thead>
                <tr>
                    {{% for field in listform.boundfields %}}
                    {{% call_method field "html_header" "<th {{attrs}}><div class='text'>{{label}}</div></th>"%}}
                    {{% endfor %}}
                </tr>
            </thead>
            <tbody>
                {{% for form in listform %}}
                <tr> 
                    {{% for field in form.boundfields %}}
                        {{% call_method field "html" "<td {{attrs}}>{{widget}}</td>"%}}
                    {{% endfor %}}
                </tr>
                {{% endfor %}}
    
            </tbody>
            {{% if listform.haslistfooter %}}
            <tfoot>
                {{% for row in listform.listfooter %}}
                <tr> 
                    {{% for column in row %}}
                    <th {{% if column.1 == 0 %}} style="display:none" {{% elif column.1 > 1 %}}colspan={{{{column.1}}}} {{% endif %}}>
                        {{% if column.0 %}}
                        {{% call_method listform "footerfield" column.0 %}}
                        {{% else %}}
                        &nbsp;
                        {{% endif %}}
                    </th>
                    {{% endfor %}}
                </tr>
                {{% endfor %}}
    
            </tfoot>
            {{% endif %}}
        </table>
        """.format(cls.model_name_lower)
    cls.template = Template(template)

    if not row_template:
        row_template = """
        {% load pbs_utils %}
        {% for form in listform.template_forms %}<tr> 
            {% for field in form.boundfields %}
                {% call_method_escape field "html" "<td {attrs}>{widget}</td>" %}
            {% endfor %}
        </tr>{% endfor %};
        """
    cls.row_template = Template(row_template)

    cls.media = form.media
    if all_actions:
        cls.all_actions = all_actions
    if all_buttons:
        cls.all_buttons = all_buttons

    cls.can_add = can_add

    if cls.can_add:
        cls.template_forms = formsets.formset_factory(form,formset=TemplateFormsetFactory(form,formset),extra=1,min_num=1,max_num=1)(prefix=cls.default_prefix)
        for field in cls.template_forms[0].fields.values():
            field.required=False
    
    if not cls.can_add and not cls.can_delete:
        cls.form_media = None
    else:
        cls.form_media = FormSetMedia(cls)
        if cls.media:
            media = Media()
            media += cls.media
            media += cls.form_media
            cls.media = media
        else:
            cls.media = cls.form_media

    return cls

