"""Run inside UnrealEditor-Cmd with -run=pythonscript -script="..." .

Creates original-resolution textures, preview materials and an empty replay
map. It does not certify original render states or a playable UE battle.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path
from datetime import datetime, timezone

import unreal


PROJECT = Path(unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir()))
DATA = PROJECT/"Content/SourceData"
MANIFEST = DATA/"manifest.json"
OUTPUT = Path(os.environ.get("T3B_EDITOR_REPORT_PATH", str(PROJECT/"Validation/ue_editor_asset_creation.json"))).resolve()
if not OUTPUT.is_relative_to((PROJECT/"Validation").resolve()):
    raise RuntimeError("Editor report must stay inside this project's Validation directory")
LIB = unreal.MaterialEditingLibrary
ASSETS = unreal.EditorAssetLibrary


def object_parts(object_path):
    package = object_path.split(".", 1)[0]
    directory, name = package.rsplit("/", 1)
    return package, directory, name


def must(ok, message):
    if not ok:
        raise RuntimeError(message)


def expression(material, cls, x, y):
    node = LIB.create_material_expression(material, cls, x, y)
    must(node is not None, f"Cannot create material node {cls}")
    return node


def link(source, output, destination, pin):
    # If input display names vary, use the editor's own reflected names.
    candidates = [pin]
    # MaterialEditingLibrary uses MaterialGraphNode::GetShortenPinName:
    # the texture expression's Coordinates input is exposed as UVs.
    aliases = {"Coordinates": ["UVs"], "AGreaterThanB": ["A > B"],
               "AEqualsB": ["A == B"], "ALessThanB": ["A < B"]}
    candidates.extend(aliases.get(pin, []))
    for name in candidates:
        if LIB.connect_material_expressions(source, output, destination, name):
            return
    raise RuntimeError(f"Cannot connect {destination.get_class().get_name()} input {pin}")


def constant(material, value, x, y):
    node = expression(material, unreal.MaterialExpressionConstant, x, y)
    node.set_editor_property("r", float(value))
    return node


def multiply(material, a, out_a, b, out_b, x, y):
    node = expression(material, unreal.MaterialExpressionMultiply, x, y)
    link(a, out_a, node, "A")
    link(b, out_b, node, "B")
    return node


def alpha_pass(material, alpha, reference):
    # The source tests alpha > reference/255, not a generic .333 opacity cut.
    zero, one = constant(material, 0, -450, 600), constant(material, 1, -450, 700)
    ref = constant(material, reference/255., -450, 500)
    node = expression(material, unreal.MaterialExpressionIf, -200, 450)
    node.set_editor_property("equals_threshold", 0.)
    link(alpha, "", node, "A")
    link(ref, "", node, "B")
    link(one, "", node, "AGreaterThanB")
    link(zero, "", node, "AEqualsB")
    link(zero, "", node, "ALessThanB")
    return node


def import_texture(resource, tools):
    source = DATA/resource["file"]
    must(hashlib.sha256(source.read_bytes()).hexdigest() == resource["container"]["sha256"],
         f"Staged texture identity changed: {source}")
    package, directory, name = object_parts(resource["asset"])
    if not ASSETS.does_asset_exist(package):
        factory = unreal.TextureFactory()
        factory.set_editor_property("no_alpha", False)
        factory.set_editor_property("create_material", False)
        task = unreal.AssetImportTask()
        task.set_editor_property("filename", str(source))
        task.set_editor_property("destination_path", directory)
        task.set_editor_property("destination_name", name)
        task.set_editor_property("automated", True)
        task.set_editor_property("replace_existing", False)
        task.set_editor_property("save", False)
        task.set_editor_property("factory", factory)
        tools.import_asset_tasks([task])
    texture = ASSETS.load_asset(package)
    must(isinstance(texture, unreal.Texture2D), f"Texture import failed: {package}")
    existing = ASSETS.get_metadata_tag(texture, "T3BSourceRGBA")
    must(not existing or existing == resource["rgba_sha256"], f"Texture provenance differs: {package}")
    texture.set_editor_property("srgb", False)
    texture.set_editor_property("compression_no_alpha", False)
    texture.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_VECTOR_DISPLACEMENTMAP)
    texture.set_editor_property("mip_gen_settings", unreal.TextureMipGenSettings.TMGS_NO_MIPMAPS)
    texture.set_editor_property("filter", unreal.TextureFilter.TF_BILINEAR)
    texture.set_editor_property("address_x", unreal.TextureAddress.TA_WRAP)
    texture.set_editor_property("address_y", unreal.TextureAddress.TA_WRAP)
    ASSETS.set_metadata_tag(texture, "T3BSourceRGBA", resource["rgba_sha256"])
    must(ASSETS.save_loaded_asset(texture), f"Cannot save texture {package}")
    return texture


def material_signature(item):
    # Map/report/commandlet compatibility edits must not invalidate previously
    # saved recipes. Material graph or helper changes still fail closed.
    graph_functions = (expression, link, constant, multiply, alpha_pass,
                       material_signature, create_material)
    recipe = {"version": "source-unlit-graph-v1", "item": item,
              "graph_source": "\n".join(inspect.getsource(function) for function in graph_functions)}
    return hashlib.sha256(json.dumps(recipe, sort_keys=True).encode("utf-8")).hexdigest()


def create_material(item, textures, tools):
    signature = material_signature(item)
    package, directory, name = object_parts(item["asset"])
    if ASSETS.does_asset_exist(package):
        material = ASSETS.load_asset(package)
        must(ASSETS.get_metadata_tag(material, "T3BMaterialSignature") == signature,
             f"Existing material differs; inspect or remove the generated asset before rebuilding: {package}")
        return material
    material = tools.create_asset(name, directory, unreal.Material, unreal.MaterialFactoryNew())
    must(material is not None, f"Cannot create {package}")
    blend = bool(item["blend"])
    masked = bool(item.get("alpha_test", True)) and not blend
    material.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    material.set_editor_property("two_sided", not bool(item["cull"]))
    material.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT if blend else
                                 unreal.BlendMode.BLEND_MASKED if masked else unreal.BlendMode.BLEND_OPAQUE)
    material.set_editor_property("opacity_mask_clip_value", .5)
    tex = expression(material, unreal.MaterialExpressionTextureSample, -800, -100)
    tex.set_editor_property("texture", textures[item["texture_asset"]])
    tex.set_editor_property("sampler_type", unreal.MaterialSamplerType.SAMPLERTYPE_LINEAR_COLOR)
    tex.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_FROM_TEXTURE_ASSET)
    uv = expression(material, unreal.MaterialExpressionTextureCoordinate, -1200, -100)
    uv.set_editor_property("u_tiling", item["su"])
    uv.set_editor_property("v_tiling", item["sv"])
    offset = expression(material, unreal.MaterialExpressionConstant2Vector, -1200, 100)
    offset.set_editor_property("r", item["ou"])
    offset.set_editor_property("g", item["ov"])
    add = expression(material, unreal.MaterialExpressionAdd, -1000, -100)
    link(uv, "", add, "A")
    link(offset, "", add, "B")
    link(add, "", tex, "Coordinates")
    color = expression(material, unreal.MaterialExpressionVertexColor, -800, 200)
    # VertexColor's first output has an empty OutputName and an RGB mask;
    # ConnectMaterialExpressions accepts "" for that output, not "RGB".
    rgb = multiply(material, tex, "RGB", color, "", -500, -100)
    scale = constant(material, item["rgb_scale"], -500, -250)
    scaled = multiply(material, rgb, "", scale, "", -200, -100)
    must(LIB.connect_material_property(scaled, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR), "Emissive connection failed")
    alpha = multiply(material, tex, "A", color, "A", -500, 300)
    test = alpha_pass(material, alpha, item["alpha_ref"]) if item.get("alpha_test", True) else None
    if masked:
        must(LIB.connect_material_property(test, "", unreal.MaterialProperty.MP_OPACITY_MASK), "Mask connection failed")
    elif blend:
        opacity = multiply(material, alpha, "", test, "", 100, 350) if test else alpha
        must(LIB.connect_material_property(opacity, "", unreal.MaterialProperty.MP_OPACITY), "Opacity connection failed")
    # Main-pass depth writes on source translucent draws remain unsupported.
    # CustomDepth and velocity depth are deliberately not used as substitutes.
    LIB.layout_material_expressions(material)
    LIB.recompile_material(material)
    ASSETS.set_metadata_tag(material, "T3BMaterialSignature", signature)
    must(ASSETS.save_loaded_asset(material), f"Cannot save material {package}")
    return material


def saved_asset(object_path, extension):
    package, _, _ = object_parts(object_path)
    must(package.startswith("/Game/"), f"Unexpected non-project asset {package}")
    path = (PROJECT/"Content"/package[len("/Game/"):]).with_suffix(extension).resolve()
    must(path.is_relative_to((PROJECT/"Content").resolve()), f"Saved asset escapes Content: {path}")
    must(path.is_file() and path.stat().st_size > 0, f"Saved package is not present on disk: {path}")
    return {"object_path": object_path, "package": package, "file": str(path),
            "bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def create_replay_map():
    # Local UE5.8.3 FileHelpers.h/.cpp exposes these static script APIs.
    # Unlike direct LevelEditorSubsystem use, this wrapper checks optional
    # editor-mode availability before GEditor->NewMap and never asks to save.
    package = "/Game/T3B/Maps/M1_SourceReplay"
    loader = unreal.EditorLoadingAndSavingUtils
    if ASSETS.does_asset_exist(package):
        world = loader.load_map(package)
    else:
        world = loader.new_blank_map(False)
    must(world is not None, "Cannot load/create commandlet replay world")
    must(loader.save_map(world, package), "Cannot save commandlet replay map")
    return package


def main():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    must(manifest["schema"] == "t3b-ue-source-bundle/v1", "Unexpected source bundle schema")
    tools = unreal.AssetToolsHelpers.get_asset_tools()
    imported = {item["asset"]: import_texture(item, tools) for item in manifest["textures"]}
    material_items = manifest["scene"]["materials"] + [item for actor in manifest["actors"] for item in actor["materials"]]
    must(all(item["wrap_s"] == 0 and item["wrap_t"] == 0 for item in material_items),
         "This import supports the observed repeat samplers only; no silent clamp substitution")
    for item in material_items:
        create_material(item, imported, tools)
    map_package = create_replay_map()
    saved = [saved_asset(item["asset"], ".uasset") for item in manifest["textures"]]
    saved += [saved_asset(item["asset"], ".uasset") for item in material_items]
    saved.append(saved_asset(map_package+".M1_SourceReplay", ".umap"))
    return {"schema": "t3b-ue-editor-asset-creation/v1", "asset_creation_completed": True,
            "textures": len(imported), "materials": len(material_items), "map": map_package,
            "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "saved_assets": saved,
            "material_recipe_signatures": {item["asset"]: material_signature(item) for item in material_items},
            "material_signature_policy": "material item plus graph/helper source; excludes map/report/wrapper changes",
            "unsupported_render_states": manifest["unsupported_render_states"],
            "source_render_states_equivalent": False, "ue_render_verified": False,
            "limits": ["Editor asset creation does not certify shader compilation, pixel identity or runtime gameplay.",
                       "Original translucent main-pass depth writes and source draw ordering require a separate verified render path.",
                       "Output color/tonemapping and winding require actual matched-view rendering."]}


if __name__ == "__main__":
    started = datetime.now(timezone.utc).isoformat()
    result = {"schema": "t3b-ue-editor-asset-creation/v1", "asset_creation_completed": False}
    try:
        result = main()
    except Exception as error:
        result["error"] = str(error)
        raise
    finally:
        result["run_id"] = os.environ.get("T3B_EDITOR_RUN_ID")
        result["process_id"] = os.getpid()
        result["started_utc"] = started
        result["finished_utc"] = datetime.now(timezone.utc).isoformat()
        result["project_file"] = unreal.Paths.get_project_file_path()
        result["project_directory"] = str(PROJECT)
        result["engine_version"] = unreal.SystemLibrary.get_engine_version()
        result["command_line"] = unreal.SystemLibrary.get_command_line()
        result["headless_asset_creation_only"] = True
        result["ue_cpp_build_executed"] = False
        result["ue_gameplay_executed"] = False
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
