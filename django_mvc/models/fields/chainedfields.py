import django

try:
    from smart_selects import db_fields
except Exception as ex:
    from django_mvc.utils import class_not_imported
    db_fields = class_not_imported("smart_selects",ex)

class ChainedForeignKey(db_fields.ChainedForeignKey):
    """
    Require django-smart-selects>=1.5.4
    A enhanced ChainedForeignKey to support 'limit_choices_to' to be configured as a callable object 
    """
    def formfield(self, **kwargs):
        if callable(self.remote_field.limit_choices_to):
            self.remote_field.limit_choices_to = self.remote_field.limit_choices_to()

        return super(ChainedForeignKey,self).formfield(**kwargs)
