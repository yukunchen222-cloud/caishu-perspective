"""Package only a clean committed Git snapshot; verify every ZIP blob before writing."""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def package_release(root: Path, output: Path) -> dict:
    root, output = Path(root).resolve(), Path(output).resolve()
    if output.exists():
        raise ValueError('目标ZIP已存在；先核对，不覆盖已验收包。')
    if root == output or root in output.parents:
        raise ValueError('ZIP必须放在源仓库以外。')
    if _git(root, 'status', '--porcelain', '--untracked-files=no').strip():
        raise ValueError('受管文件有未提交变化，不能冒称提交快照包。')
    commit = _git(root, 'rev-parse', 'HEAD').decode().strip()
    entries = {}
    for item in _git(root, 'ls-tree', '-rz', '--full-tree', 'HEAD').split(b'\0'):
        if not item:
            continue
        metadata, raw_path = item.split(b'\t', 1)
        mode, kind, oid = metadata.split()
        relative = raw_path.decode('utf-8')
        path = Path(relative)
        if kind != b'blob' or mode == b'120000':
            raise ValueError('不分发子模块或符号链接：' + relative)
        if path.name in {'auth.json', 'cookies.json', 'credentials.json'} or path.name.startswith('.env'):
            raise ValueError('禁止分发凭据文件：' + relative)
        if set(path.parts) & {'.git', '__pycache__', 'artifacts'} or path.suffix == '.pyc':
            raise ValueError('禁止分发运行缓存：' + relative)
        entries[relative] = oid.decode()
    raw = _git(root, '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
               'archive', '--format=zip', '--prefix=caishu-perspective/', commit)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC未通过。')
        files = {name.removeprefix('caishu-perspective/'): name for name in archive.namelist() if not name.endswith('/')}
        if set(files) != set(entries):
            raise ValueError('ZIP文件集合与提交不一致。')
        for relative, name in files.items():
            body = archive.read(name)
            blob = hashlib.sha1(b'blob ' + str(len(body)).encode() + b'\0' + body).hexdigest()
            if blob != entries[relative]:
                raise ValueError('ZIP正文与提交不一致：' + relative)
    with output.open('xb') as stream:
        stream.write(raw)
    return {'commit': commit, 'file_count': len(entries), 'crc': 'passed',
            'all_git_blobs_match': True, 'zip': str(output), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(package_release(args.root, args.output), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
