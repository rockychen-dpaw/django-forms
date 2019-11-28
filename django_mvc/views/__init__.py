from .views import (RequestActionMixin,UrlpatternsMixin,ParentObjectMixin,SendDataThroughUrlMixin,
        CreateView,OneToManyCreateView,
        DetailView,OneToOneDetailView,OneToManyDetailView,
        EditView,OneToOneEditView,OneToManyEditView,
        ListView,OneToManyListView,ManyToManyListView,
        ListEditView,OneToManyListEditView,
        HttpResponseRedirectException)


from django.template import Context, loader
from django.http import HttpResponseServerError

# Create your views here.
def handler500(request):
    t = loader.get_template('500.html')
    return HttpResponseServerError(t.render(request=request))


def handler404(request,ex):
    t = loader.get_template('404.html')
    return HttpResponseServerError(t.render(request=request))


