from .views import (UsersView,UserEditView)

app_name = "django_auth"
urlpatterns = []

urlpatterns.extend(UsersView.urlpatterns())
urlpatterns.extend(UserEditView.urlpatterns())



