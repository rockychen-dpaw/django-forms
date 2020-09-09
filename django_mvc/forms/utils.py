import json
from collections import OrderedDict
import hashlib
import pytz

from django import forms
from django.db import models
from django.utils.html import mark_safe

class JSONEncoder(json.JSONEncoder):
    """
    A JSON encoder to support encode model instance and static methods
    """
    def default(self,obj):
        if isinstance(obj,models.Model):
            return obj.pk
        elif callable(obj) or isinstance(obj,staticmethod):
            return id(obj)
        elif isinstance(obj,forms.Widget):
            return "{}.{}_{}".format(obj.__class__.__module__,obj.__class__.__name__,id(obj))
        return json.JSONEncoder.default(self,obj)

def hashvalue(value):
    m = hashlib.sha1()
    m.update(value.encode('utf-8'))
    return m.hexdigest()
    

class Media(forms.Media):
    def __init__(self, media=None, css=None, js=None,statements=None):
        super().__init__(media=media,css=css,js=js)
        self._statements = [] if statements is None else statements

    def __repr__(self):
        return 'Media(css=%r, js=%r, statements=%r)' % (self._css, self._js,self._statements)

    def render_statements(self):
        return [mark_safe(s) for s in self._statements]

    def __add__(self, other):
        combined_js = self.merge(self._js, other._js)
        combined_css = {
            medium: self.merge(self._css.get(medium, []), other._css.get(medium, []))
            for medium in self._css.keys() | other._css.keys()
        }
        combined = Media(js=combined_js,css=combined_css)
        if hasattr(other,"_statements"):
            combined._statements = self.merge(self._statements, other._statements)
        else:
            combined._statements = self._statements
        return combined

class NoneValueKey(KeyError):
    pass

class FieldClassConfigDict(dict):
    """
    Try to get the value of the key using the following logic
    1. if key exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    2. if name part of the key exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    3. if the key "[default_key_name].[purpose]" exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    4. if the key "[default_key_name]" exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    5. key doesn't exist,
    """
    def __init__(self,meta_class,dict_obj):
        super(FieldClassConfigDict,self).__init__()
        self.data = dict_obj if dict_obj is not None else {}
        self._meta_class = meta_class
        self._default_key_name =  "__default__"
        self._editable_fields = self._meta_class.editable_fields if self._meta_class and hasattr(self._meta_class,"editable_fields") else None
        self._purpose = self.init_purpose(self._meta_class.purpose if self._meta_class and hasattr(self._meta_class,"purpose") else None)

    def init_purpose(self,purpose):
        if not purpose:
            return ("edit","view")

        if not purpose[1]:
            return (purpose[0],"view")

        return purpose

    def keypurpose(self,name,purpose=None):
        purpose = purpose or self._purpose
        if purpose[0] and (self._editable_fields is None or name in self._editable_fields):
            return (purpose[0],True)
        else:
            return (purpose[1] or "view",False)

    def search_keys(self,name,purpose=None,enable_default_key=True):
        keypurpose,editable = self.keypurpose(name,purpose)
        if isinstance(keypurpose,str):
            if self._meta_class.is_editable_dbfield(name) or not enable_default_key:
                return ("{}.{}".format(name,keypurpose),name)
            else:
                return ("{}.{}".format(name,keypurpose),name,"{}.{}".format(self._default_key_name,keypurpose),self._default_key_name)
        else:
            if self._meta_class.is_editable_dbfield(name):
                keys = ["{}.{}".format(name,p) for p in keypurpose]
                keys.append(name)
                return keys
            else:
                keys =["{}.{}".format(name,p) for p in keypurpose]
                keys.append(name)
                if enable_default_key:
                    for p in keypurpose:
                        keys.append("{}.{}".format(self._default_key_name,p))
                    keys.append(self._default_key_name)
                return keys

    def __contains__(self,name):
        for key in self.search_keys(name):
            if key in self.data:
                return False if self.data[key] is None else True

        return False

    def __getitem__(self,name):
        return self.get_config(name)
        
    def __len__(self):
        return len(self.data) if self.data else 0

    def __str__(self):
        return str(self.data)

    def __repr__(self):
        return repr(self.data)

    def get(self,name,default=None):
        try:
            return self[name]
        except KeyError as ex:
            return default


    def get_config(self,name,purpose=None,enable_default_key=True):
        for key in self.search_keys(name,purpose,enable_default_key):
            try:
                value = self.data[key]
                if value is None:
                    raise NoneValueKey(name)
                return value
            except NoneValueKey:
                raise
            except:
                pass
        raise KeyError(name)

class FieldWidgetConfigDict(FieldClassConfigDict):
    """
    Try to get the value of the key using the following logic
    1. if key exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    2. if name part of the key exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    3. if the key "[default_key_name].[purpose]" exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    4. if the key "[default_key_name]" exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    5. key doesn't exist,
    """

    def search_keys(self,name,purpose=None,enable_default_key=True):
        keypurpose,editable = self.keypurpose(name,purpose)
        if isinstance(keypurpose,str):
            if (editable and self._meta_class.is_dbfield(name)) or not enable_default_key:
                return ("{}.{}".format(name,keypurpose),name)
            else:
                return ("{}.{}".format(name,keypurpose),"{}.{}".format(self._default_key_name,keypurpose),self._default_key_name)
        else:
            if editable and self._meta_class.is_dbfield(name):
                keys = ["{}.{}".format(name,p) for p in keypurpose]
                keys.append(name)
                return keys
            else:
                keys = ["{}.{}".format(name,p) for p in keypurpose]
                if enable_default_key:
                    for p in keypurpose:
                        keys.append("{}.{}".format(self._default_key_name,p))
                    keys.append(self._default_key_name)
                return keys

class FieldLabelConfigDict(FieldClassConfigDict):
    """
    Try to get the value of the key using the following logic
    1. if key exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    2. if name part of the key exists in the dict, return it directly if its value is not None; if its value is None, means key doesn't exist,
    3. key doesn't exist,
    """

    def search_keys(self,name,purpose=None,enable_default_key=True):
        keypurpose,editable = self.keypurpose(name,purpose)
        if isinstance(keypurpose,str):
            return ("{}.{}".format(name,keypurpose),name)
        else:
            keys = ["{}.{}".format(name,p) for p in keypurpose]
            keys.append(name)
            return keys

class SubpropertyEnabledDict(dict):
    """
    Support recursive dict structure; that means, the value of dict key can be a dict object.
    Compund key "key__subkey__subkey" can be used to access the value from inner dict object.
    """
    def __init__(self,dict_obj):
        super(SubpropertyEnabledDict,self).__init__()
        self.data = dict_obj

    @property
    def pk(self):
        """
        used to access pk directly
        """
        return self.data["pk"]

    def __contains__(self,name):
        if not self.data: return False

        if name in self.data:
            return True
        else:
            pos = name.find("__")
            if pos >= 0:
                name = name[0:pos]
                return name in self.data
            else:
                return False

    def __getitem__(self,name):
        if self.data is None: raise TypeError("dict is None")

        try:
            return self.data[name]
        except:
            pos = name.find("__")
            if pos >= 0:
                names = name.split("__")
                result = self.data
                for key in names:
                    if not result: raise KeyError(name)
                    try:
                        result = result[key]
                    except KeyError as ex:
                        raise KeyError(name)
                    except :
                        if isinstance(result,models.Model):
                            return getattr(result,key)
                        raise

                return result
            else:
                raise

    def __setitem__(self,name,value):
        if self.data is None: raise TypeError("dict is None")

        pos = name.find("__")
        if pos >= 0:
            names = name.split("__")
            result = self.data
            for key in names[0:-1]:
                try:
                    result = result[key]
                except KeyError as ex:
                    #key does not exist, create one
                    result[key] = {}
                    result = result[key]

            result[names[-1]] = value
        else:
            self.data[name] = value

    def __len__(self):
        return len(self.data) if self.data else 0

    def __str__(self):
        return str(self.data)

    def __repr__(self):
        return repr(self.data)

    def get(self,name,default=None):
        try:
            return self.__getitem__(name)
        except KeyError as ex:
            return default

class ChainDict(dict):
    """
    A dict object which consist of a array of dict objects.
    The value of a key is the value of the key in the first dict object.
    The the key doesn't exist in all dict objects, then KeyError will be thrown
    """
    def __init__(self,dict_objs):
        super(ChainDict,self).__init__()
        if isinstance(dict_objs,list):
            self.dicts = dict_objs
        elif isinstance(self.dicts,tuple):
            self.dicts = list(dict_objs)
        elif isinstance(self.dicts,dict):
            self.dicts = [dict_objs] 
        else:
            self.dicts = [dict(dict_objs)] 

    def __contains__(self,name):
        for d in self.dicts:
            if name in d:
                return True 
        return False

    def __getitem__(self,name):
        for d in self.dicts:
            try:
                return d[name]
            except:
                continue

        raise KeyError(name)

    def __len__(self):
        """
        return 1 if has value;otherwise return 0
        """
        for d in self.dicts:
            if d:
                return 1 
                
        return 0

    def __str__(self):
        return [str(d) for d in self.dicts]

    def __repr__(self):
        return [repr(d) for d in self.dicts]

    def get(self,name,default=None):
        for d in self.dicts:
            try:
                return d[name]
            except:
                continue

        return default

    def update(self,dict_obj):
        self.dicts.insert(0,dict_obj)

