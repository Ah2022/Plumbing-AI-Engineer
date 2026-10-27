"""Optional independent EPANET 2.2 C toolkit. No production solver imports."""
import ctypes as c
import hashlib
import os
from pathlib import Path
import tempfile


def run_epanet(inp, library):
    library=Path(library).resolve()
    dll=(c.WinDLL if os.name=='nt' else c.CDLL)(str(library))
    signatures={
        'EN_createproject':[c.POINTER(c.c_void_p)],'EN_deleteproject':[c.c_void_p],
        'EN_open':[c.c_void_p,c.c_char_p,c.c_char_p,c.c_char_p],
        'EN_solveH':[c.c_void_p], 'EN_close':[c.c_void_p],
        'EN_getversion':[c.POINTER(c.c_int)],
        'EN_getcount':[c.c_void_p,c.c_int,c.POINTER(c.c_int)],
        'EN_getnodeid':[c.c_void_p,c.c_int,c.c_char_p],
        'EN_getlinkid':[c.c_void_p,c.c_int,c.c_char_p],
        'EN_getnodevalue':[c.c_void_p,c.c_int,c.c_int,c.POINTER(c.c_double)],
        'EN_getlinkvalue':[c.c_void_p,c.c_int,c.c_int,c.POINTER(c.c_double)]}
    for name,args in signatures.items():
        getattr(dll,name).argtypes=args;getattr(dll,name).restype=c.c_int
    warnings=[]
    def call(name,*args):
        code=getattr(dll,name)(*args)
        if code>=100: raise ValueError(f'EPANET {name}: error {code}')
        if code: warnings.append(dict(operation=name,code=code))
    version=c.c_int();call('EN_getversion',c.byref(version))
    if version.value!=20200:
        raise ValueError('Pinned reference run requires EPANET 2.2 (20200)')
    handle=c.c_void_p();call('EN_createproject',c.byref(handle));opened=False
    temporary=tempfile.TemporaryDirectory(prefix='plm_epanet_')
    try:
        folder=temporary.name
        root=Path(folder);(root/'network.inp').write_text(inp,encoding='ascii')
        call('EN_open',handle,os.fsencode(root/'network.inp'),os.fsencode(root/'network.rpt'),b'');opened=True
        call('EN_solveH',handle)
        result={}
        for group,countcode,idfn,valfn,props in [('nodes',0,'EN_getnodeid','EN_getnodevalue',{'pressure_m':11,'demand_lps':9}),
            ('pipes',2,'EN_getlinkid','EN_getlinkvalue',{'flow_lps':8,'velocity_m_s':9})]:
            count=c.c_int();call('EN_getcount',handle,countcode,c.byref(count));rows={}
            for i in range(1,count.value+1):
                name=c.create_string_buffer(256);call(idfn,handle,i,name);row={}
                for prop,code in props.items():
                    value=c.c_double();call(valfn,handle,i,code,c.byref(value));row[prop]=value.value
                rows[name.value.decode('ascii')]=row
            result[group]=rows
        result.update(version=version.value,library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
            input_sha256=hashlib.sha256(inp.encode('ascii')).hexdigest(),warnings=warnings)
        return result
    finally:
        if opened: call('EN_close',handle)
        call('EN_deleteproject',handle)
        temporary.cleanup()
