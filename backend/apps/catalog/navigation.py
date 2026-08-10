"""Caching for the navigation tree.

The tree is the highest-fanout read in the app — every page's navigation wants
it — and it is read far more often than it changes. Serializing it walks the
whole hierarchy recursively, so its cost grows with the catalog while its
content does not change between admin edits.

**Version-keyed invalidation, with a TTL backstop sized to the cache backend.**
The key embeds a counter that any catalog write bumps, so a write is reflected
immediately and nothing has to be enumerated and deleted.

That alone is only sufficient when the cache is *shared*. On a host without
Redis, Django falls back to LocMemCache, which lives inside a single process:
a write handled by one worker bumps only that worker's counter, so every other
worker keeps serving its own stale tree — and a write from outside the web
process entirely (a management command, a shell, a second instance) reaches
none of them. This was not theoretical; it shipped, and the first deploy served
an empty navigation tree while the database plainly had categories.

So the TTL is chosen from the backend: long when the counter is shared and
authoritative, short when it cannot be trusted to travel. Staleness is then
bounded by seconds rather than forever, without giving up the cache on the
free tier where it matters most.

The tree carries no per-user data — no prices, no `unlocked` flags — so one
cached copy is correct for everyone, signed in or not. If a per-user field is
ever added to `CategoryNodeSerializer`, this cache must be reconsidered; the
test suite asserts that shape so the mistake can't be made quietly.

Redis is configured to fail soft (see settings.base), so a cache outage degrades
to recomputing the tree rather than erroring.
"""

from django.conf import settings
from django.core.cache import cache

_VERSION_KEY = "catalog:nav:version"
_TREE_KEY = "catalog:nav:tree:v{version}"

# Shared cache: the version bump is authoritative, so expiry is just a backstop
# against a key outliving its counter.
_SHARED_TTL_SECONDS = 60 * 60 * 24
# Per-process cache: the bump may never reach this worker, so expiry is the only
# thing that will. Short enough that an admin edit shows up while they are still
# looking at the page.
_LOCAL_TTL_SECONDS = 30


def _cache_is_shared():
    """True when every process sees the same cache (Redis and friends).

    LocMemCache is per-process by definition. Anything backed by a network
    service is shared, so a version bump written by one worker is visible to all.
    """
    backend = settings.CACHES.get("default", {}).get("BACKEND", "")
    return "locmem" not in backend.lower() and "dummy" not in backend.lower()


def _ttl():
    return _SHARED_TTL_SECONDS if _cache_is_shared() else _LOCAL_TTL_SECONDS


def _version():
    """Current tree version, seeded on first use.

    `cache.add` (not `set`) so two concurrent readers seeding the key at once
    can't reset each other's counter.
    """
    version = cache.get(_VERSION_KEY)
    if version is None:
        cache.add(_VERSION_KEY, 1)
        version = cache.get(_VERSION_KEY) or 1
    return version


def get_cached_tree():
    """The serialized tree, or None on a miss."""
    return cache.get(_TREE_KEY.format(version=_version()))


def set_cached_tree(payload):
    cache.set(_TREE_KEY.format(version=_version()), payload, _ttl())


def invalidate():
    """Bump the version so every reader misses.

    Uses `incr` where available so simultaneous edits can't land on the same new
    version; falls back to a plain set for cache backends without atomic incr
    (the local-memory one used in tests supports it, but be defensive).
    """
    try:
        cache.incr(_VERSION_KEY)
    except ValueError:
        # Key absent — seeding it is enough, since nothing was cached under it.
        cache.set(_VERSION_KEY, 1)
