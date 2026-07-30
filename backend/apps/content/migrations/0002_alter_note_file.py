from django.db import migrations, models

import apps.content.models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="note",
            name="file",
            field=models.FileField(
                max_length=500, upload_to=apps.content.models.note_upload_path
            ),
        ),
    ]
