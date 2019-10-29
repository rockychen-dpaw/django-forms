import re
from collections import OrderedDict

import django.apps
from django.db import models
from django.template import (Template,Context)
from django.core.exceptions import (ObjectDoesNotExist,)
from django.utils.html import mark_safe
from django.db import transaction

from django_forms.forms.widgets import DisplayWidget

HTML_TABLE = 1
STRING = 2

indent = {
    HTML_TABLE : 10,
    STRING : "  ",
}

# test prescription 988
class ProtectStatusMixin(object):
    UNTOUCHED = 1

    DELETE = 2
    DELETE_REL = 4
    UPDATE_REL = 8

    PROTECTED = 16
    PROTECTED_BY_PARENTS = 32
    PROTECTED_BY_CHILDREN = 64

    ALL_PROTECTED_STATUS = PROTECTED | PROTECTED_BY_PARENTS | PROTECTED_BY_CHILDREN

    PROTECT_STATUS_DESC = OrderedDict([
        (UNTOUCHED , "Untouched"),
        (DELETE, "Delete"),
        (DELETE_REL,"Delete Relationship"),
        (UPDATE_REL,"Update Relationship"),
        (PROTECTED,"Protected"),
        (PROTECTED_BY_PARENTS,"Protected By Parents"),
        (PROTECTED_BY_CHILDREN,"Protected By Children")

    ])

    PROTECT_STATUS_ICON = OrderedDict([
        (UNTOUCHED , None),
        (DELETE, None),
        (DELETE_REL,None),
        (UPDATE_REL,None),
        (PROTECTED_BY_PARENTS,"<img src='/static/img/protected_by_parents.png' style='padding-left:5px'>"),
        (PROTECTED,"<img src='/static/img/protected.png' style='padding-left:5px'>"),
        (PROTECTED_BY_CHILDREN,"<img src='/static/img/protected_by_children.png' style='padding-left:5px'>")
    ])
    protect_status = 0

    @property
    def protect_status_desc(self):
        return self.get_protect_status_desc(self.protect_status)
        
    def get_protect_status_desc(self,status):
        return " , ".join([value for key,value in self.PROTECT_STATUS_DESC.items() if key & status == key])

    @property
    def is_protected(self):
        return self.protect_status & self.ALL_PROTECTED_STATUS > 0

    @property
    def protect_status_icon(self):
        output = "".join([icon for key,icon in self.PROTECT_STATUS_ICON.items() if icon and key & self.protect_status == key])
        if output:
            return output
        else:
            return "&nbsp;"

class ModelRelationshipTree(object):
    relationship_trees = {}
    status = "wait_initialize"

    CASCADE = 1
    PROTECT = 2
    SET_NULL = 3
    SET_DEFAULT = 4
    SET = 5
    DELETE_REL = 6

    def __new__(cls,model):
        try:
            return cls.relationship_trees[model]
        except:
            if cls.status == "wait_initialize":
                cls.load_relationship_trees()
                return cls.relationship_trees[model]
            if cls.status == "initializing":
                instance = super().__new__(cls)
                instance.model = None
                cls.relationship_trees[model] = instance
                return instance
            elif cls.status == "initialized":
                raise Exception("Model ({}.{}) Not Found.".format(model.__module__,model.__name__))
            else:
                raise Exception("Please initialize dependency tree first")

    def __init__(self,model):
        if self.model:
            return

        self.model = model
        self.modelname = "{}.{}".format(self.model.__module__,self.model.__name__)
        self.tablename = self.model._meta.db_table

        self.many2many_rels = []
        self.one2one_rels = []
        self.one2many_rels = []

    @classmethod
    def deletepolicy(cls,policy):
        if policy == models.PROTECT:
            return cls.PROTECT
        elif policy == models.SET:
            return cls.SET
        elif policy == models.SET_NULL:
            return cls.SET_NULL
        elif policy == models.SET_DEFAULT:
            return cls.SET_DEFAULT
        elif policy == models.CASCADE:
            return cls.CASCADE

    @classmethod
    def load_relationship_trees(cls):
        if cls.status in ("initializing","initialized"):
            return
        cls.status = "initializing"
        rel_tree = None
        remote_rel_tree = None
        protect_status = None
        delpolicy = None
        #inspect all dependency relationship_trees
        for model in django.apps.apps.get_models():
            rel_tree = ModelRelationshipTree(model)
            for fields in (model._meta.fields,model._meta.local_many_to_many):
                for field in fields:
                    if isinstance(field,models.ManyToManyField):
                        rel_tree.many2many_rels.append((ModelRelationshipTree(field.remote_field.model),field.name,cls.DELETE_REL))
                        remote_rel_tree = ModelRelationshipTree(field.remote_field.model)
                        if field.remote_field.related_name:
                            related_name = field.remote_field.related_name
                        else:
                            related_name = "{}_set".format(model.__name__.lower())
                        remote_rel_tree.many2many_rels.append((rel_tree,related_name,cls.DELETE_REL))
                    elif isinstance(field,models.OneToOneField):
                        remote_rel_tree = ModelRelationshipTree(field.remote_field.model)
                        remote_rel_tree.one2one_rels.append((rel_tree,field.name,cls.deletepolicy(field.remote_field.on_delete)))
                    elif isinstance(field,models.ForeignKey):
                        remote_rel_tree = ModelRelationshipTree(field.remote_field.model)
                        remote_rel_tree.one2many_rels.append((rel_tree,field.name,cls.deletepolicy(field.remote_field.on_delete)))

        for model,rel_tree in cls.relationship_trees.items():
            rel_tree.relationships = len(rel_tree.many2many_rels) + len(rel_tree.one2one_rels) + len(rel_tree.one2many_rels)

        cls.status = "initialized"

    def verbose_name(self,plural):
        if isinstance(plural,int):
            return self.model._meta.verbose_name_plural if plural > 1 else self.model._meta.verbose_name
        else:
            return self.model._meta.verbose_name_plural if plural else self.model._meta.verbose_name

    @property
    def is_leaf(self):
        return self.relationships == 0

    def __str__(self):
        return self.modelname

class ModelDependencyTree(ProtectStatusMixin):
    dependency_trees = {}
    status = "wait_initialize"

    template = Template("""
{% load pbs_utils %}
{% if level == 0 %}
-------------------------------------------------------------------------------------------------------------------------------------------
{% endif %}

{{level_indent}}{{tree.modelname}} {% if level > 0 %}({{tree.field}}) {% endif %}\t\t({{tree.protect_status_desc}})

{% if tree.many2many_subtrees %}
{{level_indent}}{{indents.0}}{{tree.many2many_subtrees|length}} ManyToMany dependencies.
{% for subtree in tree.many2many_subtrees %}
{{level_indent}}{{indents.1}}{{subtree.modelname}} {{subtree.field}}\t\t({{subtrees.0.protect_status_desc}})
{% endfor %}
{% endif %}

{% if tree.one2one_subtrees %}
{{level_indent}}{{indents.0}}{{tree.one2one_subtrees|length}} OneToOne dependencies.
{% for subtree in tree.one2one_subtrees %}
{% call_method subtree "render" next_level %}
{% endfor %}
{% endif %}

{% if tree.one2many_subtrees %}
{{level_indent}}{{indents.0}}{{tree.one2many_subtrees|length}} OneToMany dependencies.
{% for subtree in tree.one2many_subtrees %}
{% call_method subtree "render" next_level %}
{% endfor %}
{% endif %}
""")

    indent = "  "

    PARENT = 1
    ITSELF = 2
    CHILDREN = 3

    def __new__(cls,model,parent_tree=None,field=None,delete_policy=None):
        try:
            if parent_tree is None:
                #only cache the root model
                return cls.dependency_trees[model]
            else:
                #print("  Load subdependency tree for model ({}.{}),root model is ({})".format(model.__module__,model.__name__,parent_tree.modelname))
                instance = super().__new__(cls)
                instance.rel_tree = None
                return instance
        except:
            if cls.status == "wait_initialize":
                cls.load_trees()
                return cls.dependency_trees[model]
            if cls.status == "initializing":
                instance = super().__new__(cls)
                #print("Begin to load dependency tree for model ({}.{})".format(model.__module__,model.__name__))
                instance.rel_tree = None
                cls.dependency_trees[model] = instance
                return instance
            elif cls.status == "initialized":
                raise Exception("Model ({}.{}) Not Found.".format(model.__module__,model.__name__))
            else:
                raise Exception("Please initialize dependency tree first")

    def __init__(self,model,parent_tree=None,field=None,delete_policy=None):
        if self.rel_tree:
            return

        self.protect_status = None
        self.protect_status_merge_position = None
        self.parent_tree = parent_tree
        if self.parent_tree:
            self.root_tree = self.parent_tree
            while self.root_tree.parent_tree:
                self.root_tree = self.root_tree.parent_tree
            if self.parent_tree.delete_policy_chain:
                self.delete_policy_chain = self.parent_tree.delete_policy_chain + [delete_policy]
            else:
                self.delete_policy_chain = [delete_policy]
        else:
            self.root_tree = self
            self.delete_policy_chain = None

        self.field = field
        self.rel_tree = ModelRelationshipTree(model)

        self.initialize()

    @property
    def delete_policy(self):
        if self.delete_policy_chain:
            return self.delete_policy_chain[-1]
        else:
            return None

    @property
    def is_root(self):
        return self.parent_tree is None

    def verbose_name(self,plural):
        return self.rel_tree.verbose_name(plural)

    @property
    def model(self):
        return self.rel_tree.model

    @property
    def modelname(self):
        return self.rel_tree.modelname

    @property
    def tablename(self):
        return self.rel_tree.tablename

    @classmethod
    def load_trees(cls):
        if cls.status in ("initializing","initialized"):
            return
        cls.status = "initializing"

        for model in django.apps.apps.get_models():
            tree  = ModelDependencyTree(model)

    def merge_protect_status(self,status,position):
        """
        Must merge protect status from upstream to downstream
        """
        if self.protect_status_merge_position is None:
            self.protect_status_merge_position = position
        elif self.protect_status_merge_position == self.PARENT:
            if position == self.PARENT:
                pass
            elif position == self.ITSELF:
                self.protect_status_merge_position = position
            else:
                raise Exception("Current merge position is PARENT, next merge positon can't be CHILDREN")
        elif self.protect_status_merge_position == self.ITSELF:
            if position == self.PARENT:
                raise Exception("Current merge position is ITSELF, next merge positon can't be PARENT")
            elif position == self.ITSELF:
                raise Exception("Current merge position is ITSELF, next merge positon can't be ITSELF")
            else:
                self.protect_status_merge_position = position
        elif self.protect_status_merge_position == self.CHILDREN:
            if position == self.PARENT:
                raise Exception("Current merge position is CHILDREN, next merge positon can't be PARENT")
            elif position == self.ITSELF:
                raise Exception("Current merge position is CHILDREN, next merge positon can't be ITSELF")
            else:
                pass
        else :
            raise Exception("Position({}) Not Supported".format(self.protect_status_merge_position))

        if self.protect_status_merge_position == self.CHILDREN:
            #merge child protect status, 
            #only care about 'protected by children'
            if status & self.PROTECTED == self.PROTECTED:
                status = self.PROTECTED_BY_CHILDREN
            else:
                status = 0

        if self.protect_status is None or self.protect_status == 0:
            self.protect_status = status
        elif self.protect_status == self.UNTOUCHED:
            #all downsteam objects and relationships will be reserved if protect status is UNTOUCHED
            pass
        elif self.protect_status == self.DELETE:
            self.protect_status = status
        elif self.protect_status & self.DELETE_REL == self.DELETE_REL:
            #the upstream relationship is deleted, all downstream objects and relationships will be reserved
            self.protect_status = self.UNTOUCHED
        elif self.protect_status & self.UPDATE_REL == self.UPDATE_REL:
            #the upstream relationship is updated, all downstream objects and relationships will be reserved
            self.protect_status = self.UNTOUCHED
        elif self.protect_status & self.PROTECTED_BY_PARENTS == self.PROTECTED_BY_PARENTS:
            if status == self.UNTOUCHED:
                raise Exception("The immediate downstream protect status can't be UNTOUCHED, if current protect status has PROTECTED BY PARENTS")
            elif status == self.DELETE:
                pass
            elif status == self.DELETE_REL:
                self.protect_status = self.DELETE_REL
            elif status == self.UPDATE_REL:
                self.protect_status = self.UPDATE_REL
            elif status & self.PROTECTED_BY_PARENTS == self.PROTECTED_BY_PARENTS:
                pass
            elif status & self.PROTECTED == self.PROTECTED:
                self.protect_status = self.protect_status | self.PROTECTED
            elif status & self.PROTECTED_BY_CHILDREN == self.PROTECTED_BY_CHILDREN:
                self.protect_status = self.protect_status | self.PROTECTED_BY_CHILDREN
        elif self.protect_status & self.PROTECTED == self.PROTECTED:
            if status & (self.PROTECTED_BY_CHILDREN | self.PROTECTED) > 0:
                self.protect_status = self.protect_status | self.PROTECTED_BY_CHILDREN
        elif self.protect_status & self.PROTECTED_BY_CHILDREN == self.PROTECTED_BY_CHILDREN:
            pass
        else:
            raise Exception("Can't merge current status({}) with status({})".format(self.protect_status_desc,self.get_protect_status_desc(status)))


    @classmethod
    def map_protect_status(cls,delete_policy,position):
        if delete_policy in [ModelRelationshipTree.SET,ModelRelationshipTree.SET_NULL,ModelRelationshipTree.SET_DEFAULT]:
            return cls.UPDATE_REL
        elif delete_policy == ModelRelationshipTree.DELETE_REL:
            return cls.DELETE_REL
        elif delete_policy == ModelRelationshipTree.CASCADE:
            return cls.DELETE
        elif delete_policy == ModelRelationshipTree.PROTECT:
            return cls.PROTECTED_BY_PARENTS if position == cls.PARENT else (cls.PROTECTED if position == cls.ITSELF else cls.PROTECTED_BY_CHILDREN)
        else:
            raise Exception("Delete policy ({}) not support".format(delete_policy))

    def initialize(self):
        self.many2many_subtrees = []
        self.one2one_subtrees = []
        self.one2many_subtrees = []

        #get the initial protect status from delete policy chain
        if not self.delete_policy_chain:
            #this is the root object,except it is protected by children
            self.protect_status = self.DELETE
        else:
            for policy in self.delete_policy_chain[:-1]:
                self.merge_protect_status(self.map_protect_status(policy,self.PARENT),self.PARENT)
            self.merge_protect_status(self.map_protect_status(self.delete_policy_chain[-1],self.ITSELF),self.ITSELF)

        if self.delete_policy == self.rel_tree.DELETE_REL:
            #parent model has a many2many relationship with current model, stop to inspect current model's many2many relationships
            pass
        else:
            #process many2many
            for rel in self.rel_tree.many2many_rels:
                tree = ModelDependencyTree(rel[0].model,parent_tree=self,field=rel[1],delete_policy=rel[2])
                self.merge_protect_status(tree.protect_status,self.CHILDREN)
                self.many2many_subtrees.append(tree)
            

        #process one2one
        for rel in self.rel_tree.one2one_rels:
            tree = ModelDependencyTree(rel[0].model,parent_tree=self,field=rel[1],delete_policy=rel[2])
            self.merge_protect_status(tree.protect_status,self.CHILDREN)
            self.one2one_subtrees.append(tree)

        #process one2many
        for rel in self.rel_tree.one2many_rels:
            tree = ModelDependencyTree(rel[0].model,parent_tree=self,field=rel[1],delete_policy=rel[2])
            self.merge_protect_status(tree.protect_status,self.CHILDREN)
            self.one2many_subtrees.append(tree)

    @property
    def is_leaf(self):
        return self.rel_tree.is_leaf

    @property
    def has_dependency(self):
        return self.one2one_subtrees or self.one2many_subtrees or self.many2many_subtrees


    def __str__(self):
        return "{}.{}".format(self.modelname,self.field)

    @property
    def html(self):
        return ModelDependencyTreeTableWidget().render(self.modelname,self)

    empty_line_re= re.compile('\n(\s*\n)+')
    @property
    def print(self):
        output = self.render()
        return self.empty_line_re.sub("\n",output)

    def render(self,level=0):
        level_indent = "" if level == 0 else (self.indent * (level * 2))
        indents = [self.indent * i for i in [1,2,3]]

        context = Context({"tree":self,"level":level,"next_level":level + 1,"level_indent":level_indent,"indents":indents})
        return self.template.render(context)


class ObjectDependencyTree(ProtectStatusMixin):
    template = Template("""
{% load pbs_utils %}
{% if level == 0 %}
-------------------------------------------------------------------------------------------------------------------------------------------
{% endif %}

{{level_indent}}{{tree.modelname}} ({{tree.pk}})\t\t({{tree.protect_status_desc}})

{% if tree.many2many_subtrees %}
{{level_indent}}{{indents.0}}{{tree.many2many_subtrees|length}} ManyToMany dependencies.
{% for subtrees in tree.many2many_subtrees %}
{{level_indent}}{{indents.1}}{{subtrees.0.modelname}} {{subtrees.0.field}}\t\t({{subtrees.0.protect_status_desc}})
    {% for subtree in subtrees.1 %}
{{level_indent}}{{indents.2}}{{subtree.pk}} - {{subtree}}
    {% endfor %}
{% endfor %}
{% endif %}

{% if tree.one2one_subtrees %}
{{level_indent}}{{indents.0}}{{tree.one2one_subtrees|length}} OneToOne dependencies.
{% for subtree in tree.one2one_subtrees %}
{{level_indent}}{{indents.1}}{{subtree.0.modelname}} {{subtree.0.field}}\t\t({{subtree.0.protect_status_desc}})
{% call_method subtree.1 "render" next_level %}
{% endfor %}
{% endif %}

{% if tree.one2many_subtrees %}
{{level_indent}}{{indents.0}}{{tree.one2many_subtrees|length}} OneToMany dependencies.
{% for subtrees in tree.one2many_subtrees %}
{{level_indent}}{{indents.1}}{{subtrees.0.modelname}} {{subtrees.0.field}}\t\t({{subtrees.0.protect_status_desc}})
    {% for subtree in subtrees.1 %}
{% call_method subtree "render" next_level %}
    {% endfor %}
{% endfor %}
{% endif %}
""")

    indent = "  "

    def __init__(self,obj,model_tree=None,exclude_many2many=True,exclude_unprotected=True):
        self.obj = obj
        self.exclude_many2many = exclude_many2many
        self.exclude_unprotected = exclude_unprotected
        self.model_tree = model_tree or ModelDependencyTree(obj.__class__)
        self.loaded = False
        self.protect_status = self.model_tree.protect_status
        self.load_tree()

    def load_tree(self,enforce=False):
        if self.loaded and not enforce:
            return
        self.many2many_subtrees = []
        self.one2one_subtrees = []
        self.one2many_subtrees = []

        child_protect_status = 0

        #if self.modelname == "pbs.implementation.models.Way":
        #    import ipdb;ipdb.set_trace()
        if not self.exclude_many2many:
            for subtree in self.model_tree.many2many_subtrees:
                objlist = getattr(self.obj,subtree.field).all().order_by("pk")
                if objlist:
                    #print("load many2many object {} {}".format(field[0].modelname,objlist))
                    self.many2many_subtrees.append((subtree,objlist))

        for subtree in self.model_tree.one2one_subtrees:
            if self.exclude_unprotected and not subtree.is_protected:
                #unprotected, ignore
                continue
            try:
                obj = subtree.model.objects.get(**{subtree.field:self.obj})
                obj_dependency_tree = ObjectDependencyTree(obj,model_tree=subtree,exclude_many2many=self.exclude_many2many,exclude_unprotected=self.exclude_unprotected) 
                #print("load one2one object {}({})".format(obj_dependency_tree.modelname,obj_dependency_tree.obj.pk))
                self.one2one_subtrees.append( (subtree,obj_dependency_tree) ) 
                child_protect_status = child_protect_status | obj_dependency_tree.protect_status
            except ObjectDoesNotExist as ex:
                pass

        for subtree in self.model_tree.one2many_subtrees:
            if self.exclude_unprotected and not subtree.is_protected:
                #unprotected, ignore
                continue
            sub_dependency_trees = []
                #print("Begin to load one2many objects {}.{}".format(field[0].modelname,field[1]))
            for obj in subtree.model.objects.filter(**{subtree.field:self.obj}).order_by("pk"):
                obj_dependency_tree = ObjectDependencyTree(obj,model_tree=subtree,exclude_many2many=self.exclude_many2many,exclude_unprotected=self.exclude_unprotected) 
                #print("load one2many object {}({})".format(obj_dependency_tree.modelname,obj_dependency_tree.obj.pk))
                sub_dependency_trees.append(obj_dependency_tree)
                child_protect_status = child_protect_status | obj_dependency_tree.protect_status
            if sub_dependency_trees:
                self.one2many_subtrees.append((subtree,sub_dependency_trees))

        if self.protect_status & self.PROTECTED_BY_CHILDREN == self.PROTECTED_BY_CHILDREN:
            if child_protect_status & (self.PROTECTED | self.PROTECTED_BY_CHILDREN) == 0:
                self.protect_status -= self.PROTECTED_BY_CHILDREN

        self.loaded = True

    @property
    def modelname(self):
        return self.model_tree.modelname

    @property
    def tablename(self):
        return self.model_tree.tablename

    @property
    def has_dependency(self):
        return self.one2one_subtrees or self.one2many_subtrees or self.many2many_subtrees

    @property
    def pk(self):
        return self.obj.pk

    def render(self,level=0):
        level_indent = "" if level == 0 else (self.indent * (level * 3))
        indents = [self.indent * i for i in [1,2,3]]

        context = Context({"tree":self,"level":level,"next_level":level + 1,"level_indent":level_indent,"indents":indents})
        return self.template.render(context)

    @property
    def html(self):
        return ObjectDependencyTreeTableWidget().render("{}({})".format(self.modelname,self.pk),self)

    def _delete(self):
        #delete protected relationship first
        if self.protect_status & self.PROTECTED_BY_CHILDREN == self.PROTECTED_BY_CHILDREN:
            #protected by children
            #delete protected onetoone relationship
            for subtree in self.one2one_subtrees:
                if subtree[1].protect_status & (self.PROTECTED |self.PROTECTED_BY_CHILDREN) > 0: 
                    #protected or  indirect protected
                    subtree[1]._delete()

            #delete protected onetomany relationship
            for subtree in self.one2many_subtrees:
                if subtree[0].protect_status & (self.PROTECTED |self.PROTECTED_BY_CHILDREN) > 0: 
                    #protected or  indirect protected
                    for tree in subtree[1]:
                        if tree.protect_status & (self.PROTECTED |self.PROTECTED_BY_CHILDREN) > 0: 
                            tree._delete()

        if self.protect_status & self.PROTECTED == self.PROTECTED:
            #print("Delete protected object {}({})".format(self.modelname,self.pk))
            self.obj.delete()

    def delete(self):
        with transaction.atomic():
            self._delete()
            self.obj.delete()

    empty_line_re= re.compile('\n(\s*\n)+')
    @property
    def print(self):
        output = self.render()
        return self.empty_line_re.sub("\n",output)

    def __str__(self):
        return "{}({})".format(self.modelname,self.pk)


class ModelDependencyTreeTableWidget(DisplayWidget):
    template = Template("""
{% load pbs_utils %}
<table id="{{path}}_table_" style="width:100%;">
<thead id="{{path}}_head_">
    <tr>
    {% if tree.has_dependency %}
        <th >
        <span style="padding-right:10px;">
            <i style='cursor:pointer' class='{% if widget.expandlevel >= level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_body_")'></i>
            {{ tree.protect_status_icon|safe }}
        </span>
        {{tree.modelname}} {% if level == 0 %} Dependency Tree{% endif %}
        </th>
    {% else %}
        <td>
        <span style="padding-right:10px;">
            {{ tree.protect_status_icon|safe }}
        </span>
        {{tree.modelname}} 
        </td>
    {% endif %}
    </tr>
</thead>

<tbody {% if widget.expandlevel < level%}style="display:none"{% endif %} id="{{path}}_body_">
{% if tree.many2many_subtrees %}
<tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
<table id="{{path}}_m2m" style="width:100%">
    <thead><tr><th>
        <span style='padding-right:10px'>
            <i style='cursor:pointer' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_m2m_body_")'></i>
        </span>
        {{tree.many2many_subtrees|length}} ManyToMany dependencies
    </th></tr></thead>
    <tbody {% if widget.expandlevel <= level%}style="display:none"{% endif %} id="{{path}}_m2m_body_">
    {% for subtree in tree.many2many_subtrees %}
    <tr><td style="padding-left:{{widget.indent}}px;">
        <span style="padding-left:10px;padding-right:10px;">
        {{subtree.modelname}} {{subtree.field}}  
        </span>
    </td></tr>
    {% endfor %}
    </tbody>
</table>
</tr></td>
{% endif %}

{% if tree.one2one_subtrees %}
<tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
<table id="{{path}}_o2o_table_" style="width:100%">
    <thead><tr><th>
        <span style="padding-right:10px">
            <i style='cursor:pointer' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_o2o_body_")'></i>
        </span>
        {{tree.one2one_subtrees|length}} OneToOne dependencies
    </th></tr></thead>
    <tbody id="{{path}}_o2o_body_" {% if widget.expandlevel <= level%}style="display:none"{% endif %}>
    {% setvar path "_o2o_" as subpath %}
    {% for subtree in tree.one2one_subtrees %}
    <tr><td style="padding:0px 0px 0px {{widget.indent}}px;" >
        {% call_method widget "_render" subtree next_level path=subpath %}
    </td></tr>
    {% endfor %}
    </tbody>
</table>
</tr></td>
{% endif %}

{% if tree.one2many_subtrees %}
<tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
<table id="{{path}}_o2m" style="width:100%">
    <thead><tr><th>
        <span style="padding-right:10px">
            <i style='cursor:pointer' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_o2m_body_")'></i>
        </span>
        {{tree.one2many_subtrees|length}} OneToMany dependencies
    </th>
    </tr></thead>
    <tbody id="{{path}}_o2m_body_" id="{{path}}_o2o_{{subtree.0.0.tablename}}_{{subtree.0.1}}" {% if widget.expandlevel <= level%}style="display:none"{% endif %}>
    {% setvar path "_o2m_" as subpath %}
    {% for subtree in tree.one2many_subtrees %}
    <tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
        {% call_method widget "_render" subtree next_level path=subpath %}
    </td></tr>
    {% endfor %}
    </tbody>
</table>
</tr></td>
{% endif %}

</tbody>
</table>
""")

    indent = 15
    #level_indent = lambda level,padding_left: padding_left if level == 0 else (indent * (level * 3) + padding_left)
    empty_line_re = re.compile('\n(\s*\n)+')
    #level is based 0
    expandlevel = 0

    def render(self,name,value,attrs=None,renderer=None):
        output = self._render(value)
        #output = self.empty_line_re.sub("\n",output)
        return mark_safe(output)
        
    def _render(self,tree,level=0,path=None):
        if path:
            path = "{}__{}_{}".format(path,tree.tablename,tree.field)
        else:
            path = "{}_{}".format(tree.tablename,tree.field)

        context = Context({"widget":self,"tree":tree,"level":level,"next_level":level + 1,"path":path})
        return self.template.render(context)

class ObjectDependencyTreeTableWidget(DisplayWidget):
    template = Template("""
{% load pbs_utils %}
<table id="{{path}}_table_" style="width:100%;">
<thead id="{{path}}_head_">
    <tr>
    {% if tree.has_dependency %}
        <th >
        <span style="padding-right:10px;">
            <i style='cursor:pointer' class='{% if widget.expandlevel >= level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_body_")'></i>
            {{ tree.protect_status_icon|safe }}
        </span>
        {{tree.modelname}} ({{tree.pk}}) : {{tree.obj}}{% if level == 0 %} Dependency Tree{% endif %}
        </th>
    {% else %}
        <td>
        <span style="padding-right:10px;">
            {{ tree.protect_status_icon|safe }}
        </span>
        {{tree.modelname}} ({{tree.pk}}) : {{tree.obj}} 
        </td>
    {% endif %}
    </tr>
</thead>

<tbody {% if widget.expandlevel < level%}style="display:none"{% endif %} id="{{path}}_body_">
{% if tree.many2many_subtrees %}
<tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
<table id="{{path}}_m2m" style="width:100%">
    <thead><tr>
    <th>
        <span style='padding-right:10px'>
            <i style='cursor:pointer' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_m2m_body_")'></i>
        </span>
        {{tree.many2many_subtrees|length}} ManyToMany dependencies
    </th>
    </tr></thead>
    <tbody {% if widget.expandlevel <= level%}style="display:none"{% endif %} id="{{path}}_m2m_body_">
    {% for subtrees in tree.many2many_subtrees %}
    <tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
    <table id="{{path}}_m2m_{{subtrees.0.1}}" style="width:100%">
        <thead><tr>
        <th>
            <span style="padding-right:10px">
                <i style='cursor:pointer' class='{% if widget.expandlevel >= level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_m2m_{{subtrees.0.1}}_body_")'></i>
            </span>
            {{subtrees.0.modelname}}.{{subtrees.0.field}}({{subtrees.1|length}})
        </th>
        </tr></thead>
        <tbody id="{{path}}_m2m_{{subtrees.0.tablename}}_{{subtrees.0.field}}_body_">
        {% for obj in subtrees.1 %}
        <tr><td style="padding-left:{{widget.indent}}px">
            {{obj.pk}} - {{obj}}
        </td></tr>
        {% endfor %}
        </tbody>
    </table>
    {% endfor %}
    </tbody>
</table>
</tr></td>
{% endif %}

{% if tree.one2one_subtrees %}
<tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
<table id="{{path}}_o2o_table_" style="width:100%">
    <thead><tr>
        <th>
            <span style="padding-right:10px">
                <i style='cursor:pointer' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_o2o_body_")'></i>
            </span>
            {{tree.one2one_subtrees|length}} OneToOne dependencies
        </th>
    </tr></thead>
    <tbody id="{{path}}_o2o_body_" {% if widget.expandlevel <= level%}style="display:none"{% endif %}>
    {% for subtree in tree.one2one_subtrees %}
    <tr><td style="padding:0px 0px 0px {{widget.indent}}px;" >
    <table id="{{path}}_o2o_{{subtree.0.tablename}}_{{subtree.0.field}}_table_" style="width:100%">
        <thead><tr>
            <th>
                <span style="padding-right:10px;">
                    <i style='cursor:pointer;' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_o2o_{{subtree.0.tablename}}_{{subtree.0.field}}_body_")'></i>
                    {{subtree.0.protect_status_icon|safe}}
                </span>
                {{subtree.0.modelname}}
            </th>
        </tr></thead>
        <tbody id="{{path}}_o2o_{{subtree.0.tablename}}_{{subtree.0.field}}_body_" {% if widget.expandlevel <= level%}style="display:none"{% endif %}>
            <tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
                {% setvar path "_o2o_" subtree.0.tablename "_" subtree.0.field as subpath %}
                {% call_method widget "_render" subtree.1 next_level path=subpath %}
            </td></tr>
        </tbody>
    </table>
    </td></tr>
    {% endfor %}
    </tbody>
</table>
</tr></td>
{% endif %}

{% if tree.one2many_subtrees %}
<tr><td style="padding:0px 0px 0px {{widget.indent}}px;" >
<table id="{{path}}_o2m" style="width:100%">
    <thead><tr>
        <th>
            <span style="padding-right:10px">
                <i style='cursor:pointer' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_o2m_body_")'></i>
            </span>
            {{tree.one2many_subtrees|length}} OneToMany dependencies
        </th>
    </tr></thead>
    <tbody id="{{path}}_o2m_body_" id="{{path}}_o2o_{{subtree.0.0.tablename}}_{{subtree.0.1}}" {% if widget.expandlevel <= level%}style="display:none"{% endif %}>
    {% for subtrees in tree.one2many_subtrees %}
        <tr><td style="padding:0px 0px 0px {{widget.indent}}px;">
            <table id="{{path}}_o2m_{{subtrees.0.tablename}}_{{subtrees.0.field}}_table_" style="width:100%">
            <thead><tr>
                <th>
                    <span style="padding-right:10px">
                        <i style='cursor:pointer;' class='{% if widget.expandlevel > level %}icon-minus{% else %}icon-plus{%endif%}' onclick='expandtree.call(this,"#{{path}}_o2m_{{subtrees.0.tablename}}_{{subtrees.0.field}}_body_")'></i>
                        {{ subtrees.0.protect_status_icon|safe }}
                    </span>
                    {{subtrees.0.modelname}} : {{subtrees.1|length}} {% call_method subtrees.0 "verbose_name" subtrees.1|length %}
                </th>
            </tr></thead>
            <tbody id="{{path}}_o2m_{{subtrees.0.tablename}}_{{subtrees.0.field}}_body_" {% if widget.expandlevel <= level%}style="display:none"{% endif %}>
            {% setvar path "_o2m_" subtrees.0.tablename "_" subtrees.0.field as subpath %}
            {% for subtree in subtrees.1 %}
            <tr><td style="padding:0px 0px 0px {{widget.indent}}px">
                {% call_method widget "_render" subtree next_level path=subpath %}
            </td></tr>
            {% endfor %}
            </tbody>
            </table>
        </td></tr>
    {% endfor %}
    </tbody>
</table>
</tr></td>
{% endif %}

</tbody>
</table>
""")


    indent = 15
    #level_indent = lambda level,padding_left: padding_left if level == 0 else (indent * (level * 3) + padding_left)
    empty_line_re = re.compile('\n(\s*\n)+')
    #level is based 0
    expandlevel = 0

    def render(self,name,value,attrs=None,renderer=None):
        output = self._render(value)
        #output = self.empty_line_re.sub("\n",output)
        return mark_safe(output)
        
    def _render(self,tree,level=0,path=None):
        if path:
            path = "{}__{}".format(path,tree.obj.pk)
        else:
            path = str(tree.obj.pk)

        context = Context({"widget":self,"tree":tree,"level":level,"next_level":level + 1,"path":path})
        return self.template.render(context)

