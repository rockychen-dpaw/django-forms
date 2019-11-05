import re
import traceback
from urllib import parse

from django.core.exceptions import ImproperlyConfigured,NON_FIELD_ERRORS
from django.urls import path 
from django.contrib import messages
from django.http import (Http404,HttpResponse,HttpResponseForbidden,JsonResponse,HttpResponseRedirect)
import django.views.generic.edit as django_edit_view
import django.views.generic.list as django_list_view
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
from urllib.parse import quote

from django_mvc.forms.utils import ChainDict,Media
from django_mvc.forms.formsets import ListUpdateForm
from django_mvc.forms.forms import RequestUrlMixin
from django_mvc.forms.listform import ListForm
from django_mvc.inspectmodel import (ObjectDependencyTree,ModelDependencyTree)
import django_mvc.actions


class ReturnHttpResponse(Exception):
    def __init__(self,response):
        super(ReturnHttpResponse,self).__init__(str(response))
        self.response = response

class UserMessageMixin(object):
    def add_user_message(self,message,level=messages.SUCCESS):
        messages.add_message(self.request,level,message)

    def clean_user_messages(self):
        return [m for m in messages.get_messages(self.request)]

class UserMixin(object):
    @property
    def user(self):
        return self.request.user if self.request else None

class ErrorMixin(object):
    errorform_keys = ("form",)
    error_title = "Please correct the error below."
    errors_title = "Please correct {{error_count}} errors below."

    def _get_errors(self,non_field_errors,errors):
        count = 0
        if not errors:
            return count
        for key,error in errors.items():
            if key and key != NON_FIELD_ERRORS:
                if isinstance(error,dict):
                    count += self._get_errors(non_field_errors,error)
                else:
                    count += 1
            else:
                for e in errors[key]:
                    non_field_errors.append(e)
                count += 1
        return count


    def post_update_context_data(self,context):
        super(ErrorMixin,self).post_update_context_data(context)
        error_count = 0
        non_field_errors = []
        for key in self.errorform_keys:
            form = context.get(key)
            if form is None :
                continue
            if isinstance(form,ListUpdateForm):
                error_count += self._get_errors(non_field_errors,form.errors)
            elif isinstance(form,ListForm):
                error_count += self._get_errors(non_field_errors,form.errors)
            else:
                error_count += self._get_errors(non_field_errors,form.errors)
        if error_count == 1:
            context["errortitle"] =  self.error_title
        elif error_count > 1:
            context["errortitle"] =  self.errors_title.format(error_count)
        
        context["non_field_errors"] = non_field_errors


class NextUrlMixin(object):
    def get_success_url(self):
        next_url = self.nexturl
        if next_url:
            return next_url
        
        next_url = self._get_success_url()
        if next_url:
            return next_url

        return super(NextUrlMixin,self).get_success_url()


    def get_success_url_with_nexturl(self):
        nexturl = self.nexturl
        if nexturl:
            successurl = self._get_success_url()
            if "nexturl" in successurl:
                return successurl
            elif "?" in successurl:
                return "{}&nexturl={}".format(successurl,nexturl)
            else:
                return "{}?nexturl={}".format(successurl,nexturl)
        else:
            return self._get_success_url()


    @property
    def nexturl(self):
        if self.request.method == 'GET':
            return self.request.GET.get('nexturl')
        else:
            return self.request.POST.get('nexturl')


    def update_context_data(self,context):
        super(NextUrlMixin,self).update_context_data(context)
        if self.nexturl:
            context["nexturl"] = self.nexturl

    def _get_success_url(self):
        return None

class SuccessUrlMixin(object):
    def get_success_url(self):
        next_url = self._get_success_url()
        if next_url:
            return next_url

        return super(SuccessUrlMixin,self).get_success_url()

    def _get_success_url(self):
        return None

class FormMixin(object):
    def get_form(self, form_class=None):
        if not hasattr(self,"form"):
            self.form = super(FormMixin,self).get_form(form_class)
            if self.request.method == "GET" and self.form.is_bound:
                self.form.is_valid()
        return self.form

class SendDataThroughUrlMixin(object):
    data_in_querystring = False
    data_in_url = False

    def get_form_kwargs(self):
        """Return the keyword arguments for instantiating the form."""
        if self.data_in_querystring or self.data_in_url:
            kwargs = super(SendDataThroughUrlMixin,self).get_form_kwargs()
    
            if self.request.method in ('POST', 'PUT'):
                kwargs.update({
                    'data': ChainDict([self.request.POST,self.kwargs]) if self.data_in_url else self.request.POST,
                    'files': self.request.FILES,
                })
            elif self.request.method in ('GET'):
                form_cls = self.get_form_class()
                if self.data_in_querystring and self.data_in_url:
                    data = ChainDict([self.request.GET,self.kwargs])
                elif self.data_in_querystring:
                    data = self.request.GET
                else:
                    data = self.kwargs

                editable_fields = [f for f in form_cls._meta.editable_fields if f in data]
                if editable_fields:
                    kwargs.update({
                        'data': data,
                        'editable_fields':editable_fields
                    })
            return kwargs
        else:
            return super(SendDataThroughUrlMixin,self).get_form_kwargs()

class ModelMixin(object):
    @property
    def model_verbose_name(self):
        return self.model._meta.verbose_name;

    @property
    def model_verbose_name_plural(self):
        return self.model._meta.verbose_name_plural;

    def update_context_data(self,context):
        pass

    def post_update_context_data(self,context):
        pass



class RequestActionMixin(django_mvc.actions.GetActionMixin):
    action = None
    selected_action = None
    default_get_action = None
    default_post_action = None
    is_action_valid = True
    jsonencoder = DjangoJSONEncoder

    @classmethod
    def is_default_get_action(cls,action):
        try:
            return cls._is_default_get_action(action)
        except:
            if not cls.default_get_action :
                cls._is_default_get_action = lambda action:False if action else True
            elif isinstance(cls.default_get_action,(list,tuple)):
                if len(cls.default_get_action) == 0:
                    cls._is_default_get_action = lambda action:False if action else True
                elif len(cls.default_get_action) == 1:
                    cls.default_get_action = cls.default_get_action[0]
                    cls._is_default_get_action = lambda action:False if action  and action != cls.default_get_action else True
                else:
                    cls._is_default_get_action = lambda action:False if action  and action not in cls.default_get_action else True
            else:
                cls._is_default_get_action = lambda action:False if action  and action != cls.default_get_action else True

            return cls._is_default_get_action(action)

    @classmethod
    def is_default_post_action(cls,action):
        try:
            return cls._is_default_post_action(action)
        except:
            if not cls.default_post_action :
                cls._is_default_post_action = lambda action:False if action else True
            elif isinstance(cls.default_post_action,(list,tuple)):
                if len(cls.default_post_action) == 0:
                    cls._is_default_post_action = lambda action:False if action else True
                elif len(cls.default_post_action) == 1:
                    cls.default_post_action = cls.default_post_action[0]
                    cls._is_default_post_action = lambda action:False if action  and action != cls.default_post_action else True
                else:
                    cls._is_default_post_action = lambda action:False if action  and action not in cls.default_post_action else True
            else:
                cls._is_default_post_action = lambda action:False if action  and action != cls.default_post_action else True

            return cls._is_default_post_action(action)

    def has_permission(self,request,action_name):
        action = self.get_action(action_name)

        return action.has_permission(request.user)  if action else True

    def get_template_names(self):
        if self.action == "deleteconfirm" and self.is_action_valid:
            return [self.deleteconfirm_template if hasattr(self,"deleteconfirm_template") else "{}/{}_deleteconfirm.html".format(self.model._meta.app_label.lower(),self.model.__name__.lower())]
        elif self.action == "archiveconfirm" and self.is_action_valid:
            return [self.archiveconfirm_template if hasattr(self,"archiveconfirm_template") else "{}/{}_archiveconfirm.html".format(self.model._meta.app_label.lower(),self.model.__name__.lower())]
        else:
            return super(RequestActionMixin,self).get_template_names()

    def dispatch(self,request, *args, **kwargs):
        handler = None
        self.is_default_action = False
        try:
            if "action" in kwargs:
                self.action = kwargs.pop("action")
            elif request.method == "GET":
                if "action__" in request.GET:
                    self.action = request.GET["action__"]
            else:
                if "action__" in request.POST:
                    self.action = request.POST["action__"]

            if request.method == "GET":
                self.is_default_action = self.is_default_get_action(self.action)
            else:
                self.is_default_action = self.is_default_post_action(self.action)

            self.selected_action = self.action
            #execute the customized action for non default action or ajax request
            if not self.is_default_action or request.is_ajax():
                if not self.is_default_action and not self.has_permission(request,self.action):
                    return HttpResponseForbidden('Not authorised.')
                if self.is_default_action:
                    if request.is_ajax():
                        if request.method == "GET":
                            handlers = ["get_ajax"]
                        else:
                            handlers = ["post_ajax".format(self.action)]
                    else:
                        handlers = []
                else:
                    if request.is_ajax():
                        if request.method == "GET":
                            handlers = ["{}_get_ajax".format(self.action),"{}_ajax".format(self.action),"{}_get".format(self.action)]
                        else:
                            handlers = ["{}_post_ajax".format(self.action),"{}_ajax".format(self.action),"{}_post".format(self.action)]
                    elif request.method == "GET":
                        handlers = ["{}_get".format(self.action)]
                    else:
                        handlers = ["{}_post".format(self.action)]

                for handler in handlers:
                    if hasattr(self,handler):
                        if hasattr(self,"pre_action"):
                            self.pre_action(*args,**kwargs)
                        res = getattr(self,handler)()
                        if request.is_ajax() and (not res or not isinstance(res,HttpResponse)):
                            return JsonResponse(res or {"status":"ok"},encoder=self.jsonencoder)
                        else:
                            try:
                                return res or HttpResponseRedirect(self.get_success_url())
                            except Exception as ex:
                                traceback.print_exc()
                                self.is_action_valid = False
                                messages.add_message(self.request,messages.ERROR,str(ex))
                                return HttpResponseRedirect(self.get_success_url())
                #raise 404 exception if customized action handler is not found for non default action
                #continue to execute the default action for ajax request with default action
                if not self.is_default_action:
                    raise Http404("Action '{}' is not supported.".format(self.action))
            return super(RequestActionMixin,self).dispatch(request,*args,**kwargs)
        except ReturnHttpResponse as ex:
            return ex.response
        except Http404:
            raise
        except Exception as ex:
            traceback.print_exc()
            return HttpResponse(status=500,reason=str(ex),content=str(ex))

    def get_basic_action_context(self):
        return {}

    def get_action_context(self):
        context = self.get_basic_action_context()

        #common action context
        self.update_action_context(context)
        if hasattr(self,"update_{}_context".format(self.action)):
            #specific action related context
            getattr(self,"update_{}_context".format(self.action))(context)
        return context

    def update_action_context(self,context):
        pass

class RequestUrl(object):
    ordering_re = re.compile('[?&]order_by=([-+]?)([a-zA-Z0-9_\-]+)')
    action_re = re.compile('[?&]action=([a-zA-Z0-9_\-]+)')
    paging_re = re.compile('[?&]page=([0-9]+)')

    qs_without_sorting = None
    qs_without_paging = None
    current_page = None
    _sorting = None
    current_action = None

    def __init__(self,request):
        self.request = request

    @property
    def path(self):
        """
        A string representing the full path to the requested page, not including the scheme or domain.
        Example: "/music/bands/the_beatles/"
        """
        return self.request.path

    @property
    def fullpath(self):
        """
        the path, plus an appended query string, if applicable.
        Example: "/music/bands/the_beatles/?print=true"
        """
        return self.request.get_full_path()

    @property
    def quotedfullpath(self):
        """
        the quoted full path
        Example: "/music/bands/the_beatles/?print=true"
        """
        return quote(self.request.get_full_path())

    def _get_request_parameter(self,param_re,qs=None,repeat=False,remove=True):
        """
        Find the parameter from request query string.
        remove: remove the parameter from the querystring if repeat is true;otherwise querystring will not be changed.
        Return a tuple
            if repeat is False, return (querystring,(matching_string,subgroups)) 
            if repeat is True, return (querystring,[(matching_string,subgroups),...]) 
        """
        qs = qs or self.request.META["QUERY_STRING"]
        if qs:
            qs = "?{}".format(qs)
        else:
            return ("",None)
        if repeat:
            pos = 0
            m =  param_re.search(qs,pos)
            if not m:
                return (qs,None)
            matches = []
            while(m):
                matches.append((m.group(0),m.groups()))
                if remove:
                    if m.start() == 0:
                        if m.end() == len(qs):
                            qs = ""
                            break
                        else:
                            qs = "?{}".format(qs[m.end() + 1:])
                            pos = 0
                    elif m.end() == len(qs):
                        qs = qs[:m.start()]
                        break
                    else:
                        qs = "{}{}".format(qs[:m.start()],qs[m.end():])
                        pos = m.start()
                else:
                    pos = m.end()

                m =  param_re.search(qs,pos)
            return (qs,matches)
        else:
            m = param_re.search(qs)
            if m:
                if remove:
                    if m.start() == 0:
                        if m.end() == len(qs):
                            qs = ""
                        else:
                            qs = "?{}".format(qs[m.end() + 1:])
                    elif m.end() == len(qs):
                        qs = qs[:m.start()]
                    else:
                        qs = "{}{}".format(qs[:m.start()],qs[m.end():])
                return (qs,(m.group(0),m.groups()))
            else:
                return (qs,None)

    def _parse_sorting(self):
        """
        get the sorting status from request querystring and set the order related data to properties
            qs_without_sorting: querystring without ordering related parameters
            _sorting: a tuple(sorting column, asc/desc). only support single parameter sorting but can map to multiple column sorting in view
        """
        if self.qs_without_sorting is None:
            self.qs_without_sorting,groups = self._get_request_parameter(self.ordering_re,remove=True)
            if groups:
                self._sorting = (groups[1][1],False if groups[1][0] == '-' else True )
            else:
                self._sorting = None

    @property
    def sorting(self):
        """
        sorting status
        a tuple(sorting column, asc/desc). only support single parameter sorting but can map to multiple column sorting in view
        """
        self._parse_sorting()
        return self._sorting

    @property
    def sorting_string(self):
        """
        sorting string used in queryset to sort the table data
        return None, if no sorting in request querystring
        """
        self._parse_sorting()
        if self._sorting:
            return "{}{}".format("" if self._sorting[1] else "-" ,self._sorting[0])
        else:
            return None

    def _parse_paging(self):
        """
        get the paging status from request querystring and set the paging related data to properties
            qs_withoug_paging: querystring without paging related parameters
            _current_page: current request page, 0 based if have; otherwise None
        """
        if self.qs_without_paging is None:
            self.qs_without_paging,groups = self._get_request_parameter(self.paging_re,remove=True)
            if groups:
                self.current_page = int(groups[1][0])
            else:
                self.current_page = None

    def querystring(self,ordering=None,page=None):
        """
        Return a modified query string
            if ordering is false or empty string, return a query string without sorting.
            if ordering is a string, return a query string with new sorting string
            if page is false or emptry string, return a query string without paging
            if page is integer or integer string,return a query string with new paging.


        """
        if ordering is not None:
            self._parse_sorting()
            if not ordering:
                return self.qs_without_sorting
            elif self.qs_without_sorting:
                return "{}&order_by={}".format(self.qs_without_sorting,ordering)
            else:
                return "?order_by={}".format(ordering)
        elif page is not None:
            self._parse_paging()
            if page is False:
                return self.qs_without_paging
            elif self.qs_without_paging:
                return "{}&page={}".format(self.qs_without_paging,page)
            else:
                return "?page={}".format(page)
        else:
            return self.request.META["QUERY_STRING"]

    @property
    def querystring_without_ordering(self):
        """
        A query string without sorting
        """
        self._parse_sorting()
        return self.qs_without_sorting

    @property
    def querystring_without_paging(self):
        """
        A query string without paging
        """
        self._parse_paging()
        return self.qs_without_paging

    def get_querystring(self,paramname,paramvalue=None):
        """
        return if paramvalue is None, return the new querystring without the request parameter spefified by paramname
               if paramvalue is not None, return the new querystring with the new value of the request parameter specified by paramname
        """
        #import ipdb;ipdb.set_trace()
        if paramname == "order_by":
            if paramvalue:
                return self.querystring(ordering=paramvalue)
            else:
                return self.querystring_without_ordering
        elif paramname == "page":
            if paramvalue:
                return self.querystring(page=paramvalue)
            else:
                return self.querystring_without_paging

        parameter_re = re.compile('[?&]{}=([^&]+)'.format(paramname))
        qs,groups = self._get_request_parameter(parameter_re,remove=True)
        if paramvalue:
            if qs:
                return "{}&{}={}".format(qs,paramname,paramvalue)
            else:
                return "?{}={}".format(paramname,paramvalue)
        else:
            return qs

class UrlpatternsMixin(object):
    urlpattern = None
    urlname = None

    @classmethod
    def urlpatterns(cls):
        if not hasattr(cls,"_urlpatterns"):
            setattr(cls,"_urlpatterns",cls._get_urlpatterns())
        return cls._urlpatterns

    @classmethod
    def _get_urlpatterns(cls):
        model_name = cls.model.__name__.lower()
        urlpatterns = None
        if issubclass(cls,django_edit_view.CreateView):
            urlpatterns=[path((cls.urlpattern or '{}/add/').format(model_name), cls.as_view(),name=(cls.urlname or '{}_create').format(model_name))]
        elif issubclass(cls,django_edit_view.UpdateView):
            urlpatterns=[path((cls.urlpattern or '{}/<int:pk>/').format(model_name), cls.as_view(),name=(cls.urlname or '{}_update').format(model_name))]
        elif issubclass(cls,django_edit_view.UpdateView):
            urlpatterns=[path((cls.urlpattern or '{}/<int:pk>/').format(model_name), cls.as_view(),name=(cls.urlname or '{}_update').format(model_name))]
        elif issubclass(cls,django_edit_view.DeleteView):
            urlpatterns=[path((cls.urlpattern or '{}/<int:pk>/delete/').format(model_name), cls.as_view(),name=(cls.urlname or '{}_delete').format(model_name))]
        elif issubclass(cls,django_list_view.ListView):
            urlpatterns=[path((cls.urlpattern or '{}/').format(model_name), cls.as_view(),name=(cls.urlname or '{}_list').format(model_name))]
        else:
            urlpatterns = []

        extra_urlpatterns = cls._get_extra_urlpatterns()
        if extra_urlpatterns:
            urlpatterns.extend(extra_urlpatterns)

        return urlpatterns


    @classmethod
    def _get_extra_urlpatterns(cls):
        return None

class HtmlMediaMixin(object):
    medias = {}

    def get_mediaforms(self):
        return (self.get_form_class(),)

    def add_htmlmedia_context(self,context):
        mediaforms = self.get_mediaforms()
        try:
            context["htmlmedia"] = self.medias[mediaforms]
        except:
            media = Media()
            for mediaform in mediaforms:
                media += mediaform.media
            self.medias[mediaforms] = media
            context["htmlmedia"] = media

    def update_context_data(self,context):
        super(HtmlMediaMixin,self).update_context_data(context)
        self.add_htmlmedia_context(context)

    def update_action_context(self,context):
        super(HtmlMediaMixin,self).update_action_context(context)
        self.add_htmlmedia_context(context)

class ParentObjectMixin(object):
    pmodel = None
    pform_class = None
    ppk_url_kwarg = "ppk"
    context_pform_name = None
    context_pobject_name = None

    @property
    def pobject(self):
        if hasattr(self,"_pobject"):
            return self._pobject
        ppk = self.kwargs.get(self.ppk_url_kwarg)
        if ppk is None:
            raise AttributeError("parent primary key ({}) is missing".format(self.ppk_url_kwarg))

        try:
            self._pobject = self.pmodel.objects.get(id=ppk)
            return self._pobject
        except self.model.DoesNotExist:
            raise Http404("The {0} (id={1}) does not exist".format(self.pmodel._meta.verbose_name,ppk))

    def get_form_kwargs(self):
        kwargs = super(ParentObjectMixin,self).get_form_kwargs()
        kwargs["parent_instance"] = self.pobject
        return kwargs

    def get_pform(self):
        pform_class = self.get_pform_class()
        if pform_class:
            if self.request.method == 'GET':
                return pform_class(instance=self.pobject,request=self.request)
            else:
                return pform_class(instance=self.pobject,data=self.request.POST,request=self.request)
        else:
            return None

    @property
    def pform(self):
        if not hasattr(self,"_pform"):
            self._pform = self.get_pform()
        
        return self._pform

    def update_context_data(self,context):
        super(ParentObjectMixin,self).update_context_data(context)
        context["pobject"] = self.pobject
        if self.pform:
            context["pform"] = self.pform
            if self.context_pform_name:
                context[self.context_pform_name] = self.pform

        if self.context_pobject_name:
            context[self.context_pobject_name] = self.pobject

    def update_action_context(self,context):
        super().update_action_context(context)
        context['pobject'] = self.pobject
        if self.context_pobject_name:
            context[self.context_pobject_name] = self.pobject

    def get_pform_class(self):
        return self.pform_class

class OneToOneModelMixin(ParentObjectMixin):
    """
    used for one to one table relationship
    a special way to get sub table's object through parent table's object
    """
    """
    parent model
    """
    one_to_one_field_name = None

    def get_object(self,queryset=None):
        queryset = queryset or self.get_queryset()
        queryset = queryset.filter(**{self.one_to_one_field_name:self.pobject})

        try:
            obj = queryset.get()
        except self.model.DoesNotExist:
            #raise Http404("The {0} ({1}={2}) does not exist".format(queryset.model._meta.verbose_name,self.one_to_one_field_name,self.pobject.pk))
            return None

        return obj
            
        
class CreateView(ErrorMixin,HtmlMediaMixin,NextUrlMixin,UrlpatternsMixin,FormMixin,ModelMixin,UserMessageMixin,UserMixin,django_edit_view.CreateView):
    title = None
    default_post_action ="save"
    def get_form_kwargs(self):
        kwargs = super(CreateView,self).get_form_kwargs()
        kwargs['request'] = self.request
        if issubclass(self.get_form_class(),RequestUrlMixin):
            kwargs['requesturl'] = RequestUrl(self.request)

        return kwargs

    def get_context_data(self,**kwargs):
        context = super(CreateView,self).get_context_data(**kwargs)
        context["title"] = self.title or "Add {}".format(self.model._meta.verbose_name)
        self.update_context_data(context)
        self.post_update_context_data(context)
        return context
    """
    def get(self,*args,**kwargs):
        import ipdb;ipdb.set_trace()
        return super(CreateView,self).get(*args,**kwargs)
    """

    """
    def post(self,*args,**kwargs):
        import ipdb;ipdb.set_trace()
        return super(CreateView,self).post(*args,**kwargs)
    """


class DetailView(HtmlMediaMixin,UrlpatternsMixin,FormMixin,ModelMixin,RequestActionMixin,UserMessageMixin,UserMixin,NextUrlMixin,django_edit_view.UpdateView):
    title = None
    def get_form_kwargs(self):
        kwargs = super(DetailView,self).get_form_kwargs()
        kwargs['request'] = self.request
        if issubclass(self.get_form_class(),RequestUrlMixin):
            kwargs['requesturl'] = RequestUrl(self.request)
        return kwargs

    def get_context_data(self,**kwargs):
        context = super(DetailView,self).get_context_data(**kwargs)
        context["title"] = self.title or self.model._meta.verbose_name
        self.update_context_data(context)
        self.post_update_context_data(context)
        return context

    def pre_action(self,*args,**kwargs):
        self.object = self.get_object()

    def get_basic_action_context(self):
        context = {
            "object":self.object,
            "form":self.get_form(),
            "title":self.title or self.model._meta.verbose_name,
        }
        if self.context_object_name:
            context[self.context_object_name] = self.object
        return context

    def post(self,request,*args,**kwargs):
        return HttpResponseForbidden()

    def put(self,request,*args,**kwargs):
        return HttpResponseForbidden()

class UpdateView(ErrorMixin,HtmlMediaMixin,UrlpatternsMixin,NextUrlMixin,FormMixin,ModelMixin,RequestActionMixin,UserMessageMixin,UserMixin,django_edit_view.UpdateView):
    title = None
    default_post_action ="save"

    def get_form_kwargs(self):
        kwargs = super(UpdateView,self).get_form_kwargs()
        kwargs['request'] = self.request
        if issubclass(self.get_form_class(),RequestUrlMixin):
            kwargs['requesturl'] = RequestUrl(self.request)
        return kwargs

    def get_context_data(self,**kwargs):
        context = super(UpdateView,self).get_context_data(**kwargs)
        context["title"] = self.title or "Update {}".format(self.model._meta.verbose_name)
        self.update_context_data(context)
        self.post_update_context_data(context)
        return context

    def get_basic_action_context(self):
        context = {
            "object":self.object,
            "form":self.get_form(),
            "title":self.title or self.model._meta.verbose_name,
        }
        if self.context_object_name:
            context[self.context_object_name] = self.object
        return context

    def get_basic_action_context(self):
        return {}

    def pre_action(self,*args,**kwargs):
        self.object = self.get_object()

    """
    def get(self,*args,**kwargs):
        import ipdb;ipdb.set_trace()
        return super(UpdateView,self).get(*args,**kwargs)
    """

    """
    def post(self,*args,**kwargs):
        import ipdb;ipdb.set_trace()
        return super(UpdateView,self).post(*args,**kwargs)
    """

class OneToOneUpdateView(OneToOneModelMixin,UpdateView):
    pass

class OneToOneDetailView(OneToOneModelMixin,DetailView):
    pass

class OneToManyModelMixin(ParentObjectMixin):
    """
    used for one to many table relationship
    a special way to get sub table's object list through parent table's object
    """
    """
    parent model
    """
    one_to_many_field_name = None

    def get_queryset(self):
        self.queryset = self.queryset if hasattr(self,"queryset") and self.queryset else self.model.objects
        self.queryset = self.queryset.filter(**{self.one_to_many_field_name:self.pobject})

        return super(OneToManyModelMixin,self).get_queryset()

class OneToManyUpdateView(OneToManyModelMixin,UpdateView):
    pass

class OneToManyDetailView(OneToManyModelMixin,DetailView):
    pass

class OneToManyCreateView(OneToManyModelMixin,CreateView):
    def get_form(self, form_class=None):
        form = super(OneToManyCreateView,self).get_form(form_class)
        setattr(form.instance,self.one_to_many_field_name,self.pobject)
        return form

class ManyToManyModelMixin(ParentObjectMixin):
    """
    used for many to many table relationship
    a special way to get sub table's object list through parent table's object
    """
    """
    parent model
    """
    many_to_many_field_name = None

    def get_queryset(self):
        self.queryset = getattr(self.pobject,self.many_to_many_field_name).all()
        return super(ManyToManyModelMixin,self).get_queryset()

    def get_object(self,queryset=None):
        queryset = queryset or self.get_queryset()
        queryset = queryset.filter(pk=self.kwargs["pk"])

        try:
            obj = queryset.get()
        except self.model.DoesNotExist:
            raise Http404("The {0} ({1}={2}) does not exist".format(queryset.model._meta.verbose_name,one_to_one_field_name,ppk))

        return obj
            
    def select_post(self):
        selected_ids = self.get_selected_ids()

        #remove previous selected but not selected rows.
        for o in getattr(self.pobject,self.many_to_many_field_name).all().exclude(pk__in=selected_ids):
            getattr(self.pobject,self.many_to_many_field_name).remove(o)
        

        #add new selected rows
        for o in self.model.objects.filter(pk__in=selected_ids).exclude(**{self.related_field_name:self.pobject}):
            getattr(self.pobject,self.many_to_many_field_name).add(o)

        return HttpResponseRedirect(self.get_success_url())

class ListBaseView(UrlpatternsMixin,ModelMixin,RequestActionMixin,UserMessageMixin,UserMixin,django_list_view.ListView):
    default_action = "search"
    title = None
    order_by_re = re.compile('[?&]order_by=([-+]?)([a-zA-Z0-9_\-]+)')
    filter_class = None
    filterform_class = None
    filtertool = True
    default_order = "id"
    template_name_suffix = "_list"

    order_mapping = None

    def get_template_names(self):
        try:
            return super().get_template_names()
        except ImproperlyConfigured:
            return "{}/{}{}.html".format(self.model._meta.app_label,self.model._meta.model_name,self.template_name_suffix)

    def get_filter_class(self):
        return self.filter_class

    def get_filterform_class(self):
        return self.filterform_class

    def get_filterform_data(self):
        return self.request.GET

    def get_queryset(self):
        filterformclass = self.get_filterform_class()
        if not filterformclass:
            queryset = self.model.objects.all() if self.queryset is None else self.queryset
        else:
            self.filterform = filterformclass(data=self.get_filterform_data(),request=self.request)
            if self.filterform.is_valid():
                filterclass = self.get_filter_class()
                if filterclass:
                    data_filter = self.get_filter_class()(self.filterform,request=self.request,queryset=self.queryset)
                    queryset = data_filter.qs
                else:
                    queryset = self.model.objects.all() if self.queryset is None else self.queryset
            else:
                queryset = self.model.objects.none()
 
        ordering = self.get_ordering()
        if ordering:
            if isinstance(ordering,str):
                queryset = queryset.order_by(ordering)
            else:
                queryset = queryset.order_by(*ordering)

        allow_empty = self.get_allow_empty()

        if not allow_empty:
            # When pagination is enabled and object_list is a queryset,
            # it's better to do a cheap query than to load the unpaginated
            # queryset in memory.
            if self.get_paginate_by(queryset) is not None and hasattr(queryset, 'exists'):
                is_empty = not queryset.exists()
            else:
                is_empty = not queryset
            if is_empty:
                raise Http404(_("Empty list and '%(class_name)s.allow_empty' is False.") % {
                    'class_name': self.__class__.__name__,
                })
        page_size = self.get_paginate_by(queryset)
        if page_size:
            paginator, page, queryset, is_paginated = self.paginate_queryset(queryset, page_size)
            self.paging_context = {
                'paginator': paginator,
                'page_obj': page,
                'is_paginated': is_paginated,
                'object_list': queryset
            }
        else:
            self.paging_context = {
                'paginator': None,
                'page_obj': None,
                'is_paginated': False,
                'object_list': queryset
            }

        return queryset

    def get_context_data(self, *, object_list=None, **kwargs):
        """Get the context for this view."""
        queryset = object_list if object_list is not None else self.object_list

        context = self.paging_context or {'object_list':queryset}
        context_object_name = self.get_context_object_name(queryset)
        if context_object_name is not None:
            context[context_object_name] = queryset
        context.update(kwargs)
        context["object_list_length"] = len(queryset)
        #add action related context data
        if self.request.method == 'GET':
            if self.request.GET.get("select_all") == "true" :
                context["select_all"] = "true"
            elif "selectedpks" in self.request.GET:
                context["selectedpks"] = [int(pk) for pk in self.request.GET.getlist("selectedpks")]
            elif "pk" in self.kwargs:
                context["selectedpks"] = [self.kwargs["pk"]]
            else:
                context["selectedpks"] = []
        else:
            if self.request.POST.get("select_all") == "true" :
                context["select_all"] = "true"
            elif "selectedpks" in self.request.POST:
                context["selectedpks"] = [int(pk) for pk in self.request.POST.getlist("selectedpks")]
            elif "pk" in self.kwargs:
                context["selectedpks"] = [self.kwargs["pk"]]
            else:
                context["selectedpks"] = []
        
        context["action__"] = self.selected_action

        self.update_context_data(context)
        self.post_update_context_data(context)
        return context

    def get_selected_ids(self,queryset=None):
        """
        return None is select all
        return empty list if select nothing
        return list of ids if select some 
        """
        if self.request.method == 'GET':
            if self.request.GET.get("select_all") == "true" :
                return None
            elif "selectedpks" in self.request.GET:
                return [int(pk) for pk in self.request.GET.getlist("selectedpks")]
            elif "pk" in self.kwargs:
                return [self.kwargs["pk"]]
            else:
                return []
        else:
            if self.request.POST.get("select_all") == "true" :
                return None
            elif "selectedpks" in self.request.POST:
                return [int(pk) for pk in self.request.POST.getlist("selectedpks")]
            elif "pk" in self.kwargs:
                return [self.kwargs["pk"]]
            else:
                return []

    def get_queryset_4_selected(self,queryset=None):
        selected_ids = self.get_selected_ids(queryset)
        if selected_ids is None :
            filterformclass = self.get_filterform_class()
            if not filterformclass:
                return self.model.objects.all() if queryset is None else queryset
            else:
                self.filterform = filterformclass(data=self.request.POST,request=self.request)
                if not self.filterform.is_valid():
                    raise http.HttpResponseServerError()

                data_filter = self.get_filter_class()(self.filterform,request=self.request,queryset=queryset)
                queryset = data_filter.qs
                #print("All {} records are selected.".format(len(queryset)))
        elif selected_ids:
            queryset = (queryset or self.model.objects).filter(pk__in=selected_ids)
        elif self.nexturl:
            messages.add_message(self.request,messages.ERROR,"No {} is selected".format(self.model_verbose_name))
            raise ReturnHttpResponse(HttpResponseRedirect(self.nexturl))
        else:
            raise Exception("No {} is selected.".format(self.model_verbose_name))

        #print("{} records are selected.".format(len(queryset)))
        return queryset

    def get_ordering(self):
        if self.order_mapping:
            order = self.requesturl.sorting_string or self.default_order
            return self.order_mapping.get(order,order)
        else:
            return self.requesturl.sorting_string or self.default_order

    def dispatch(self,request, *args, **kwargs):
        self.requesturl = RequestUrl(request)
        return super(ListBaseView,self).dispatch(request,*args,**kwargs)

    def get_success_url(self):
        return self.request.path

    def check_action_valid(self):
        if not self.object_list:
            raise Exception("Please choose at least one {} to continue.".format(self.model_verbose_name))

    def get_listform_kwargs(self):
        return {"instance_list":self.object_list,"request":self.request,"requesturl" :self.requesturl}

    def get_listform(self):
        form_class = self.get_listform_class()
        if form_class:
            return form_class(**self.get_listform_kwargs())
        else:
            return None


    def get_basic_action_context(self):
        self.object_list = self.get_queryset_4_selected()
        try:
            self.check_action_valid()
            self.is_action_valid = True
        except :
            self.is_action_valid = False
            raise 

        self.listform = self.get_listform()
        context = {
            'object_list':self.object_list,
            'listform':self.listform,
            'nexturl':self.nexturl
        }
        self.add_htmlmedia_context(context)
        return context

    def update_deleteconfirm_context(self,context):
        context['title'] = "Delete {}".format(self.model._meta.verbose_name if len(self.object_list) < 2 else self.model._meta.verbose_name_plural)
        context['confirm_message'] = "Are you sure you wish to delete the {}?".format(self.model._meta.verbose_name if len(self.object_list) < 2 else self.model._meta.verbose_name_plural)
        context['confirm_url'] = self.deleteconfirm_url if hasattr(self,"deleteconfirm_url") else ""
        context['delete_type']="object"

    def update_archiveconfirm_context(self,context):
        context['title'] = "Archive {}".format(self.model._meta.verbose_name if len(self.object_list) < 2 else self.model._meta.verbose_name_plural)
        context['confirm_message'] = "Are you sure you wish to archive the {}?".format(self.model._meta.verbose_name if len(self.object_list) < 2 else self.model._meta.verbose_name_plural)
        context['confirm_url'] = self.archiveconfirm_url if hasattr(self,"archiveconfirm_url") else ""

    def deleteconfirm_get(self):
        return self.render_to_response(self.get_action_context())

    def deleteconfirm_post(self):
        return self.deleteconfirm_get()

    def deleteconfirmed_post(self):
        selected_ids = self.get_selected_ids()
        #remove selected rows.
        is_protected = None
        for o in self.model.objects.filter(pk__in=selected_ids):
            msg = "Delete {}({} - {}) successfully.".format(o._meta.verbose_name,o.pk,o)
            if is_protected is None:
                is_protected = ModelDependencyTree(o.__class__).is_protected
            if is_protected:
                #is protected 
                ObjectDependencyTree(o).delete()
            else:
                o.delete()
            messages.add_message(self.request,messages.SUCCESS,msg)
    
        return HttpResponseRedirect(self.get_success_url())
        
    def archiveconfirm_get(self):
        return self.render_to_response(self.get_action_context())

    def archiveconfirm_post(self):
        return self.archiveconfirm_get()

    def archiveconfirmed_post(self):
        selected_ids = self.get_selected_ids()
        #remove selected rows.
        for o in self.model.objects.filter(pk__in=selected_ids):
            try:
                if o.is_archived:
                    messages.add_message(self.request,messages.WARNING,"{}({} - {}) is already archived.".format(o._meta.verbose_name,o.pk,o))
                else:
                    o.archive()
                    messages.add_message(self.request,messages.SUCCESS,"Archive {}({} - {}) successfully.".format(o._meta.verbose_name,o.pk,o))
            except Exception as ex:
                messages.add_message(self.request,messages.ERROR,"Failed to archive {}({} - {}) dut to {}".format(o._meta.verbose_name,o.pk,o, ex))
    
        return HttpResponseRedirect(self.get_success_url())
        
class ListView(ErrorMixin,HtmlMediaMixin,NextUrlMixin,ListBaseView):
    listform_class = None
    default_post_action = 'save'
    default_get_action = 'search'
    errorform_keys = ("listform",)

    def get_mediaforms(self):
        filterform_cls = self.get_filterform_class()
        listform_cls = self.get_listform_class()
        if listform_cls and filterform_cls:
            return (listform_cls,filterform_cls)
        elif listform_cls:
            return (listform_cls,)
        elif filterform_cls:
            return (filterform_cls,)
        else:
            return ()

    def get_listform_class(self):
        return self.listform_class

    def get(self, request, *args, **kwargs):
        self.object_list = self.get_queryset()
        self.listform = self.get_listform()
        context = self.get_context_data()
        return self.render_to_response(context)

    def post(self,request,*args,**kwargs):
        raise Http404("Post method is not supported.")

    def update_context_data(self,context):
        super(ListView,self).update_context_data(context)
        context["title"] = self.title or "{} List".format(self.model._meta.verbose_name)
        if self.listform is not None:
            context["listform"] = self.listform
        context["modelname"] = self.model_verbose_name
        context["requesturl"] = self.requesturl
        if self.get_filterform_class():
            context["filterform"] = self.filterform
            context["filtertool"] = self.filtertool
        else:
            context["filtertool"] = False

class OneToManyListView(OneToManyModelMixin,ListView):
    def get_listform_kwargs(self):
        kwargs = super(OneToManyListView,self).get_listform_kwargs()
        kwargs["parent_instance"] = self.pobject
        return kwargs


class ManyToManyListView(ManyToManyModelMixin,ListView):
    def update_deleteconfirm_context(self,context):
        super().update_deleteconfirm_context(context)
        context['delete_type']="manytomany"
        context['title'] = "Delete {0} from {1}".format(self.model._meta.verbose_name if len(self.object_list) < 2 else self.model._meta.verbose_name_plural,self.pmodel._meta.verbose_name)
        context['confirm_message'] = "Are you sure you wish to delete the {0} from {1}({2})?".format(self.model._meta.verbose_name if len(self.object_list) < 2 else self.model._meta.verbose_name_plural,self.pmodel._meta.verbose_name,self.pobject)

    def deleteconfirmed_post(self):
        selected_ids = self.get_selected_ids()
        #remove selected rows.
        is_protected = None
        for o in self.model.objects.filter(pk__in=selected_ids):
            msg = "Delete {0}({1} - {2}) from {3}({4}) successfully.".format(o._meta.verbose_name,o.pk,o,self.pmodel._meta.verbose_name,self.pobject)
            getattr(self.pobject,self.many_to_many_field_name).remove(o)
            messages.add_message(self.request,messages.SUCCESS,msg)
    
        return HttpResponseRedirect(self.get_success_url())
        
class ListUpdateView(ListView):
    default_post_action = 'save'
    default_get_action = 'search'
    template_name_suffix = "_changelist"

    def get_listform_kwargs(self):
        kwargs = super(ListUpdateView,self).get_listform_kwargs()
        if self.request.method == "POST":
            kwargs["data"] = self.request.POST
        return kwargs

    def post(self,request,*args,**kwargs):
        self.object_list = self.get_queryset()
        self.listform = self.get_listform()
        if not isinstance(self.listform,ListUpdateForm) or self.listform.is_valid():
            return self.form_valid()
        else:
            return self.form_invalid()

    def form_invalid(self):
        #print(self.listform.errors)
        context = self.get_context_data()
        return self.render_to_response(context)

    def form_valid(self):
        if isinstance(self.listform,ListUpdateForm):
            self.listform.save()
        return HttpResponseRedirect(self.get_success_url())

        
class OneToManyListUpdateView(OneToManyModelMixin,ListUpdateView):
    atomic_update = True

    def get_listform_kwargs(self):
        kwargs = super(OneToManyListUpdateView,self).get_listform_kwargs()
        kwargs["parent_instance"] = self.pobject
        return kwargs

    def post(self,request,*args,**kwargs):
        self.object_list = self.get_queryset()
        self.listform = self.get_listform()
        if isinstance(self.listform,ListUpdateForm):
            if self.listform.is_valid():
                return self.form_valid()
            else:
                return self.form_invalid()
        else:
            raise Exception("The list form class({}.{}) must be a subclass of ListUpdateForm in OneToManyListUpdateView".format(listform_class.__module__,listform_class.__name__))


    def form_valid(self):
        try:
            if self.atomic_update:
                with transaction.atomic():
                    if isinstance(self.listform,ListUpdateForm):
                        self.listform.save()
                    if self.pform and self.pform.editable:
                        if self.pform.is_valid():
                            self.pform.save()
                        else:
                            raise Exception("Invalid input")
            else:
                if isinstance(self.listform,ListUpdateForm):
                    self.listform.save()
                if self.pform and self.pform.editable:
                    if self.pform.is_valid():
                        self.pform.save()
                    else:
                        raise Exception("Invalid input")
            return HttpResponseRedirect(self.get_success_url())
        except:
            return self.form_invalid()

