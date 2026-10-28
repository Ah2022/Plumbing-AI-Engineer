"""Recompare native execution evidence without Revit or manual database editing."""
import argparse
import json
from pathlib import Path
from bim.round_trip import verify_round_trip


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('record',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.record.stat().st_size>20*1024*1024:parser.error('Partition native execution records larger than 20 MB')
    if args.output and args.output.resolve()==args.record.resolve():parser.error('Output must not overwrite source evidence')
    record=json.loads(args.record.read_text(encoding='utf-8-sig'))
    if record.get('schema_version')!='revit-native-harness-1' or record.get('write',{}).get('status')!='COMMITTED':
        parser.error('A committed native harness record is required; dry run cannot verify a round trip')
    result=verify_round_trip(record['before'],record['after'],record['handoff'])
    text=json.dumps(result,indent=2,allow_nan=False)
    if args.output:args.output.write_text(text,encoding='utf-8')
    print(text)
    return 0 if result['status']=='PASS' else 1


if __name__=='__main__':raise SystemExit(main())
