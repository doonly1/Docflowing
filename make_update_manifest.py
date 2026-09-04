"""生成更新清单 version.json。

客户端通过它知道「有没有新版本、去哪下、下完该是什么样子」。
sha256 在这里算好写进清单，客户端下载后校验，杜绝被改写/截断的安装包。

用法::

    python make_update_manifest.py \
        --file dist/Docflowing_Setup.exe \
        --output dist/version.json \
        --repo doonly1/Docflowing \
        --notes "修复 FTS 搜索崩溃；新增回收站批量还原"

生成的清单由 CI 作为 Release 资产上传，客户端默认访问
``https://github.com/<repo>/releases/latest/download/version.json``
（稳定地址，不需要调 api.github.com）。
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import version  # noqa: E402


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def build_manifest(repo, version_str, notes, min_required, installer, portable,
                   mirror_base=None, channel=None):
    packages = {}

    if installer and os.path.isfile(installer):
        name = os.path.basename(installer)
        url = f'https://github.com/{repo}/releases/download/v{version_str}/{name}'
        pkg = {
            'url': url,
            'sha256': sha256_of(installer),
            'size': os.path.getsize(installer),
        }
        if mirror_base:
            pkg['mirror'] = mirror_base.rstrip('/') + '/' + name
        packages['installer'] = pkg

    if portable and os.path.isfile(portable):
        name = os.path.basename(portable)
        url = f'https://github.com/{repo}/releases/download/v{version_str}/{name}'
        pkg = {
            'url': url,
            'sha256': sha256_of(portable),
            'size': os.path.getsize(portable),
        }
        if mirror_base:
            pkg['mirror'] = mirror_base.rstrip('/') + '/' + name
        packages['portable'] = pkg

    if not packages:
        raise SystemExit('错误：没有可用的安装包文件，请检查 --file / --portable-file')

    manifest = {
        'version': version_str,
        'channel': channel or version.UPDATE_CHANNEL,
        'notes': notes or '',
        'published_at': datetime.now(timezone.utc).strftime('%Y-%m-%d'),
        'packages': packages,
    }
    if min_required:
        manifest['min_required'] = min_required
    return manifest


def main():
    parser = argparse.ArgumentParser(description='生成 Docflowing 更新清单 version.json')
    parser.add_argument('--file', help='安装包路径（NSIS 生成的 Setup.exe）')
    parser.add_argument('--portable-file', help='便携版压缩包路径（可选）')
    parser.add_argument('--output', default='dist/version.json', help='输出路径')
    parser.add_argument('--repo', default='doonly1/Docflowing', help='GitHub 仓库 owner/repo')
    parser.add_argument('--version', default=None, help='版本号，默认取 version.py')
    parser.add_argument('--notes', default='', help='更新说明')
    parser.add_argument('--notes-file', default=None, help='从文件读取更新说明')
    parser.add_argument('--min-required', default='', help='低于此版本强制更新')
    parser.add_argument('--mirror', default='', help='镜像基地址（国内加速用）')
    parser.add_argument('--channel', default=None, help='发布通道，默认取 version.py')
    args = parser.parse_args()

    notes = args.notes
    if args.notes_file and os.path.isfile(args.notes_file):
        with open(args.notes_file, 'r', encoding='utf-8') as f:
            notes = f.read().strip()

    ver = args.version or version.format_version()

    manifest = build_manifest(
        repo=args.repo,
        version_str=ver,
        notes=notes,
        min_required=args.min_required,
        installer=args.file,
        portable=args.portable_file,
        mirror_base=args.mirror or None,
        channel=args.channel,
    )

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write('\n')

    print(f'[manifest] 已生成 {args.output}')
    print(f'[manifest] 版本 {ver}  通道 {manifest["channel"]}')
    for key, pkg in manifest['packages'].items():
        print(f'[manifest]   {key}: {pkg["size"] / 1024 / 1024:.1f} MB  sha256={pkg["sha256"][:16]}…')


if __name__ == '__main__':
    main()
