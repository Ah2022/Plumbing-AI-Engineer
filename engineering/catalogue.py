"""Small explicit SI catalogue CSV interchange; source records stay in package."""
import csv
import io
import math

COMMON=['model_id','manufacturer','source_id','fluid','max_pressure_kpa','min_temperature_c','max_temperature_c']
SCHEMAS={
    'pump':COMMON+['efficiency','npshr_m'],
    'tank':COMMON+['usable_volume_l'],
    'relief':['model','source_id','service','rating_basis','set_gauge_kpa','certified_capacity_kw','rating_temperature_c','listing','evidence_reference'],
}
TEXT={'model_id','model','manufacturer','source_id','fluid','service','rating_basis','listing','evidence_reference'}


def _read(raw,columns,limit):
    if not isinstance(raw,bytes) or len(raw)>2000000:raise ValueError('Catalogue CSV must be at most 2 MB')
    reader=csv.DictReader(io.StringIO(raw.decode('utf-8-sig')))
    if reader.fieldnames!=columns:raise ValueError('CSV columns/order must be: '+','.join(columns))
    result=[]
    for row in reader:
        if len(result)>=limit:raise ValueError('Catalogue CSV exceeds row bound')
        if None in row or any(v is None or not v.strip() or len(v)>2000 for v in row.values()):raise ValueError('CSV rows must have every declared field, with bounded nonempty values')
        item={}
        for key,value in row.items():
            if key in TEXT:
                if value.lstrip().startswith(('=','+','-','@')):raise ValueError('CSV text fields cannot begin with spreadsheet formula prefixes')
                item[key]=value.strip()
            else:
                try:item[key]=float(value)
                except ValueError as e:raise ValueError('Catalogue SI numeric field invalid: '+key) from e
                if not math.isfinite(item[key]):raise ValueError('Catalogue values must be finite')
        result.append(item)
    if not result:raise ValueError('Catalogue CSV has no data rows')
    return result


def import_catalogue(raw,kind,curve_raw=None):
    if kind not in SCHEMAS:raise ValueError('Catalogue kind must be pump, tank or relief')
    result=_read(raw,SCHEMAS[kind],500); key='model' if kind=='relief' else 'model_id'
    ids=[r[key] for r in result]
    if len(set(ids))!=len(ids):raise ValueError('Duplicate catalogue model ID')
    if kind=='pump':
        points=_read(curve_raw,['model_id','flow_lps','head_m'],10000)
        for point in points:
            if point['model_id'] not in ids:raise ValueError('Pump curve references an unknown catalogue model')
        from engineering.pumps import validate_curve
        for row in result:
            row['pump_curve']=[{k:p[k] for k in ('flow_lps','head_m')} for p in points if p['model_id']==row['model_id']]
            validate_curve(row['pump_curve'])
    elif curve_raw is not None:raise ValueError('Curve CSV applies only to pumps')
    return result


def export_catalogue(catalogue,kind):
    def dump(columns,values):
        buf=io.StringIO(newline=''); writer=csv.DictWriter(buf,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(values)
        return buf.getvalue()
    # Prevent formula execution if an external spreadsheet opens textual fields.
    # Import refuses these prefixes too; data belongs in plain-text CSV editors.
    for row in catalogue:
        for key,value in row.items():
            if key in TEXT and isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):
                raise ValueError('CSV text fields cannot begin with spreadsheet formula prefixes')
    models=dump(SCHEMAS[kind],catalogue)
    curves=dump(['model_id','flow_lps','head_m'],[dict(model_id=r['model_id'],**p) for r in catalogue for p in r.get('pump_curve',[])]) if kind=='pump' else None
    return models,curves
