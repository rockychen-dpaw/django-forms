from __future__ import unicode_literals
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ObjectDoesNotExist,ValidationError
from django.db import models
from django.utils import timezone
import threading

class SelectOptionMixin(object):
    """
    simulate a selection object, which should be a tuple or list or iterable object with length 2
    """
    def __iter__(self):
        """
        Returns itself as an iterator
        """
        self._position = -1
        return self

    def __next__(self):
        self._position += 1
        if self._position == 0:
            return self.option_value
        elif self._position == 1:
            return self.option_label
        else:
            raise StopIteration()

    @property
    def option_value(self):
        return self.id

    @property
    def option_label(self):
        return str(self)


class DictMixin(object):
    """
    simulate a dict object 
    """
    def __contains__(self,name):
        return hasattr(self,name)

    def __getitem__(self,name):
        try:
            return getattr(self,name)
        except AttributeError as ex: 
            raise KeyError(name)

    def get(self,name,default = None):
        """
        Implement a speicial name 'self', which will return the dict object itself.
        """
        try:
            return self[name]
        except:
            if name == "self":
                return self
            else:
                return default

class ModelDictMixin(DictMixin):
    """
    simulate a dict object 
    """
    def __getitem__(self,name):
        try:
            result = getattr(self,name)
            return result
        except AttributeError as ex: 
            raise KeyError(name)

    def __delitem__(self,name):
        #model dict doesn't support del item,
        pass

    @property
    def dependency_tree(self):
        from django_mvc.inspectmodel import ObjectDependencyTree
        try:
            return self._dependency_tree
        except:
            self._dependency_tree = ObjectDependencyTree(self,exclude_unprotected=False,exclude_many2many=False)
            return self._dependency_tree

    def __len__(self):
        """
        fake len, just make sure ModelDictMixin instane is always true
        """
        return 1

class DictWrapper(object):
    """
    wrapper a object to simulate a dict object 
    """
    def __init__(self,obj):
        self.obj = obj

    def __contains__(self,name):
        return hasattr(self.obj,name)

    def __getitem__(self,name):
        try:
            return getattr(self.obj,name)
        except AttributeError as ex: 
            raise KeyError(name)

    def __delitem__(self,name):
        #model dict doesn't support del item,
        pass

    def get(self,name,default = None):
        """
        Implement a speicial name 'self', which will return the dict object itself.
        """
        try:
            return self.__getitem__(name)
        except:
            if name == "self":
                return self.obj
            else:
                return default

class ModelDictWrapper(DictWrapper):
    """
    wrapper a model instance to simulate a dict object 
    """
    @property
    def dependency_tree(self):
        from django_mvc.inspectmodel import ObjectDependencyTree
        try:
            return self.obj._dependency_tree
        except:
            self.obj._dependency_tree = ObjectDependencyTree(self.obj,exclude_unprotected=False,exclude_many2many=False)
            return self.obj._dependency_tree

    def __len__(self):
        """
        fake len, just make sure ModelDictMixin instane is always true
        """
        return 1

class ActiveMixinManager(models.Manager):
    """Manager class for ActiveMixin.
    """
    def current(self):
        return self.filter(effective_to=None)

    def deleted(self):
        return self.filter(effective_to__isnull=False)


class ActiveMixin(models.Model):
    """Model mixin to allow objects to be saved as 'non-current' or 'inactive',
    instead of deleting those objects.
    The standard model delete() method is overridden.

    "effective_to" is used to flag 'deleted' objects (not null==deleted).
    """
    effective_to = models.DateTimeField(null=True, blank=True)
    objects = ActiveMixinManager()

    class Meta:
        abstract = True

    def is_active(self):
        return self.effective_to is None

    def is_deleted(self):
        return not self.is_active()

    def delete(self, *args, **kwargs):
        """Overide the standard delete method; sets effective_to the current
        date and time.
        """
        if 'force' in kwargs and kwargs['force']:
            kwargs.pop('force', None)
            super(ActiveMixin, self).delete(*args, **kwargs)
        else:
            self.effective_to = timezone.now()
            super(ActiveMixin, self).save(*args, **kwargs)


class AuditMixin(models.Model):
    """Model mixin to update creation/modification datestamp and user
    automatically on save.
    """
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_created', editable=False)
    modifier = models.ForeignKey(
        settings.AUTH_USER_MODEL, blank=True, null=True, on_delete=models.PROTECT,
        related_name='%(app_label)s_%(class)s_modified', editable=False)
    created = models.DateTimeField(default=timezone.now, editable=False)
    modified = models.DateTimeField(auto_now=True, editable=False)

    class Meta:
        abstract = True


    def clean_fields(self, exclude=None):
        """
        Override clean_fields to do what model validation should have done
        in the first place -- call clean_FIELD during model validation.
        """
        errors = {}

        for f in self._meta.fields:
            if f.name in exclude:
                continue
            if hasattr(self, "clean_%s" % f.attname):
                try:
                    getattr(self, "clean_%s" % f.attname)()
                except ValidationError as e:
                    # TODO: Django 1.6 introduces new features to
                    # ValidationError class, update it to use e.error_list
                    errors[f.name] = e.messages
        try:
            super(AuditMixin, self).clean_fields(exclude)
        except ValidationError as e:
            errors = e.update_error_dict(errors)

        if errors:
            raise ValidationError(errors)
