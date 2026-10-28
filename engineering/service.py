"""Validate evidence envelopes, dispatch scoped calculations and preserve review gates."""
import hashlib
import json
from copy import deepcopy
from engineering.common import fields,text
from engineering.registry import MODULES
from engineering.pumps import operating_point,equipment_selection
from engineering.hot_water import recirculation
from engineering.drainage import fixture_minimum,gravity_flow,trap_pressure,vent_arrangement,backwater_overflow
from engineering.storm import route_storage
from engineering.fire import fire_separation
from engineering.effects import noise_screen,water_hammer,thermal_expansion
from engineering.medical_gas import medical_gas
from engineering.dynamic_drainage import dynamic_drainage
from engineering.recirculation_network import recirculation_network
from engineering.transients import network_transient
from engineering.acoustic_structural import acoustic_prediction,pipe_stress,relief_selection
from engineering.drainage_air import drainage_air

METHODS={'pump_system':operating_point,'recirculation':recirculation,'fixture_minimum':fixture_minimum,
    'gravity_flow':gravity_flow,'trap_pressure':trap_pressure,'vent_arrangement':vent_arrangement,
    'backwater_overflow':backwater_overflow,'storm_storage':route_storage,'fire_separation':fire_separation,
    'equipment_selection':equipment_selection,'noise_screen':noise_screen,'water_hammer':water_hammer,'thermal_expansion':thermal_expansion,
    'medical_gas':medical_gas,'dynamic_drainage':dynamic_drainage,'recirculation_network':recirculation_network,
    'network_transient':network_transient,'acoustic_prediction':acoustic_prediction,'pipe_stress':pipe_stress,'relief_selection':relief_selection,
    'drainage_air':drainage_air}


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def validate_envelope(package):
    fields(package,'schema_version module code_id code_edition basis_reference sources data')
    if package.get('schema_version')!='engineering-input-1' or package.get('module') not in METHODS:raise ValueError('Unsupported engineering input version/module')
    for field in ('code_id','code_edition','basis_reference'):text(package,field)
    sources=package.get('sources')
    if not isinstance(sources,list) or not 1<=len(sources)<=500:raise ValueError('Supply explicit source records, including assumed/synthetic data')
    byid={}
    for source in sources:
        fields(source,'id type document revision locator verification_status reviewed_by sha256')
        for name in ('id','document','revision','locator'):text(source,name)
        if source['id'] in byid:raise ValueError('Duplicate source ID')
        if source.get('type') not in ('CODE','MANUFACTURER','PROJECT','MEASURED','SYNTHETIC','METHOD_REFERENCE'):raise ValueError('Unsupported source type')
        if source.get('verification_status') not in ('UNVERIFIED','REVIEWED_AS_REPORTED'):raise ValueError('Source status must be UNVERIFIED or REVIEWED_AS_REPORTED; it cannot grant engineering approval')
        if source['verification_status']=='REVIEWED_AS_REPORTED':text(source,'reviewed_by')
        if source.get('sha256') is not None:
            value=source['sha256']
            if not isinstance(value,str) or len(value)!=64 or any(c not in '0123456789abcdef' for c in value):raise ValueError('Source checksum must be a lowercase SHA-256')
        byid[source['id']]=source
    data=package.get('data')
    if not isinstance(data,dict):raise ValueError('Calculation data must be an object')
    text(data,'source_id')
    def walk(value):
        if isinstance(value,dict):
            for key,child in value.items():
                if key=='source_id' and child not in byid:raise ValueError('Missing source record for '+str(child))
                walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(data);digest(package)
    if package['module'] in ('equipment_selection','relief_selection'):
        for row in data.get('catalogue',[]):
            if not isinstance(row,dict) or row.get('source_id') not in byid:raise ValueError('Each catalogue entry needs its own source binding')
            if byid[row['source_id']]['type'] not in ('MANUFACTURER','SYNTHETIC'):raise ValueError('Catalogue rows require manufacturer evidence or an explicitly synthetic demonstration source')
    return deepcopy(package)


def run_module(package):
    package=validate_envelope(package);metadata=next(m for m in MODULES if m['id']==package['module'])
    try:output=METHODS[package['module']](package['data']);digest(output)
    except ArithmeticError as error:raise ValueError('Inputs exceed the supported numerical domain') from error
    statuses=[c['status'] for c in output['checks']]
    status='FAIL' if 'FAIL' in statuses else 'NOT_EVALUATED' if not output['complete'] else 'PASS' if statuses else 'CALCULATED_NOT_APPROVED'
    return dict(schema_version='engineering-result-1',module=metadata['id'],technical_status=status,
        review_status='REVIEW_REQUIRED',code_compliance_status='NOT_EVALUATED',coverage_status='PARTIAL',
        input_sha256=digest(package),input_package=package,scope=metadata['scope'],required_source_data=metadata['required_source_data'],
        not_evaluated=metadata['not_evaluated'],validation_status=metadata['validation_status'],
        source_status='SYNTHETIC' if any(s['type']=='SYNTHETIC' for s in package['sources']) else 'UNVERIFIED' if any(s['verification_status']=='UNVERIFIED' for s in package['sources']) else 'REVIEWED_AS_REPORTED',
        **output)
