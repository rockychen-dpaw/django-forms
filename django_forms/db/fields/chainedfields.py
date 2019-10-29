import django

import smart_selects

class ChainedForeignKey(smart_selects.db_fields.ChainedForeignKey):
    def formfield(self, **kwargs):
        if django.VERSION < (2, 0):
            if callable(self.rel.limit_choices_to):
                self.rel.limit_choice_to = self.rel.limit_choice_to()

        else:
            if callable(self.remote_field.limit_choices_to):
                self.remote_field.limit_choices_to = self.remote_field.limit_choices_to()

        return super(ChainedForeignKey,self).formfield(**kwargs)
