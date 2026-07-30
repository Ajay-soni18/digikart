from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("siteconfig", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitecontent",
            name="highlight1_title",
            field=models.CharField(default="Chapter-wise lectures", max_length=120),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="highlight1_desc",
            field=models.CharField(blank=True, default="Curated YouTube playlists, organized unit by unit.", max_length=200),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="highlight2_title",
            field=models.CharField(default="Complete notes", max_length=120),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="highlight2_desc",
            field=models.CharField(blank=True, default="Protected, watermarked notes you can read anywhere.", max_length=200),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="highlight3_title",
            field=models.CharField(default="Built for MBBS", max_length=120),
        ),
        migrations.AddField(
            model_name="sitecontent",
            name="highlight3_desc",
            field=models.CharField(blank=True, default="Pathology, Pharmacology & more — clean and focused.", max_length=200),
        ),
    ]
