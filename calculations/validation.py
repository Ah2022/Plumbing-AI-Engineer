"""Shared physical-domain validation at public calculation boundaries."""
import math
from numbers import Real
from functools import wraps
import json


def finite(name, value, *, minimum=None, maximum=None, positive=False):
    if isinstance(value,bool) or not isinstance(value,Real) or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite number')
    if positive and value <= 0:
        raise ValueError(f'{name} must be positive')
    if minimum is not None and value < minimum:
        raise ValueError(f'{name} must be >= {minimum}')
    if maximum is not None and value > maximum:
        raise ValueError(f'{name} must be <= {maximum}')
    return float(value)


def checked_numeric(function):
    @wraps(function)
    def checked(*args,**kwargs):
        try:
            result=function(*args,**kwargs)
            if isinstance(result,Real): finite('conversion result',result)
            elif isinstance(result,(dict,list)): json.dumps(result,allow_nan=False)
            return result
        except ArithmeticError as error:
            raise ValueError('Inputs exceed the supported numerical domain') from error
    return checked
