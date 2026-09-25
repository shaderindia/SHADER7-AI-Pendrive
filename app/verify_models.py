"""Read-only verification of every model against its stored SHA-256 manifest."""
from pathlib import Path
import hashlib
import json
import re
import sys

def main():
    root = Path(__file__).resolve().parent.parent / 'models'
    manifests = root / 'manifests'
    if not manifests.is_dir():
        print('Missing models/manifests folder. Keep models beside the app folder.')
        return 1
    blobs = {}
    failed = 0
    count = 0
    for manifest in manifests.rglob('*'):
        if not manifest.is_file():
            continue
        count += 1
        try:
            document = json.loads(manifest.read_text(encoding='utf-8'))
            for layer in [document['config'], *document['layers']]:
                digest = layer['digest']
                if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                    raise ValueError('Invalid digest')
                blobs[digest] = layer['size']
        except (ValueError, KeyError, OSError) as error:
            print('FAIL manifest:', manifest.relative_to(root), error)
            failed += 1
    print(f'Checking {count} models and {len(blobs)} unique files. This may take several minutes on USB.', flush=True)
    for index, (digest, size) in enumerate(blobs.items(), 1):
        path = root / 'blobs' / digest.replace(':', '-')
        valid = False
        try:
            if path.stat().st_size == size:
                with path.open('rb') as blob:
                    valid = hashlib.file_digest(blob, 'sha256').hexdigest() == digest[7:]
        except OSError:
            pass
        print(f'{index}/{len(blobs)} {"OK" if valid else "FAIL"} {path.name}', flush=True)
        failed += not valid
    if count == 0 or not blobs:
        print('FAIL: no models were found.')
        return 1
    print('All model files passed.' if failed == 0 else f'{failed} checks failed. Preserve a backup and restore the failed files before using those models.')
    return int(failed != 0)

if __name__ == '__main__':
    sys.exit(main())
