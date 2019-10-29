from datetime import datetime,date,timedelta
import json

from django import forms
from django.utils.html import mark_safe
from django.utils import timezone

from .widgets import DisplayWidget
from ..utils import Media

to_localtime = lambda d:(timezone.localtime(d) if timezone.is_aware(d) else timezone.make_aware(d)) if isinstance(d,datetime) else d
class DatetimeDisplay(DisplayWidget):
    def __init__(self,date_format="%d/%m/%Y %H:%M:%S"):
        super(DatetimeDisplay,self).__init__()
        self.date_format = date_format or "%d/%m/%Y %H:%M:%S"

    def render(self,name,value,attrs=None,renderer=None):
        if value:
            try:
                return to_localtime(value).strftime(self.date_format)
            except:
                return value
        else:
            return ""

class DatetimeInput(forms.TextInput):
    def __init__(self,format=('Y-m-d H:i',"%Y-%m-%d %H:%M"),dateformat=('Y-m-d',"%Y-%m-%d"),timeformat=('H:i','%H:%M'),width="120px",datepicker=True,timepicker=True,maxDate=None,minDate=None,maxTime=None,minTime=None,step=30,*args,**kwargs):
        if "attrs" not in kwargs:
            kwargs["attrs"] = {}
        if "style" not in kwargs["attrs"]:
            kwargs["attrs"]["style"] =  "width:{}".format(width)
        super(DatetimeInput,self).__init__(*args,**kwargs)
        attrs = {}
        if format:
            attrs["format"] = format[0] or "Y-m-d H:i"
            self.format = format[1]
        else:
            attrs["format"] = "Y-m-d H:i"
            self.format = "%Y-%m-%d %H:%M"

        attrs["datepicker"] =  True if datepicker is None else datepicker
        attrs["timepicker"] = True if timepicker is None else timepicker
        now = timezone.now()
        if attrs["timepicker"]:
            attrs["step"] = step or 30
            for key,value in (("minTime",minTime),("maxTime",maxTime)):
                if value is not None:
                    if isinstance(value,bool):
                        if value == True:
                            attrs[key] = 0
                    elif isinstance(value,int):
                        if value == 0:
                            attrs[key] = 0
                    elif isinstance(value,str):
                        attrs[key] = value

        if attrs["datepicker"]:
            dateformat = dateformat or ("Y-m-d","%Y-%m-%d")
            for key,value in (("maxDate",maxDate),("minDate",minDate)):
                if value is not None:
                    if isinstance(value,bool):
                        if value == True:
                            attrs[key] = now.strftime(dateformat[1])
                    elif isinstance(value,int):
                        if value == 0:
                            attrs[key] = now.strftime(dateformat[1])
                        else:
                            attrs[key] = (now + timedelta(days=value)).strftime(dateformat[1])


        self.datetime_picker = """
        <script type="text/javascript">
            $("#{{}}").datetimepicker({{{}}}); 
        </script>
        """.format(json.dumps(attrs))

    @property
    def media(self):
        js = [
            'js/jquery.datetimepicker.full.min.js',
        ]
        css = {
            "all":['css/jquery.datetimepicker.css']
        }
        return Media(js=js,css=css)

    def render(self,name,value,attrs=None,renderer=None):
        value = (value if isinstance(value,str) else to_localtime(value).strftime(self.format)) if value else ""
        html = super(DatetimeInput,self).render(name,value,attrs)
        return mark_safe("{}{}".format(html,self.datetime_picker.format(attrs["id"])))

class DateInput(DatetimeInput):
    def __init__(self,format=('Y-m-d','%Y-%m-%d'),*args,**kwargs):
        super(DateInput,self).__init__(format=format,timepicker=False,datepicker=True,width="80px",*args,**kwargs)

class TimeInput(DatetimeInput):
    def __init__(self,format=('H:i',"%H:%M"),step=5,*args,**kwargs):
        super(TimeInput,self).__init__(format=format,step=step,timepicker=True,datepicker=False,width="40px",*args,**kwargs)
