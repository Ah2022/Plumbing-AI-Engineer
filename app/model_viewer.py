"""Local centreline viewer and schematic editor. No external scripts or inferred BIM solids."""
import math
from copy import deepcopy

import streamlit as st

HTML = """
<div class="toolbar" role="toolbar" aria-label="Model navigation">
  <button data-view="3D" type="button">3D</button><button data-view="Plan" type="button">Plan</button>
  <button data-view="Elevation" type="button">Elevation</button><button class="fit" type="button">Fit</button>
  <span class="hint"></span>
</div>
<canvas tabindex="0" role="img" aria-label="Interactive plumbing centreline model. Use the object selector below for keyboard navigation."></canvas>
<div class="legend">Water <span style="color:#1e88e5">●</span> Hot water <span style="color:#ed7958">●</span>
Drainage <span style="color:#a57ce1">●</span> Other <span style="color:#8293a4">●</span></div>
"""
CSS = """
:host {font-family:var(--st-font);color:var(--st-text-color)}
.toolbar {display:flex;flex-wrap:wrap;gap:6px;align-items:center;padding:8px 0}
button {color:var(--st-text-color);background:var(--st-secondary-background-color);border:1px solid var(--st-border-color,#8293a4);border-radius:6px;padding:6px 12px;cursor:pointer}
button:focus-visible {outline:2px solid var(--st-primary-color)}
canvas {width:100%;height:380px;background:var(--st-secondary-background-color);border:1px solid var(--st-border-color,#8293a4);border-radius:8px;touch-action:none}
.hint,.legend {font-size:12px;opacity:.8}.legend{padding:6px}
"""
JS = """
export default function(component) {
  const {data, parentElement, setTriggerValue} = component;
  const canvas = parentElement.querySelector('canvas'), ctx = canvas.getContext('2d');
  const network = data.mode === 'network';
  const root = parentElement;
  const state = canvas._viewer || {yaw:.65,pitch:.5,zoom:1,view:network?'Plan':'3D'};
  canvas._viewer = state;
  let projected=[], down=null, moved=false;
  root.querySelector('.hint').textContent=network?'Drag nodes to arrange · Click to inspect · Wheel to zoom':'Drag to orbit · Wheel to zoom · Click a pipe to inspect';
  root.querySelectorAll('[data-view]').forEach(b=>{ b.hidden=network; b.onclick=()=>{state.view=b.dataset.view;draw();}; });
  root.querySelector('.fit').onclick=()=>{state.zoom=1;draw();};
  function color(s) {
    s=String(s||'').toLowerCase();
    return s.includes('hot')?'#ed7958':s.includes('drain')||s.includes('sanit')?'#a57ce1':s.includes('water')||s.includes('cold')?'#1e88e5':'#8293a4';
  }
  const nodes = (data.nodes||[]).map(n=>({...n,xyz:[...n.xyz]}));
  const objects = data.objects||[];
  const points=network?nodes.map(n=>n.xyz):objects.flatMap(o=>[o.start,o.end]);
  const min=[0,1,2].map(i=>Math.min(...points.map(p=>p[i]))), max=[0,1,2].map(i=>Math.max(...points.map(p=>p[i])));
  const center=min.map((v,i)=>(v+max[i])/2), span=Math.max(1,...max.map((v,i)=>v-min[i]));
  let width=600,height=380,scale=1;
  function project(p) {
    let [x,y,z]=p.map((v,i)=>v-center[i]);
    if(state.view==='Elevation') return [width/2+x*scale,height/2-z*scale];
    if(state.view==='Plan') return [width/2+x*scale,height/2-y*scale];
    let a=Math.cos(state.yaw)*x-Math.sin(state.yaw)*y, b=Math.sin(state.yaw)*x+Math.cos(state.yaw)*y;
    return [width/2+a*scale,height/2-(z*Math.cos(state.pitch)+b*Math.sin(state.pitch))*scale];
  }
  function line(a,b,id,service) {
    ctx.beginPath();ctx.moveTo(...a);ctx.lineTo(...b);ctx.strokeStyle=id===data.selected?'#e9ad22':color(service);
    ctx.lineWidth=id===data.selected?6:3;ctx.stroke();projected.push({id,a,b});
  }
  function draw() {
    width=Math.max(280,canvas.clientWidth);height=380;
    const ratio=window.devicePixelRatio||1;canvas.width=width*ratio;canvas.height=height*ratio;ctx.scale(ratio,ratio);
    scale=Math.min(width-60,height-60)/span*state.zoom;projected=[];ctx.clearRect(0,0,width,height);
    ctx.globalAlpha=.12;ctx.strokeStyle='#8293a4';ctx.lineWidth=1;
    for(let x=0;x<width;x+=30){ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke();}
    for(let y=0;y<height;y+=30){ctx.beginPath();ctx.moveTo(0,y);ctx.lineTo(width,y);ctx.stroke();}ctx.globalAlpha=1;
    if(network){
      const byId=new Map(nodes.map(n=>[n.id,n]));
      for(const p of objects){const a=byId.get(p.from),b=byId.get(p.to);if(a&&b){const pa=project(a.xyz),pb=project(b.xyz);line(pa,pb,p.id,p.system);
        const t=Math.atan2(pb[1]-pa[1],pb[0]-pa[0]),mx=(pa[0]+pb[0])/2,my=(pa[1]+pb[1])/2;
        ctx.beginPath();ctx.moveTo(mx,my);ctx.lineTo(mx-9*Math.cos(t-.5),my-9*Math.sin(t-.5));ctx.moveTo(mx,my);ctx.lineTo(mx-9*Math.cos(t+.5),my-9*Math.sin(t+.5));ctx.stroke();}}
      for(const n of nodes){const p=project(n.xyz);ctx.beginPath();ctx.arc(...p,n.id===data.selected?10:7,0,Math.PI*2);ctx.fillStyle=n.id===data.selected?'#e9ad22':'#1e88e5';ctx.fill();ctx.font='12px sans-serif';ctx.fillStyle='#8293a4';ctx.fillText(n.id,p[0]+12,p[1]-8);projected.push({id:n.id,a:p,b:p,node:n});}
    } else for(const o of objects)line(project(o.start),project(o.end),o.id,o.system);
    if(!points.length){ctx.font='14px sans-serif';ctx.fillStyle='#8293a4';ctx.fillText('No extracted axes in this scope',25,50);}
  }
  function position(e){const r=canvas.getBoundingClientRect();return[e.clientX-r.left,e.clientY-r.top];}
  function distance(p,o){const [a,b]=[o.a,o.b],dx=b[0]-a[0],dy=b[1]-a[1],length=dx*dx+dy*dy;
    const t=length?Math.max(0,Math.min(1,((p[0]-a[0])*dx+(p[1]-a[1])*dy)/length)):0;
    return Math.hypot(p[0]-a[0]-t*dx,p[1]-a[1]-t*dy);}
  function pick(p){const visible=[...projected].reverse();
    const node=visible.filter(o=>o.node&&distance(p,o)<12).sort((a,b)=>distance(p,a)-distance(p,b))[0];
    return node||visible.sort((a,b)=>distance(p,a)-distance(p,b)).find(o=>distance(p,o)<12);}
  canvas.onpointerdown=e=>{const p=position(e);down={p,hit:pick(p)};moved=false;canvas.setPointerCapture(e.pointerId);};
  canvas.onpointermove=e=>{if(!down)return;const p=position(e),dx=p[0]-down.p[0],dy=p[1]-down.p[1];
    if(Math.hypot(dx,dy)>2)moved=true;
    if(network&&down.hit&&down.hit.node){down.hit.node.xyz[0]+=dx/scale;down.hit.node.xyz[1]-=dy/scale;}
    else if(!network){state.yaw+=dx*.009;state.pitch=Math.max(-1.5,Math.min(1.5,state.pitch-dy*.009));state.view='3D';}
    down.p=p;draw();};
  canvas.onpointerup=e=>{if(!down)return;
    if(network&&moved&&down.hit&&down.hit.node){setTriggerValue('event',{action:'move',id:down.hit.id,xy:down.hit.node.xyz.slice(0,2)});}
    else if(!moved){const hit=pick(position(e));if(hit)setTriggerValue('event',{action:'select',id:hit.id});}down=null;};
  canvas.onpointercancel=()=>{down=null;};
  canvas.onwheel=e=>{e.preventDefault();state.zoom=Math.max(.2,Math.min(12,state.zoom*Math.exp(-e.deltaY*.001)));draw();};
  const observer=new ResizeObserver(draw);observer.observe(canvas);draw();
  return ()=>observer.disconnect();
}
"""


@st.cache_resource
def _registered_component(html, css, js):
    return st.components.v2.component('plumbing_geometry_workspace', html=html, css=css, js=js)


def _component():
    # Hash the assets as cache arguments so source reloads update the renderer.
    return _registered_component(HTML, CSS, JS)


def _point(value):
    return (isinstance(value, (list, tuple)) and len(value) == 3
            and all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in value))


def geometry_payload(inventory, system='All systems', query=''):
    objects = inventory.get('objects', [])
    filtered = [o for o in objects if (system == 'All systems' or o.get('system') == system)
                and query.casefold() in str(o.get('source_id', '') + ' ' + str(o.get('name', ''))).casefold()]
    axes = [dict(id=o['source_id'], start=o['start_xyz_m'], end=o['end_xyz_m'], system=o.get('system', ''))
            for o in filtered if _point(o.get('start_xyz_m')) and _point(o.get('end_xyz_m'))]
    if len(axes) > 2000:
        raise ValueError('This view contains over 2,000 axes. Filter by system or object before viewing.')
    return dict(mode='model', objects=axes, missing_geometry=len(filtered)-len(axes)), filtered


def render_model_viewer(inventory, key):
    st.subheader('Model explorer')
    st.caption('Extracted centrelines in metres. Orbit in 3D or switch to plan/elevation; select an object to inspect its source facts. Tessellated solids and drawing-sheet overlays are outside this viewer.')
    systems = ['All systems'] + sorted({o.get('system') for o in inventory.get('objects', []) if o.get('system')})
    focus = st.session_state.get('workspace_model_focus')
    if focus and focus['project_id'] == st.session_state.get('project_id'):
        st.session_state.pop('workspace_model_focus')
        if focus['source_id'] in [o['source_id'] for o in inventory.get('objects', [])]:
            st.session_state[key + '_selected'] = focus['source_id']
            st.session_state[key + '_system'] = 'All systems'
            st.session_state[key + '_search'] = focus['source_id']
        else:
            st.info('Issue location: ' + str(focus['source_id']) + '. No exact source ID matches this extraction; search by name or inspect the correct model revision.')
    col1, col2 = st.columns(2)
    system = col1.selectbox('Visible system', systems, key=key + '_system')
    query = col2.text_input('Find model object', key=key + '_search', placeholder='Name or source ID')
    try:
        payload, filtered = geometry_payload(inventory, system, query)
    except ValueError as error:
        st.warning(str(error)); return
    st.caption(f"{len(payload['objects'])} visible axes · {payload['missing_geometry']} objects without usable axis geometry")
    if not filtered:
        st.info('No source objects match this filter.'); return
    ids = [o['source_id'] for o in filtered]
    selected_key = key + '_selected'
    if st.session_state.get(selected_key) not in ids:
        st.session_state[selected_key] = ids[0]
    payload['selected'] = st.session_state[selected_key]

    def pick_object():
        event = st.session_state[key + '_canvas'].event
        if event and event.get('action') == 'select' and event.get('id') in ids:
            st.session_state[selected_key] = event['id']

    _component()(data=payload, key=key + '_canvas', on_event_change=pick_object)
    selected = st.selectbox('Selected model object', ids, key=selected_key,
        format_func=lambda identity: next((o.get('name') or identity) + ' · ' + identity for o in filtered if o['source_id'] == identity))
    obj = next(o for o in filtered if o['source_id'] == selected)
    with st.container(border=True):
        st.markdown('**' + str(obj.get('name') or obj['source_id']) + '**')
        st.caption(f"{obj.get('source_class', obj.get('kind', 'Object'))} · {obj.get('system') or 'System unmapped'} · {obj['source_id']}")
        details = {k.replace('_', ' '): str([round(float(v), 4) for v in obj[k]]) if k.endswith('xyz_m') else str(obj[k])
                   for k in ('nominal_mm', 'internal_mm', 'flow_lps', 'length_m', 'start_xyz_m', 'end_xyz_m') if obj.get(k) is not None}
        if details:
            st.dataframe([dict(Property=k, Value=v) for k,v in details.items()], hide_index=True, width='stretch', alt='Selected model object dimensions, flow and source coordinates')
        if not _point(obj.get('start_xyz_m')) or not _point(obj.get('end_xyz_m')):
            st.info('This object has no usable extracted axis. It remains available in the object selector; its position is not inferred.')


def network_payload(model):
    nodes, pipes = model.get('nodes', []), model.get('pipes', [])
    if not nodes or len(nodes) > 500 or len(pipes) > 500:
        raise ValueError('Graphical editing supports 1–500 nodes and up to 500 pipes.')
    ids = [n.get('id') for n in nodes]
    pipe_ids = [p.get('id') for p in pipes]
    if any(not isinstance(i, str) or not i.strip() for i in ids + pipe_ids) or len(set(ids+pipe_ids)) != len(ids+pipe_ids):
        raise ValueError('Use nonempty, unique IDs across nodes and pipes before graphical editing.')
    if any(p.get('from_node') not in ids or p.get('to_node') not in ids for p in pipes):
        raise ValueError('Correct pipe connections to missing nodes in Editable tables before graphical editing.')
    layout = model.get('schematic_layout', {})
    if not isinstance(layout, dict):
        raise ValueError('Schematic layout must map node IDs to x/y coordinate pairs.')
    adjacency = {identity: [] for identity in ids}
    for pipe in pipes:
        adjacency[pipe['from_node']].append(pipe['to_node'])
        adjacency[pipe['to_node']].append(pipe['from_node'])
    root = model.get('root') if model.get('root') in ids else ids[0]
    depth, queue = {root: 0}, [root]
    for identity in queue:
        for neighbor in adjacency[identity]:
            if neighbor not in depth:
                depth[neighbor] = depth[identity] + 1
                queue.append(neighbor)
    layers = {}
    for identity in ids:
        layers.setdefault(depth.get(identity, 0), []).append(identity)
    automatic = {identity: [level * 160, ((len(group)-1)/2-index)*120]
                 for level, group in layers.items() for index, identity in enumerate(group)}
    positions = []
    for i, identity in enumerate(ids):
        xy = layout.get(identity, automatic[identity])
        if not isinstance(xy, (list, tuple)) or not _point(list(xy) + [0]):
            raise ValueError('Schematic positions must contain finite x and y coordinates.')
        positions.append(dict(id=identity, xyz=list(xy) + [0]))
    return dict(mode='network', nodes=positions,
                objects=[dict(id=p['id'], **{'from': p['from_node'], 'to': p['to_node']}, system=model.get('service')) for p in pipes])


def apply_network_event(model, event):
    result = deepcopy(model)
    if not isinstance(event, dict):
        raise ValueError('Invalid network editing event.')
    if event.get('action') == 'move':
        xy = event.get('xy')
        if event.get('id') not in [n['id'] for n in model['nodes']] or not isinstance(xy, list) or not _point(xy + [0]) or any(abs(v)>1e6 for v in xy):
            raise ValueError('Invalid schematic node position.')
        result.setdefault('schematic_layout', {})[event['id']] = xy
    elif event.get('action') != 'select':
        raise ValueError('Unsupported graphical editing action.')
    return result
