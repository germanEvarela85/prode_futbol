from .models import Fecha

def fecha_activa(request):
    fecha = Fecha.objects.order_by('-id').first()
    return {
        'fecha': fecha
    }
