"""Native acceptance runner. Invoke inside Revit CPython, never as an offline pass.

Reads the active host and loaded links; all test writes occur in a detached RVT.
Incremental JSON keeps failures and incomplete runs visible. No cloud save/sync.
"""
import datetime
import json
import time
import traceback
from copy import deepcopy
from pathlib import Path

from bim.revit_extract import extract_document, element_id
from bim.revit_handoff import (checksum, preflight_handoff, apply_handoff,
                              TEXT_FIELDS, NUMBER_FIELDS, FLAG_FIELDS)
from bim.revit_bindings import validate_result_binding
from bim.round_trip import verify_round_trip, run_in_revit
from bim.mapping import revit_inventory, initial_mapping, snapshot


CATEGORIES = ('OST_PipeCurves', 'OST_PipeFitting', 'OST_PlumbingFixtures',
              'OST_PipeAccessory', 'OST_MechanicalEquipment', 'OST_GenericModel')


def classify(label):
    # Native label classification only, not engineering service acceptance.
    return {'Domestic Cold Water': 'cold_water', 'DomesticColdWater': 'cold_water',
            'Domestic Hot Water': 'hot_water', 'DomesticHotWater': 'hot_water',
            'Sanitary': 'drainage', 'Vent': 'vent', 'Storm': 'storm'}.get(label)


def run(uiapp, DB, source_copy, output_root, controlled_host_copy=False, performance_source=None):
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    root = Path(output_root) / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    root.mkdir(parents=True, exist_ok=False)
    host = uiapp.ActiveUIDocument.Document
    application = host.Application
    from System import EventHandler
    if controlled_host_copy and host.IsModelInCloud:
        raise ValueError('An isolated host-copy run must use a local RVT, never a cloud host')
    report = dict(schema_version='revit-evidence-suite-1', execution_environment='REVIT_API',
                  started_at=started, revit_version=host.Application.VersionNumber,
                  host_title=host.Title, host_path=host.PathName,
                  host_workshared=host.IsWorkshared, cases=[], status='RUNNING',
                  limitations=['Controlled numeric inputs are software test data, not reviewed design inputs.',
                               'No multi-user contention or cloud synchronization is simulated.',
                               'Linked coordinates remain in link-local space; no federated topology is claimed.'])

    def save(name, value):
        (root / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')

    save('suite.json',report)

    def check(name, action):
        clock = time.perf_counter()
        try:
            detail = action()
            row = dict(name=name, status='PASS', detail=detail)
        except Exception as error:
            row = dict(name=name, status='FAIL', error=str(error), traceback=traceback.format_exc())
        row['seconds'] = time.perf_counter() - clock
        report['cases'].append(row)
        save('suite.json', report)
        return row

    def collect(doc):
        return [e for category in CATEGORIES for e in
                DB.FilteredElementCollector(doc).OfCategory(getattr(DB.BuiltInCategory, category)).WhereElementIsNotElementType()]

    def benchmark(doc=host,prefix='host'):
        elements = collect(doc)
        rows = []
        total = 0
        for index in range(0, len(elements), 5000):
            ids = {element_id(e) for e in elements[index:index+5000]}
            begin = time.perf_counter()
            extract = extract_document(doc, DB, classify, ids)
            seconds = time.perf_counter() - begin
            filename = prefix+'-partition-{:03d}.json'.format(index // 5000)
            save(filename, extract)
            count = len(extract['inventory']['objects'])
            total += count
            rows.append(dict(file=filename, selected=len(ids), extracted=count,
                             skipped=len(extract['skipped']), seconds=seconds, sha256=checksum(extract)))
            save(prefix+'-benchmark-progress.json', rows)
        return dict(model_title=doc.Title,total_native_instances=DB.FilteredElementCollector(doc).WhereElementIsNotElementType().GetElementCount(),
                    candidate_elements=len(elements), extracted_objects=total, partition_size=5000,
                    partitions=rows, scope='All six supported host categories; unsupported equipment can be skipped',
                    acceptance='Measured throughput only; no project performance SLA supplied')

    host_benchmark = check('host_partitioned_extraction', benchmark)

    def links():
        result = []
        for instance in DB.FilteredElementCollector(host).OfClass(DB.RevitLinkInstance):
            linked = instance.GetLinkDocument()
            row = dict(instance_id=element_id(instance), instance_uid=instance.UniqueId,
                       loaded=linked is not None)
            if linked is not None:
                elements = collect(linked)
                selected = {element_id(e) for e in elements[:100]}
                payload = extract_document(linked, DB, classify, selected)
                transform = instance.GetTotalTransform()
                row.update(model_identity=payload['revit_model_id'], candidates=len(elements),
                           sampled=len(selected), extracted=len(payload['inventory']['objects']),
                           instance_object_keys=[instance.UniqueId+'|'+payload['revit_model_id']+'|'+o['source_id'] for o in payload['inventory']['objects']],
                           transform_feet=[[v.X,v.Y,v.Z] for v in
                                           (transform.BasisX,transform.BasisY,transform.BasisZ,transform.Origin)])
                save('link-{}.json'.format(row['instance_id']), payload)
            result.append(row)
        if not result:raise ValueError('No native link instances; linked-model coverage unavailable')
        if not any(r['loaded'] and r.get('extracted',0) for r in result):
            raise ValueError('No loaded link yielded supported objects; linked extraction not exercised')
        return dict(links=result, scope='Read-only sample per loaded link; repeated link instances remain separate')

    if not controlled_host_copy:
        check('loaded_link_extraction_and_instance_identity', links)
    test_doc = None
    conn = None
    try:
        source = Path(source_copy).resolve()
        if not source.is_file():raise ValueError('Disposable source RVT missing: '+str(source))
        options = DB.OpenOptions()
        options.DetachFromCentralOption = DB.DetachFromCentralOption.DetachAndPreserveWorksets
        options.SetOpenWorksetsConfiguration(DB.WorksetConfiguration(DB.WorksetConfigurationOption.CloseAllWorksets))
        open_warnings=[]
        def opening_warnings(sender, args):
            accessor=args.GetFailuresAccessor()
            warning_doc=accessor.GetDocument()
            if warning_doc.Equals(host) or str(warning_doc.PathName).lower()!=str(source).lower():return
            for failure in accessor.GetFailureMessages():
                if (failure.GetSeverity()==DB.FailureSeverity.Warning and
                        failure.GetDescriptionText()=='Room is not in a properly enclosed region'):
                    open_warnings.append(failure.GetDescriptionText())
                    accessor.DeleteWarning(failure)
        if controlled_host_copy:
            detached_name=source.stem+'_detached.rvt'
            if not ((host.IsDetached and (not host.PathName or Path(host.PathName).name==detached_name)) or Path(host.PathName).resolve()==source):
                raise ValueError('Isolated test source must match the explicitly opened local RVT')
            test_doc=host
        else:
            warning_handler = EventHandler[DB.Events.FailuresProcessingEventArgs](opening_warnings)
            application.FailuresProcessing += warning_handler
            try:
                test_doc = host.Application.OpenDocumentFile(DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(str(source)), options)
            finally:
                application.FailuresProcessing -= warning_handler
                report['detached_open_warnings']=open_warnings
        if (test_doc.Equals(host) and not controlled_host_copy) or test_doc.IsModelInCloud:
            raise ValueError('Test writes require an independent local detached document')
        source_workshared=test_doc.IsWorkshared
        if not source_workshared:
            # Some supplied test copies already have worksharing discarded.
            # Enable it only in this independent local disposable document.
            test_doc.EnableWorksharing('Shared Levels and Grids','PLM Native Test')
        save_options = DB.SaveAsOptions()
        if test_doc.IsWorkshared:
            worksharing = DB.WorksharingSaveAsOptions()
            worksharing.SaveAsCentral = True
            save_options.SetWorksharingOptions(worksharing)
        test_doc.SaveAs(str(root / 'controlled.rvt'), save_options)
        report['controlled_model'] = dict(path=test_doc.PathName, workshared=test_doc.IsWorkshared,
                                        source_was_workshared=source_workshared,
                                        worksharing_enabled_for_test=not source_workshared,
                                        is_detached=test_doc.IsDetached, is_cloud=test_doc.IsModelInCloud)
        save('suite.json', report)

        def setup():
            transaction = DB.Transaction(test_doc, 'PLM controlled native test fixture and bindings')
            transaction.Start()
            old_file = host.Application.SharedParametersFilename
            try:
                host.Application.SharedParametersFilename = str(Path(__file__).resolve().parents[1] / 'bim/revit/PLM_shared_parameters.txt')
                definitions = host.Application.OpenSharedParameterFile()
                categories = host.Application.Create.NewCategorySet()
                categories.Insert(test_doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_PipeCurves))
                binding = host.Application.Create.NewInstanceBinding(categories)
                for group in definitions.Groups:
                    for definition in group.Definitions:
                        if definition.Name in TEXT_FIELDS + NUMBER_FIELDS + FLAG_FIELDS:
                            if not test_doc.ParameterBindings.Insert(definition, binding, DB.GroupTypeId.Data):
                                existing = DB.SharedParameterElement.Lookup(test_doc, definition.GUID)
                                if existing is None:raise ValueError('Cannot bind '+definition.Name)
                pipe_type = DB.FilteredElementCollector(test_doc).OfClass(DB.Plumbing.PipeType).FirstElement()
                system = next((s for s in DB.FilteredElementCollector(test_doc).OfClass(DB.Plumbing.PipingSystemType)
                               if str(s.SystemClassification)=='DomesticColdWater'), None)
                if system is None:
                    system = DB.Plumbing.PipingSystemType.Create(test_doc, DB.MEPSystemClassification.DomesticColdWater, 'PLM controlled cold water')
                level = DB.FilteredElementCollector(test_doc).OfClass(DB.Level).FirstElement()
                if pipe_type is None or level is None:raise ValueError('Test source lacks a pipe type/level')
                pipe = DB.Plumbing.Pipe.Create(test_doc, system.Id, pipe_type.Id, level.Id,
                                              DB.XYZ(0,0,level.Elevation), DB.XYZ(10,0,level.Elevation))
                pipe.get_Parameter(DB.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM).Set(25/304.8)
                test_doc.Regenerate()
                if transaction.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Fixture commit failed')
                return pipe.UniqueId
            finally:
                host.Application.SharedParametersFilename = old_file
                if transaction.GetStatus()==DB.TransactionStatus.Started:transaction.RollBack()
                transaction.Dispose()

        uid = setup()
        pipe = test_doc.GetElement(uid)
        selected = {element_id(pipe)}

        if controlled_host_copy:
            def linked_fixture():
                from System.Collections.Generic import List
                class KeepDestinationTypes(DB.IDuplicateTypeNamesHandler):
                    __namespace__='PlumbingEvidence_'+root.name.replace('-','_')
                    def OnDuplicateTypeNamesFound(self, args):
                        return DB.DuplicateTypeAction.UseDestinationTypes
                linked=host.Application.NewProjectDocument(DB.UnitSystem.Metric)
                try:
                    transaction=DB.Transaction(linked,'Controlled linked pipe fixture')
                    transaction.Start()
                    try:
                        pipe_ids=List[DB.ElementId]()
                        pipe_ids.Add(pipe.Id)
                        copy_options=DB.CopyPasteOptions()
                        copy_options.SetDuplicateTypeNamesHandler(KeepDestinationTypes())
                        DB.ElementTransformUtils.CopyElements(test_doc,pipe_ids,linked,
                                                             DB.Transform.Identity,copy_options)
                        copy_options.Dispose()
                        if transaction.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Link fixture copy failed')
                    finally:
                        if transaction.GetStatus()==DB.TransactionStatus.Started:transaction.RollBack()
                        transaction.Dispose()
                    linked.SaveAs(str(root/'linked-fixture.rvt'),DB.SaveAsOptions())
                finally:linked.Close(False)
                transaction=DB.Transaction(test_doc,'Two controlled linked-model instances')
                transaction.Start()
                try:
                    loaded=DB.RevitLinkType.Create(test_doc,DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(str(root/'linked-fixture.rvt')),DB.RevitLinkOptions(False))
                    first=DB.RevitLinkInstance.Create(test_doc,loaded.ElementId)
                    second=DB.RevitLinkInstance.Create(test_doc,loaded.ElementId)
                    DB.ElementTransformUtils.MoveElement(test_doc,second.Id,DB.XYZ(20,0,0))
                    identities=[first.UniqueId,second.UniqueId]
                    if transaction.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Link instances did not commit')
                finally:
                    if transaction.GetStatus()==DB.TransactionStatus.Started:transaction.RollBack()
                    transaction.Dispose()
                return dict(instance_uids=identities,translation_feet=20,
                            scope='Controlled RVT copied from a real native pipe, loaded twice; original project links remain unloaded')
            check('controlled_link_fixture',linked_fixture)
            check('loaded_link_extraction_and_instance_identity',links)

        def worksharing_check():
            if not test_doc.IsWorkshared:raise ValueError('Detached fixture did not preserve worksharing')
            status=DB.WorksharingUtils.GetCheckoutStatus(test_doc,pipe.Id)
            info=DB.WorksharingUtils.GetWorksharingTooltipInfo(test_doc,pipe.Id)
            if status==DB.CheckoutStatus.OwnedByOtherUser:raise ValueError('Test fixture is owned by another user')
            return dict(checkout_status=str(status),owner=info.Owner,creator=info.Creator,
                        scope='Local detached workshared model; no second-user contention or central sync')

        check('workshared_native_ownership',worksharing_check)

        def binding_check():
            rows=[]
            for name in TEXT_FIELDS + NUMBER_FIELDS + FLAG_FIELDS:
                parameter=pipe.LookupParameter(name)
                if parameter is None:raise ValueError('Missing '+name)
                error=validate_result_binding(test_doc, DB, pipe, name, parameter)
                if error:raise ValueError(name+': '+error)
                rows.append(dict(name=name,guid=str(parameter.GUID),storage=str(parameter.StorageType),
                                 spec=parameter.Definition.GetDataType().TypeId,read_only=parameter.IsReadOnly))
            return rows

        check('shared_guid_instance_category_bindings', binding_check)
        from database.db import init_db
        from compliance.rule_loader import load_all_rules
        conn=init_db(root/'native-engine.db')
        load_all_rules(conn)
        conn.execute("INSERT INTO projects(project_name,building_type,code_id) VALUES ('Native software test fixture','Office','IPC')")
        conn.commit()
        pid=conn.execute('SELECT max(project_id) FROM projects').fetchone()[0]
        before=extract_document(test_doc,DB,classify,selected)
        save('controlled-before.json',before)
        mapping=initial_mapping(revit_inventory(before))
        for row in mapping:
            row.update(service='cold_water',nominal_mm=25.,internal_mm=20.,design_flow_lps=.2,
                       elevation_m=before['pipes'][0]['start_xyz_m'][2],
                       engineering_reviewer='AUTOMATED SOFTWARE TEST - NOT ENGINEERING REVIEW',
                       evidence_reference='Controlled test inputs: 20 mm bore, 0.2 L/s; not production design data')
        reviewed=snapshot(revit_inventory(before),mapping,[],
                          'AUTOMATED SOFTWARE TEST - NOT ENGINEERING REVIEW','Native controlled fixture')

        def harness(commit):
            record=run_in_revit(test_doc,DB,conn,pid,reviewed,classify,1.,
                               'Software test assertion: velocity <= 1 m/s; not a design criterion',commit=commit)
            save('committed.json' if commit else 'dry-run.json',record)
            if commit:
                if record['write']['status']!='COMMITTED' or record['verification']['status']!='PASS':
                    raise ValueError('Committed native round-trip failed: '+str(record['write']))
            else:
                if record['write']['status']!='DRY_RUN_ROLLED_BACK':raise ValueError(str(record['write']))
                a=record['before']['inventory'];b=record['after']['inventory']
                if a!=b:raise ValueError('Dry-run fresh extraction differs after rollback')
            return dict(write=record['write'],verification=record['verification'])

        check('native_dry_run_write_and_rollback_fresh_read',lambda:harness(False))
        committed=check('native_committed_write_and_fresh_comparison',lambda:harness(True))
        if committed['status']!='PASS':raise ValueError('Cannot exercise stale-write cases without a valid committed packet')
        packet=json.loads((root/'committed.json').read_text(encoding='utf-8'))['handoff']

        def stale(kind):
            transaction=DB.Transaction(test_doc,'PLM rollback-only '+kind)
            transaction.Start()
            try:
                original=test_doc.GetElement(uid)
                candidate=deepcopy(packet)
                if kind=='changed_geometry':DB.ElementTransformUtils.MoveElement(test_doc,original.Id,DB.XYZ(0,0,1))
                elif kind=='deleted_element':test_doc.Delete(original.Id)
                elif kind=='replacement_identity':
                    copied=DB.ElementTransformUtils.CopyElement(test_doc,original.Id,DB.XYZ(0,0,2))
                    replacement=test_doc.GetElement(list(copied)[0])
                    candidate['payload']['updates'][0]['unique_id']=replacement.UniqueId
                    candidate['sha256']=checksum(candidate['payload'])
                test_doc.Regenerate()
                plan=preflight_handoff(test_doc,DB,candidate)
                if plan['can_write']:raise ValueError('Stale handoff was incorrectly accepted')
                return dict(blocked=True,errors=plan['errors'])
            finally:
                if transaction.RollBack()!=DB.TransactionStatus.RolledBack:raise ValueError('Adversarial test rollback failed')
                transaction.Dispose()

        for kind in ('changed_geometry','deleted_element','replacement_identity'):
            check(kind,lambda kind=kind:stale(kind))

        def duplicate():
            candidate=deepcopy(packet)
            candidate['payload']['updates'].append(deepcopy(candidate['payload']['updates'][0]))
            candidate['sha256']=checksum(candidate['payload'])
            try:preflight_handoff(test_doc,DB,candidate)
            except ValueError as error:
                if 'Duplicate' not in str(error):raise
                return dict(rejected=str(error))
            raise ValueError('Duplicate update accepted')

        check('duplicate_identity',duplicate)
        def final_check():
            committed_record=json.loads((root/'committed.json').read_text(encoding='utf-8'))
            fresh=extract_document(test_doc,DB,classify,selected)
            comparison=verify_round_trip(committed_record['before'],fresh,packet)
            save('after-adversarial-tests.json',fresh)
            if comparison['status']!='PASS':raise ValueError(str(comparison))
            test_doc.Save()
            return comparison
        check('rollback_restoration_and_saved_test_copy',final_check)
        if performance_source:
            def large_benchmark():
                performance_doc=None
                options=DB.OpenOptions()
                options.DetachFromCentralOption=DB.DetachFromCentralOption.DetachAndPreserveWorksets
                warnings=[]
                def performance_warnings(sender,args):
                    accessor=args.GetFailuresAccessor()
                    if accessor.GetDocument().Equals(host):return
                    for failure in accessor.GetFailureMessages():
                        if (failure.GetSeverity()==DB.FailureSeverity.Warning and
                                failure.GetDescriptionText()=='Room is not in a properly enclosed region'):
                            warnings.append(failure.GetDescriptionText())
                            accessor.DeleteWarning(failure)
                performance_handler=EventHandler[DB.Events.FailuresProcessingEventArgs](performance_warnings)
                application.FailuresProcessing+=performance_handler
                try:
                    performance_doc=host.Application.OpenDocumentFile(DB.ModelPathUtils.ConvertUserVisiblePathToModelPath(str(performance_source)),options)
                    measured=benchmark(performance_doc,'large')
                    measured['opening_warnings']=warnings
                    save('large-benchmark.json',measured)
                    if measured['extracted_objects']<=10000:raise ValueError('Supplemental model did not provide more than 10000 supported objects')
                    return measured
                finally:
                    try:application.FailuresProcessing-=performance_handler
                    finally:
                        if performance_doc is not None:performance_doc.Close(False)
            check('large_model_partitioned_extraction',large_benchmark)
        else:
            def host_large_benchmark():
                if host_benchmark['status']!='PASS' or host_benchmark['detail']['extracted_objects']<=10000:
                    raise ValueError('Large-model evidence requires more than 10000 extracted objects; supply a supplemental model')
                return host_benchmark['detail']
            check('large_model_partitioned_extraction',host_large_benchmark)
    except Exception as error:
        report['cases'].append(dict(name='controlled_native_suite',status='FAIL',error=str(error),traceback=traceback.format_exc()))
    finally:
        if conn is not None:conn.close()
        if test_doc is not None and not test_doc.Equals(host):test_doc.Close(False)
        report['status']='PASS' if report['cases'] and all(c['status']=='PASS' for c in report['cases']) else 'INCOMPLETE'
        report['finished_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        save('suite.json',report)
    return str(root)
