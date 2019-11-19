from .views import (UsersView,UserUpdateView)

app_name = "django_auth"
urlpatterns = []

urlpatterns.extend(UsersView.urlpatterns())
urlpatterns.extend(UserUpdateView.urlpatterns())



