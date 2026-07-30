"""
Site-wide, admin-editable content: the standalone legal/info pages plus the
help/contact copy.

This is a singleton (always one row, pk=1) so the admin edits "the site" rather
than juggling records. The admin can change any of these fields anytime.

NOTE: The rest of the site's copy — homepage hero/highlights, byline, owner
name, footer tagline, social channel links, and the SEO meta description — is
NOT admin-editable. It is hardcoded in the frontend (client/src: pages/Landing.jsx,
components/Footer.jsx, index.html). Update it there if it ever changes.
"""

from django.db import models


class SiteContent(models.Model):
    # --- Standalone legal / info pages (linked in the footer). Plain text; the
    # admin writes them here. Blank pages show a friendly placeholder. ---
    about_us = models.TextField(blank=True, help_text="Content of the About Us page.")
    privacy_policy = models.TextField(blank=True, help_text="Content of the Privacy Policy page.")
    disclaimer = models.TextField(blank=True, help_text="Content of the Disclaimer page.")

    # --- Help / contact ---
    help_text = models.TextField(
        blank=True,
        default="Have a doubt or need support? Reach out and we'll get back to you.",
    )
    contact_email = models.EmailField(blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site content"
        verbose_name_plural = "Site content"

    def __str__(self):
        return "Site content"

    def save(self, *args, **kwargs):
        self.pk = 1  # enforce singleton
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        """Return the singleton row, creating it with defaults if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
