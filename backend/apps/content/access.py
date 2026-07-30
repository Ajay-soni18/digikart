"""
Central place that decides whether a user may access notes.

The rule: you must be signed in to read ANY note (free ones included — free
means "no payment", not "no account"). Beyond that there are two granularities,
and `note_unlocked` is the one the file delivery endpoint enforces:

  - chapter_unlocked — whole-chapter access: a free chapter is open to every
    signed-in user; an admin previews everything; otherwise the user must hold an
    active entitlement for the chapter, its unit, or its subject (hierarchical
    access — see apps/payments/entitlements.py).
  - note_unlocked — a single note: free note, OR whole-chapter access (above),
    OR the user bought this exact note on its own.

Keeping this in one place means every endpoint (the note context endpoint, the
signed-URL endpoint, and the student content tree) shares exactly one access rule
— we never trust the frontend to decide. The signed-URL endpoint re-runs the
per-note check on every request before it will sign a URL.
"""


def chapter_unlocked(user, chapter):
    """Return True if `user` may read the notes for `chapter`.

    Authentication is required first — even free notes are gated behind having
    an account, so an anonymous visitor can never read them (the note endpoints
    also require auth; this keeps the single access rule consistent with that).
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if chapter.is_free:
        return True
    if user.is_staff:  # admins can preview everything
        return True
    # Hierarchical purchase check: chapter / unit / subject entitlement.
    # Imported lazily to avoid a content<->payments import cycle.
    from apps.payments.entitlements import user_owns_chapter

    return user_owns_chapter(user, chapter)


def note_unlocked(user, note):
    """Return True if `user` may read this individual note.

    Auth is required first (a free note still needs an account). Then access is
    granted if the note itself is free, OR the user has whole-chapter access (a
    free chapter / admin preview / a chapter-, unit- or subject-level entitlement
    — see `chapter_unlocked`), OR the user bought this exact note on its own.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if note.is_free:
        return True
    if chapter_unlocked(user, note.chapter):
        return True
    # Bought this single note directly. Lazy import avoids a content<->payments cycle.
    from apps.payments.entitlements import user_owns_object

    return user_owns_object(user, note)
