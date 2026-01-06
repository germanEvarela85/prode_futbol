# recordatorio_cierre.py
import os
import django
from django.utils import timezone

print("==== Ejecutando recordatorio_cierre ====")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "prode_project.settings")
django.setup()

from prode_app.models import Fecha
from prode_app.utils import enviar_recordatorio_cierre

def main():
    for fecha in Fecha.objects.all():
        enviar_recordatorio_cierre(fecha)

if __name__ == "__main__":
    main()
    print("==== Fin ejecución ====")
