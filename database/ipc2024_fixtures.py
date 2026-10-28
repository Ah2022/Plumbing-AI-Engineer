"""IPC 2024 fixture-load transcription candidates; adoption/review stays pending.

Numerical facts cross-checked against ICC's indexed Spanish 2024 Table 709.1.
Labels are abbreviated. Footnote/application review is mandatory, particularly
for indirect receptors, building drains and combination groups.
"""
SOURCE='https://codes.iccsafe.org/content/IPCSP2024P1/capitulo-7-drenaje-sanitario'
REVISION='IPC-2024-709.1-candidate-1'
# id, display name, DFU (None = determine from connected load), trap inches.
TABLE=[
 ('washer_commercial','Commercial washer',3,2),
 ('washer_residential','Residential washer',2,2),
 ('bathgroup_16','Bathroom group, 1.6 gpf',5,None),
 ('bathgroup_high','Bathroom group, above 1.6 gpf',6,None),
 ('bathtub','Bathtub',2,1.5),('bidet','Bidet',1,1),
 ('sink_tray','Sink/tray combination',2,1.5),('dental_basin','Dental basin',1,1.25),
 ('dental_unit','Dental unit',1,1.25),('dishwasher','Domestic dishwasher',2,1.5),
 ('drinking','Drinking fountain',.5,1.25),('emergency_floor','Emergency floor drain',0,2),
 ('floor_drain','Floor drain',2,2),('floor_sink','Floor sink',None,2),
 ('kitchen','Domestic kitchen sink',2,1.5),('kitchen_group','Kitchen/disposer/dishwasher combination',2,1.5),
 ('laundry','Laundry tray',2,1.5),('lavatory','Lavatory',1,1.25),
 ('shower_57','Shower <=5.7 gpm',2,1.5),('shower_123','Shower >5.7–12.3 gpm',3,2),
 ('shower_258','Shower >12.3–25.8 gpm',5,3),('shower_556','Shower >25.8–55.6 gpm',6,4),
 ('service_sink','Service sink',2,1.5),('sink','Sink',2,1.5),
 ('urinal','Urinal',4,None),('urinal_low','Urinal <=1 gpf',2,None),('urinal_dry','Waterless urinal',.5,None),
 ('washsink','Wash sink, each faucet set',2,1.5),('wc_flushometer_tank','WC flushometer tank',4,None),
 ('wc_private_16','Private WC, 1.6 gpf',3,None),('wc_private_high','Private WC, above 1.6 gpf',4,None),
 ('wc_public_16','Public WC, 1.6 gpf',4,None),('wc_public_high','Public WC, above 1.6 gpf',6,None),
]


def choices():
    result=[]
    for identity,name,dfu,trap in TABLE:
        notes=['Check adoption, all Table 709.1 footnotes and fixture applicability before use.']
        if identity in ('floor_sink','floor_drain'): notes.append('Indirect receptor: use connected load and receptor minimum under 709.4; clear-water-only exception needs separate review.')
        if identity=='bidet': notes.append('Trap transcription needs English-edition/manufacturer cross-check; do not use as an approved trap minimum.')
        if 'washer' in identity: notes.append('Review 406.2 branch/stack requirements independently of trap size.')
        if identity=='emergency_floor': notes.append('Zero DFU applies only to an emergency-only floor drain, not a routine discharge receptor.')
        if identity.startswith('shower_'): notes.append('Flow band uses the combined flow of all heads/body sprays; no extrapolation beyond 55.6 gpm.')
        if 'bathgroup' in identity or identity=='kitchen_group': notes.append('Group load includes its member fixtures. Do not also count those members; add only extra fixtures.')
        if identity.startswith(('wc_','urinal')): notes.append('Review footnote e for building-drain/sewer loads; fixture outlet governs trap designation.')
        result.append(dict(fixture_id=identity,fixture_name=name,label=name+(' — determine connected load' if dfu is None else f' — {dfu:g} DFU'),
            unit_value=dfu,unit='DFU',minimum_trap_in=trap,occupancy='As labeled',confidence='FLAGGED',
            table_reference='IPC 2024 Table 709.1; '+SOURCE,catalogue_revision=REVISION,conditions=' '.join(notes),
            review_status='REVIEW_REQUIRED'))
    return result
