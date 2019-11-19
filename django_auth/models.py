from django.contrib.auth.models import (User,Group)

for attr,name in (("FMSB","Fire Management Services Branch"),):
    try:
        setattr(Group,attr,Group.objects.get(name=name))
    finally:
        setattr(Group,attr,None)
