"""Readable project status presentation, independent of technical export format."""
import streamlit as st


def project_status(governance):
    basis=governance.get('basis') or {};profile=governance.get('profile') or {}
    approval=basis.get('basis_status','NOT_DECLARED')
    if approval=='APPROVED' and 'Profile or source data changed after adoption approval' in governance['issues']:approval='STALE'
    adoption={'DRAFT':'Draft — adoption review pending','APPROVED':'Project adoption recorded',
              'STALE':'Adoption needs renewed review','NOT_DECLARED':'Code basis not saved'}.get(approval,approval.replace('_',' ').capitalize())
    with st.container(horizontal=True):
        st.metric('Code profile',profile.get('display_name') or basis.get('profile_id','Not selected'))
        st.metric('Basis revision',str(basis.get('revision','—')))
    st.caption('Project adoption: '+adoption)
    if governance['review_status']=='REVIEW_REQUIRED':st.info('Engineering review is pending. Recording project adoption does not verify the code tables or certify a calculation.')
    else:st.success('The recorded verification checks are complete for this context.')
