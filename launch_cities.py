"""Launch catalogue. Only explicitly enabled markets can accept signup."""
CITIES=[
    {'code':'BLR','name':'Bangalore','aliases':['Bengaluru'],'enabled':True},
    {'code':'DEL','name':'Delhi','aliases':['New Delhi'],'enabled':True},
    {'code':'BOM','name':'Mumbai','aliases':['Bombay'],'enabled':True},
    {'code':'HYD','name':'Hyderabad','aliases':[],'enabled':False},
    {'code':'MAA','name':'Chennai','aliases':[],'enabled':False},
    {'code':'CCU','name':'Kolkata','aliases':[],'enabled':False},
    {'code':'PNE','name':'Pune','aliases':[],'enabled':False},
    {'code':'AMD','name':'Ahmedabad','aliases':[],'enabled':False},
]
def active():return [dict(c) for c in CITIES if c['enabled']]
def find(value):
    if not isinstance(value,str):return None
    value=value.strip().casefold()
    return next((dict(c) for c in CITIES if value in [x.casefold() for x in [c['code'],c['name'],*c['aliases']]]),None)
