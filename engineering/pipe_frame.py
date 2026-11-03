"""Linear 3D circular-pipe frame and forced structure-borne response prototypes."""
import math
import numpy as np
from engineering.common import fields,num,text,rows,unique,check,result

DOFS=('ux','uy','uz','rx','ry','rz')


def assemble(frame):
    fields(frame,'nodes elements constraints springs loads gravity_x_m_s2 gravity_y_m_s2 gravity_z_m_s2')
    nodes=rows(frame,'nodes',limit=40);unique(nodes);elements=rows(frame,'elements',limit=60);unique(elements)
    ids={text(n,'id'):i for i,n in enumerate(nodes)};coords=[]
    for n in nodes:
        fields(n,'id source_id x_m y_m z_m');text(n,'source_id');coords.append([num(n,k) for k in ('x_m','y_m','z_m')])
    coords=np.array(coords);size=6*len(nodes);elastic=np.zeros((size,size));physical=np.zeros(size);prepared=[]
    gravity=np.array([num(frame,k) for k in ('gravity_x_m_s2','gravity_y_m_s2','gravity_z_m_s2')])
    for e in elements:
        fields(e,'id source_id from_node to_node internal_mm external_mm youngs_modulus_mpa poisson_ratio '
            'density_kg_m3 fluid_density_kg_m3 alpha_per_k temperature_change_k stress_intensification internal_gauge_kpa')
        text(e,'source_id');a=e.get('from_node');b=e.get('to_node')
        if a not in ids or b not in ids or a==b:raise ValueError('Frame element endpoints must be different known nodes')
        ri=num(e,'internal_mm',positive=True)/2000;ro=num(e,'external_mm',positive=True)/2000
        if ro<=ri:raise ValueError('Pipe outside diameter must exceed bore')
        vector=coords[ids[b]]-coords[ids[a]];length=float(np.linalg.norm(vector))
        if length/(2*ro)<10:raise ValueError('Euler-Bernoulli frame requires each straight element length/outside-diameter >=10')
        young=num(e,'youngs_modulus_mpa',positive=True)*1e6;poisson=num(e,'poisson_ratio',minimum=0,maximum=.49)
        shear=young/(2*(1+poisson));area=math.pi*(ro*ro-ri*ri);inertia=math.pi/4*(ro**4-ri**4);polar=2*inertia
        mass=num(e,'density_kg_m3',positive=True)*area+num(e,'fluid_density_kg_m3',minimum=0)*math.pi*ri**2
        alpha=num(e,'alpha_per_k',minimum=0);delta=num(e,'temperature_change_k');num(e,'stress_intensification',minimum=1)
        num(e,'internal_gauge_kpa',minimum=0)
        ex=vector/length;guide=np.array([0.,0.,1.]) if abs(ex[2])<.9 else np.array([0.,1.,0.])
        ey=np.cross(guide,ex);ey/=np.linalg.norm(ey);ez=np.cross(ex,ey);rotation=np.array([ex,ey,ez])
        transform=np.zeros((12,12))
        for start in (0,3,6,9):transform[start:start+3,start:start+3]=rotation
        local=np.zeros((12,12))
        for indices,stiffness in [([0,6],young*area/length),([3,9],shear*polar/length)]:
            local[np.ix_(indices,indices)]+=stiffness*np.array([[1.,-1.],[-1.,1.]])
        l=length;bend=young*inertia/l**3*np.array([[12,6*l,-12,6*l],[6*l,4*l*l,-6*l,2*l*l],[-12,-6*l,12,-6*l],[6*l,2*l*l,-6*l,4*l*l]])
        local[np.ix_([1,5,7,11],[1,5,7,11])]+=bend
        signs=np.diag([1,-1,1,-1]);local[np.ix_([2,4,8,10],[2,4,8,10])]+=signs@bend@signs
        load=np.zeros(12);q=rotation@(mass*gravity)
        load[:3]=q*l/2;load[6:9]=q*l/2
        load[4]=-q[2]*l*l/12;load[10]=q[2]*l*l/12;load[5]=q[1]*l*l/12;load[11]=-q[1]*l*l/12
        thermal=young*area*alpha*delta;load[0]-=thermal;load[6]+=thermal
        index=list(range(6*ids[a],6*ids[a]+6))+list(range(6*ids[b],6*ids[b]+6))
        elastic[np.ix_(index,index)]+=transform.T@local@transform;physical[index]+=transform.T@load
        prepared.append(dict(row=e,index=index,T=transform,k=local,load=load,A=area,I=inertia,J=polar,ri=ri,ro=ro,L=l))
    loads=rows(frame,'loads',empty=True,limit=100)
    for load in loads:
        fields(load,'node source_id fx_n fy_n fz_n mx_nm my_nm mz_nm');text(load,'source_id')
        if load.get('node') not in ids:raise ValueError('Load references an unknown node')
        index=6*ids[load['node']];physical[index:index+6]+=[num(load,k) for k in ('fx_n','fy_n','fz_n','mx_nm','my_nm','mz_nm')]
    stiffness=elastic.copy();force=physical.copy();prescribed={}
    constraints=rows(frame,'constraints',empty=True,limit=size)
    for c in constraints:
        fields(c,'node dof value source_id');text(c,'source_id')
        if c.get('node') not in ids or c.get('dof') not in DOFS:raise ValueError('Unknown constrained node/DOF')
        index=6*ids[c['node']]+DOFS.index(c['dof'])
        if index in prescribed:raise ValueError('Duplicate constrained DOF')
        prescribed[index]=num(c,'value')
    springs=rows(frame,'springs',empty=True,limit=size)
    springids=set()
    for spring in springs:
        fields(spring,'node dof stiffness reference_displacement source_id');text(spring,'source_id')
        if spring.get('node') not in ids or spring.get('dof') not in DOFS:raise ValueError('Unknown spring node/DOF')
        index=6*ids[spring['node']]+DOFS.index(spring['dof'])
        if index in springids:raise ValueError('Duplicate spring DOF')
        springids.add(index);k=num(spring,'stiffness',positive=True);rest=num(spring,'reference_displacement')
        stiffness[index,index]+=k;force[index]+=k*rest
    free=[i for i in range(size) if i not in prescribed]
    if free:
        sub=stiffness[np.ix_(free,free)];diag=np.diag(sub)
        if min(diag)<=0:raise ValueError('Unrestrained/zero-stiffness frame DOF; add physical supports or correct connectivity')
        scale=1/np.sqrt(diag);condition=float(np.linalg.cond(scale[:,None]*sub*scale[None,:]))
        if not math.isfinite(condition) or condition>1e12:raise ValueError('Frame has a mechanism or ill-conditioned restraints; review disconnected parts and support directions')
    else:condition=1.
    return dict(nodes=nodes,ids=ids,coords=coords,K=stiffness,elastic=elastic,F=force,physical=physical,
        fixed=prescribed,free=free,elements=prepared,condition=condition)


def piping_flexibility(data):
    fields(data,'source_id frame allowable_stress_mpa maximum_translation_mm maximum_rotation_rad')
    ref=text(data,'source_id');model=assemble(data.get('frame'));k=model['K'];force=model['F'];u=np.zeros(len(force))
    allow=num(data,'allowable_stress_mpa',positive=True);translation=num(data,'maximum_translation_mm',positive=True)
    rotation=num(data,'maximum_rotation_rad',positive=True,maximum=.1)
    for i,value in model['fixed'].items():u[i]=value
    free=model['free'];fixed=list(model['fixed'])
    if free:
        rhs=force[free]-(k[np.ix_(free,fixed)]@u[fixed] if fixed else 0)
        u[free]=np.linalg.solve(k[np.ix_(free,free)],rhs)
    residual=k@u-force;reaction=model['elastic']@u-model['physical'];trace=[];peak=0.
    for prepared in model['elements']:
        e=prepared['row'];end=prepared['k']@(prepared['T']@u[prepared['index']])-prepared['load']
        ri=prepared['ri'];ro=prepared['ro'];p=e['internal_gauge_kpa']*1000
        hoop=p*(ro**2+ri**2)/(ro**2-ri**2);radial=-p;axial_pressure=p*ri**2/(ro**2-ri**2)
        maximum=0.
        for offset,sign in ((0,-1),(6,1)):
            axial=sign*end[offset]/prepared['A']+axial_pressure
            bend=e['stress_intensification']*math.hypot(end[offset+4],end[offset+5])*ro/prepared['I']
            tau=end[offset+3]*ro/prepared['J']
            for side in (-1,1):
                z=axial+side*bend
                vm=math.sqrt(((hoop-radial)**2+(radial-z)**2+(z-hoop)**2)/2+3*tau*tau)/1e6
                maximum=max(maximum,vm)
        peak=max(peak,maximum)
        trace.append(dict(kind='element',id=e['id'],maximum_screened_von_mises_mpa=maximum,
            axial_force_from_n=end[0],axial_force_to_n=end[6],torsion_from_nm=end[3],
            bending_from_nm=math.hypot(end[4],end[5]),bending_to_nm=math.hypot(end[10],end[11]),source_id=e['source_id']))
    maxtrans=0.;maxrot=0.
    for node in model['nodes']:
        i=6*model['ids'][node['id']];disp=u[i:i+6];r=reaction[i:i+6]
        maxtrans=max(maxtrans,float(np.linalg.norm(disp[:3]))*1000);maxrot=max(maxrot,float(np.linalg.norm(disp[3:])))
        trace.append(dict(kind='node',id=node['id'],**{d:float(v) for d,v in zip(DOFS,disp)},
            reaction_fx_n=r[0],reaction_fy_n=r[1],reaction_fz_n=r[2],reaction_mx_nm=r[3],reaction_my_nm=r[4],reaction_mz_nm=r[5]))
    residual_norm=float(np.max(np.abs(residual[free]))) if free else 0.
    values=dict(maximum_translation_mm=maxtrans,maximum_rotation_rad=maxrot,maximum_screened_von_mises_mpa=peak,
        free_dof_residual=residual_norm,scaled_condition_number=model['condition'])
    return result(values,dict(maximum_translation_mm='mm',maximum_rotation_rad='rad',maximum_screened_von_mises_mpa='MPa',free_dof_residual='N or N·m',scaled_condition_number='1'),
        [check('frame_translation',maxtrans<=translation,maxtrans,translation,'mm',ref),check('small_rotation',maxrot<=rotation,maxrot,rotation,'rad',ref),
         check('supplied_stress_screen',peak<=allow,peak,allow,'MPa',ref),check('linear_equilibrium',residual_norm<=1e-7*max(1,float(np.max(np.abs(force)))),residual_norm,0,'N or N·m',ref)],trace,
        notes=['Linear 3D Euler-Bernoulli frame with six DOFs/node, axial/biaxial bending/torsion, uniform thermal strain, self/fluid gravity, nodal forces/moments, prescribed supports and linear springs. Source SI units: spring N/m or N·m/rad, prescribed m or rad.',
            'Initial increment toward piping flexibility: straight slender isotropic elements only. No elbow ovalization/flexibility factors, pressure thrust/Poisson displacement coupling, gaps/friction supports, geometric nonlinearity, fatigue, buckling or certified ASME stress categories.',
            'Supplied pressure membrane stresses are added to end-force/bending/torsion screening; they are not pressure-thrust displacement loads. Support reactions include physical spring forces. Model-specific source/allowable and mesh comparisons remain required.'])


def structure_borne(data):
    fields(data,'source_id frame inertias mass_damping_per_s stiffness_damping_s radiation_area_m2 radiation_efficiency '
        'air_density_kg_m3 sound_speed_m_s receiver_distance_m directivity_factor room_constant_m2 limit_dba receiver_node receiver_dof spectrum')
    ref=text(data,'source_id');model=assemble(data.get('frame'));size=len(model['F']);mass=np.zeros(size)
    if any(abs(v)>0 for v in model['fixed'].values()):raise ValueError('Harmonic boundary DOFs must be zero; nonzero static supports are not harmonic excitation')
    inertias=rows(data,'inertias',limit=40);unique(inertias,'node')
    for row in inertias:
        fields(row,'node source_id mass_kg jx_kg_m2 jy_kg_m2 jz_kg_m2');text(row,'source_id')
        if row['node'] not in model['ids']:raise ValueError('Unknown inertia node')
        i=6*model['ids'][row['node']];m=num(row,'mass_kg',minimum=0);mass[i:i+3]=m
        mass[i+3:i+6]=[num(row,k,minimum=0) for k in ('jx_kg_m2','jy_kg_m2','jz_kg_m2')]
    free=model['free']
    if not free or any(mass[i]<=0 for i in free):raise ValueError('Every free harmonic DOF requires an explicit positive lumped mass/inertia; include pipe, fluid, supports and equipment consistently')
    alpha=num(data,'mass_damping_per_s',minimum=0);beta=num(data,'stiffness_damping_s',minimum=0)
    if alpha==beta==0:raise ValueError('Supply reviewed nonzero Rayleigh damping; undamped resonance is not supported')
    area=num(data,'radiation_area_m2',positive=True);efficiency=num(data,'radiation_efficiency',minimum=0,maximum=1)
    density=num(data,'air_density_kg_m3',positive=True);speed=num(data,'sound_speed_m_s',positive=True)
    distance=num(data,'receiver_distance_m',positive=True);directivity=num(data,'directivity_factor',positive=True,maximum=8)
    room=num(data,'room_constant_m2',positive=True);limit=num(data,'limit_dba')
    receiver=text(data,'receiver_node');dof=text(data,'receiver_dof')
    if receiver not in model['ids'] or dof not in DOFS[:3]:raise ValueError('Radiation receiver must be an existing translational DOF normal to the supplied radiator')
    ri=6*model['ids'][receiver]+DOFS.index(dof);spectrum=rows(data,'spectrum',limit=40);seen=set();trace=[];energy=0.;maxv=0.
    k=model['K'][np.ix_(free,free)];m=np.diag(mass[free]);damping=alpha*m+beta*k
    for row in spectrum:
        fields(row,'frequency_hz source_id a_weight_db excitations');text(row,'source_id');hz=num(row,'frequency_hz',positive=True,maximum=10000)
        if hz in seen:raise ValueError('Duplicate harmonic frequency')
        seen.add(hz);weight=num(row,'a_weight_db');omega=2*math.pi*hz;force=np.zeros(size,dtype=complex)
        for excitation in rows(row,'excitations',limit=100):
            fields(excitation,'node dof rms_amplitude phase_rad')
            node=excitation.get('node');direction=excitation.get('dof')
            if node not in model['ids'] or direction not in DOFS:raise ValueError('Unknown harmonic force/moment node/DOF')
            index=6*model['ids'][node]+DOFS.index(direction)
            if index not in free:raise ValueError('A harmonic force on a restrained DOF is not represented as frame excitation')
            force[index]+=num(excitation,'rms_amplitude',minimum=0)*np.exp(1j*num(excitation,'phase_rad'))
        impedance=k-omega*omega*m+1j*omega*damping
        if np.linalg.cond(impedance)>1e12:raise ValueError('Ill-conditioned harmonic response near resonance; review damping/mesh and excitation data')
        displacement=np.zeros(size,dtype=complex);displacement[free]=np.linalg.solve(impedance,force[free])
        velocity=abs(omega*displacement[ri]);maxv=max(maxv,float(velocity))
        power=efficiency*density*speed*area*velocity**2
        transfer=directivity/(4*math.pi*distance**2)+4/room;bandenergy=power/1e-12*transfer
        energy+=bandenergy*10**(weight/10)
        trace.append(dict(frequency_hz=hz,normal_rms_velocity_m_s=float(velocity),radiated_power_w=float(power),
            receiver_band_db=10*math.log10(bandenergy) if bandenergy>0 else None,source_id=row['source_id']))
    total=10*math.log10(energy) if energy>0 else None
    return result(dict(maximum_normal_rms_velocity_m_s=maxv,predicted_receiver_dba=total),
        dict(maximum_normal_rms_velocity_m_s='m/s RMS',predicted_receiver_dba='dBA'),
        [check('supplied_structure_borne_receiver_limit',total is None or total<=limit,total,limit,'dBA',ref)],trace,
        notes=['Linear frame harmonic mobility using explicit lumped nodal masses/inertias, reviewed Rayleigh damping and coherent RMS force/moment phasors at each frequency. Distinct frequency energies are added incoherently.',
            'A supplied normal radiator velocity is converted to acoustic power using radiation efficiency, area and rho*c, then direct/diffuse receiver transfer. Mass is not automatically inferred or double-counted.',
            'Initial structure-borne path model, not full building acoustics: no shell/panel spatial modes, junction flanking/transmission networks, contact nonlinearity, stochastic forcing or certified noise prediction. Radiation/source/damping inputs need measured validation.'])
