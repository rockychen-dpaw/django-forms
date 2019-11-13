import traceback
import json
import locale

from django import forms
from django.core.cache import caches
from django.urls import reverse
from django.db import models
from django.utils.html import mark_safe
from django.utils.encoding import force_text
from django.utils.http import urlencode
from django.template import (Template,Context)
from django.dispatch import receiver
from django.template.defaultfilters import filesizeformat

from ..utils import hashvalue,JSONEncoder,Media
from django_mvc.signals import listformfields_inited, widgets_inited
from django_mvc.utils import get_class


to_str = lambda o: "" if o is None else str(o)

class NullValueMixin(object):
    """
    A widget mixin to return a specified null value if the data is null
    """
    def __init__(self,null_value = "",is_null = None,extra_value=False,*args,**kwargs):
        super(NullValueMixin,self).__init__(*args,**kwargs)
        self.null_value = null_value or ""

        if is_null:
            self.is_null = is_null
        else:
            self.is_null = lambda val : False if val else True

        self.null_value = mark_safe(self.null_value)
        self._render = self.render
        if extra_value:
            self.render = self._render3
        else:
            self.render = self._render2



    def _render2(self,name,value,attrs=None,renderer=None):
        if self.is_null(value):
            return self.null_value
        else:
            return self._render(name,value,attrs=attrs,renderer=renderer)
    
    def _render3(self,name,value,attrs=None,renderer=None,**extra_values):
        if self.is_null(value):
            return self.null_value
        else:
            return self._render(name,value,attrs=attrs,renderer=renderer,**extra_values)
    
class DisplayMixin(object):
    """
    A mixin to check whether a widget is a display widget or not.
    """
    def build_attrs(self, base_attrs, extra_attrs=None):
        """Build an attribute dictionary."""
        if not extra_attrs:
            return base_attrs
        elif not base_attrs:
            return extra_attrs
        else:
            for k,v in base_attrs.item():
                if k in extra_attrs:
                    continue
                extra_attrs[k] = v
            return extra_attrs

class DisplayWidget(NullValueMixin,DisplayMixin,forms.Widget):
    """
    A super class for display widget
    """
    def __deepcopy__(self, memo):
        return self

    def render(self,name,value,attrs=None,renderer=None):
        return str(value) if value else ""

class HtmlTag(DisplayWidget):
    """
    Render a html tag with html tag, tag attributes and value
    value can be a HtmlTag too.
    """
    template = "<{0} {1}>{2}</{0}>"
    def __init__(self,tag,attrs = None,value=None):
        self._tag = tag
        self._value = value 
        self._attrs = attrs

        if self._value:
            if isinstance(self._value,HtmlTag):
                value = self._value.render()
            else:
                value = self._value
        else:
            value = ""

        if self._attrs:
            attrs = " ".join(["{}=\"{}\"".format(key,value) for key,value in self._attrs.items()])
        else:
            attrs = ""

        self._template = "<{0} {1} {{0}}>{2}</{0}>".format(self._tag,attrs,value)
        self._html = mark_safe("<{0} {1}>{2}</{0}>".format(self._tag,attrs,value))

    def render(self,attrs = None):
        if attrs:
            return mark_safe(self._template.format(attrs))
        else:
            return self._html

    @property
    def html(self):
        return mark_safe(self.render())

class HtmlString(DisplayWidget):
    def render(self,name,value,attrs=None,renderer=None):
        return to_str(value)

class TextDisplay(DisplayWidget):
    def render(self,name,value,attrs=None,renderer=None):
        return to_str(value)

class ObjectDisplay(DisplayWidget):
    """
    Render a object.
    """
    def __init__(self,template=None,func=None):
        """
        template: render template; if none, return the string representation of the value
        func: get the represent value from object; if none, use the object directly
        """
        self.template = template
        self.func = func

    def render(self,name,value,attrs=None,renderer=None):
        value = self.func(value) if self.func else value
        if self.template:
            self.template.format(value)
        else:
            return to_str(value)


class TextareaDisplay(DisplayWidget):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if self.attrs:
            self.attrs = " ".join(["{}='{}'".format(k,v) for k,v in self.attrs.items()])
            self.template =  "<pre {}>{{}}</pre>".format(self.attrs)
        else:
            self.attrs = ""
            self.template =  "<pre>{}</pre>"

    def render(self,name,value,attrs=None,renderer=None):
        return self.template.format(to_str(value))

class IntegerDisplay(DisplayWidget):
    def render(self,name,value,attrs=None,renderer=None):
        if value is None:
            return ""
        else:
            return value

class FloatDisplay(DisplayWidget):
    def __init__(self,precision=2):
        self.format = '%.{}f'.format(precision)

    def render(self,name,value,attrs=None,renderer=None):
        if value is None:
            return ""
        else:
            return locale.format(self.format, value, True)

class FilesizeDisplay(DisplayWidget):
    def render(self,name,value,attrs=None,renderer=None):
        if value is None:
            return ""
        return filesizeformat(value)

class FinancialYearDisplay(DisplayWidget):
    def render(self,name,value,attrs=None,renderer=None):
        if value is None:
            return ""
        else:
            value = int(value)
            return "{}/{}".format(value,value+1)

class HyperlinkWidget(DisplayWidget):
    template = None
    def __init__(self,widget=TextDisplay,template=None):
        super(HyperlinkWidget,self).__init__(is_null=lambda value: value is None or value == "",extra_value=True)
        if widget:
            self.widget = widget if isinstance(widget,forms.Widget) else widget()
        else:
            self.widget = None
        if template:
            self.template = template
        else:
            self.template = "<a href='{url}' onclick='event.stopPropagation();'>{widget}</a>"

    def render(self,name,value,attrs=None,renderer=None,url=""):
        if self.widget:
            if callable(self.template):
                return self.template(value).format(url=url,widget=self.widget.render(name,value,attrs,renderer))
            else:
                return self.template.format(url=url,widget=self.widget.render(name,value,attrs,renderer))
        else:
            if callable(self.template):
                return self.template(value).format(url=url)
            else:
                return self.template.format(url=url)


widget_classes = {}
widget_class_id = 0

class TemplateDisplay(DisplayWidget):
    PATTERN = 2
    TEMPLATE = 3

    def __init__(self,widget,template,template_format=2,marked_safe=True,**kwargs):
        self.marked_safe = marked_safe
        if template_format == self.PATTERN:
            self.template = template
            self.render = self._render_pattern
        else:
            self.template = Template(template)
            self.render = self._render_template
        self.widget = widget
        super(TemplateDisplay,self).__init__(**kwargs)

    def _render_pattern(self,name,value,attrs=None,renderer=None):
        result = self.widget.render(name,value,attrs,renderer) if self.widget else value
        if  self.is_null(value):
            return result or ""

        if result is None:
            return ""
        if self.marked_safe:
            return mark_safe(self.template.format(result))
        else:
            return self.template.format(result)

    def _render_template(self,name,value,attrs=None,renderer=None):
        result = self.widget.render(name,value,attrs,renderer) if self.widget else value
        if  not value:
            return result or ""

        if result is None:
            return ""
        if self.marked_safe:
            return mark_safe(self.template.render(Context({"object":result})))
        else:
            return self.template.render(Context({"object":result}))

class TemplateWidgetMixin(object):
    template = ""

    def render(self,name,value,attrs=None,renderer=None):
        widget_html = super(TemplateWidgetMixin,self).render(name,value,attrs)
        return mark_safe(self.template.format(widget_html))


def TemplateWidgetFactory(widget_class,template):
    global widget_class_id
    key = "TemplateWidget<{}>".format(hashvalue("{}{}{}".format(widget_class.__name__,TemplateWidgetMixin.__name__,template)))
    cls = widget_classes.get(key)
    if not cls:
        widget_class_id += 1
        class_name = "{}_template_{}".format(widget_class.__name__,widget_class_id)
        cls = type(class_name,(TemplateWidgetMixin,widget_class),{"template":template})
        widget_classes[key] = cls
    return cls

class SwitchWidgetMixin(object):
    """
    A widget mixin to hide/show a external html element or provided html string based on a boolean type or similar boolean type value
    html: a html string which is hide/show based on the value. used if html_id is None
    html_id: a id of html element which is hide/show based on the value
    template: a template to render widget html and the wrapped html
    """
    html = ""
    template = ""
    true_value = True
    reverse = False
    html_id = None

    def render(self,name,value,attrs=None,renderer=None):
        value_str = str(value) if value is not None else ""
        if not self.html_id:
            html_id = "{}_switched".format( attrs.get("id"))
            wrapped_html = "<span id='{}' {} >{}</span>".format(html_id,"style='display:none'" if (not self.reverse and value_str != self.true_value) or (self.reverse and value_str == self.true_value) else "" ,self.html)
        else:
            html_id = self.html_id
            if (not self.reverse and value_str == self.true_value) or (self.reverse and value_str != self.true_value):
                wrapped_html = ""
            else:
                wrapped_html = """
                <script type="text/javascript">
                $(document).ready(function() {{
                    $('#{}').hide()
                }})
                </script>
                """.format(html_id)
        
        show_html = "$('#{0}').show();".format(html_id)
        hide_html = "$('#{0}').hide();".format(html_id)

        attrs = attrs or {}
        if isinstance(self,forms.RadioSelect):
            attrs["onclick"]="""
                if (this.value === '{0}') {{
                    {1}
                }} else {{
                    {2}
                }}
            """.format(self.true_value,hide_html if self.reverse else show_html,show_html if self.reverse else hide_html)
        elif isinstance(self,forms.CheckboxInput):
            attrs["onclick"]="""
                if (this.checked) {{
                    {0}
                }} else {{
                    {1}
                }}
            """.format(hide_html if self.reverse else show_html,show_html if self.reverse else hide_html)
        elif isinstance(self,forms.Select):
            attrs["onchange"]="""
                if (this.value === '{0}') {{
                    {1}
                }} else {{
                    {2}
                }}
            """.format(self.true_value,hide_html if self.reverse else show_html,show_html if self.reverse else hide_html)
        else:
            raise Exception("Not implemented")

        widget_html = super(SwitchWidgetMixin,self).render(name,value,attrs)
        return mark_safe(self.template.format(widget_html,wrapped_html))

def SwitchWidgetFactory(widget_class,html=None,true_value=True,template="{0}<br>{1}",html_id=None,reverse=False):
    """
    A factory to generate a SwitchWidget class
    """
    global widget_class_id
    if html_id:
        template="""{0}
        {1}
        """
    key = "SwitchWidget<{}>".format(hashvalue("{}{}{}{}{}{}".format(widget_class.__name__,true_value,template,html,html_id,reverse)))
    cls = widget_classes.get(key)
    true_value = str(true_value) if true_value is not None else ""
    if not cls:
        widget_class_id += 1
        class_name = "{}_{}".format(widget_class.__name__,widget_class_id)
        cls = type(class_name,(SwitchWidgetMixin,widget_class),{"template":template,"true_value":true_value,"html":html,"reverse":reverse,"html_id":html_id})
        widget_classes[key] = cls
    return cls

class ChoiceDisplay(DisplayWidget):
    """
    A widget to render predefined html for enumeration value.
    the html can be html string or html template or html pattern
    """
    choices = None
    marked_safe = False
    coerce = None
            
    def _render(self,name,value,attrs=None,renderer=None):
        value = self.coerce(value)
        try:
            result = self.__class__.choices[value]
        except KeyError as ex:
            result = self.__class__.choices.get("__default__",value)
        if result is None:
            return ""
        if self.marked_safe:
            return mark_safe(result)
        else:
            return result

    def _render_pattern(self,name,value,attrs=None,renderer=None):
        value = self.coerce(value)
        try:
            result = self.__class__.choices[value]
        except KeyError as ex:
            result = self.__class__.choices.get("__default__",value)

        if result is None:
            return ""
        if self.marked_safe:
            return mark_safe(result.format(value))
        else:
            return result.format(value)

    def _render_template(self,name,value,attrs=None,renderer=None):
        value = self.coerce(value)
        try:
            result = self.__class__.choices[value]
        except KeyError as ex:
            result = self.__class__.choices.get("__default__",value)

        if result is None:
            return ""
        if self.marked_safe:
            return mark_safe(result.render(Context({"object":value})))
        else:
            return result.render(Context({"object":value}))

def ChoiceWidgetFactory(name,choices,marked_safe=False,data_format=1,coerce=None):
    global widget_class_id
    widget_class = ChoiceDisplay
    if isinstance(choices,list) or isinstance(choices,tuple):
        choices = dict(choices)
    elif isinstance(choices,dict):
        choices = choices
    else:
        raise Exception("Choices must be a dictionary or can be converted to a  dictionary.")

    key = "ChoiceWidget<{}>".format(hashvalue("{}{}".format(widget_class.__name__,name)))
    if coerce is None:
        coerce = lambda v:v

    coerce = staticmethod(coerce)

    cls = widget_classes.get(key)
    if not cls:
        widget_class_id += 1
        class_name = "{}_{}".format(widget_class.__name__,name)
        if data_format == ChoiceWidgetFactory.STRING:
            cls = type(class_name,(widget_class,),{"choices":choices,"marked_safe":marked_safe,"render":ChoiceDisplay._render,"coerce":coerce})
        elif data_format == ChoiceWidgetFactory.PATTERN:
            cls = type(class_name,(widget_class,),{"choices":choices,"marked_safe":marked_safe,"render":ChoiceDisplay._render_pattern,"coerce":coerce})
        else:
            #convert the choices value to Template
            if hasattr(choices,"choices"):
                index = 0
                while index < len(choices.choices):
                    if not isinstance(choices.choices[index][1],Template):
                        if isinstance(choices.choices[index],tuple):
                            choices.choices[index] = list(choices.choices[index])

                        choices.choices[index][1] = Template(choices.choices[index][1])
                        choices.choices[index] = tuple(choices.choices[index])
                    index += 1
            cls = type(class_name,(widget_class,),{"choices":choices,"marked_safe":marked_safe,"render":ChoiceDisplay._render_template,"coerce":coerce})
        widget_classes[key] = cls
    return cls

ChoiceWidgetFactory.STRING = 1
ChoiceWidgetFactory.PATTERN = 2
ChoiceWidgetFactory.TEMPLATE = 3

ImgBooleanDisplay = ChoiceWidgetFactory("ImgBooleanDisplay",{
    True:"<img src=\"/static/img/icon-yes.gif\">",
    False:"<img src=\"/static/img/icon-no.gif\"/>",
    None:""
},True)

CheckboxBooleanDisplay = ChoiceWidgetFactory("CheckboxBooleanDisplay",{
    True:"<input type='checkbox' disabled checked/>",
    False:"<input type='checkbox' disabled/>",
    None:"<input type='checkbox' disabled/>",
},True)

TextBooleanDisplay = ChoiceWidgetFactory("TextBooleanDisplay",{
    True:"Yes",
    False:"No",
    None:""
})

class NullBooleanSelect(forms.widgets.Select):
    """
    Select widget for nullable boolean
    """
    def __init__(self, attrs=None,true_label = "Yes",false_label = "No",none_label = "Unknown"):
        if none_label is None:
            choices = (
                ('True', true_label),
                ('False',false_label),
            )
        else:
            choices = (
                ('-',none_label),
                ('True', true_label),
                ('False',false_label),
            )
        super(NullBooleanSelect,self).__init__(attrs, choices)

    def format_value(self, value):
        return "" if value is None else str(value)

    def value_from_datadict(self, data, files, name):
        value = data.get(name)
        return None if (value == "-" or value == "" or value is None) else (True if value == 'True' else False) 

html_id_seq = 0
class SelectableSelect(forms.Select):
    """
    not completed
    """
    def __init__(self,**kwargs):
        if kwargs.get("attrs"):
            if kwargs["attrs"].get("class"):
                kwargs["attrs"]["class"] = "{} selectpicker dropup".format(kwargs["attrs"]["class"])
            else:
                kwargs["attrs"]["class"] = "selectpicker dropup"
        else:
            kwargs["attrs"] = {"class":"selectpicker dropup"}
        super(SelectableSelect,self).__init__(**kwargs)


    def render(self,name,value,attrs=None,renderer=None):
        global html_id_seq
        html_id = attrs.get("id",None) if attrs else None
        if not html_id:
            html_id_seq += 1
            html_id = "auto_id_{}".format(html_id_seq)
            if attrs is None:
                attrs = {"id":html_id}
            else:
                attrs["id"] = html_id

        html = super(SelectableSelect,self).render(name,value,attrs)


        return mark_safe(u"""
        {}
        <script type="text/javascript">
            $("#{}").selectpicker({{
              style: 'btn-default',
              size: 6,
              liveSearch: true,
              dropupAuto: false,
            }});
        </script>
        """.format(html,html_id))

def ChoiceFieldRendererFactory(outer_html = None,inner_html = None,layout = None):
    """
    A factory to generate a choice field renderer class.
    layout: none, horizontal,vertical
    outer_html: used if layout is None
    inner_html:used in layout is None
    """
    global widget_class_id

    if layout == "vertical":
        return forms.widgets.ChoiceFieldRenderer

    if layout == "horizontal":
        outer_html = '<ul{id_attr} style="padding:0px;margin:0px">{content}</ul>'
        ivenner_html = '<li style="list-style-type:none;padding:0px 15px 0px 0px;display:inline;">{choice_value}{sub_widgets}</li>'

    renderer_class = forms.widgets.CheckboxFieldRenderer

    key = "ChoiceFieldRenderer<{}>".format(hashvalue("ChoiceFieldRenderer<{}.{}{}{}>".format(renderer_class.__module__,renderer_class.__name__,outer_html,inner_html)))
    cls = widget_classes.get(key)
    if not cls:
        widget_class_id += 1
        class_name = "{}_{}".format(renderer_class.__name__,widget_class_id)
        cls = type(class_name,(renderer_class,),{"outer_html":outer_html,"inner_html":inner_html})
        widget_classes[key] = cls
    return cls


def DisplayWidgetFactory(widget_class):
    """
    Use editable widget as display widget.
    """
    global widget_class_id

    key = "DisplayWidget<{}>".format(hashvalue("DisplayWidget<{}.{}>".format(widget_class.__module__,widget_class.__name__)))
    cls = widget_classes.get(key)
    if not cls:
        widget_class_id += 1
        class_name = "{}_{}".format(widget_class.__name__,widget_class_id)
        cls = type(class_name,(DisplayMixin,widget_class),{})
        widget_classes[key] = cls
    return cls


class DropdownMenuSelectMultiple(forms.widgets.SelectMultiple):
    """
    A button style multiple select widget
    """
    def __init__(self,include_all_option=False,button_text=None,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.include_all_option = include_all_option
        self.button_text = button_text
        self.html = """
        {{1}}
        <script type="text/javascript">
            $(document).ready(function(){{{{
                $("#{{0}}").multiselect({{{{
                    buttonClass: "btn btn-small",
                    checkboxName: $("#{{0}}").attr("id"),
                    includeSelectAllOption: {0},
                    {1}
                }}}});
            }}}})
        </script>
        """.format("true" if self.include_all_option else "false","""buttonText: function() {{{{return "{0}";}}}},""".format(self.button_text) if self.button_text else "")
    def render(self, name, value, attrs=None, renderer=None):
        if not attrs:
            attrs={"style":"display:none"}
        elif attrs.get("style"):
            attrs["style"]="{};display:none".format(attrs["style"])
        else:
            attrs["style"]="display:none"

        attrs["id"] = name
        html = super(DropdownMenuSelectMultiple,self).render("",value,attrs,renderer)
        html_id = attrs.get("id")
        if html_id:
            html = self.html.format(html_id,html)
        return html


class HiddenInput(forms.Widget):
    """
    A hidden widget
    """
    def __init__(self,display_widget=None,*args,**kwargs):
        super(HiddenInput,self).__init__(*args,**kwargs)
        self.display_widget = display_widget

    def render(self,name,value,attrs=None,renderer=None):
        if attrs and "id" in attrs:
            htmlid = "id='{}'".format(attrs["id"])
            del attrs["id"]
        else:
            htmlid = ""
        if self.display_widget:
            return "<input type='hidden' name='{}' value='{}' {} >{}".format(name,"" if value is None else value,htmlid,self.display_widget.render(name,value,attrs,renderer))
        else:
            return "<input type='hidden' name='{}' value='{}' {} >".format(name,"" if value is None else value,htmlid)
        return to_str(value)

class AjaxWidgetMixin(object):
    """
    A widget mixin to implement ajax enabled html element.
    """
    def render(self,name,value,attrs=None,renderer=None,url=""):
        if not attrs:
            attrs = {}
        for k,v in self.ajax_attrs.items():
            attrs[k] = v.format(url=url)

        return super().render(name,value,attrs=attrs,renderer=renderer)

def AjaxWidgetFactory(widget_class,data_func=None,method="post",succeed=None,failed=None,js=None):
    """
    Create ajax widget class
    widget: can be a widget class
    """
    global widget_class_id

    if js and isinstance(js,str):
        js = [js]

    key = "AjaxWidget<{}>".format(hashvalue("AjaxWidget<{}.{}.{}{}{}{}{}>".format(widget_class.__module__,widget_class.__name__,json.dumps(data_func,cls=JSONEncoder),method,succeed,failed,js)))
    cls = widget_classes.get(key)
    
    if not cls:
        widget_class_id += 1
        class_name = "{}_{}".format(widget_class.__name__,widget_class_id)
        if not succeed:
            succeed = """function (res) {
            }
            """
        
        ajax_attrs = {}
        if issubclass(widget_class,forms.CheckboxInput):
            if not failed :
                failed  = """function (srcElement,msg) {
                    alert(msg);
                    srcElement.checked = !srcElement.checked;
                }
                """

            ajax_attrs["onclick"]="{class_name}_ajax(this,'{{url}}')".format(class_name=class_name)
            if not data_func:
                data_func = """function(){
                        if (this.checked) {
                            return {"value":this.value}
                        } else {
                            return {}
                        }
                    }
                """
        elif issubclass(widget_class,forms.Select):
            if not failed :
                failed  = """function (srcElement,msg) {
                    alert(msg);
                }
                """

            ajax_attrs["onchange"]="{class_name}_ajax(this,'{{url}}')".format(class_name=class_name)
            if not data_func:
                data_func = """function(){
                        return {"value":this.value}
                    }
                """
        else:
            raise NotImplementedError()

        ajax_func = """
            var {class_name}_data = {data_func}
            var {class_name}_failed = {failed}
            var {class_name}_succeed = {succeed}
            function {class_name}_ajax(srcElement,url) {{
                previous_cursor = document.body.style.cursor;
                try{{
                    document.body.style.cursor = "wait";
                    var data = {class_name}_data.call(srcElement)
                    $.ajax({{
                        url:url,
                        data:data,
                        dataType:"json",
                        error: function(xhr,status,error) {{
                            try{{
                                {class_name}_failed(srcElement,xhr.responseText || error)
                            }} finally {{
                                document.body.style.cursor = previous_cursor
                            }}
                        }},
                        success:function(resp,stat,xhr) {{
                            try{{
                                {class_name}_succeed(srcElement,resp)
                            }} finally {{
                                document.body.style.cursor = previous_cursor
                            }}
                        }},
                        method:"{method}",
                        xhrFields:{{
                            withCredentials:true
                        }}
        
                    }})
                }}catch(ex){{
                    document.body.style.cursor = previous_cursor
                    if (ex) {{
                        alert(ex)
                    }}
                }}
            }}
        """.format(class_name=class_name,data_func=data_func,failed=failed,succeed=succeed,method=method)
        media = Media(statements=[ajax_func],js=js)
        ajax_class = None
        attrs = {"media":media,"data_func":data_func,"method":method,"ajax_attrs":ajax_attrs}
        ajax_class = AjaxWidgetMixin
        cls = type(class_name,(ajax_class,widget_class),attrs)

        widget_classes[key] = cls
    return cls

class ListDisplay(DisplayWidget):
    """
    A widget to display a list value
    """
    widget=None
    template=None
    def render(self,name,value,attrs=None,renderer=None):
        if value:
            return mark_safe(self.template.render(Context({"widgets":[self.widget.render(name,val,attrs,renderer) for val in value]})))
        else:
            return ""


def ListDisplayFactory(widget,template=None):
    """
    A factory to generate a ListDisplay widget class
    widget: can be widget class or widget instance
    """
    global widget_class_id

    if isinstance(widget,forms.Widget):
        key = "ListDisplay<{}>".format(hashvalue("ListDisplay<{}{}>".format(id(widget),template if self.template else "")))
        widget_class = widget.__class__
        widget = widget
    else:
        key = "ListDisplay<{}>".format(hashvalue("ListDisplay<{}.{}{}>".format(widget.__module__,widget.__name__,template if template else "")))
        widget_class = widget
        widget = widget_class()
    if not template:
        template = """
        <ul style="list-style-type:square">
            {% for widget in widgets %}
             <li>{{widget}}</li>
            {% endfor %}
        </ul>
        """
    cls = widget_classes.get(key)
    if not cls:
        widget_class_id += 1
        class_name = "{}List_{}".format(widget_class.__name__,widget_class_id)
        cls = type(class_name,(ListDisplay,),{"template":Template(template),"widget":widget})
        widget_classes[key] = cls
    return cls

class ChoiceFilterMixin(object):
    """
    A mixin to implement a Choice widget with a filter function.
    """
    def __init__(self,option_filter,*args,**kwargs):
        #option filter is a function with three arguments: value,label, selected_value
        self.option_filter = option_filter
        super().__init__(*args,**kwargs)

    @staticmethod
    def _choice_has_empty_value(choice):
        """Return True if the choice's value is empty string or None."""
        value = choice[0]
        return value is None or value == ''

    def optgroups(self, name, value, attrs=None):
        """Return a list of optgroups for this widget."""
        groups = []
        selected_values = []
        for index, (option_value, option_label,option) in enumerate(self.choices):
            if not self.option_filter(option,value):
                continue
            if option_value is None:
                option_value = ''

            subgroup = []
            if isinstance(option_label, (list, tuple)):
                group_name = option_value
                subindex = 0
                choices = option_label
            else:
                group_name = None
                subindex = None
                choices = [(option_value, option_label)]
            groups.append((group_name, subgroup, index))

            for subvalue, sublabel in choices:
                selected = (
                    str(subvalue) in value and
                    (not selected_values or self.allow_multiple_selected)
                )
                if selected:
                    selected_values.append(str(subvalue))
                subgroup.append(self.create_option(
                    name, subvalue, sublabel, selected, index,
                    subindex=subindex, attrs=attrs,
                ))
                if subindex is not None:
                    subindex += 1

        return groups

class FilteredSelect(ChoiceFilterMixin,forms.Select):
    pass


class FormSetWidget(forms.Widget):

    def __init__(self,field):
        self.field = field
        self.widget = self.field.widget

    def __deepcopy__(self, memo):
        return self

    def render(self,name,formset,errors=None,attrs=None,renderer=None):
        return "{}{}".format(str(formset.management_form),formset.template.render(Context({"listform":formset,"errors":errors or []})))


class FormSetDisplayWidget(DisplayMixin,forms.Widget):

    def __init__(self,field):
        self.field = field
        self.widget = self.field.widget

    def __deepcopy__(self, memo):
        return self

    def render(self,name,formset,errors=None,attrs=None,renderer=None):
        return formset.template.render(Context({"formset":formset}))


class ListFormWidget(DisplayMixin,forms.Widget):
    def __init__(self,field):
        self.field = field
        self.widget = self.field.widget

    def __deepcopy__(self, memo):
        return self

    def render(self,name,listform,errors=None,attrs=None,renderer=None):
        return listform.template.render(Context({"form":listform}))


@receiver(listformfields_inited)
def init_widgets(sender,**kwargs):
    for key,cls in widget_classes.items():
        #print("{}={}".format(key,cls))
        if hasattr(cls,"__init_class"):
            #initialize the class, and remove the class initialize method
            cls.__init_class()
    widgets_inited.send(sender="widgets")


