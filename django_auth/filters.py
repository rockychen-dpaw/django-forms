from django_mvc.forms import filters

class UserFilter(filters.Filter):
    q = filters.QFilter(fields=(("username","icontains"),("first_name","icontains"),("last_name","icontains"),("email","icontains")))
    is_active = filters.BooleanFilter(field_name='is_active',lookup_expr='exact')
    groupid = filters.NumberFilter(field_name='groups',lookup_expr='exact')

