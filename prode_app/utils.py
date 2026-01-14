# prode_app/utils.py
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.utils import timezone
from .models import Fecha, Tarjeta
from datetime import timedelta
from django.conf import settings


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

            from_email = settings.DEFAULT_FROM_EMAIL
            recipient_list = [usuario.email]

            try:
                send_mail(subject, message, from_email, recipient_list)
                print(f"✅ Email enviado a {usuario.email}")
            except Exception as e:
                print(f"❌ Error enviando email a {usuario.email}: {e}")
    else:
        print(f"No corresponde enviar recordatorio para fecha {fecha.numero}, faltan {tiempo_restante}.")


def enviar_ganadores(fecha_id, test_mode=True):
    """
    Envía un email a los ganadores de la fecha indicada.
    - Solo considera tarjetas pagadas (comprobante procesado).
    - Divide el pozo total entre la cantidad de ganadores.
    - test_mode=True -> imprime el email sin enviarlo.
    """
    fecha = Fecha.objects.get(id=fecha_id)

    if not fecha.pozo_total:
        print("❌ La fecha no tiene pozo cargado.")
        return

    tarjetas_pagas = Tarjeta.objects.filter(
        fecha=fecha,
        comprobante__procesado=True
    ).select_related("usuario")

    if not tarjetas_pagas.exists():
        print("❌ No hay tarjetas pagadas.")
        return

    max_puntos = tarjetas_pagas.order_by("-puntos").first().puntos
    ganadores = tarjetas_pagas.filter(puntos=max_puntos)

    cantidad = ganadores.count()
    premio = fecha.pozo_total / cantidad if cantidad else 0

    emails = []
    detalle = ""

    for t in ganadores:
        detalle += (
            f"- Usuario: {t.usuario.username}\n"
            f"  Tarjeta: {t.nombre_tarjeta}\n"
            f"  Puntos: {t.puntos}\n\n"
        )
        if t.usuario.email:
            emails.append(t.usuario.email)

    subject = f"🏆 Prode Farina - Ganadores Fecha {fecha.numero}"
    body = (
        f"¡Felicitaciones!\n\n"
        f"Fecha {fecha.numero}\n"
        f"Pozo total: ${fecha.pozo_total:,} ARS\n"
        f"Ganadores: {cantidad}\n"
        f"Premio por ganador: ${premio:,.2f} ARS\n\n"
        f"{detalle}"
        "Gracias por participar."
    )

    if not emails:
        print("⚠️ No hay emails para enviar")
        return

    if test_mode:
        print("----- Email a enviar -----")
        print("Asunto:", subject)
        print("Cuerpo:\n", body)
        print("Destinatarios:", emails)
        print("--------------------------")
    else:
        send_mail(
            subject,
            body,
            settings.DEFAULT_FROM_EMAIL,
            list(set(emails)),
            fail_silently=False
        )
        print(f"✅ Email enviado a {len(set(emails))} ganador/es")
