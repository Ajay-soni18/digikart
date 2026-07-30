"""Entitlement queries — the hierarchical access rule lives here.

A chapter is owned if the user holds an active entitlement for the chapter
itself, OR its unit, OR its subject. A note is owned if the user bought that note
directly, OR holds any of those higher-level entitlements. Buying higher up the
tree unlocks everything beneath it, including items added later.
"""

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from apps.content.models import Chapter, Subject, Unit

from .models import Entitlement


def _ct(model):
    return ContentType.objects.get_for_model(model)


def user_owns_chapter(user, chapter):
    """True if `user` has access to `chapter`'s notes via any level."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    q = (
        Q(content_type=_ct(Chapter), object_id=chapter.id)
        | Q(content_type=_ct(Unit), object_id=chapter.unit_id)
        | Q(content_type=_ct(Subject), object_id=chapter.unit.subject_id)
    )
    return Entitlement.objects.filter(user=user, is_active=True).filter(q).exists()


def user_owns_object(user, obj):
    """True if the user already holds an entitlement for this exact object."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return Entitlement.objects.filter(
        user=user, is_active=True, content_type=_ct(type(obj)), object_id=obj.id
    ).exists()


def user_owns_note(user, note):
    """True if `user` may access `note` — bought directly, or via any higher level
    (its chapter, unit or subject)."""
    if not user or not getattr(user, "is_authenticated", False):
        return False
    return user_owns_object(user, note) or user_owns_chapter(user, note.chapter)


def grant(user, obj, order=None):
    """Idempotently grant an entitlement for `obj` to `user`."""
    Entitlement.objects.get_or_create(
        user=user,
        content_type=_ct(type(obj)),
        object_id=obj.id,
        defaults={"order": order, "is_active": True},
    )
