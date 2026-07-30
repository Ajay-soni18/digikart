"""Introduce a top-level GeneralVideoHeading above GeneralVideoSection so the
dashboard's general videos become a 3-level tree:

    GeneralVideoHeading (e.g. "The Academic Edge")
      → GeneralVideoSection (a playlist / subheading card)
        → GeneralVideo

Safe to apply without a one-off default because the general-video tables hold
no data yet.
"""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('content', '0005_generalvideosection_generalvideo'),
    ]

    operations = [
        migrations.CreateModel(
            name='GeneralVideoHeading',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(help_text='Dashboard heading, e.g. "The Academic Edge".', max_length=160)),
                ('slug', models.SlugField(blank=True, max_length=180, unique=True)),
                ('order', models.PositiveIntegerField(default=0)),
                ('is_published', models.BooleanField(default=True)),
            ],
            options={
                'verbose_name': 'general video heading',
                'ordering': ['order', 'id'],
            },
        ),
        migrations.AlterModelOptions(
            name='generalvideosection',
            options={'ordering': ['order', 'id'], 'verbose_name': 'general video playlist'},
        ),
        migrations.AlterField(
            model_name='generalvideosection',
            name='title',
            field=models.CharField(help_text='Subheading shown on the card, e.g. "How to study effectively".', max_length=160),
        ),
        migrations.AlterField(
            model_name='generalvideosection',
            name='description',
            field=models.TextField(blank=True, help_text='Optional short blurb shown on the card.'),
        ),
        migrations.AddField(
            model_name='generalvideosection',
            name='heading',
            field=models.ForeignKey(
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='playlists',
                to='content.generalvideoheading',
            ),
            preserve_default=False,
        ),
    ]
