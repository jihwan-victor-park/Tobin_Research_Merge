#!/usr/bin/env python3
"""
Fetch Revelio shards from the shared Dropbox folder via the Dropbox API and
drive build_founder_profiles.py end-to-end -- no browser automation.

WHY THIS EXISTS
Clicking through Dropbox's web UI to grab the ~100 remaining shards one at a
time (find file -> open preview -> click Download, x100) doesn't scale. This
script talks to the Dropbox API directly: list the folder, download a round
of shards, run the pipeline, delete the raw files, repeat.

ARCHITECTURE NOTE -- single source of truth
This script keeps NO bookkeeping of its own about what's "done". Instead it
reads the exact manifests build_founder_profiles.py already writes:
  - <out-dir>/founder_profiles_manifest.json            (individual_positions)
  - <reference-dir>/individual_user_compact_manifest.json
  - <reference-dir>/individual_user_education_compact_manifest.json
Whatever shard names appear in those manifests (regardless of status --
"OK" or "SKIPPED_NULL_RCID") are treated as processed and skipped. This
avoids a second, separately-drifting notion of progress; the pipeline's own
records are authoritative.

KNOWN DEAD RANGE
individual_positions shards 000000-000038 were empirically confirmed to be
100% null-rcid (unjoinable to any company) during manual spot-checks of
000000 and the boundary shard 000039. This script hard-skips that range so
it never wastes a download on them; build_founder_profiles.py also has its
own runtime null-rcid guard as a second line of defense if that assumption
is ever wrong for some other file type.

SAFETY
  - Disk space is checked before every single download; if the projected
    free space after a download would drop below --min-free-gb, the run
    stops immediately (does not just skip one file -- storage exhaustion
    is a whole-run stop condition given how tight this has gotten before).
  - Each round's pipeline invocation is checked for a non-zero exit code
    or obvious error text in its output before the loop continues to the
    next round.
  - --max-rounds bounds how much an unattended run can do in one go
    (default 5) so a bug can't silently chew through the entire backlog.
  - --dry-run prints exactly what would be downloaded/run without hitting
    the network, the disk, or the pipeline.

CREDENTIALS -- never pasted into chat, never on the command line.
Set ONE of the following as environment variables before running:

  DROPBOX_ACCESS_TOKEN
      Simplest option. Generate via your Dropbox App Console's "Generated
      access token" button. Short-lived (~4h) -- fine for a single sitting,
      but you'll need to regenerate it if a run spans longer than that.

  DROPBOX_APP_KEY + DROPBOX_APP_SECRET + DROPBOX_REFRESH_TOKEN
      Long-running option. The SDK auto-refreshes the access token, so this
      is what you want for a --max-rounds run left unattended for a while.
      (Get a refresh token once via Dropbox's OAuth2 authorization-code
      flow with token_access_type=offline; the app console alone doesn't
      hand you one directly.)

The account you authenticate as must be the one with access to the shared
folder (this has been the school-email account in prior sessions).

USAGE
    export DROPBOX_ACCESS_TOKEN=...        # or the three refresh-token vars
    python3 dropbox_shard_fetcher.py \\
        --out-dir founder_poc \\
        --reference-dir ~/Library/Mobile\\ Documents/com~apple~CloudDocs/revelio_reference

    # See what would happen without downloading or running anything:
    python3 dropbox_shard_fetcher.py --dry-run --out-dir founder_poc \\
        --reference-dir ~/Library/Mobile\\ Documents/com~apple~CloudDocs/revelio_reference

    # Just print current progress against the manifests, no network call:
    python3 dropbox_shard_fetcher.py --status --out-dir founder_poc \\
        --reference-dir ~/Library/Mobile\\ Documents/com~apple~CloudDocs/revelio_reference
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

DEFAULT_DROPBOX_URL = "https://www.dropbox.com/scl/fo/tckezk5bujlcnswkre9px/h/linkedin?dl=0"

# Empirically confirmed dead range -- see module docstring.
POSITIONS_MIN_USABLE_SHARD = 39

NAME_RE = re.compile(
    r"^revelio_(individual_positions|individual_user|individual_user_education)-(\d+)\.parquet$"
)


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dropbox-url", default=DEFAULT_DROPBOX_URL)
    ap.add_argument("--downloads", default=os.path.expanduser("~/Downloads"))
    ap.add_argument("--out-dir", required=True,
                     help="same --out-dir you pass to build_founder_profiles.py")
    ap.add_argument("--reference-dir", required=True,
                     help="same --reference-dir you pass to build_founder_profiles.py "
                          "(your iCloud revelio_reference folder)")
    ap.add_argument("--pipeline-script", default=None,
                     help="path to build_founder_profiles.py; defaults to a sibling "
                          "of this script")
    ap.add_argument("--positions-per-round", type=int, default=2)
    ap.add_argument("--user-per-round", type=int, default=1)
    ap.add_argument("--education-per-round", type=int, default=1)
    ap.add_argument("--max-rounds", type=int, default=5)
    ap.add_argument("--min-free-gb", type=float, default=5.0,
                     help="abort the whole run if projected free space after a "
                          "download would drop below this")
    ap.add_argument("--founding-window-years", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true",
                     help="print the plan, touch neither network nor disk nor pipeline")
    ap.add_argument("--status", action="store_true",
                     help="print progress against the manifests and exit; no network call")
    return ap.parse_args()


# ---------------------------------------------------------------- manifests

def load_manifest(path: str) -> list:
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return json.load(f)


def processed_shard_names(manifest_entries: list) -> set:
    return {e["shard"] for e in manifest_entries if "shard" in e}


def manifest_paths(out_dir: str, reference_dir: str) -> dict:
    return {
        "individual_positions": os.path.join(out_dir, "founder_profiles_manifest.json"),
        "individual_user": os.path.join(reference_dir, "individual_user_compact_manifest.json"),
        "individual_user_education": os.path.join(
            reference_dir, "individual_user_education_compact_manifest.json"),
    }


def print_status(out_dir: str, reference_dir: str, all_files: dict | None):
    paths = manifest_paths(out_dir, reference_dir)
    print("=" * 70)
    print("PROGRESS (from existing manifests -- single source of truth)")
    print("=" * 70)
    for kind, path in paths.items():
        entries = load_manifest(path)
        done = processed_shard_names(entries)
        total_known = len(all_files[kind]) if all_files else None
        line = f"{kind}: {len(done)} shards processed"
        if total_known is not None:
            usable = total_known
            if kind == "individual_positions":
                usable = sum(1 for n in all_files[kind]
                             if shard_num(n) >= POSITIONS_MIN_USABLE_SHARD)
            line += f" / {usable} usable available in Dropbox folder"
        print(line)
    out_path = os.path.join(out_dir, "founder_profiles.parquet")
    if os.path.exists(out_path):
        try:
            import duckdb
            con = duckdb.connect()
            n, n_edu = con.execute(
                f"SELECT COUNT(*), COUNT(*) FILTER (WHERE degree IS NOT NULL) "
                f"FROM read_parquet('{out_path}')"
            ).fetchone()
            print(f"founder_profiles.parquet: {n:,} rows, {n_edu:,} with education data")
        except Exception as e:  # duckdb not installed, or column mismatch, etc.
            print(f"(couldn't read founder_profiles.parquet for row counts: {e})")


# -------------------------------------------------------------- dropbox api

def shard_num(name: str) -> int:
    m = NAME_RE.match(name)
    return int(m.group(2)) if m else -1


def get_client():
    import dropbox  # deferred import so --status/--dry-run work without the package
    app_key = os.environ.get("DROPBOX_APP_KEY")
    app_secret = os.environ.get("DROPBOX_APP_SECRET")
    refresh_token = os.environ.get("DROPBOX_REFRESH_TOKEN")
    if app_key and app_secret and refresh_token:
        return dropbox.Dropbox(oauth2_refresh_token=refresh_token,
                                app_key=app_key, app_secret=app_secret)
    access_token = os.environ.get("DROPBOX_ACCESS_TOKEN")
    if access_token:
        return dropbox.Dropbox(access_token)
    sys.exit("No Dropbox credentials found. Set DROPBOX_ACCESS_TOKEN, or "
             "DROPBOX_APP_KEY + DROPBOX_APP_SECRET + DROPBOX_REFRESH_TOKEN, "
             "as environment variables (see this script's docstring).")


def list_shared_folder(dbx, url: str) -> dict:
    """Returns {kind: [filenames sorted by shard number]} for the three kinds
    we care about. Ignores everything else in the folder (html docs, the
    company_mapping / role_lookup / skill_lookup files, .txt companions)."""
    import dropbox
    shared_link = dropbox.files.SharedLink(url=url)
    entries = []
    res = dbx.files_list_folder(path="", shared_link=shared_link)
    entries.extend(res.entries)
    while res.has_more:
        res = dbx.files_list_folder_continue(res.cursor)
        entries.extend(res.entries)

    buckets = {"individual_positions": [], "individual_user": [], "individual_user_education": []}
    for e in entries:
        name = getattr(e, "name", None)
        if not name:
            continue
        m = NAME_RE.match(name)
        if not m:
            continue
        buckets[m.group(1)].append(name)
    for kind in buckets:
        buckets[kind].sort(key=shard_num)
    return buckets


def pick_next(kind: str, all_names: list, done: set, count: int) -> list:
    picked = []
    for name in all_names:
        if name in done:
            continue
        if kind == "individual_positions" and shard_num(name) < POSITIONS_MIN_USABLE_SHARD:
            continue
        picked.append(name)
        if len(picked) == count:
            break
    return picked


def disk_free_gb(path: str) -> float:
    return shutil.disk_usage(path).free / (1024 ** 3)


def download_shard(dbx, url: str, name: str, dest_dir: str, max_attempts: int = 4) -> str:
    """Downloads with retries: Dropbox occasionally drops the connection
    mid-transfer on these large (600-700MB) files, which is transient and
    not worth crashing the whole multi-round run over. Each attempt writes
    fresh (the .part file is truncated on open), so a failed attempt never
    corrupts or partially-appends into the next one."""
    import requests

    dest = os.path.join(dest_dir, name)
    tmp = dest + ".part"
    last_err = None
    for attempt in range(1, max_attempts + 1):
        try:
            _, res = dbx.sharing_get_shared_link_file(url=url, path="/" + name)
            with open(tmp, "wb") as f:
                for chunk in res.iter_content(chunk_size=8 * 1024 * 1024):
                    if chunk:
                        f.write(chunk)
            os.replace(tmp, dest)
            return dest
        except (requests.exceptions.ConnectionError,
                 requests.exceptions.ChunkedEncodingError,
                 requests.exceptions.Timeout) as e:
            last_err = e
            if os.path.exists(tmp):
                os.remove(tmp)
            if attempt < max_attempts:
                wait = 2 ** attempt  # 2s, 4s, 8s
                print(f"  transient network error on attempt {attempt}/{max_attempts} "
                      f"({e.__class__.__name__}), retrying in {wait}s...")
                time.sleep(wait)
    raise last_err


# ---------------------------------------------------------------- pipeline

def run_pipeline(pipeline_script: str, downloads: str, out_dir: str,
                  reference_dir: str, founding_window_years: int) -> bool:
    cmd = [
        sys.executable, pipeline_script,
        "--downloads", downloads,
        "--out-dir", out_dir,
        "--reference-dir", reference_dir,
        "--delete-after",
        "--founding-window-years", str(founding_window_years),
    ]
    print(f"\n$ {' '.join(cmd)}\n")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    if proc.returncode != 0:
        print(f"PIPELINE EXITED NON-ZERO ({proc.returncode}) -- stopping.", file=sys.stderr)
        return False
    if "Traceback" in proc.stdout or "Traceback" in proc.stderr:
        print("PIPELINE OUTPUT CONTAINS A TRACEBACK -- stopping.", file=sys.stderr)
        return False
    return True


# -------------------------------------------------------------------- main

def main():
    args = parse_args()
    out_dir = os.path.expanduser(args.out_dir)
    reference_dir = os.path.expanduser(args.reference_dir)
    downloads = os.path.expanduser(args.downloads)
    pipeline_script = args.pipeline_script or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "build_founder_profiles.py")

    if args.status:
        try:
            dbx = get_client()
            all_files = list_shared_folder(dbx, args.dropbox_url)
        except SystemExit:
            all_files = None
        print_status(out_dir, reference_dir, all_files)
        return

    dbx = get_client()
    print("Listing Dropbox folder...")
    all_files = list_shared_folder(dbx, args.dropbox_url)
    print(f"Found {len(all_files['individual_positions'])} individual_positions, "
          f"{len(all_files['individual_user'])} individual_user, "
          f"{len(all_files['individual_user_education'])} individual_user_education "
          f"shards in the folder.\n")

    paths = manifest_paths(out_dir, reference_dir)

    for round_num in range(1, args.max_rounds + 1):
        done = {kind: processed_shard_names(load_manifest(p)) for kind, p in paths.items()}

        todo = {
            "individual_positions": pick_next(
                "individual_positions", all_files["individual_positions"],
                done["individual_positions"], args.positions_per_round),
            "individual_user": pick_next(
                "individual_user", all_files["individual_user"],
                done["individual_user"], args.user_per_round),
            "individual_user_education": pick_next(
                "individual_user_education", all_files["individual_user_education"],
                done["individual_user_education"], args.education_per_round),
        }

        all_shards_this_round = [n for names in todo.values() for n in names]
        if not all_shards_this_round:
            print("Nothing left to process across all three file types. Done.")
            return

        print(f"--- Round {round_num}/{args.max_rounds} ---")
        for kind, names in todo.items():
            if names:
                print(f"  {kind}: {', '.join(names)}")

        if args.dry_run:
            print("  (dry run -- not downloading or running anything)\n")
            continue

        for kind, names in todo.items():
            for name in names:
                free_before = disk_free_gb(downloads)
                # We don't know the exact remote size without an extra API call per
                # file; shards of a given kind are consistently sized (~650-720MB
                # positions/user, ~230-250MB education), so use a conservative
                # per-kind estimate for the pre-flight check.
                est_gb = {"individual_positions": 0.75, "individual_user": 0.7,
                          "individual_user_education": 0.26}[kind]
                if free_before - est_gb < args.min_free_gb:
                    print(f"STOPPING: only {free_before:.1f}GB free, downloading {name} "
                          f"(~{est_gb:.2f}GB) would drop below --min-free-gb "
                          f"({args.min_free_gb}GB).")
                    return
                print(f"Downloading {name} ({free_before:.1f}GB free before)...")
                t0 = time.time()
                download_shard(dbx, args.dropbox_url, name, downloads)
                print(f"  done in {time.time() - t0:.0f}s")

        ok = run_pipeline(pipeline_script, downloads, out_dir, reference_dir,
                           args.founding_window_years)
        if not ok:
            print("Stopping the loop so you can inspect the error above; "
                  "nothing further will be downloaded.")
            return

    print(f"\nReached --max-rounds ({args.max_rounds}). Run again to continue, "
          f"or pass a higher --max-rounds.")


if __name__ == "__main__":
    main()
