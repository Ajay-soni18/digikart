"""Caching for the navigation tree.

The tree is the highest-fanout read in the app — every page's navigation wants
it — and it is read far more often than it changes. Serializing it walks the
whole hierarchy recursively, so its cost grows with the catalog while its
content does not change between admin edits.

**Version-keyed invalidation, not a TTL.** A TTL forces a choice between stale
navigation and a cache that rarely hits. Instead the cache key embeds a version
counter that any catalog write bumps: readers immediately miss and recompute,
and no stale tree is ever served. Nothing has to be enumerated and deleted, which
matters because the key varies (today only trivially, later by locale or
experiment).

The tree carries no per-user data — no prices, no `unlocked` flags — so one
cached copy is correct for everyone, signed in or not. If a per-user field is
ever added to `CategoryNodeSerializer`, this cache must be reconsidered; the
test suite asserts that shape so the mistake can't be made quietly.

Redis is configured to fail soft (see settings.base), so a cache outage degrades
to recomputing the tree rather than erroring.
"""

from django.core.cache import cache

_VERSION_KEY = "catalog:nav:version"
_TREE_KEY = "catalog:nav:tree:v{version}"

# Long, because correctness comes from the version bump rather than expiry. This
# is only a backstop against a key that somehow outlives its version counter.
_TREE_TTL_SECONDS = 60 * 60 * 24


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
    cache.set(_TREE_KEY.format(version=_version()), payload, _TREE_TTL_SECONDS)


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
