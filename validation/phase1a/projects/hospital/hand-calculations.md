# Hospital candidate hand calculation

Prepared independently of production calculation imports; engineering approval PENDING.

IPC 2024 is the target edition; no code-table approval is claimed. Occupancy 240 is contextual and does not determine peak flow.

Q trunk = Q A + Q B. V = 4Q / (pi D^2). Use Q m3/s and internal bore D m.
hf = 10.67 L Q^1.852 / (C^1.852 D^4.8704); hm = K V^2 / (2 g); g = 9.80665 m/s2.
Residual pressure head = source head - elevation rise - sum(hf + hm). Margin = residual - required.

|Pipe|Q L/s|Nominal mm|Bore mm|V m/s|hf m|hm m|
|---|---:|---:|---:|---:|---:|---:|
|P0|3.500000000|63.000000000|58.000000000|1.324714152|1.179825178|0.089473346|
|P1|2.000000000|50.000000000|46.000000000|1.203440023|1.664024130|0.073841112|
|P2|1.500000000|40.000000000|36.000000000|1.473656880|4.297262265|0.110724080|

A: 30 - 8 - path losses = 18.992836233 m; required 10 m; margin 8.992836233 m.

B: 30 - 25 - path losses = -0.677284869 m; required 12 m; margin -12.677284869 m.

Governing: B; technical envelope FAIL; REVIEW_REQUIRED.
Drainage table candidates (not code): 50/6, 75/24, 100/100 mm/DFU. Required D0,D1,D2: [100, 75, 100]; actual slope 1/20*100=5% against stipulated 1%. No DFU-to-L/s conversion.
Heat m*cp*dT = 376.740000000 kW; storage Q*t*3.6*1.10 = 13.860000000 m3; pump rho*g*Q*H/eta/1000 = 2.059396500 kW; runoff C*I*A/3600 = 22.500000000 L/s.

Expected warning identifiers: CODE_EDITION_AND_TABLES_UNVERIFIED, MANUFACTURER_CATALOGUE_UNVERIFIED, INDEPENDENT_ENGINEER_REVIEW_PENDING, DRAINAGE_PARTIAL_COVERAGE
Unevaluated: fixture diversity and WSFU-to-flow applicability; minimum-pressure survey and pressure zones; backflow and maximum static pressure; hot-water recirculation heat loss, balancing, scald and hygiene controls; pump curve/NPSH and tank operation; drainage vent/trap/cleanout/offset arrangement; storm secondary drainage and local rainfall adoption; CAD/IFC/Revit extraction completeness; all licensed code-table values and local amendments

Review: BIM MANAGER; identity, qualifications, independence and signed evidence pending.
