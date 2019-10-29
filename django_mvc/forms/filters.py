from django.db import models
from django.utils import timezone
from django.db.models import Q

from django_filters.rest_framework import *

from django_filters import filters
from django_filters.constants import EMPTY_VALUES


class Filter(FilterSet):
    def __init__(self,form,request=None,queryset=None):
        queryset = form._meta.model.objects.all() if queryset is None else queryset
        super(Filter,self).__init__(request,queryset=queryset)
        self._form = form

    def filter_queryset(self, queryset):
        """
        Filter the queryset with the underlying form's `cleaned_data`. You must
        call `is_valid()` or `errors` before calling this method.

        This method should be overridden if additional filtering needs to be
        applied to the queryset before it is cached.
        """
        for name, value in self.form.cleaned_data.items():
            if value is None:
                continue
            elif isinstance(value,models.Model):
                value = value.pk
            elif name not in self.filters:
                continue
            queryset = self.filters[name].filter(queryset, value)
            assert isinstance(queryset, models.QuerySet), \
                "Expected '%s.%s' to return a QuerySet, but got a %s instead." \
                % (type(self).__name__, name, type(queryset).__name__)
        return queryset


class QFilter(filters.CharFilter):
    def __init__(self, fields, **kwargs):
        super(QFilter,self).__init__( **kwargs)
        self.fields = fields

    def filter(self, qs, value):
        if value in EMPTY_VALUES:
            return qs
        if self.distinct:
            qs = qs.distinct()
        qfilter = None
        for field in self.fields:
            if qfilter:
                qfilter = qfilter | Q(**{"{0}__{1}".format(*field):value})
            else:
                qfilter = Q(**{"{0}__{1}".format(*field):value})
        qs = self.get_method(qs)(qfilter)
        return qs



class DateRangeFilter(filters.DateRangeFilter):
    choices = [
        ('today', 'Today'),
        ('yesterday', 'Yesterday'),
        ('last_7_days', 'Past 7 days'),
        ('current_month','This month'),
        ('current_year', 'This year'),
    ]

    filters = {
        'today': lambda qs, name: qs.filter(**{
            '%s__gte' % name: timezone.now().date()
        }),
        'yesterday': lambda qs, name: qs.filter(**{
            '%s__gte' % name: (lambda d: timezone.datetime(d.year,d.month,d.day - 1))(timezone.now()),
            '%s__lt' % name: (lambda d: timezone.datetime(d.year,d.month,d.day))(timezone.now())
        }),
        'last_7_days': lambda qs, name: qs.filter(**{
            '%s__gte' % name: (lambda d: timezone.datetime(d.year,d.month,d.day - 6))(timezone.now())
        }),
        'current_month': lambda qs, name: qs.filter(**{
            '%s__gte' % name: (lambda d: timezone.datetime(d.year,d.month,1))(timezone.now())
        }),
        'current_year': lambda qs, name: qs.filter(**{
            '%s__gte' % name: (lambda d: timezone.datetime(d.year,1,1))(timezone.now())
        }),
    }



