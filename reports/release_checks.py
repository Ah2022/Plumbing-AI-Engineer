"""Independent arithmetic release checks on explicitly fictional, in-memory sources."""
import datetime
import math
from calculations.hot_water import heater_capacity, hot_water_demand
from calculations.tanks import size_domestic_water_tank, size_hot_water_storage_tank_from_demand
from calculations.pumps import select_pump_duty
from calculations.stormwater import design_rainfall_intensity, size_roof_drain, size_storm_drain_pipe
from calculations.hydraulics import rational_method_peak_flow
from database.db import init_db
from reports.provenance import engine_manifest


def run_release_benchmarks():
    conn = init_db(':memory:')
    cases = []
    def table(code,domain,name,rows):
        tid = conn.execute('INSERT INTO design_tables(code_id,domain,table_name,reference,status) VALUES (?,?,?,?,?)',
            (code,domain,name,'SYNTHETIC SOFTWARE BENCHMARK — NOT A CODE TABLE','POPULATED')).lastrowid
        for i,row in enumerate(rows):
            for key,value in row.items():
                conn.execute('''INSERT INTO design_table_values(table_id,row_key,col_key,value_num,value_text,confidence)
                                VALUES (?,?,?,?,?,'CONFIRMED')''',
                    (tid,str(i),key,value if isinstance(value,(int,float)) else None,value if isinstance(value,str) else None))
    def check(name, expected, unit, tolerance, operation):
        try:
            actual = operation()
            match = math.isclose(actual,expected,rel_tol=0,abs_tol=tolerance)
            cases.append(dict(case=name,expected=expected,actual=actual,unit=unit,tolerance=tolerance,status='PASS' if match else 'FAIL'))
        except (ValueError,TypeError,KeyError) as error:
            cases.append(dict(case=name,expected=expected,actual=None,unit=unit,tolerance=tolerance,status='FAIL',error=str(error)))
    try:
        for code in ('IPC','SYNTHETIC'):
            conn.execute('INSERT INTO codes(code_id,code_name) VALUES (?,?)',(code,'Synthetic method benchmark; not adopted code'))
        table('IPC','hot_water','9_Hot_Water_Basis [fixture+gph]',[{'fixture':'Synthetic fixture','gph':10}])
        table('SYNTHETIC','storm','Riyadh 24hr Design Rainfall Depth',[{'return_period_yr':10,'riyadh_station_mm':100}])
        table('SYNTHETIC','storm','8_Rainfall_Intensity [duration+ratio_to_24hr]',[{'duration':'15 min','ratio_to_24hr':.15}])
        table('SYNTHETIC','storm','8_Rainfall_Intensity [leader_mm+25 mm/hr]',[
            {'leader_mm':50,'25 mm/hr':500,'75 mm/hr':100}, {'leader_mm':100,'25 mm/hr':1000,'75 mm/hr':600}])
        table('SYNTHETIC','storm','8_Rainfall_Intensity [pipe_mm+vertical_drain_lpm]',[
            {'pipe_mm':50,'vertical_drain_lpm':100,'horiz_5mm_m':50}, {'pipe_mm':100,'vertical_drain_lpm':1000,'horiz_5mm_m':500}])
        check('Hot-water sensible heat: 0.5 × 4.186 × 45',94.185,'kW',1e-4,
              lambda: heater_capacity(.5,15,60,'BENCH').result_value)
        check('Domestic storage: 2 L/s × 4 h × 3600 / 1000 × 1.10',31.68,'m3',1e-3,
              lambda: size_domestic_water_tank(2,4,'BENCH',10).result_value)
        check('Pump: 5 L/s at 20 m, 80% efficiency',1.22583125,'kW',1e-4,
              lambda: select_pump_duty(5,10,2,1,3,4,.8,'BENCH').result_value)
        check('Rational Method: 0.9 × 60 × 1000 / 3600',15,'L/s',1e-4,
              lambda: rational_method_peak_flow(.9,60,1000,'BENCH').result_value)
        def hot():
            return hot_water_demand(conn,[{'fixture_name':'Synthetic fixture','quantity':40}],'BENCH')
        check('Synthetic hourly demand: 40 × 10 × 0.25',100,'GPH',.05,lambda: hot().result_value)
        check('Synthetic hot storage: 100 × 0.6 × 3.78541',227.1246,'L',.05,
              lambda: size_hot_water_storage_tank_from_demand(hot(),'BENCH-STORAGE').result_value)
        check('Synthetic rainfall: 100 × 0.15 / 0.25',60,'mm/hr',1e-3,
              lambda: design_rainfall_intensity(conn,'SYNTHETIC',10,'15 min','BENCH').result_value)
        check('Synthetic leader: use 75 mm/hr column for 60 mm/hr',100,'nominal mm',0,
              lambda: size_roof_drain(conn,'SYNTHETIC',300,60,'BENCH').result_value)
        check('Synthetic vertical storm pipe: 5 L/s = 300 L/min',100,'nominal mm',0,
              lambda: size_storm_drain_pipe(conn,'SYNTHETIC',5,'BENCH').result_value)
    finally:
        conn.close()
    return dict(schema_version='release-software-checks-1',generated_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        software_status='PASS' if cases and all(c['status']=='PASS' for c in cases) else 'FAIL', cases=cases,
        runtime=engine_manifest(), engineering_status='REVIEW_REQUIRED', live_writeback_status='NOT_VALIDATED',
        limitations=['Synthetic source rows verify method arithmetic and lookup boundaries only; they do not verify any licensed code table.',
            'Pump curves, project adoption, code applicability, model completeness and real-model writeback need separate acceptance evidence.'])
