#!/usr/bin/env python3
"""Add public guides to the already allowlisted source ZIP, with internal hashes."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'v\d+\.\d+\.\d+(?:-[A-Za-z0-9.-]+)?', args.version):
        raise SystemExit('Invalid version')
    folder = args.output
    name = 'HP-ZGX-Nano-' + args.version
    source_name = 'hp-zgx-fury-showcase-' + args.version
    additions = {
        'START-HERE.pdf': (folder / 'HP-ZGX-Nano-Quickstart.pdf').read_bytes(),
        'COMPLETE-GUIDE.pdf': (folder / 'HP-ZGX-Nano-Complete-Guide.pdf').read_bytes(),
        'PRESENTER-CARD.pdf': (ROOT / 'docs/stage/PRESENTER_CARD.pdf').read_bytes(),
        'RELEASE-NOTES.md': (ROOT / 'docs/NANO_RELEASE_NOTES.md').read_bytes(),
        'README.txt': (
            'HP ZGX NANO EXPERIENCE — ' + args.version + '\n\n'
            '1. Read START-HERE.pdf (three pages).\n'
            '2. Use a vendor-provisioned Ubuntu 24.04 ARM64 / GB10 Nano with 128 GB memory.\n'
            '3. Reserve 200 GiB free disk and internet for ~95.9 GiB of models plus dependencies.\n'
            '4. Open Terminal inside ' + source_name + ' and run:\n'
            '   chmod +x install.sh launch.sh showcase ops/nano-desktop.sh\n'
            '   ./install.sh\n'
            '   ./launch.sh free\n'
            '5. Open http://127.0.0.1:18808/free on the Nano.\n\n'
            'Run install/launch as a normal user, not sudo. Only one model stack at a time.\n'
            'This kit contains source and public guides, not preloaded models or private sessions.\n'
            'Check the outer release file against GitHub SHA256SUMS. For extracted kit contents,\n'
            'run sha256sum -c KIT-SHA256SUMS from this folder.\n\n'
            'Release: https://github.com/Navigatedhustle/hp-zgx-fury-showcase/releases/tag/' + args.version + '\n'
            'Community demonstration; not official HP/NVIDIA product support.\n'
        ).encode(),
    }
    output = folder / (name + '-share-kit.zip')
    hashes = {}
    with zipfile.ZipFile(folder / (source_name + '.zip')) as source, zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as kit:
        for item in source.infolist():
            path = PurePosixPath(item.filename)
            if path.is_absolute() or '..' in path.parts or path.parts[0] != source_name:
                raise SystemExit('Unexpected source path')
            content = source.read(item)
            entry = zipfile.ZipInfo(name + '/' + item.filename, date_time=(2026, 11, 18, 0, 0, 0))
            entry.external_attr = item.external_attr
            entry.compress_type = zipfile.ZIP_DEFLATED
            kit.writestr(entry, content)
            hashes[item.filename] = hashlib.sha256(content).hexdigest()
        for filename, content in additions.items():
            kit.writestr(name + '/' + filename, content)
            hashes[filename] = hashlib.sha256(content).hexdigest()
        kit.writestr(name + '/KIT-SHA256SUMS', ''.join(hashes[key] + '  ' + key + '\n' for key in sorted(hashes)))
    # A release checksum file lists only complete public assets, never itself.
    sidecars = ['HP-ZGX-Nano-Quickstart.pdf', 'HP-ZGX-Nano-Complete-Guide.pdf',
                'HP-ZGX-Nano-Presenter-Card.pdf', source_name + '.zip', source_name + '.tar.gz', output.name]
    (folder / 'HP-ZGX-Nano-Presenter-Card.pdf').write_bytes(additions['PRESENTER-CARD.pdf'])
    (folder / 'SHA256SUMS').write_text(''.join(hashlib.sha256((folder / key).read_bytes()).hexdigest() + '  ' + key + '\n' for key in sidecars))
    print(output)


if __name__ == '__main__':
    main()
