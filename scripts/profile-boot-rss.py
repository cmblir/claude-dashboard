"""Profile boot-time memory allocators.

Run: python3 scripts/profile-boot-rss.py
Reports tracemalloc top allocators per file/line and process RSS.
Standalone script. Not imported anywhere.
"""
import os
import sys
import time
import tracemalloc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

tracemalloc.start(25)

# Phase 1: import core modules (mirrors what server.py imports at startup)
t_imp_start = time.time()
from server import db  # noqa: E402
from server import config  # noqa: E402
from server import utils  # noqa: E402
from server import sessions  # noqa: E402
from server import mcp  # noqa: E402
from server import ai_providers  # noqa: E402
from server import ai_keys  # noqa: E402
from server import workflows  # noqa: E402
from server import routes  # noqa: E402
from server import prefs  # noqa: E402
from server import system  # noqa: E402
from server import nav_catalog  # noqa: E402
from server import translations  # noqa: E402
imp_ms = (time.time() - t_imp_start) * 1000
print(f"core imports: {imp_ms:.1f}ms")

snap_after_import = tracemalloc.take_snapshot()

# Phase 2: db init
t0 = time.time()
try:
    if hasattr(db, "_db_init"):
        db._db_init()
except Exception as e:
    print(f"db init skipped: {e}")
print(f"db_init: {(time.time()-t0)*1000:.1f}ms")

# Phase 3: session indexing
t0 = time.time()
try:
    if hasattr(sessions, "index_all_sessions"):
        sessions.index_all_sessions()
    elif hasattr(sessions, "_index_all_sessions"):
        sessions._index_all_sessions()
except Exception as e:
    print(f"sessions index error: {e}")
print(f"index_all_sessions: {(time.time()-t0)*1000:.1f}ms")

# Phase 4: mcp warmup (optional)
t0 = time.time()
try:
    if hasattr(mcp, "warmup_caches"):
        mcp.warmup_caches()
    elif hasattr(mcp, "warm_caches"):
        mcp.warm_caches()
except Exception as e:
    print(f"mcp warmup skipped: {e}")
print(f"mcp warmup: {(time.time()-t0)*1000:.1f}ms")

snap = tracemalloc.take_snapshot()

print("\n=== Top allocators by FILE (post-everything) ===")
for stat in snap.statistics("filename")[:20]:
    fr = stat.traceback[0]
    print(f"  {stat.size/1024/1024:7.2f} MB  {stat.count:>8} blocks  {fr.filename}")

print("\n=== Top allocators by LINE (post-everything) ===")
for stat in snap.statistics("lineno")[:30]:
    fr = stat.traceback[0]
    print(f"  {stat.size/1024/1024:7.2f} MB  {stat.count:>8} blocks  {fr.filename}:{fr.lineno}")

print("\n=== Top allocators by FILE (import phase only) ===")
for stat in snap_after_import.statistics("filename")[:15]:
    fr = stat.traceback[0]
    print(f"  {stat.size/1024/1024:7.2f} MB  {stat.count:>8} blocks  {fr.filename}")

import resource  # noqa: E402
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
print(f"\nMaxRSS raw: {rss}")
if sys.platform == "darwin":
    print(f"  macOS bytes -> {rss/1024/1024:.0f} MB")
else:
    print(f"  linux KB    -> {rss/1024:.0f} MB")

try:
    import subprocess
    out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(os.getpid())]).decode().strip()
    print(f"  ps RSS:     {int(out)/1024:.0f} MB")
except Exception as e:
    print(f"  ps RSS unavailable: {e}")
