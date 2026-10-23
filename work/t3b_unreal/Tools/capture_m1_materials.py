"""Opt-in game startup capture driver; install hook only in a disposable test copy."""
import hashlib
import json
import os
from pathlib import Path
import time

import unreal

OUTPUT = Path(os.environ["T3B_M1_CAPTURE_DIR"]).resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
shots = [
    ("front_legacy", 0, (200, -380, 92), (0, 0, 92)),
    ("front_ordered", 1, (200, -380, 92), (0, 0, 92)),
    ("back_legacy", 0, (0, 440, 92), (0, 0, 92)),
    ("back_ordered", 1, (0, 440, 92), (0, 0, 92)),
    ("weapon_legacy", 0, (-90, -160, 140), (0, 0, 130)),
    ("weapon_ordered", 1, (-90, -160, 140), (0, 0, 130)),
]
state = {"index": 0, "stage": "prepare", "after": time.time() + 4, "rows": []}


def tick(_delta):
    if time.time() < state["after"]:
        return
    world = unreal.find_object(None, "/Game/T3B/Maps/M1_SourceReplay.M1_SourceReplay")
    if world is None:
        return
    if state["index"] == len(shots):
        (OUTPUT / "capture.json").write_text(json.dumps({"schema": "t3b-m1-material-capture/v1",
            "engine": unreal.SystemLibrary.get_engine_version(), "samples": state["rows"],
            "scope": "actual UE viewport A/B; visual review still required"}, indent=2), encoding="utf-8")
        unreal.unregister_slate_post_tick_callback(handle)
        unreal.SystemLibrary.execute_console_command(world, "quit")
        return
    name, ordered, location, target = shots[state["index"]]
    image = OUTPUT / (name + ".png")
    if state["stage"] == "prepare":
        pc = unreal.GameplayStatics.get_player_controller(world, 0)
        pawn = pc.get_controlled_pawn() if pc else None
        if pawn is None:
            return
        location, target = unreal.Vector(*location), unreal.Vector(*target)
        rotation = unreal.MathLibrary.find_look_at_rotation(location, target)
        pawn.set_actor_location_and_rotation(location, rotation, False, True)
        pc.set_control_rotation(rotation)
        for command in ("T3B.Replay.Pause 1", "T3B.Replay.Seek 0.65", "fov 40", "r.AntiAliasingMethod 0",
                        "r.ScreenPercentage 100", "r.T3BGE.DepthWrite 1",
                        f"T3B.Replay.OriginalMaterials {ordered}"):
            unreal.SystemLibrary.execute_console_command(world, command)
        # Full scene A/B is retained; choose a side front camera outside the enemy.
        state.update(stage="capture", after=time.time() + 1.5)
    elif state["stage"] == "capture":
        unreal.SystemLibrary.execute_console_command(world, f"HighResShot 1 filename={image.as_posix()}")
        state.update(stage="save", after=time.time() + 1)
    elif image.is_file():
        state["rows"].append({"name": name, "ordered": ordered, "source_seconds": 0.65,
            "camera": list(shots[state["index"]][2]), "target": list(shots[state["index"]][3]),
            "file": str(image), "sha256": hashlib.sha256(image.read_bytes()).hexdigest()})
        state.update(index=state["index"] + 1, stage="prepare", after=time.time() + .2)


handle = unreal.register_slate_post_tick_callback(tick)
