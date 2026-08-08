"""Central place that decides whether a user may access catalog content.

Mirrors the discipline of the old apps/content/access.py: one module owns the
rule, every endpoint defers to it, and the frontend is never trusted. The
signed-URL endpoint re-runs `file_accessible` on every single request.

The rule: you must be signed in to reach ANY product file (free ones included —
free means "no payment", not "no account"). Beyond that a product is open if it
is marked free, the user is staff (admin preview), or the user owns it directly
or through a bundle (see entitlements.py).

Categories deliberately have no access function. They are navigation only and
can never grant anything; a product's access never depends on where it sits.
"""

from .entitlements import owns_product


def product_unlocked(user, product):
    """Return True if `user` may open `product`'s files.

    Authentication is required first — even a free product is gated behind
    having an account.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if product.is_free:
        return True
    if user.is_staff:  # admins can preview everything
        return True
    return owns_product(user, product)


def file_accessible(user, product_file):
    """Return True if `user` may fetch this specific file.

    `is_published` controls *listing*, not ownership. Someone who has paid keeps
    what they paid for even after the product or the file is withdrawn from
    sale — unpublishing is how you take something off the shelf, not how you
    repossess it.

    This deliberately matches `product_unlocked`, which also ignores
    `is_published`. The two used to disagree (an unpublished product stayed
    readable, an unpublished file did not), which meant the same admin toggle
    had two different meanings depending on which row it was set on.

    The cost is that attaching a half-finished file to an already-sold product
    exposes it to existing buyers immediately. That is the milder failure: the
    alternative silently revokes access people paid for.
    """
    return product_unlocked(user, product_file.product)
