"""Product counts for the navigation tree.

A category card says "Browse N items". The only N a shopper means by that is
"everything I'll find under here" — a direct-children count reads as an empty
category whenever the stock happens to sit one level deeper, which is the normal
shape of a catalog: `Medicine ▸ Year 2 ▸ Pathology ▸ General Pathology ▸ …`,
with products only at the leaves.

So counts roll up the tree: a category reports the published products at or
beneath it, and a parent's number is always at least its children's.

Two queries regardless of catalog size — one for the per-category totals, one
for the parent links — then the roll-up happens in memory. Doing it per node
would be a query per category per page.
"""

from django.db.models import Count

from .models import Category, Product


def subtree_product_counts():
    """{category_id: published products at or beneath that category}."""
    direct = dict(
        Product.objects.filter(is_published=True)
        .values("category_id")
        .annotate(n=Count("id"))
        .values_list("category_id", "n")
    )
    parents = dict(Category.objects.values_list("id", "parent_id"))

    totals = dict.fromkeys(parents, 0)
    for category_id, count in direct.items():
        node = category_id
        seen = set()
        # Walk to the root, adding this category's products to every ancestor.
        # `seen` guards against a cycle: Category.clean() rejects one on save,
        # but a bad row must not spin a request forever.
        while node is not None and node not in seen:
            seen.add(node)
            totals[node] = totals.get(node, 0) + count
            node = parents.get(node)
    return totals
