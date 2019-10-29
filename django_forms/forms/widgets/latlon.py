try:
    import LatLon
except Exception as ex:
    from django_forms.utils import object_not_imported
    LatLon = object_not_imported("LatLon",ex)

from .widgets import DisplayWidget

class DmsCoordinateDisplay(DisplayWidget):
    def render(self,name,value,attrs=None,renderer=None):
        if value:
            c=LatLon.LatLon(LatLon.Longitude(value.get_x()), LatLon.Latitude(value.get_y()))
            latlon = c.to_string('d% %m% %S% %H')
            lon = latlon[0].split(' ')
            lat = latlon[1].split(' ')
        
            # need to format float number (seconds) to 1 dp
            lon[2] = str(round(eval(lon[2]), 1))
            lat[2] = str(round(eval(lat[2]), 1))
        
            # Degrees Minutes Seconds Hemisphere
            lat_str = lat[0] + u'\N{DEGREE SIGN} ' + lat[1].zfill(2) + '\' ' + lat[2].zfill(4) + '\" ' + lat[3]
            lon_str = lon[0] + u'\N{DEGREE SIGN} ' + lon[1].zfill(2) + '\' ' + lon[2].zfill(4) + '\" ' + lon[3]
        
            return 'Lat/Lon ' + lat_str + ', ' + lon_str
        else:
            return ""

