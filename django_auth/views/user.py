from django.contrib.auth.models import (User,Group)

from django_auth.filters import (UserFilter,)
from django_auth.forms import (UserListForm,UserFilterForm,UserUpdateForm,UserViewForm)
from django_mvc import views


class UserUpdateView(views.UpdateView):
    title = "Update User"
    model = User
    context_object_name = "currentuser"
    form_class = UserUpdateForm
    urlpattern = "user/<int:pk>/"
    urlname = "user_update"
    template_name_suffix = "_update"

    @property
    def title(self):
        if self.can_admin:
            return "Update User"
        else:
            return "User Detail"


    @property
    def can_admin(self):
        if self.request.user.is_superuser:
            return True
        else:
            user_groups = self.request.user.groups.all()
            if any(g in user_groups for g in (Group.FMSB,)):
                return True

        return False

    def get_form_class(self):
        if self.can_admin:
            return UserUpdateForm
        else:
            return UserViewForm


    def _get_success_url(self):
        return urls.reverse("user:user_list")

    def post(self,*args,**kwargs):
        if not self.can_admin:
            return HttpResponseForbidden('Not authorised.')
        return super().post(*args,**kwargs)



class UsersView(views.ListView):
    model = User
    context_object_name = "currentuser"
    filter_class = UserFilter
    filterform_class = UserFilterForm
    listform_class = UserListForm
    urlpattern = "user/"
    urlname = "user_list"
    filtertool = False
    template_name_suffix = "_list"
    title = "User List"
    default_order = "username"
    paginate_by=100

    def _get_success_url(self):
        return urls.reverse("django_auth:user_list")

    @property
    def queryset(self):
        return User.objects.filter(id__gt = 0)

    def update_context_data(self,context):
        super().update_context_data(context)
        context["activestatuslist"] = ((True,"Yes"),(False,"No"))
        context["grouplist"] = [(g.id,g.name) for g in Group.objects.all()]




