# Office candidate hand calculation

Prepared independently of production calculation imports; engineering approval PENDING.

IPC 2024 is the target edition; no code-table approval is claimed. Occupancy 120 is contextual and does not determine peak flow.

Q trunk = Q A + Q B. V = 4Q / (pi D^2). Use Q m3/s and internal bore D m.
hf = 10.67 L Q^1.852 / (C^1.852 D^4.8704); hm = K V^2 / (2 g); g = 9.80665 m/s2.
Residual pressure head = source head - elevation rise - sum(hf + hm). Margin = residual - required.

|Pipe|Q L/s|Nominal mm|Bore mm|V m/s|hf m|hm m|
|---|---:|---:|---:|---:|---:|---:|
|P0|1.400000000|40.000000000|36.000000000|1.375413088|1.575755125|0.096452976|
|P1|0.800000000|32.000000000|26.000000000|1.506792361|3.272600663|0.115759368|
|P2|0.600000000|25.000000000|20.000000000|1.909859317|10.340640408|0.185973937|

A: 48 - 3 - path losses = 39.939431867 m; required 10 m; margin 29.939431867 m.

B: 48 - 15 - path losses = 20.801177554 m; required 12 m; margin 8.801177554 m.

Governing: B; technical envelope PASS; REVIEW_REQUIRED.
Drainage table candidates (not code): 50/6, 75/24, 100/100 mm/DFU. Required D0,D1,D2: [75, 75, 75]; actual slope 1/20*100=5% against stipulated 1%. No DFU-to-L/s conversion.
Heat m*cp*dT = 150.696000000 kW; storage Q*t*3.6*1.10 = 5.544000000 m3; pump rho*g*Q*H/eta/1000 = 0.640701133 kW; runoff C*I*A/3600 = 11.250000000 L/s.

Expected warning identifiers: CODE_EDITION_AND_TABLES_UNVERIFIED, MANUFACTURER_CATALOGUE_UNVERIFIED, INDEPENDENT_ENGINEER_REVIEW_PENDING, DRAINAGE_PARTIAL_COVERAGE
Unevaluated: fixture diversity and WSFU-to-flow applicability; minimum-pressure survey and pressure zones; backflow and maximum static pressure; hot-water recirculation heat loss, balancing, scald and hygiene controls; pump curve/NPSH and tank operation; drainage vent/trap/cleanout/offset arrangement; storm secondary drainage and local rainfall adoption; CAD/IFC/Revit extraction completeness; all licensed code-table values and local amendments

Review: BIM MANAGER; identity, qualifications, independence and signed evidence pending.
