"""Animus Mod & Outfit Manager - command-line interface.

Commands:
  list          show installed mods
  apply  PACK   apply a .jmod package
  remove NAME   restore backups and remove a package
  discover      list .jmod packages found in mods/packages
  game           show the detected game folder

Exit code 0 on success, 1 on error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .core import DEFAULT_GAME_DIR, Loader, LoaderError
from .outfits import OutfitError
from .packs import CATEGORY_OUTFIT, CATEGORY_WEAPON, PackError, PackManager, NEXUS_GAME_ID
from .nexus import NexusClient, NexusError


def _loader(args) -> Loader:
    return Loader(game_dir=Path(args.game_dir))


def cmd_discover(args) -> int:
    loader = _loader(args)
    packages = loader.discover_packages()
    if not packages:
        print("No .jmod packages found in:", loader.packages_dir)
        return 0
    for path in packages:
        try:
            pkg = loader.read_package(path)
            print(f"{path.name}  ->  {pkg.name} {pkg.version} by {pkg.author}")
        except LoaderError as exc:
            print(f"{path.name}  ->  INVALID: {exc}")
    return 0


def cmd_list(args) -> int:
    loader = _loader(args)
    records = loader.list_installed()
    if not records:
        print("No mods installed.")
        return 0
    for rec in records:
        state = "enabled" if rec.enabled else "disabled"
        print(f"{rec.name} {rec.version} [{state}] priority={rec.priority}")
    return 0


def cmd_pack(args) -> int:
    loader = _loader(args)
    path = Path(args.package).resolve()
    if not path.is_file():
        print(f"ERROR: package not found: {path}", file=sys.stderr)
        return 1
    try:
        backups = loader.apply(path, priority=args.priority)
    except LoaderError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(f"Applied {path.name}")
    for entry in backups:
        if entry.get("mode") == "loose-file":
            print(f"  copied -> {entry.get('dest')} backup={entry.get('backup') or 'none'}")
        else:
            print(f"  patched {entry.get('forge')} occurrence {entry.get('occurrence',0)} backup={entry.get('backup')}")
    return 0


def cmd_remove(args) -> int:
    loader = _loader(args)
    restored = loader.remove(args.name)
    if not restored:
        print(f"No installed mod named '{args.name}'.")
    else:
        for path in restored:
            print(f"Restored {path}")
    # Also delete the package file so the mod fully disappears.
    path = None
    for p in loader.discover_packages():
        try:
            if loader.read_package(p).name == args.name:
                path = p
                break
        except LoaderError:
            continue
    if path and path.is_file():
        path.unlink()
        print(f"Removed package file '{path.name}'.")
        return 0
    return 0 if restored else 1


def cmd_remove_files(args) -> int:
    loader = _loader(args)
    try:
        loader.remove(args.name)
    except Exception:
        pass
    path = None
    for p in loader.discover_packages():
        try:
            if loader.read_package(p).name == args.name:
                path = p
                break
        except LoaderError:
            continue
    if path and path.is_file():
        path.unlink()
        print(f"Removed package file for '{args.name}'.")
        return 0
    print(f"No package file found for '{args.name}'.")
    return 1


def cmd_game_dir(args) -> int:
    loader = _loader(args)
    print(loader.game_dir)
    return 0


def _packs(args) -> PackManager:
    return PackManager(game_dir=Path(args.game_dir))


def _print_packs(packs, active, label: str) -> None:
    if not packs:
        print(f"No {label} imported yet.")
        return
    for p in packs:
        mark = " *active*" if p.id == active else ""
        print(f"{p.id}  {p.name}{mark}  ({len(p.slots)} slot(s))")


def cmd_pack_list(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        active = mgr.active_pack_id()
        packs = mgr.list_packs(category=category)
        _print_packs(packs, active, label)
        return 0
    return run


def cmd_pack_import(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        pack = mgr.import_pack(Path(args.folder).resolve(), name=args.name,
                               category=category)
        print(f"Imported '{pack.name}' ({len(pack.slots)} slot(s)): {pack.id}")
        if args.activate:
            result = mgr.switch_pack(pack.id)
            print(f"Activated. {result}")
        return 0
    return run


def cmd_pack_switch(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        result = mgr.switch_pack(args.id if args.id != "none" else None)
        print(f"Active {label} now: {mgr.active_pack_id()}")
        if result.get("reverted"):
            print("  reverted previous: " + json.dumps(result["reverted"]))
        if result.get("applied"):
            print("  applied: " + json.dumps(result["applied"]))
        return 0
    return run


def cmd_pack_revert(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        if getattr(args, "pack_id", None):
            result = mgr.revert_pack(args.pack_id)
            print(f"Reverted {result['reverted']} write(s) for {args.pack_id}.")
            for i in result.get("issues", []):
                print(f"  NOTE: {i}")
            return 0
        result = mgr.revert_all()
        print(f"Reverted {result['reverted']} write(s) to vanilla.")
        return 0
    return run


def cmd_pack_enable(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        mgr.set_enabled(args.id, args.enabled)
        print(f"{'Enabled' if args.enabled else 'Disabled'} {args.id} (staged, not applied).")
        if args.apply:
            res = mgr.apply_staged(category)
            print(f"Applied staged set: {res} ")
        return 0
    return run


def cmd_pack_apply(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        res = mgr.apply_staged(category)
        if not res.get("packs"):
            print(f"No enabled {label} packs to apply.")
            return 0
        print(f"Applied {len(res['packs'])} enabled {label} pack(s) "
              f"({res['external_mips']} mips, {res['materials']} materials).")
        for c in res.get("conflicts", []):
            print(f"  CONFLICT slot {c['slot']}: '{c['loser']}' overridden by "
                  f"'{c['winner']}'")
        return 0
    return run


def cmd_pack_order(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        mgr.set_order(category, args.order.split(","))
        print(f"New order (bottom = highest priority): {args.order}")
        return 0
    return run


def cmd_pack_set_nexus(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        mgr.set_nexus(args.id, args.mod_id, game_id=args.game_id or NEXUS_GAME_ID,
                      version=args.version)
        print(f"Linked {args.id} -> Nexus mod {args.mod_id} (game {args.game_id or NEXUS_GAME_ID}).")
        return 0
    return run


def cmd_pack_check_updates(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        results = mgr.check_updates()
        cats = [r for r in results if r["category"] == category]
        if not cats:
            print(f"No {label} packs with Nexus ids.")
            return 0
        for r in cats:
            if r.get("error"):
                print(f"{r['name']}: ERROR {r['error']}")
            elif r["mod_id"] is None:
                print(f"{r['name']}: no nexus id set")
            elif r["has_update"]:
                print(f"UPDATE {r['name']}: {r['current']} -> {r['latest']}  (nexus {r['mod_id']})")
            else:
                print(f"   up-to-date  {r['name']}: {r['latest']}")
        return 0
    return run


def cmd_mod_set_nexus(args) -> int:
    loader = _loader(args)
    loader.set_nexus(args.name, args.mod_id, game_id=args.game_id or NEXUS_GAME_ID,
                     version=args.version)
    print(f"Linked mod '{args.name}' -> Nexus mod {args.mod_id}.")
    return 0


def cmd_mod_check_updates(args) -> int:
    loader = _loader(args)
    results = loader.check_updates()
    found = False
    for r in results:
        if r.get("mod_id") is None:
            continue
        found = True
        if r.get("error"):
            print(f"{r['name']}: ERROR {r['error']}")
        elif r.get("has_update"):
            print(f"UPDATE {r['name']}: {r.get('current') or '?'} -> {r['latest']}  (nexus {r['mod_id']})")
        else:
            print(f"   up-to-date  {r['name']}: {r.get('latest')}")
    if not found:
        print("No mods have a Nexus id set. Use 'mod-set-nexus <name> <mod-id>'.")
    return 0


def cmd_mod_update(args) -> int:
    print("Direct Nexus downloads are disabled. Download the update in your browser, "
          "then use the manager's Update action to select the replacement archive.")
    return 0


def cmd_pack_install(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        result = mgr.install(Path(args.pack).resolve(), name=args.name, category=category)
        pack = result["pack"]
        print(f"Installed '{pack.name}' ({len(pack.slots)} slot(s)) and activated.")
        return 0
    return run


def cmd_pack_status(category: str, label: str) -> callable:
    def run(args) -> int:
        mgr = _packs(args)
        status = mgr.status()
        print(f"Active {label} : {status['active'] or 'none (vanilla)'}")
        print(f"Journal       : {'present' if status['journal'] else 'clean'}")
        print(f"Forge present : {status['forge_exists']}")
        return 0
    return run


def cmd_outfit_list(args) -> int:
    return cmd_pack_list(CATEGORY_OUTFIT, "outfits")(args)


def cmd_outfit_import(args) -> int:
    return cmd_pack_import(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_switch(args) -> int:
    return cmd_pack_switch(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_install(args) -> int:
    return cmd_pack_install(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_revert(args) -> int:
    return cmd_pack_revert(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_status(args) -> int:
    return cmd_pack_status(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_enable(args) -> int:
    return cmd_pack_enable(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_apply(args) -> int:
    return cmd_pack_apply(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_order(args) -> int:
    return cmd_pack_order(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_set_nexus(args) -> int:
    return cmd_pack_set_nexus(CATEGORY_OUTFIT, "outfit")(args)


def cmd_outfit_check_updates(args) -> int:
    return cmd_pack_check_updates(CATEGORY_OUTFIT, "outfit")(args)


def _add_pack_group(sub, name: str, help_text: str,
                    list_fn, import_fn, install_fn, switch_fn, revert_fn, status_fn,
                    enable_fn, apply_fn, order_fn, set_nexus_fn, check_fn) -> None:
    group = sub.add_parser(name, help=help_text)
    group_sub = group.add_subparsers(dest=f"{name}_command", required=True)

    l = group_sub.add_parser("list", help=f"List imported {name}s")
    l.set_defaults(func=list_fn)

    i = group_sub.add_parser("import", help=f"Import a {name} pack folder/archive")
    i.add_argument("folder")
    i.add_argument("--name")
    i.set_defaults(func=import_fn)

    inst = group_sub.add_parser("install", help=f"One-click install + activate a {name} pack")
    inst.add_argument("pack")
    inst.add_argument("--name")
    inst.set_defaults(func=install_fn)

    s = group_sub.add_parser("switch", help=f"Switch active {name} ('none' to clear)")
    s.add_argument("id")
    s.set_defaults(func=switch_fn)

    e = group_sub.add_parser("enable", help=f"Enable/disable a {name} (staged)")
    e.add_argument("id")
    e.add_argument("enabled", choices=["on", "off"])
    e.add_argument("--apply", action="store_true", help="Also apply the staged set")
    e.set_defaults(func=enable_fn)

    a = group_sub.add_parser("apply", help=f"Apply all enabled {name}s (merged)")
    a.set_defaults(func=apply_fn)

    o = group_sub.add_parser("order", help="Set order (comma-separated ids, bottom wins)")
    o.add_argument("order")
    o.set_defaults(func=order_fn)

    sn = group_sub.add_parser("set-nexus", help="Attach a Nexus mod id to a pack (for update checks)")
    sn.add_argument("id")
    sn.add_argument("mod_id", type=int)
    sn.add_argument("--game-id", type=int, default=None)
    sn.add_argument("--version", default=None, help="Installed version to compare against")
    sn.set_defaults(func=set_nexus_fn)

    up = group_sub.add_parser("check-updates", help=f"Check {name} packs on Nexus for updates")
    up.set_defaults(func=check_fn)

    v = group_sub.add_parser("revert", help=f"Revert a {name} pack (or all if no id) to vanilla")
    v.add_argument("pack_id", nargs="?", default=None)
    v.set_defaults(func=revert_fn)

    st = group_sub.add_parser("status", help=f"Show {name} manager status")
    st.set_defaults(func=status_fn)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Animus Mod & Outfit Manager")
    parser.add_argument(
        "--game-dir",
        default=str(DEFAULT_GAME_DIR),
        help="Path to the Black Flag Resynced game folder",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    d = sub.add_parser("discover", help="List .jmod packages")
    d.set_defaults(func=cmd_discover)

    l = sub.add_parser("list", help="List installed mods")
    l.set_defaults(func=cmd_list)

    p = sub.add_parser("pack", help="Apply a .jmod package")
    p.add_argument("package")
    p.add_argument("--priority", type=int, default=0)
    p.set_defaults(func=cmd_pack)

    r = sub.add_parser("remove", help="Remove an installed mod")
    r.add_argument("name")
    r.set_defaults(func=cmd_remove)

    rf = sub.add_parser("remove-files", help="Delete a mod's package file (full removal)")
    rf.add_argument("name")
    rf.set_defaults(func=cmd_remove_files)

    g = sub.add_parser("game-dir", help="Show the game folder")
    g.set_defaults(func=cmd_game_dir)

    mn = sub.add_parser("mod-set-nexus", help="Attach a Nexus mod id to a .jmod mod")
    mn.add_argument("name")
    mn.add_argument("mod_id", type=int)
    mn.add_argument("--game-id", type=int, default=None)
    mn.add_argument("--version", default=None)
    mn.set_defaults(func=cmd_mod_set_nexus)

    mc = sub.add_parser("mod-check-updates", help="Check .jmod mods on Nexus for updates")
    mc.set_defaults(func=cmd_mod_check_updates)

    mu = sub.add_parser("mod-update", help="Explain the manual Nexus update workflow")
    mu.add_argument("name")
    mu.set_defaults(func=cmd_mod_update)

    _add_pack_group(sub, "outfit", "Outfit manager commands",
                    cmd_outfit_list, cmd_outfit_import,
                    cmd_outfit_install, cmd_outfit_switch,
                    cmd_outfit_revert, cmd_outfit_status,
                    cmd_outfit_enable, cmd_outfit_apply, cmd_outfit_order,
                    cmd_outfit_set_nexus, cmd_outfit_check_updates)
    _add_pack_group(sub, "weapon", "Weapon manager commands",
                    cmd_pack_list(CATEGORY_WEAPON, "weapons"),
                    cmd_pack_import(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_install(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_switch(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_revert(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_status(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_enable(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_apply(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_order(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_set_nexus(CATEGORY_WEAPON, "weapon"),
                    cmd_pack_check_updates(CATEGORY_WEAPON, "weapon"))

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (LoaderError, OutfitError, PackError, NexusError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
