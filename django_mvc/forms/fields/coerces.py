
def coerce_TrueFalse(value):
    if value is None or value == '':
        return None
    if isinstance(value,str):
        return value == "True"
    return value

def coerce_YesNo(value):
    if value is None or value == '':
        return None
    if isinstance(value,basestring):
        return value == "Yes"
    return value

def coerce_int(value):
    if value is None or value == '':
        return None
    return int(value)


