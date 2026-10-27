# Residential candidate hand calculation

Prepared independently of production calculation imports; engineering approval PENDING.

IPC 2024 is the target edition; no code-table approval is claimed. Occupancy 24 is contextual and does not determine peak flow.

Q trunk = Q A + Q B. V = 4Q / (pi D^2). Use Q m3/s and internal bore D m.
hf = 10.67 L Q^1.852 / (C^1.852 D^4.8704); hm = K V^2 / (2 g); g = 9.80665 m/s2.
Residual pressure head = source head - elevation rise - sum(hf + hm). Margin = residual - required.

|Pipe|Q L/s|Nominal mm|Bore mm|V m/s|hf m|hm m|
|---|---:|---:|---:|---:|---:|---:|
|P0|0.600000000|25.000000000|20.000000000|1.909859317|2.757504109|0.185973937|
|P1|0.250000000|25.000000000|20.000000000|0.795774715|0.726613873|0.032287142|
|P2|0.350000000|25.000000000|20.000000000|1.114084602|2.032469637|0.063282798|

A: 35 - 1 - path losses = 30.297620940 m; required 10 m; margin 20.297620940 m.

B: 35 - 6 - path losses = 23.960769520 m; required 12 m; margin 11.960769520 m.

Governing: B; technical envelope PASS; REVIEW_REQUIRED.
Drainage table candidates (not code): 50/6, 75/24, 100/100 mm/DFU. Required D0,D1,D2: [75, 50, 50]; actual slope 1/20*100=5% against stipulated 1%. No DFU-to-L/s conversion.
Heat m*cp*dT = 47.092500000 kW; storage Q*t*3.6*1.10 = 2.376000000 m3; pump rho*g*Q*H/eta/1000 = 0.203978320 kW; runoff C*I*A/3600 = 2.250000000 L/s.

Expected warning identifiers: CODE_EDITION_AND_TABLES_UNVERIFIED, MANUFACTURER_CATALOGUE_UNVERIFIED, INDEPENDENT_ENGINEER_REVIEW_PENDING, DRAINAGE_PARTIAL_COVERAGE
Unevaluated: fixture diversity and WSFU-to-flow applicability; minimum-pressure survey and pressure zones; backflow and maximum static pressure; hot-water recirculation heat loss, balancing, scald and hygiene controls; pump curve/NPSH and tank operation; drainage vent/trap/cleanout/offset arrangement; storm secondary drainage and local rainfall adoption; CAD/IFC/Revit extraction completeness; all licensed code-table values and local amendments

Review: BIM MANAGER; identity, qualifications, independence and signed evidence pending.
