import django.dispatch

django_inited = django.dispatch.Signal()
actions_inited = django.dispatch.Signal()

fields_inited = django.dispatch.Signal()
formfields_inited = django.dispatch.Signal()
formsetfields_inited = django.dispatch.Signal()
listformfields_inited = django.dispatch.Signal()

widgets_inited = django.dispatch.Signal()

forms_inited = django.dispatch.Signal()
listforms_inited = django.dispatch.Signal()
formsets_inited = django.dispatch.Signal()

views_inited = django.dispatch.Signal()

system_ready = django.dispatch.Signal()

