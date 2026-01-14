from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('prode_app', '0009_alter_fecha_cierre_prode'),
    ]

    operations = [
        migrations.AddField(
            model_name='fecha',
            name='pozo_enviado',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='fecha',
            name='pozo_total',
            field=models.IntegerField(blank=True, null=True),
        ),
    ]

