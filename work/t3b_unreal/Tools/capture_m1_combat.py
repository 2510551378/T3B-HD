"""Opt-in actual UE gameplay screenshot driver, in a disposable test project.

Use T3B_COMBAT_CAPTURE_DIR and a temporary Content/Python/init_unreal.py hook.
All actions call the normal combat API; this is separate from the deterministic
smoke which freezes enemy AI to test source geometry reproducibly.
"""
import hashlib
import json
import os
from pathlib import Path
import time

import unreal

OUTPUT = Path(os.environ["T3B_COMBAT_CAPTURE_DIR"]).resolve()
OUTPUT.mkdir(parents=True, exist_ok=True)
state = {"stage": 0, "after": time.monotonic() + 3, "rows": []}


def command(world, text):
    unreal.SystemLibrary.execute_console_command(world, text)


def capture(world, name):
    path = OUTPUT / (name + ".png")
    command(world, f"HighResShot 1 filename={path.as_posix()}")
    state["rows"].append({"name": name, "file": str(path)})


def tick(_delta):
    if time.monotonic() < state["after"]:
        return
    world = unreal.find_object(None, "/Game/T3B/Maps/M1_SourceReplay.M1_SourceReplay")
    if world is None:
        return
    directors = unreal.GameplayStatics.get_all_actors_of_class(world, unreal.T3BCombatDirector)
    if not directors:
        return
    director = directors[0]
    stage = state["stage"]
    delay = .6
    if stage == 0:
        director.reset_combat()
        command(world, "r.ScreenPercentage 100")
        director.toggle_lock()
    elif stage == 1:
        capture(world, "M1_locked")
    elif stage == 2:
        director.begin_overdive()
        delay = .7
    elif stage == 3:
        capture(world, "M1_overdive")
        delay = 1.1
    elif stage == 4:
        director.set_fire_held(True)
        delay = .06
    elif stage == 5:
        director.set_fire_held(False)
        capture(world, "M1_hit")
        delay = .4
    elif stage == 6:
        director.set_fire_held(True)
        delay = 1.2
    elif stage == 7:
        director.set_fire_held(False)
        director.write_combat_probe()
        capture(world, "M1_clear")
    else:
        for row in state["rows"]:
            path = Path(row["file"])
            row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        (OUTPUT / "capture.json").write_text(json.dumps({
            "schema": "t3b-m1-combat-capture/v1", "engine": unreal.SystemLibrary.get_engine_version(),
            "scope": "actual D3D11 normal gameplay with enemy AI enabled; visual review required",
            "samples": state["rows"],
        }, indent=2), encoding="utf-8")
        unreal.unregister_slate_post_tick_callback(handle)
        command(world, "quit")
        return
    state.update(stage=stage + 1, after=time.monotonic() + delay)


handle = unreal.register_slate_post_tick_callback(tick)
