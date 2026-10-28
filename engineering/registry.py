"""Public module scopes. UI exposure requires matching executed validation evidence."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CASES=ROOT/'validation/engineering/reference_cases.json'
EVIDENCE=ROOT/'validation/engineering/software_evidence.json'


def module(identity,priority,title,scope,sources,omissions,method_url):
    return dict(id=identity,priority=priority,title=title,scope=scope,required_source_data=sources,
        not_evaluated=omissions,method_references=[method_url],engineering_status='REVIEW_REQUIRED',
        validation_status='SOFTWARE_REFERENCE_TESTED_ENGINEERING_PENDING')


MODULES=[
 module('general_pressure',1,'General pressure-network solver','Existing EPANET2.2 loops, equipment, PDA, EPS and scenario boundary.',
    ['Reviewed normalized graph, nodal demands, source heads, equipment curves and controls'],['Code approval, transients, thermal recirculation and gravity flow'],
    'https://www.epa.gov/water-research/epanet'),
 module('pump_system',2,'Pump curves and system curves','Unique operating intersection of a tabular decreasing pump curve and Hstatic + R Q²; no extrapolation.',
    ['Manufacturer H-Q points','Reviewed single-circuit static head and quadratic resistance, m/(L/s)²'],['Looped-system curve generation, variable-speed control, efficiency and NPSH approval'],
    'https://datatool.pumps.org/pump-fundamentals/combined.html'),
 module('recirculation',3,'Hot-water recirculation','Steady no-draw parallel-loop heat balance, required circulation flow, return temperature, loop loss and balancing head.',
    ['Loop lengths and reviewed W/m losses','Water density/cp at design temperature','Bores, Darcy factors, fitting K and temperature criterion'],['Shared-trunk loss, mixing/control dynamics, hygiene and scald certification'],
    'https://www.caleffi.com/en-us/blog/2-single-loop-recirculation-systems'),
 module('fixture_minimum',4,'Fixture-level minimum-size checks','Selected nominal designation, supplied design flow and available pressure compared with explicit fixture criteria.',
    ['Adopted code/manufacturer fixture minimums and designation mapping','Selected nominal size and actual bore','Simultaneous hydraulic flow and residual pressure'],['Automatic source-inch to DN mapping, fixture listing and whole-network approval'],
    'https://codes.iccsafe.org/content/IPC2024V2.0/chapter-6-water-supply-and-distribution'),
 module('gravity_flow',5,'Gravity drainage flow','Manning normal depth/capacity and velocity for a uniform circular free-surface pipe, fill ratio no greater than0.9.',
    ['Actual bore, slope and Manning n','Independent design L/s, maximum fill and reviewed minimum-velocity criterion'],['DFU-to-L/s conversion, surcharged/backwater network, unsteady and solids transport'],
    'https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest/stable-channel-design-functions/uniform-flow-computations'),
 module('trap_pressure',6,'Trap-seal and air-pressure checks','Constant-rate seal evaporation screen and supplied air-pressure peaks against an explicit allowable budget; hydrostatic equivalence.',
    ['Measured/validated positive and negative air-pressure peaks','Trap seal, evaporation exposure and adopted pressure/seal limits'],['Trap geometry/oscillation, siphonage, two-phase air-network prediction and seal-break certification'],
    'https://codes.iccsafe.org/content/IPC2024V2.0/chapter-10-traps-interceptors-and-separators'),
 module('vent_arrangement',7,'Wet, circuit and AAV venting','Supplied arrangement applicability/count/DFU/nominal and attributed geometry/relief/listing conditions.',
    ['Applicable adopted wet/circuit/AAV criteria','Fixture types/floors/DFU and vent sizes','Reviewed geometry, relief and AAV manufacturer listing/capacity/clearance'],['Automatic geometry inference, all code exceptions, complete stack/vent sizing or authority approval'],
    'https://codes.iccsafe.org/content/IPC2024V2.0/chapter-9-vents'),
 module('backwater_overflow',8,'Backwater and overflow checks','Static downstream HGL/flood-rim/protection screen and idealized free weir or fully wetted orifice capacity.',
    ['Design HGL, invert/flood-rim and water/tailwater levels','Reviewed protection/device and outlet dimensions/coefficients'],['Submerged weirs, partly wetted/submerged orifices, sewer surcharge dynamics and device reliability'],
    'https://www.hec.usace.army.mil/confluence/rasdocs/ras1dtechref/latest'),
 module('storm_storage',9,'Stormwater routing and storage','Single level-pool Modified Puls routing with explicit storage/outflow rating, hydrograph and mass balance.',
    ['Independent inflow hydrograph','Monotone level/storage/outflow rating covering the entire event','Initial storage and permitted level'],['Rainfall-runoff calibration, distributed sewer routing, tailwater coupling and extrapolated overflow'],
    'https://www.hec.usace.army.mil/confluence/hmsdocs/hmstrm/channel-flow/modified-puls-model'),
 module('fire_separation',10,'Fire-flow and domestic/fire separation','Supplied simultaneous fire hydraulic margins, storage reservations and reviewed directional separation-path screening.',
    ['Reviewed fire hydraulic scenario results/criteria','Classified layout and documented separation-device orientation','Usable tank capacity and non-overlapping reserves'],['NFPA/fire authority certification, device listing tests and automatic fire-demand derivation'],
    'https://www.epa.gov/water-research/epanet'),
 module('equipment_selection',11,'Manufacturer equipment selection','Pump or tank candidate filtering at supplied duty, fluid, pressure/temperature ratings and supplied NPSH/usable storage.',
    ['User-imported manufacturer catalogue with model, revision/page and source records','Published curves/ratings and duty-specific efficiency/NPSHr or usable tank volume'],['Purchasing, manufacturer endorsement, operating region/trim, viscosity corrections and certified final selection'],
    'https://www.epa.gov/water-research/epanet'),
 module('noise_screen',12,'Noise risk and measured acoustics','Velocity against a reviewed acoustic-risk limit and optional like-for-like measured dB comparison.',
    ['Flow/bore and referenced velocity criterion','Matched acoustic measurement/limit weighting and conditions if supplied'],['dBA prediction from velocity, room acoustics, vibration and cavitation-noise modeling'],
    'https://www.caleffi.com/sites/default/files/media/file/Idronics_11.pdf'),
 module('water_hammer',12,'Water hammer screen','Single-line Joukowsky envelope and stated slow linear-velocity closure approximation with pressure/cavitation checks.',
    ['Reviewed wave speed, line length, velocity change and closure model/time','Water density, operating/allowable/atmospheric/vapour pressures'],['Network method-of-characteristics transient, column separation and arrestor/air-vessel sizing'],
    'https://live-resources-e2e-sales.ksb.com/resource/blob/762108/b03ed4dd6aa0139a876090d66fe3b9f2/water-hammer-data.pdf'),
 module('thermal_expansion',12,'Thermal expansion and vessel screen','Density-based water expansion, free pipe elongation and ideal polytropic vessel acceptance using absolute pressures.',
    ['Reviewed cold/hot densities, system volume and material expansion coefficient','Temperatures, vessel precharge/cold fill/maximum/atmospheric pressure and gas exponent'],['Relief margin, membrane/usable acceptance, glycol corrections and pipe restraint/flexibility'],
    'https://www.varem.com/en/technical-support/sizing-heating-expansion-vessels-vessels/'),
]


def implementation_fingerprint():
    files={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
        for p in sorted((ROOT/'engineering').glob('*.py'))}
    return hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()


def exposure_status():
    try:
        evidence=json.loads(EVIDENCE.read_text(encoding='utf-8'));cases=json.loads(CASES.read_text(encoding='utf-8'))
        ready=(evidence['software_status']=='PASS' and evidence['implementation_sha256']==implementation_fingerprint()
            and evidence['reference_cases_sha256']==hashlib.sha256(CASES.read_text(encoding='utf-8').encode()).hexdigest())
        covered={c['module'] for c in cases}
    except (OSError,ValueError,KeyError,TypeError):ready=False;covered=set()
    result=[]
    for metadata in MODULES:
        explicit=all(metadata.get(k) for k in ('scope','required_source_data','not_evaluated','method_references','validation_status'))
        available=explicit and (metadata['id']=='general_pressure' or ready and metadata['id'] in covered)
        result.append(dict(metadata,available=available,exposure_reason='Scope/source/validation contract available' if available else 'Matching executed reference evidence is missing or stale'))
    return result
