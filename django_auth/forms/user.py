from django_mvc.actions import (BUTTON_ACTIONS,OPTION_ACTIONS)

from django.contrib.auth.models import (User,)
from django.urls import  reverse

from django_mvc import forms

class UserCleanMixin(object):
    pass

class UserConfigMixin(object):
    class Meta:
        field_classes_config = {
            "__default__":forms.fields.CharField,
            "q":forms.fields.CharField,
            "groupid.filter":forms.fields.IntegerField,
            "username.list":forms.fields.HyperlinkFieldFactory(
                User,
                "username",
                lambda value,form,instance:"{}?nexturl={}".format(reverse("django_auth:user_update",kwargs={"pk":instance.id}),form.quotedfullpath)
            ),
        }
        labels_config = {
            "is_superuser":"",
            "is_active":"",
            "is_superuser.list":"Administrator?",
            "is_active.list":"Active?",
            "q":"Search"
        }
        widgets_config = {
            "__default__.view":forms.widgets.TextDisplay(),
            "__default__.edit":forms.widgets.TextInput(),
            "__default__.filter":forms.widgets.HiddenInput(),
            "q.filter":forms.widgets.TemplateWidgetFactory(forms.widgets.TextInput,"""
                <div class="input-prepend input-append">
                    <span class="add-on"><i class="icon-search"></i></span>
                    {}
                    <button class="btn" type="submit">Search</button>
                </div>
            """)(attrs={"style":"width:160px"}),
            "username.list":forms.widgets.HyperlinkWidget(),
            "is_active.filter":forms.widgets.HiddenInput(),
            "is_active.view":forms.widgets.TemplateWidgetFactory(forms.widgets.ImgBooleanDisplay,"""
            {}<b style="padding-left:15px">Approved User (i.e. enable login for this user?)</b>
            """)(),
            "is_active.list":forms.widgets.ImgBooleanDisplay(),
            "is_active.edit":forms.widgets.TemplateWidgetFactory(forms.widgets.CheckboxInput,"""
            {}<b style="padding-left:15px">Approved User (i.e. enable login for this user?)</b>
            """)(),
            "is_superuser.list":forms.widgets.ImgBooleanDisplay(),
            "is_superuser.view":forms.widgets.TemplateWidgetFactory(forms.widgets.ImgBooleanDisplay,"""
            {}<b style="padding-left:15px">Administrator</b>
            """)(),
            "groupid.filter":forms.widgets.HiddenInput(),
            "groups.view":forms.widgets.ListDisplayFactory(forms.widgets.TextDisplay)(),
            "groups.edit":forms.widgets.TemplateWidgetFactory(forms.widgets.FilteredSelectMultiple,"""
                <span >The groups this user belongs to. A user will get all permissions granted to each of his/her group. Hold down "Control", or "Command" on a Mac, to select more than one.</span>
                {0}
            """)("groups",False),
        }


class UserBaseForm(UserCleanMixin,UserConfigMixin,forms.ModelForm):
    class Meta:
        pass

class UserFilterForm(UserConfigMixin,forms.FilterForm):
    all_buttons = [
        BUTTON_ACTIONS["update_filter"],
    ]

    class Meta:
        model = User
        third_party_model=True
        purpose = ('filter',"view")
        all_fields = ("q","is_active","groupid")

class UserForm(forms.ModelForm):

    def __init__(self, *args, **kwargs):
        super(UserForm, self).__init__(*args, **kwargs)
        self.fields['is_active'].label = ("Approved User (i.e. enable login "
                                          "for this user?)")
        instance = getattr(self, 'instance', None)
        if instance and instance.pk and not instance.profile.is_fpc_user():
            self.fields['username'].widget.attrs['readonly'] = True
            self.fields['email'].widget.attrs['readonly'] = True
            self.fields['first_name'].widget.attrs['readonly'] = True
            self.fields['last_name'].widget.attrs['readonly'] = True

    class Meta:
        model = User
        third_party_model=True
        all_fields = ('is_active', 'groups')

class UserEditForm(UserBaseForm):
    all_buttons = [
        BUTTON_ACTIONS["update_user"],
        BUTTON_ACTIONS["cancel"]
    ]

    class Meta:
        model = User
        third_party_model=True
        purpose = ('edit',"view")
        all_fields = ('username', 'email',"first_name","last_name","is_superuser","is_active","groups")
        editable_fields = ["is_active","groups"]


class UserViewForm(UserEditForm):
    all_buttons = [
        BUTTON_ACTIONS["cancel"]
    ]
    class Meta:
        model = User
        third_party_model=True
        editable_fields = []

class UserBaseListForm(UserConfigMixin,forms.ListForm):
    class Meta:
        purpose = (None,('list','view'))

class UserListForm(UserBaseListForm):
    def __init__(self, *args, **kwargs):
        super(UserListForm, self).__init__(*args, **kwargs)

    class Meta:
        model = User
        third_party_model=True
        columns_attrs = {
        }
        all_fields = ("username","email","first_name","last_name","is_active","is_superuser")
        
        editable_fields = []


