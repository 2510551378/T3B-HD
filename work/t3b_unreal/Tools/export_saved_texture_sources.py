"""Read-only export of saved Texture2D source art from a fresh UE commandlet.

TextureExporterPNG uses ExportTextureSourceGeneric, not a GPU screenshot.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

import unreal

PROJECT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())).resolve()
REPORT = Path(os.environ['T3B_TEXTURE_REPORT']).resolve()
if not REPORT.is_relative_to(PROJECT/'Validation'):
    raise RuntimeError('Texture export report outside Validation')
MANIFEST = PROJECT/'Content/SourceData/manifest.json'
FROZEN = PROJECT/'Validation/asset_import_runs/0fac54502ca140d4accffa2e5a7bc618/ue_editor_asset_creation.json'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def must(value, message):
    if not value:
        raise RuntimeError(message)


def check_packages(items):
    for item in items:
        path = Path(item['file']).resolve()
        must(path.is_relative_to(PROJECT/'Content'), 'Frozen package escapes Content')
        must(path.stat().st_size == item['bytes'] and digest(path) == item['sha256'], f'Frozen package changed: {path}')


def main():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    frozen = json.loads(FROZEN.read_text(encoding='utf-8-sig'))
    must(manifest['schema'] == 't3b-ue-source-bundle/v1' and len(manifest['textures']) == 76, 'Unexpected manifest')
    must(frozen['asset_creation_completed'] and len(frozen['saved_assets']) == 161, 'Frozen creation incomplete')
    check_packages(frozen['saved_assets'])
    folder = REPORT.parent/'texture_sources'
    folder.mkdir(exist_ok=False)
    rows = []
    for index, item in enumerate(manifest['textures']):
        texture = unreal.EditorAssetLibrary.load_asset(item['asset'])
        must(isinstance(texture, unreal.Texture2D), f'Not a saved Texture2D: {item["asset"]}')
        target = folder/f'{index:03d}_{texture.get_name()}.png'
        task = unreal.AssetExportTask()
        task.set_editor_property('object', texture)
        task.set_editor_property('filename', str(target))
        task.set_editor_property('exporter', unreal.TextureExporterPNG())
        task.set_editor_property('automated', True)
        task.set_editor_property('prompt', False)
        task.set_editor_property('replace_identical', False)
        must(unreal.Exporter.run_asset_export_task(task), f'PNG export failed: {item["asset"]}')
        must(not list(task.get_editor_property('errors')), f'PNG exporter reported errors: {item["asset"]}')
        must(target.is_file() and target.stat().st_size > 0, f'Missing texture source export: {target}')
        rows.append({'asset':item['asset'], 'export_file':str(target), 'export_png_sha256':digest(target),
                     'source_file':str(PROJECT/'Content/SourceData'/item['file']),
                     'width':item['width'], 'height':item['height'], 'rgba_sha256':item['rgba_sha256']})
    check_packages(frozen['saved_assets'])
    return {'schema':'t3b-ue-texture-source-export/v1', 'export_completed':True,
            'textures_exported':len(rows), 'rows':rows, 'package_files_unchanged':161,
            'manifest_sha256':digest(MANIFEST), 'frozen_import_report_sha256':digest(FROZEN),
            'exporter_script_sha256':digest(Path(__file__)), 'ue_render_verified':False,
            'scope':'Saved Texture2D source art only; no GPU sampling, shader, pixel rendering or gameplay acceptance.'}


if __name__ == '__main__':
    result = {'schema':'t3b-ue-texture-source-export/v1', 'export_completed':False}
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = main()
    except Exception as error:
        result['error'] = str(error)
        raise
    finally:
        result.update({'run_id':os.environ['T3B_TEXTURE_RUN_ID'], 'process_id':os.getpid(),
                       'started_utc':started, 'finished_utc':datetime.now(timezone.utc).isoformat(),
                       'project_file':unreal.Paths.get_project_file_path(),
                       'engine_version':unreal.SystemLibrary.get_engine_version(),
                       'command_line':unreal.SystemLibrary.get_command_line()})
        REPORT.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
