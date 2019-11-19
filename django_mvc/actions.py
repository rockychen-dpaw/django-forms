import inspect

from django.dispatch import receiver

from django_mvc.signals import django_inited,actions_inited

class Action(object):
    """
    all attr name should be lower case
    """
    def __init__(self,action,tag="button",tag_body=None,tag_attrs=None,permission=None):
        self.permission = permission if permission else None

        self.tag = tag.lower()
        self.action = action
        self.tag_body = tag_body or action
        self.tag_attrs = tag_attrs or {}
        self.callable_attrs = None
        self.cloned_actions = None
        self.initialized = False

    def initialize(self):
        if self.initialized:
            return

        from django_mvc.forms import widgets
        if self.permission and callable(self.permission):
            self.permission = self.permission()

        if self.tag_body and callable(self.tag_body):
            self.tag_body = self.tag_body()

        default_attrs = []
        if self.tag == "option":
            default_attrs=[("value",self.action)]
        elif self.tag == "button":
            if "onclick" in self.tag_attrs:
                default_attrs=[("class","btn btn-primary"),("value",self.action),("name","action__")]
            else:
                default_attrs=[("class","btn btn-primary"),("type","submit"),("value",self.action),("name","action__")]

        for k,v in default_attrs:
            if k not in self.tag_attrs:
                self.tag_attrs[k] = v 
        if self.tag_attrs:
            for k in self.tag_attrs.keys():
                if callable(self.tag_attrs[k]):
                    argspec = inspect.getfullargspec(self.tag_attrs[k])
                    if not argspec.args:
                        self.tag_attrs[k] = self.tag_attrs[k]()

                    if callable(self.tag_attrs[k]):
                        #initialized attribute need further initialization
                        argspec = inspect.getfullargspec(self.tag_attrs[k])
                        self.callable_attrs = [] if self.callable_attrs is None else self.callable_attrs
                        self.callable_attrs.append((k,(lambda method,argspec:(lambda kwargs: method(*[kwargs.get(p) for p in argspec.args])))(self.tag_attrs[k],argspec) ))

        #delete non-ready attributes which need further initialization from tag_attrs
        if self.callable_attrs:
            self.html = self._html2
            for k,m in self.callable_attrs:
                del self.tag_attrs[k]
        else:
            self.html = self._html1
        
        self._widget = widgets.HtmlTag(self.tag,self.tag_attrs,self.tag_body)

        if not self.permission:
            self.has_permission = self._always_has_permission
        elif isinstance(self.permission,str):
            self.permission = RightPermission(self.permission)
            self.has_permission = self._check_permission
        elif isinstance(self.permission,(list,tuple)):
            self.permission = [ RightPermission(perm) if isinstance(perm,str) else perm for perm in self.permission]
            self.has_permission = self._check_any_permissions
        else:
            self.has_permission = self._check_permission

        if self.cloned_actions:
            for a in self.cloned_actions:
                a.initialize()

        self.initialized = True


    def clone(self,tag_attrs=None,tag_body=None):
        attrs = dict(self.tag_attrs)
        if tag_attrs:
            attrs.update(tag_attrs)
        action  = Action(self.action,tag=self.tag,tag_body=tag_body or self.tag_body,tag_attrs=attrs,permission=self.permission)
        if self.cloned_actions is None:
            self.cloned_actions = [action]
        else:
            self.cloned_actions.append(action)

        if self.initialized:
            action.initialize()
        return action

    def _always_has_permission(self,user):
        return True;

    def _check_permission(self,user):
        print("check permission:user={}, permission={}".format(user,self.permission))
        if user.is_superuser:
            return True
        return self.permission.check(user)

    def _check_any_permissions(self,user):
        print("check permission:user={}, permission={}".format(user,self.permission))
        if user.is_superuser:
            return True
        for perm in self.permission:
            if perm.check(user):
                return True
        return False

    @property
    def widget(self):
        return self._widget

    @property
    def basehtml(self):
        return self.html()

    def _html1(self,value = "",**kwargs):
        value = value or ""
        if value == self.action:
            return self._widget.render("selected=\"selected\"")
        else:
            return self._widget.render()

    def _html2(self,value = "",**kwargs):
        value = value or ""
        attrs = {} 
        for k,m in self.callable_attrs:
            v = m(kwargs)
            if v:
                attrs[k] = v
        if attrs:
            attrs =  " ".join(["{}=\"{}\"".format(key,value) for key,value in attrs.items()])
        else:
            attrs = None

        if value == self.action:
            return self._widget.render("selected=\"selected\"",attrs=attrs)
        else:
            return self._widget.render(attrs=attrs)

class BasePermission(object):
    def initialize(self):
        pass

    def check(self,user):
        return False

class GroupPermission(BasePermission):
    def __init__(self,group):
        self.group_not_exist = False
        self.group = group

    def initialize(self):
        from django.contrib.auth.models import Group
        try:
           if isinstance(self.group,str):
               self.group = Group.objects.get(name=self.group)
           elif isinstance(self.group,int):
               self.group = Group.objects.get(id=self.group)
           elif isinstance(self.group,Group):
               pass
           else:
               self.group_not_exist = True
        except ObjectDoesNotExist as ex:
            self.group_not_exist = True

    def __str__(self):
        return "User Group:{}".format(self.group)

    def check(self,user):
        if self.group_not_exist:
            return False
        elif self.group:
            return self.group in user.groups.all()
        else:
            return True

class RightPermission(BasePermission):
    def __init__(self,permission):
        self.permission = permission

    def __str__(self):
        return "Permission:{}".format(self.permission)

    def check(self,user):
        return user.has_perm(self.permission)

class UsernamePermission(BasePermission):
    def __init__(self,user,casesensitive=False,exact_match=False,exclusive=False):
        self.casesensitive = casesensitive
        self.exclusive = exclusive
        self.exact_match = exact_match

        if isinstance(user,str):
            self.user = [user if self.casesensitive else user.upper()]
        else:
            self.user = [u if self.casesensitive else u.upper() for u in user]

        if self.exact_match:
            self.is_match = lambda loginuser,user: loginuser == user if self.casesensitive else loginuser.upper() == user
        else:
            self.is_match = lambda loginuser,user: user in loginuser if self.casesensitive else user in loginuser.upper()

    def __str__(self):
        return "Login user should {} {} with {}".format("not be" if self.exclusive else "be",self.user,"case sensitive" if self.casesensitive else "case insensitive")

    def check(self,user):
        if self.exclusive:
            for u in self.user:
                if self.is_match(user.username,u):
                    return False
            return True
        else:
            for u in self.user:
                if self.is_match(user.username,u):
                    return True
            return False

class AndPermission(BasePermission):
    def __init__(self,permissions):
        self.permissions = permissions

    def initialize(self):
        for permission in self.permissions:
            permission.initialize()

    def check(self,user):
        for perm in self.permissions:
            if not perm.check(user):
                return False

        return True

class OrPermission(BasePermission):
    def __init__(self,permissions):
        self.permissions = permissions

    def initialize(self):
        for permission in self.permissions:
            permission.initialize()

    def check(self,user):
        for perm in self.permissions:
            if perm.check(user):
                return True

        return False


class GetActionMixin(object):
    def get_action(self,action_name):
        return BUTTON_ACTIONS.get(action_name) or OPTION_ACTIONS.get(action_name)


class DynamicAction(Action):
    def __init__(self,action,extra_attrs):
        self.action = action
        self.extra_attrs = extra_attrs

    def clone(self):
        raise NotImplementedError("Not Implemented")

    @property
    def has_permission(self):
        return self.action.has_permission

    @property
    def widget(self):
        return self.action.widget

    @property
    def basehtml(self):
        return self.html()

    @property
    def tag_attrs(self):
        return self.action.tag_attrs

    def html(self,value = "",**kwargs):
        value = value or ""
        if value == self.action.action:
            return self.widget.render("selected=\"selected\" {}".format(self.extra_attrs))
        else:
            return self.widget.render(self.extra_attrs)

BUTTON_ACTIONS = {
    "save":Action("save","button","Save",{"class":"btn btn-primary btn-success","type":"submit"}),
    "select":Action("select","button","Select",{"class":"btn btn-primary btn-success","type":"submit",}),
    "cancel":Action("cancel","a","Cancel",{
        "class":"btn btn-danger",
        "onclick":lambda nexturl: "window.location='{}';".format(nexturl) if nexturl else "history.go(-1);" 
    }),
    "upload":Action("upload","button","Upload",{"class":"btn btn-success","type":"submit"}),
    "download":Action("download","button","Download",{"class":"btn btn-success btn-block","type":"submit","style":"width:260px"}),
    "deleteconfirm":Action("delete","button","Delete",{"class":"btn btn-success btn-block","type":"submit","style":"width:260px"}),
    "deleteconfirmed":Action("deleteconfirm","button","Yes,I'm sure",{"class":"btn btn-success btn-block","type":"submit","style":"width:260px"}),
    "archiveconfirm":Action("archive","button","Archive",{"class":"btn btn-success btn-block","type":"submit","style":"width:260px"}),
    "archiveconfirmed":Action("archiveconfirm","button","Archive",{"class":"btn btn-success btn-block","type":"submit","style":"width:260px"}),
    "close":Action("close","button","Close",{"class":"btn btn-success","type":"submit"}),
    "update_filter":Action("search","button","Update",{"class":"btn btn-success btn-block","type":"submit","style":"width:100px"}),
}
OPTION_ACTIONS = {
    "empty_action":Action("","option","----------"),
    "delete_selected_documents":Action("deleteconfirm","option","Delete selected documents",permission="prescription.delete_prescription"),
    "archive_selected_documents":Action("archiveconfirm","option","Archive selected documents",permission="document.archive_document"),
}

@receiver(django_inited)
def initialize_actions(sender,**kwargs):
    for action in BUTTON_ACTIONS.values():
        action.initialize()

    for action in OPTION_ACTIONS.values():
        action.initialize()

    actions_inited.send(sender="actions")
