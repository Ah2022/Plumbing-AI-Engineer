"""Safe DOT topology from explicit mapped IDs; no CAD geometry is inferred."""
import json
import streamlit as st
from calculations.validation import finite


def _identity(row, field):
    value = row.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'Preview requires a nonempty {field} on every mapped object.')
    if len(value) > 256:
        raise ValueError('Preview object IDs must be 256 characters or fewer.')
    return value


def network_dot(model, *, dark=False):
    """Render incomplete/looped drafts, but never invent missing or duplicate nodes."""
    if not isinstance(model, dict) or model.get('schema_version') != '1.0' or model.get('units') != 'SI':
        raise ValueError('Preview requires schema_version 1.0 and explicit SI units.')
    nodes, pipes = model.get('nodes'), model.get('pipes')
    if not isinstance(nodes, list) or not isinstance(pipes, list) or not nodes:
        raise ValueError('Add mapped nodes and a pipes list to preview the network.')
    if len(nodes) > 500 or len(pipes) > 500:
        raise ValueError('Preview supports up to 500 nodes and 500 pipes. Partition larger networks.')
    identifiers = {}
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            raise ValueError('Every preview node must be a mapped object.')
        identity = _identity(node, 'id')
        if identity in identifiers:
            raise ValueError('Duplicate preview node ID: ' + identity)
        identifiers[identity] = f'n{index}'
    root = model.get('root')
    if not isinstance(root, str) or root not in identifiers:
        raise ValueError('Select a source/outlet root that matches a mapped node ID.')
    quote = lambda text: json.dumps(str(text), ensure_ascii=False)
    background, fill, foreground = ('#111827', '#1f2937', '#e5edf9') if dark else ('#ffffff', '#f1f5f9', '#17212f')
    dot = ['digraph plumbing {', f'graph [rankdir=LR, bgcolor="{background}", pad="0.3"];',
           f'node [shape=box, style="rounded,filled", fontname="Arial", fillcolor="{fill}", color="{foreground}", fontcolor="{foreground}"];',
           f'edge [fontname="Arial", color="{foreground}", fontcolor="{foreground}"];']
    for node in nodes:
        identity = node['id']
        kind = node.get('kind', 'unmapped')
        kind = kind[:40] if isinstance(kind, str) else 'unmapped'
        labels = [identity, kind]
        for field, label, unit in [('elevation_m', 'z', 'm'), ('design_flow_lps', 'Q', 'L/s'),
                                    ('water_wsfu', 'Supply', 'WSFU'), ('drainage_dfu', 'Drainage', 'DFU')]:
            if node.get(field) is not None:
                value = finite(field, node[field], minimum=0 if field != 'elevation_m' else None)
                labels.append(f'{label}: {value:g} {unit}')
        shape = 'doubleoctagon' if identity == root else ('ellipse' if kind == 'fixture' else 'box')
        dot.append(f'{identifiers[identity]} [label={quote(chr(10).join(labels))}, shape={shape}];')
    seen = set()
    for pipe in pipes:
        if not isinstance(pipe, dict):
            raise ValueError('Every preview pipe must be a mapped object.')
        identity = _identity(pipe, 'id')
        if identity in seen:
            raise ValueError('Duplicate preview pipe ID: ' + identity)
        seen.add(identity)
        start, end = _identity(pipe, 'from_node'), _identity(pipe, 'to_node')
        if start not in identifiers or end not in identifiers:
            raise ValueError(f'Pipe {identity} references an unknown node: {start} → {end}')
        labels = [identity]
        if pipe.get('length_m') is not None:
            labels.append(f"{finite('length_m', pipe['length_m'], positive=True):g} m")
        if pipe.get('nominal_mm') is not None:
            labels.append(f"Nominal {finite('nominal_mm', pipe['nominal_mm'], positive=True):g} mm")
        dot.append(f'{identifiers[start]} -> {identifiers[end]} [label={quote(chr(10).join(labels))}];')
    dot.append('}')
    return '\n'.join(dot)


def render_network_preview(model, model_error=None):
    st.subheader('Rendered network')
    if model_error:
        st.info('Preview unavailable until the JSON or table errors are corrected. No previous diagram is shown.')
        return
    try:
        dot = network_dot(model, dark=st.context.theme.type == 'dark')
    except ValueError as error:
        st.warning('Network preview: ' + str(error))
        return
    st.caption(f"{len(model['nodes'])} nodes · {len(model['pipes'])} pipes · Root: {model['root']}")
    st.graphviz_chart(dot, width='stretch', alt='Mapped plumbing nodes and directed pipe connections; schematic layout')
    st.caption('Arrows follow the mapped pipe direction. This is a connectivity schematic, not a scaled CAD drawing or a compliance result. Run network review to validate the design.')
