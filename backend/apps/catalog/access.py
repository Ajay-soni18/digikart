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
    having an account, matching the old behaviour for free notes.
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

    An unpublished file is closed to everyone but staff, so a half-prepared
    upload can't leak to buyers who already own the product.
    """
    if not product_file.is_published and not (
        user and getattr(user, "is_authenticated", False) and user.is_staff
    ):
        return False
    return product_unlocked(user, product_file.product)
