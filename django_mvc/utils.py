import hashlib
import imp
import sys
import os
import inspect

from django.db import models
from django.http.request import (QueryDict,)
from django.utils.datastructures import (MultiValueDict,)

def getclassmethodargs(cls,method_name,processed_classes=None):
    func_kwonlyargs = []
    func_args = []
    varargs = True
    varkw = True

    processed_classes = processed_classes or set()

    if method_name in cls.__dict__:
        argspec = inspect.getfullargspec(getattr(cls,method_name))
        #get the args introduced by current method
        if argspec.args:
            try:
                for k in argspec.args if type(cls.__dict__[method_name]) == 'staticmethod' else argspec.args[1:]:
                    func_args.append(k)
            except:
                for k in argspec.args :
                    func_args.append(k)

        #get the kwargs introduced by current method
        if argspec.kwonlyargs:
            for k in argspec.kwonlyargs:
                func_kwonlyargs.append(k)

        varargs = argspec.varargs
        varkw = argspec.varkw


    #get the args and kwargs introduced by parent class
    if varkw or varargs:
        for base_cls in cls.__bases__:
            if base_cls not in processed_classes:
                if base_cls != object and hasattr(base_cls,method_name) :
                    base_args,base_kwonlyargs = getclassmethodargs(base_cls,method_name,processed_classes)
                    if base_args and varargs:
                        for k in base_args:
                            if k not in func_args:
                                func_args.append(k)
                    if base_kwonlyargs and varkw:
                        for k in base_kwonlyargs:
                            if k not in func_kwonlyargs:
                                func_kwonlyargs.append(k)
                processed_classes.add(base_cls)
    return (func_args,func_kwonlyargs)

def getallargs(func):
    qualname = func.__qualname__
    if "." in qualname:
        #maybe is a class method
        module_name = func.__module__
        parent_name = "{}.{}".format(module_name,qualname.rsplit(".",1)[0])
        func_name = func.__name__

        try:
            cls = get_type_object(parent_name)
            if inspect.isclass(cls) and hasattr(cls,func_name):
                #it is a class method
                return getclassmethodargs(cls,func_name)
        except:
            pass

    argspec = inspect.getfullargspec(func)
    return (argspec.args,argspec.kwonlyargs)





    module_name = func.__module__


class DynamicMultiValueDict(MultiValueDict):
    def __init__(self,key_to_list_mapping=(),request=None):
        super().__init__(key_to_list_mapping)
        self.request = request
        
    def __getitem__(self, key):
        v = super().__getitem__(key)
        if callable(v):
            v = v(self.request)
        return v

    def _getlist(self, key):
        v = super()._getlist(key)
        if v:
            index = 0
            while index < len(v):
                if callable(v[index]):
                    v[index] = v[index](self.request)
                index += 1
        return v
        
    def getlist(self, key):
        return self._getlist(key)


class ChainMultiValueDict(MultiValueDict):
    """
    readonly not for editing
    """
    def __init__(self,dicts,f_isnone=None):
        self.dicts = dicts
        self.f_isnone = f_isnone or (lambda v:False if v else True)

    def __contains__(self, key):
        for d in self.dicts:
            if key in d:
                return True

        return False

    def __getitem__(self, key):
        #if key == "is_burn":
        #    import ipdb;ipdb.set_trace()
        for d in self.dicts:
            try:
                v = d[key]
                if self.f_isnone(v):
                    continue
                else:
                    return v
            except:
                continue
        raise KeyError("{} Not Exist".format(key))

    def get(self, key, default=None):
        try:
            return self.__getitem__(key)
        except KeyError as es:
            return default


    def _getlist(self, key):
        for d in self.dicts:
            try:
                v = d.getlist(key)
                if self.f_isnone(v):
                    continue
                else:
                    return v
            except:
                continue
        return []
        
    def getlist(self, key):
        return self._getlist(key)

    def items(self):
        for key in self.dicts[0].keys():
            yield key, self[key]

    def lists(self):
        for key in self.dicts[0].keys():
            yield key, self.getlist(key)

    def values(self):
        for key in self.dicts[0].keys():
            yield self[key]
    
    def dict(self):
        raise NotImplementedError("Not implemented")

def is_equal(o1,o2):
    if o1 == o2:
        return True
    elif o1 is None:
        return False
    elif o2 is None:
        return False

    if o1 == "":
        o1 == None
    elif isinstance(o1,models.Model) or isinstance(o2,models.Model):
        o1 = o1.pk if isinstance(o1,models.Model) else o1
    elif isinstance(o1,models.manager.Manager):
        o1 = o1.all()
    elif isinstance(o1,models.query.QuerySet):
        o1 = list(o1)

    if o2 == "":
        o2 = None
    elif isinstance(o2,models.Model) or isinstance(o2,models.Model):
        o2 = o2.pk if isinstance(o2,models.Model) else o2
    elif isinstance(o2,models.manager.Manager):
        o2 = o2.all()
    elif isinstance(o2,models.query.QuerySet):
        o2 = list(o2)

    if o1 == o2:
        return True
    elif o1 is None:
        return False
    elif o2 is None:
        return False
    elif isinstance(o1,(list,tuple)) and isinstance(o1,(list,tuple)):
        if len(o1) != len(o2):
            return False
        else:
            for  o in o1:
                if o not in o2:
                    return False
            return True
    elif isinstance(o1,dict) and isinstance(o2,dict):
        if len(o1) != len(o2):
            return False
        else:
            for  k,v in o1.items():
                if k not in o2:
                    return False
                elif not is_equal(v,o2[k]):
                    return False
            return True
    elif o1.__class__ == o2.__class__:
        return False
    else:
        raise Exception("Comparing {}.{}({}) with {}.{}({}) Not Supported".format(o1.__class__.__module__,o1.__class__.__name__,o1,o2.__class__.__module__,o2.__class__.__name__,o2))

def hashvalue(value):
    m = hashlib.sha1()
    m.update(value.encode('utf-8'))
    return m.hexdigest()
    
class RangeChoice(dict):
    """
     a dict object which key is choosed against a range
     choices is a list of tuple or list with 2 members. the first member is a number, the second member is the value
    """
    def __init__(self,choices,operator="lt"):
        self.choices = choices or []
        self.operator = getattr(self,"_{}".format(operator))

    def _lt(self,choice_value,value):
        return choice_value is None or value < choice_value

    def _lte(self,choice_value,value):
        return choice_value is None or value <= choice_value

    def _gt(self,choice_value,value):
        return choice_value is None or value > choice_value

    def _gt(self,choice_value,value):
        return choice_value is None or value >= choice_value

    def __contains__(self,name):
        try:
            value = self[name]
            return True
        except:
            return False

    def __getitem__(self,name):
        for choice in self.choices:
            if self.operator(choice[0],name):
                return choice[1]

        raise KeyError("Key '{}' does not exist.".format(name))
        
    def __len__(self):
        return len(self.choices)

    def __str__(self):
        return str(self.choices)

    def __repr__(self):
        return repr(self.choices)

    def get(self,name,default=None):
        try:
            return self[name]
        except KeyError as ex:
            return default

class ConditionalChoice(dict):
    """
     a dict object which key is a object or a list or tuple
     choices is a list of tuple or list with 2 members. the first member is a lambda expression with the same parameters, the second member is the value
    """
    def __init__(self,choices,single_parameter = True):
        self.choices = choices or []
        self.single_parameter = single_parameter

    def __contains__(self,key):
        try:
            value = self[key]
            return True
        except:
            return False

    def __getitem__(self,key):
        for choice in self.choices:
            if self.single_parameter:
                if choice[0](key):
                    return choice[1]
            else:
                if choice[0](*key):
                    return choice[1]


        raise KeyError("Key '{}' does not exist.".format(key))
        
    def __len__(self):
        return len(self.choices)

    def __str__(self):
        return str(self.choices)

    def __repr__(self):
        return repr(self.choices)

    def get(self,key,default=None):
        try:
            return self[key]
        except KeyError as ex:
            return default

def load_module(name,base_path="."):
    # Fast path: see if the module has already been imported.
    try:
        return sys.modules[name]
    except KeyError:
        pass
    
    path,filename = os.path.split(name.replace(".","/"))
    if not path.startswith("/"):
        base_path = os.path.realpath(base_path)
        path = os.path.join(base_path,path)

    # If any of the following calls raises an exception,
    # there's a problem we can't handle -- let the caller handle it.

    print("find module {}:{}".format(filename,path))
    fp, pathname, description = imp.find_module(filename,[path])

    try:
        return imp.load_module(name, fp, pathname, description)
    finally:
        # Since we may exit via an exception, close fp explicitly.
        if fp:
            fp.close()

def get_type_object(type_name):
    """
    Return the type object with type name; throw exception if not found
    """
    names = []
    module_name,name = type_name.rsplit(".",1)
    module = None
    while module_name:
        try:
            module = sys.modules[module_name]
            names.insert(0,name)
            break
        except KeyError:
            names.insert(0,name)
            module_name,name = module_name.rsplit(".",1)

    if not module:
        raise Exception("Can't find type '{}'.".format(type_name))

    type_object = module
    for name in names:
        if hasattr(type_object,name):
            type_object = getattr(type_object,name)
        else:
            raise Exception("'{}' has no attribute '{}'.".format(type_object,name))

    return type_object

def get_class(class_name):
    """
    Return clss object with class name; throw exception if not found or not a class
    """
    type_obj = get_type_object(class_name)
    if inspect.isclass(type_obj):
        return type_obj
    else:
        raise Exception("'{}' is not a class.".format(class_name))



def filesize(f):
    if f:
        size = f.size
        if size < 1024:
            return "{} B".format(size)
        elif size < 1048576:
            return "{} K".format(round(size / 1024,2))
        elif size < 1073741824:
            return "{} M".format(round(size / 1048576,2))
        else:
            return "{} G".format(round(size / 1073741824,2))

    else:
        return None

not_imported_classes = {}
def class_not_imported(name,ex):
    if name not in not_imported_classes:
        class ClassNotImported(object):
            _name = name
            _ex = ex

            def __init__(self,*args,**kwargs):
                pass

            def __getattr__(self,name):
                raise Exception("Can't import '{}'. {}".format(self._name,str(self._ex)))

        not_imported_classes[name] = ClassNotImported

    return not_imported_classes[name]

def object_not_imported(name,ex):
    return class_not_imported(name,ex)()
