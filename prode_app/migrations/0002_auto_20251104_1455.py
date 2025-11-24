from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('prode_app', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='partido',
            name='resultado_real',
            field=models.IntegerField(choices=[(1, 'Local'), (2, 'Empate'), (3, 'Visitante')], blank=True, null=True),
        ),
        migrations.AddField(
            model_name='tarjeta',
            name='puntos',
            field=models.IntegerField(default=0),
        ),
    ]
