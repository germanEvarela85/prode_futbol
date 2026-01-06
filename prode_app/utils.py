# prode_app/utils.py
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from .models import Fecha
from datetime import timedelta

def enviar_recordatorio_cierre(fecha):
    """
    Envía un email a todos los usuarios activos 2 hs antes del cierre de la fecha.
    """
    if not fecha.cierre_prode:
        return  # Si la fecha no tiene cierre, no hace nada

    ahora = timezone.now()
    tiempo_restante = fecha.cierre_prode - ahora

    # Revisar si faltan 2 hs (+/- 5 min para no duplicar)
    if timedelta(hours=1, minutes=55) <= tiempo_restante <= timedelta(hours=2, minutes=5):
        User = get_user_model()
        usuarios = User.objects.filter(is_active=True)

        for usuario in usuarios:
            if not usuario.email:
                continue

            subject = f"⚠ Recordatorio: Cierre de la fecha {fecha.numero} en 2 horas"
            message = f"""Hola {usuario.username}!

Faltan 2 horas para que cierre la fecha {fecha.numero} del Prode Fútbol.
Asegurate de crear o enviar tus tarjetas antes de las {fecha.cierre_prode.strftime('%H:%M:%S')}.

Saludos,
Prode Fútbol"""

            from_email = "prodefarina26@gmail.com"
            recipient_list = [usuario.email]

            try:
                send_mail(subject, message, from_email, recipient_list)
                print(f"✅ Email enviado a {usuario.email}")
            except Exception as e:
                print(f"❌ Error enviando email a {usuario.email}: {e}")
    else:
        print(f"No corresponde enviar recordatorio para fecha {fecha.numero}, faltan {tiempo_restante}.")
