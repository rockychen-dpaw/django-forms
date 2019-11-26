import inspect
import collections

from django.utils.html import html_safe,conditional_escape,mark_safe
from django.core.exceptions import ValidationError
from django.utils import six
from django import forms
from django.db import models
from django.utils import safestring

from . import widgets
from . import fields

class BoundFieldIterator(collections.Iterable):
    def __init__(self,form,fields=None,multirows=False):
        self.form = form
        self._index = None
        self._multirows = multirows
        self._fields = fields or self.form._meta.ordered_fields
        self._length = len(self._fields)

    def __iter__(self):
        self._index = -1
        return self

    def __next__(self):
        self._index += 1
        if self._index >= self._length:
            raise StopIteration()
        elif self._multirows:
            return [self.form[f] for f in self._fields[self._index]]
        else:
            return self.form[self._fields[self._index]]

class HtmlStringBoundField(forms.boundfield.BoundField):
    def __init__(self, form, field, name):
        self.form_field_name = name
        self.form = form
        self.name = name
        self.field = field

    @property
    def is_display(self):
        return True

    @property
    def is_hidden(self):
        return False


    @property
    def initial(self):
        return self.field.html

    @property
    def auto_id(self):
        return ""

    def html(self):
        return mark_safe(self.as_widget())
    
    @property
    def hascleanvalue(self):
        return False

    def value(self):
        """
        Returns the value for this BoundField, using the initial value if
        the form is not bound or the data otherwise.
        """
        return self.field.html

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        """
        Renders the field by rendering the passed widget, adding any HTML
        attributes passed as attrs.  If no widget is specified, then the
        field's default widget will be used.
        """
        return self.field.widget.render(self.name,self.value())

class BoundField(forms.boundfield.BoundField):
    defult_display_widget = widgets.TextDisplay()
    def __init__(self, form, field, name):
        self.form_field_name = name
        if isinstance(field,fields.AliasFieldMixin) and name != field.field_name:
            super(BoundField,self).__init__(form,field,field.field_name)
            self.html_name = form.add_prefix(name)
            self.html_initial_name = form.add_initial_prefix(name)
            self.html_initial_id = form.add_initial_prefix(self.auto_id)
        else:
            super(BoundField,self).__init__(form,field,name)

    def css_classes(self, extra_classes=None):
        return None
    """ 
    Extend django's BoundField to support the following features
    1. Get extra css_classes from field's attribute 'css_classes'
    """
    def css_classes(self, extra_classes=None):
        if hasattr(self.field,"css_classes"):
            if extra_classes:
                if hasattr(extra_classes, 'split'):
                    extra_classes = extra_classes.split()
                extra_classes += getattr(self.field,"css_classes")
                return super(BoundField,self).css_classes(extra_classes)
            else:
                return super(BoundField,self).css_classes(getattr(self.field,"css_classes"))
        else:
            return super(BoundField,self).css_classes(extra_classes)

    @property
    def is_display(self):
        return isinstance(self.field.widget,widgets.DisplayMixin)

    @property
    def is_hidden(self):
        return isinstance(self.field.widget,widgets.HiddenInput) and not self.field.widget.display_widget


    @property
    def initial(self):
        data = super(BoundField,self).initial

        #print("{}: {} = {}".format("view" if self.is_display else "edit",self.name ,data))
        if not self.is_display and isinstance(data,models.Model):
            return data.pk
        else:
            return data

    @property
    def auto_id(self):
        if self.is_display:
            return ""
        else:
            html_id = super(BoundField,self).auto_id
            if "." in html_id:
                return html_id.replace(".","_")
            else:
                return html_id

    def html(self,template=None,method="as_widget"):
        if hasattr(self.field,"css_classes"):
            attrs = " class=\"{}\"".format(" ".join(self.field.css_classes))
        else:
            attrs = ""

        if template:
            return mark_safe(template.format(attrs=attrs,widget=getattr(self,method)()))
        else:
            return mark_safe(getattr(self,method)())
    
    @property
    def cleanvalue(self):
        return self.form.cleaned_data.get(self.name)

    @property
    def hascleanvalue(self):
        return self.name in self.form.cleaned_data

    def value(self):
        """
        Returns the value for this BoundField, using the initial value if
        the form is not bound or the data otherwise.
        """
        if not self.form.is_bound or isinstance(self.field.widget,widgets.DisplayWidget) or self.field.widget.attrs.get("disabled"):
            data = self.initial
        else:
            data = self.field.bound_data(
                self.data, self.form.initial.get(self.name, self.field.initial)
            )
        if self.is_display and (isinstance(data,models.Model) or isinstance(data,models.query.QuerySet) or (isinstance(data,(list,tuple)) and data and isinstance(data[0],models.Model))):
            return data
        else:
            return self.field.prepare_value(data)

    @property
    def display(self):
        if self.is_display:
            return self.html()
        elif hasattr(self.field,"display_widget"):
            return super(BoundField,self).as_widget(self.field.display_widget)
        else:
            return super(BoundField,self).as_widget(self.default_display_widget)

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        """
        Renders the field by rendering the passed widget, adding any HTML
        attributes passed as attrs.  If no widget is specified, then the
        field's default widget will be used.
        """
        if self.is_hidden:
            attrs = {'style':'display:none'}
        html = super(BoundField,self).as_widget(widget,attrs,only_initial)
        if not self.is_display and self.name in self.form.errors:
            html =  "<div style=\"display:inline\"><table class=\"error\" style=\"width:100%;\"><tr><td class=\"error\">{}<div class=\"text-error\" style=\"margin:0px\"><i class=\"icon-warning-sign\"></i> {}</div></td></tr></table></div>".format(html,"<br>".join(self.form.errors[self.name]))
            pass
        return html

class LoginUserBoundField(BoundField):
    @property
    def initial(self):
        if self.form.request:
            return self.form.request.user
        else:
            return None

    def value(self):
        """
        Returns the value for this BoundField, using the initial value if
        the form is not bound or the data otherwise.
        """
        return self.initial

class AggregateBoundField(BoundField):

    def value(self):
        return self.field.value(self.form)

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        return self.field.widget.render(self.name,self.value())

@html_safe
class CompoundBoundFieldMixin(object):
    """
    a mixin to implement compound bound field
    """
    def __init__(self, form, field, name):
        super(CompoundBoundFieldMixin,self).__init__(form,field,name)
        if self.field.field_prefix:
            self.related_fields = [self.form["{}{}".format(self.field.field_prefix,name)] for name in field.related_field_names]
        else:
            self.related_fields = [self.form[name] for name in field.related_field_names]

    def __str__(self):
        """Renders this field as an HTML widget."""
        if self.field.show_hidden_initial:
            return self.as_widget() + self.as_hidden(only_initial=True)
        return self.as_widget()

    def __iter__(self):
        """
        Yields rendered strings that comprise all widgets in this BoundField.

        This really is only useful for RadioSelect widgets, so that you can
        iterate over individual radio buttons in a template.
        """
        id_ = self.field.widget.attrs.get('id') or self.auto_id
        attrs = {'id': id_} if id_ else {}
        attrs = self.build_widget_attrs(attrs)
        for subwidget in self.field.widget.subwidgets(self.html_name, self.value(), attrs):
            yield subwidget

    def __len__(self):
        return len(list(self.__iter__()))

    def __getitem__(self, idx):
        # Prevent unnecessary reevaluation when accessing BoundField's attrs
        # from templates.
        if not isinstance(idx, six.integer_types + (slice,)):
            raise TypeError
        return list(self.__iter__())[idx]

    def get_field(self,field_name):
        if self.field.field_prefix:
            return self.form["{}{}".format(self.field.field_prefix,field_name)]
        else:
            return self.form[field_name]

    def get_fieldvalue(self,field_name):
        if self.field.field_prefix:
            return self.form["{}{}".format(self.field.field_prefix,field_name)].value()
        else:
            return self.form[field_name].value()

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        """
        Renders the field by rendering the passed widget, adding any HTML
        attributes passed as attrs.  If no widget is specified, then the
        field's default widget will be used.
        """
        #print("============{}  {}".format(self.name,self.field.field_name))
        #if self.field.field_name == "prescription__loc_locality":
        #    import ipdb;ipdb.set_trace()

        html_layout,field_names,include_primary_field = self.field.get_layout(self)
        def get_args():
            index0 = 0
            index1 = 0
            args = []
            while index1 < len(field_names):
                if isinstance(field_names[index1],(tuple,list)):
                    if field_names[index1][0] != self.field.related_field_names[index0]:
                        index0 += 1
                    else:
                        args.append(self.related_fields[index0].as_widget(only_initial=only_initial,attrs=field_names[index1][1]))
                        index0 += 1
                        index1 += 1
                elif field_names[index1] != self.field.related_field_names[index0]:
                    index0 += 1
                else:
                    args.append(self.related_fields[index0].as_widget(only_initial=only_initial))
                    index0 += 1
                    index1 += 1
            return args

        if include_primary_field:
            if isinstance(html_layout,(tuple,list)):
                html = super(CompoundBoundFieldMixin,self).as_widget(attrs=html_layout[1],only_initial=only_initial)
                html_layout = html_layout[0]
            else:
                html = super(CompoundBoundFieldMixin,self).as_widget(only_initial=only_initial)

            if field_names:
                args = get_args()
                args.append(self.auto_id)
                return safestring.SafeText(html_layout.format(html,*args))
            elif html_layout:
                return safestring.SafeText(html_layout.format(html,self.auto_id))
            else:
                return html
        elif field_names:
            args = get_args()
            return safestring.SafeText(html_layout.format(*args))
        elif html_layout:
            return safestring.SafeText(html_layout)
        else:
            return ""

    def as_text(self, attrs=None, **kwargs):
        """
        Returns a string of HTML for representing this as an <input type="text">.
        """
        raise Exception("Not supported")

    def as_textarea(self, attrs=None, **kwargs):
        "Returns a string of HTML for representing this as a <textarea>."
        raise Exception("Not supported")

    def as_hidden(self, attrs=None, **kwargs):
        """
        Returns a string of HTML for representing this as an <input type="hidden">.
        """
        html = super(CompoundBoundFieldMixin,self).as_widget(self.field.hidden_widget(), attrs, **kwargs)
        return self.field.hidden_layout.format(html,*[f.as_widget(f.field.hidden_widget(),None,**kwargs) for f in self.related_fields])

class FormBoundField(BoundField):
    def __init__(self,*args,**kwargs):
        super(FormBoundField,self).__init__(*args,**kwargs)
        self._bound_fields_cache = {}
        if self.form.is_bound and not self.field.is_display:
            raise NotImplementedError
        else:
            self.innerform = self.field.form_class(instance=self.value(),prefix=self.name,check=self.form.check)

    @property
    def initial(self):
        return self.form.initial.get(self.name, self.field.get_initial())

    def html(self,template=None,method="as_widget"):
        raise NotImplementedError

    @property
    def is_bound(self):
        return self.form.is_bound and not self.field.is_display

    @property
    def is_changed(self):
        return self.innerform.is_changed

    def set_data(self):
        obj = self.initial
        self.form.set_data(obj)

    def full_clean(self):
        if self.innerform.is_valid():
            return self.innerform.cleaned_data
        else:
           raise ValidationError("") #error placeholder, but not display in page

    def full_check(self):
        return self.innerform.full_check()

    def value(self):
        """
        Returns the value for this BoundField, using the initial value if
        the form is not bound or the data otherwise.
        """
        if self.form.is_bound and not self.field.is_display:
            raise NotImplementedError
        else:
            return self.form.initial.get(self.name, self.field.get_initial())

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        raise NotImplementedError

    def __getitem__(self, name):
        """Return a BoundField with the given name."""
        return self.innerform[name]
    
    def save(self):
        return self.innnerform.save(savemessage=False)

class FormSetBoundField(BoundField):
    _is_changed = None

    def __init__(self,*args,**kwargs):
        super(FormSetBoundField,self).__init__(*args,**kwargs)
        self.formset = self.field.formset_class(
            data=self.form.data if self.form.is_bound else None,
            instance_list=self.initial,
            prefix=self.name,
            parent_instance=self.form.instance,
            check=self.form.check,
            request=self.form.request,
            requesturl=self.form.requesturl
        )

    @property
    def initial(self):
        return self.form.initial.get(self.name, self.field.get_initial())

    def html(self,template=None,method="as_widget"):
        raise NotImplementedError

    @property
    def is_bound(self):
        return self.form.is_bound and not self.field.is_display

    def full_clean(self):
        if self.formset.is_valid():
            return [form.cleaned_data for form in self.formset]
        else:
           raise ValidationError("") #error placeholder, but not display in page

    def full_check(self):
        return self.formset.full_check()

    def set_data(self):
        objs = self.initial
        if isinstance(objs,models.manager.Manager):
            objs = objs.all()
        self.formset.set_data(objs)

    @property
    def is_changed(self):
        if self._is_changed is None:
            try:
                changed = False
                for form in self.formset:
                    if form.can_delete:
                        if form.instance.pk:
                            changed = True
                            break
                    elif form.is_changed:
                        changed = True
                        break
                self._is_changed = changed
            finally:
                pass
                for form in self.formset:
                    if form.can_delete:
                        if form.instance.pk:
                            print("Delete {}({})".format(form.instance.__class__.__name__,form.instance.pk))
        return self._is_changed


    def save(self):
        if not self.is_changed:
            return

        for form in self.formset:
            if form.can_delete:
                if form.instance.pk:
                    form.instance.delete()
            else:
                form.save(savemessage=False)

    def as_widget(self, widget=None, attrs=None, only_initial=False):
        return self.field.widget.render(self.name,self.formset,self.form.errors.get(self.name))

    def __iter__(self):
        return self.formset

class ListFormBoundField(BoundField):
    def __init__(self,*args,**kwargs):
        super(ListFormBoundField,self).__init__(*args,**kwargs)
        objs = self.initial
        if isinstance(objs,models.manager.Manager):
            objs = objs.all()
        self.listform = self.field.listform_class(data=None,instance_list=objs,prefix=self.name,parent_instance=self.form.instance,request=self.form.request,requesturl=self.form.requesturl)

    @property
    def initial(self):
        return self.form.initial.get(self.name, None)

    def html(self,template=None,method="as_widget"):
        raise NotImplementedError

    @property
    def is_bound(self):
        return False

    def set_data(self):
        objs = self.initial
        if isinstance(objs,models.manager.Manager):
            objs = objs.all()
        self.listform.set_data(objs)



    def as_widget(self, widget=None, attrs=None, only_initial=False):
        return self.field.widget.render(self.name,self.listform)

    def __iter__(self):
        return self.formset


class ListBoundFieldMixin(object):
    def __init__(self, form, field, name):
        super(ListBoundFieldMixin,self).__init__(form,field,name)
        self.sortable = name in self.form._meta.sortable_fields if self.form._meta.sortable_fields else False

    @property
    def sorting(self):
        if not self.sortable:
            return None
        elif not self.form.sorting :
            return "sortable"
        elif self.form_field_name == self.form.sorting[0]:
            return "asc" if self.form.sorting[1] else "desc"
        else:
            return "sortable"

    @property
    def sorting_html_class(self):
        """
        return sort html class if have; otherwise return ""
        """
        if not self.sortable:
            return ""
        elif not self.form.sorting :
            return getattr(self.form._meta,"sorting_html_class")
        elif self.form_field_name == self.form.sorting[0]:
            return getattr(self.form._meta,"asc_sorting_html_class" if self.form.sorting[1] else "desc_sorting_html_class")
        else:
            return getattr(self.form._meta,"sorting_html_class")

    def html_toggle(self,template):
        label = (conditional_escape(self.label) or '') if self.label else ''

        if self.form._meta.default_toggled_fields and self.name in self.form._meta.default_toggled_fields:
            activeclass = " btn-info"
        else:
            activeclass = ""

        return mark_safe(template.format(name=self.name,label=label,activeclass=activeclass))


    def html_header(self,template,style=""):
        label = (conditional_escape(self.label) or '') if self.label else ''
        if self.form._meta.columns_attrs and self.form_field_name in self.form._meta.columns_attrs:
            attrs = self.form._meta.columns_attrs[self.form_field_name][0] or {}
        else:
            attrs={}

        if style:
            if "style" in attrs:
                attrs["style"] = "{};{}".format(style,attrs["style"])
            else:
                attrs["style"] = style

        if self.is_hidden:
            if "style" in attrs:
                attrs["style"] = "dispaly:none;{}".format(attrs["style"])
            else:
                attrs["style"] = "display:none"
        elif not self.sortable:
            if hasattr(self.field,"css_classes"):
                if "class" in attrs:
                    attrs["class"] = "{} {}".format(" ".join(self.field.css_classes),attrs["class"])
                else:
                    attrs["class"] = " ".join(self.field.css_classes)
        else:
            sorting = self.sorting
            sorting_class = self.sorting_html_class
            attrs["onclick"] = "document.location='{}'".format(self.form.querystring(ordering="{}{}".format("-" if sorting == 'asc' else '',self.form_field_name)))

            if hasattr(self.field,"css_classes"):
                if "class" in attrs:
                    attrs["class"] = "{} {} {}".format(sorting_class," ".join(self.field.css_classes),attrs["class"])
                else:
                    attrs["class"] = "{} {}".format(sorting_class," ".join(self.field.css_classes))
            elif "class" in attrs:
                attrs["class"] = "{} {}".format(sorting_class,attrs["class"])
            else:
                attrs["class"] = sorting_class

        attrs = " ".join(["{}=\"{}\"".format(k,v) for k,v in attrs.items()])

        return mark_safe(template.format(label=label,attrs=attrs))

    def html(self,template,style=""):
        if self.form._meta.columns_attrs and self.form_field_name in self.form._meta.columns_attrs:
            attrs = self.form._meta.columns_attrs[self.form_field_name][1] or {}
        else:
            attrs={}

        if style:
            if "style" in attrs:
                attrs["style"] = "{};{}".format(style,attrs["style"])
            else:
                attrs["style"] = style

        if self.is_hidden:
            if "style" in attrs:
                attrs["style"] = "dispaly:none;{}".format(attrs["style"])
            else:
                attrs["style"] = "display:none"
        elif hasattr(self.field,"css_classes"):
            if "class" in attrs:
                attrs["class"] = "{} {}".format(" ".join(self.field.css_classes),attrs["class"])
            else:
                attrs["class"] = " ".join(self.field.css_classes)

        attrs = " ".join(["{}=\"{}\"".format(k,v) for k,v in attrs.items()])

        return mark_safe(template.format(attrs=attrs,widget=self.as_widget()))

class MultiValueBoundField(BoundField):
    def as_widget(self, widget=None, attrs=None, only_initial=False):
        attrs = attrs or {}
        attrs = self.build_widget_attrs(attrs, self.field.widget)
        if self.auto_id and 'id' not in self.field.widget.attrs:
            attrs.setdefault('id', self.html_initial_id if only_initial else self.auto_id)

        return self.field.render(self.form,self.name,self.value(),attrs=attrs)
 

listboundfield_classes = {}
def get_listboundfield(boundfield):
    """
    Get a base boundfield's corresponding list bound field
    """
    if boundfield not in listboundfield_classes:
        name = boundfield.__name__
        if name.endswith("BoundField"):
            name = "{}ListBoundField".format(name[0:-len("BoundField")])
        else:
            name = "{}ListBoundField".format(name)
        listboundfield_classes[boundfield] = type(name,(ListBoundFieldMixin,boundfield),{})

    return listboundfield_classes[boundfield]


compoundboundfield_classes = {}
def get_compoundboundfield(boundfield):
    """
    Get a base boundfield's corresponding compound bound field
    """
    if boundfield not in compoundboundfield_classes:
        name = boundfield.__name__
        if name.endswith("BoundField"):
            name = "{}CompoundBoundField".format(name[0:-len("BoundField")])
        else:
            name = "{}CompoundBoundField".format(name)
        compoundboundfield_classes[boundfield] = type(name,(CompoundBoundFieldMixin,boundfield),{})

    return compoundboundfield_classes[boundfield]


