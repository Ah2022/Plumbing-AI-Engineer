"""Finite SI data and source-aware screening helpers; no implicit code limits."""
import math

G=9.80665


def fields(row,allowed):
    if not isinstance(row,dict):raise ValueError('Engineering inputs must be objects')
    extra=set(row)-set(allowed.split())
    if extra:raise ValueError('Unsupported input fields: '+', '.join(sorted(extra)))


def num(row,key,*,minimum=None,positive=False,maximum=None):
    value=row.get(key)
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):raise ValueError(key+' must be finite numeric data')
    if positive and value<=0 or minimum is not None and value<minimum or maximum is not None and value>maximum:raise ValueError(key+' is outside its supported range')
    return value


def text(row,key):
    value=row.get(key)
    if not isinstance(value,str) or not value.strip():raise ValueError(key+' is required')
    return value.strip()


def flag(row,key):
    if type(row.get(key)) is not bool:raise ValueError(key+' must be explicitly true or false')
    return row[key]


def rows(data,key,*,empty=False,limit=1000):
    values=data.get(key)
    if not isinstance(values,list) or not empty and not values or len(values)>limit or not all(isinstance(r,dict) for r in values):raise ValueError(key+' must be a bounded list of records')
    return values


def unique(values,key='id'):
    ids=[text(r,key) for r in values]
    if len(ids)!=len(set(ids)):raise ValueError('Duplicate '+key)


def check(identity,okay,actual,limit,unit,reference):
    return dict(check=identity,status='PASS' if okay else 'FAIL',actual=actual,limit=limit,unit=unit,source_id=reference)


def result(values,units,checks=None,trace=None,*,complete=True,notes=None):
    if set(values)!=set(units):raise ValueError('Every engineering result must declare its unit')
    return dict(values=values,units=units,checks=checks or [],trace=trace or [],complete=complete,notes=notes or [])


def interpolate(points,x,xkey,ykey):
    if x<points[0][xkey] or x>points[-1][xkey]:raise ValueError('Requested value is outside the supplied source curve; extrapolation is not allowed')
    for a,b in zip(points,points[1:]):
        if a[xkey]<=x<=b[xkey]:
            return a[ykey]+(b[ykey]-a[ykey])*(x-a[xkey])/(b[xkey]-a[xkey])
    return points[-1][ykey]
