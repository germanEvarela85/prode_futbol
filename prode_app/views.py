from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .models import Fecha, Partido, Tarjeta, Pronostico, Comprobante
from .forms import TarjetaForm, RegistroForm, ComprobanteForm
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.auth import login
from django.db.models import Q, Case, When, Value, IntegerField
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.contrib.auth import get_user_model
from django.conf import settings


# --------------------------
# REGISTRO Y ACTIVACIÓN
# --------------------------
def registro(request):
    enviado_email = False

    if request.method == "POST":
        form = RegistroForm(request.POST)

        if form.is_valid():
            usuario = form.save(commit=False)
            usuario.is_active = False  # desactiva hasta confirmar email
            usuario.save()

            # Enviar email de activación
            current_site = get_current_site(request)
            mail_subject = "Activá tu cuenta en Prode Fútbol"
            message = render_to_string("prode_app/activation_email.html", {
                "user": usuario,
                "domain": current_site.domain,
                "uid": urlsafe_base64_encode(force_bytes(usuario.pk)),
                "token": default_token_generator.make_token(usuario),
            })

            email = EmailMessage(mail_subject, message, to=[usuario.email])
            email.send()

            enviado_email = True

    else:
        form = RegistroForm()

    return render(request, "prode_app/registro.html", {
        "form": form,
        "enviado_email": enviado_email
    })


def activar_cuenta(request, uidb64, token):
    User = get_user_model()

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        usuario = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        usuario = None

    if usuario is not None and default_token_generator.check_token(usuario, token):
        usuario.is_active = True
        usuario.save()
        messages.success(request, "Cuenta activada correctamente. Ahora podés iniciar sesión.")
        return redirect("login")
    else:
        messages.error(request, "El enlace de activación no es válido o expiró.")
        return redirect("home")


# --------------------------
# POST LOGIN
# --------------------------
@login_required
def post_login(request):
    if request.user.is_superuser:
        return redirect("cargar_resultados", fecha_id=1)
    else:
        return redirect("mis_tarjetas")


# --------------------------
# CREAR TARJETA
# --------------------------
@login_required
def crear_tarjeta(request, fecha_id=None):
    if fecha_id:
        fecha = get_object_or_404(Fecha, id=fecha_id)
    else:
        fecha = Fecha.objects.first()

    if not fecha:
        return render(request, "prode_app/crear_tarjeta.html", {
            "mensaje": "No hay fechas cargadas."
        })

    partidos = Partido.objects.filter(fecha=fecha)

    if request.method == "POST":
        tarjeta_form = TarjetaForm(request.POST)

        if tarjeta_form.is_valid():
            dobles = 0
            for partido in partidos:
                opcion2 = request.POST.get(f"opcion2_{partido.id}")
                if opcion2:
                    dobles += 1

            if dobles == 0:
                messages.error(request, "Debes seleccionar UNA opción doble en tu tarjeta.")
                return render(request, "prode_app/crear_tarjeta.html", {
                    "fecha": fecha,
                    "partidos": partidos,
                    "tarjeta_form": tarjeta_form
                })

            if dobles > 1:
                messages.error(request, "Solo puedes elegir UNA opción doble por tarjeta.")
                return render(request, "prode_app/crear_tarjeta.html", {
                    "fecha": fecha,
                    "partidos": partidos,
                    "tarjeta_form": tarjeta_form
                })

            tarjeta = tarjeta_form.save(commit=False)
            tarjeta.usuario = request.user
            tarjeta.fecha = fecha
            tarjetas_existentes = Tarjeta.objects.filter(usuario=request.user, fecha=fecha).count()
            tarjeta.numero_tarjeta = tarjetas_existentes + 1
            tarjeta.save()

            for partido in partidos:
                opcion1 = request.POST.get(f"opcion1_{partido.id}")
                opcion2 = request.POST.get(f"opcion2_{partido.id}")
                if opcion1:
                    Pronostico.objects.create(
                        tarjeta=tarjeta,
                        partido=partido,
                        opcion1=int(opcion1),
                        opcion2=int(opcion2) if opcion2 else None
                    )

            messages.info(request, "Tarjeta creada. Ahora debes subir el comprobante para activarla.")
            return redirect("subir_comprobante")  # redirige directamente al upload
        else:
            messages.error(request, "Hay errores en el formulario.")
    else:
        tarjeta_form = TarjetaForm()

    context = {
        "fecha": fecha,
        "partidos": partidos,
        "tarjeta_form": tarjeta_form
    }
    return render(request, "prode_app/crear_tarjeta.html", context)


# --------------------------
# MIS TARJETAS
# --------------------------
@login_required
def mis_tarjetas(request):
    """
    Mostrar todas las tarjetas de todos los usuarios.
    - Primero las tarjetas del usuario actual (más recientes primero).
    - Luego las tarjetas del resto de los usuarios.
    - Solo el superusuario puede borrar tarjetas.
    - Se indican cuáles tienen comprobante enviado.
    """
    # Tarjetas del usuario actual
    tarjetas_mias = Tarjeta.objects.filter(usuario=request.user).select_related('usuario', 'fecha').order_by('-fecha__numero','-numero_tarjeta')
    
    # Tarjetas de otros usuarios
    tarjetas_otros = Tarjeta.objects.exclude(usuario=request.user).select_related('usuario', 'fecha').order_by('-fecha__numero','-numero_tarjeta')
    
    # Combinar listas manteniendo la separación
    todas_tarjetas = list(tarjetas_mias) + list(tarjetas_otros)
    
    # Agregar estado de comprobante
    tarjetas_con_estado = []
    for t in todas_tarjetas:
        pagada = Comprobante.objects.filter(tarjeta=t, procesado=True).exists()
        tarjetas_con_estado.append({
            "tarjeta": t,
            "pagada": pagada
        })

    return render(request, "prode_app/mis_tarjetas.html", {"tarjetas": tarjetas_con_estado})


# --------------------------
# DETALLE TARJETA
# --------------------------
@login_required
def detalle_tarjeta(request, tarjeta_id):
    tarjeta = get_object_or_404(Tarjeta, pk=tarjeta_id)
    pronosticos = Pronostico.objects.filter(tarjeta=tarjeta).select_related('partido__fecha','partido__local','partido__visitante')

    detalles = []
    for p in pronosticos:
        resultado = p.partido.resultado_real
        acierto = False
        if resultado is not None:
            if resultado == p.opcion1 or (p.opcion2 and resultado == p.opcion2):
                acierto = True
        detalles.append({
            "pronostico": p,
            "resultado": resultado,
            "acierto": acierto,
        })

    return render(request, "prode_app/detalle_tarjeta.html", {
        "tarjeta": tarjeta,
        "detalles": detalles,
    })


# --------------------------
# BORRAR TARJETA
# --------------------------
@login_required
def borrar_tarjeta(request, tarjeta_id):
    if not request.user.is_superuser:
        raise PermissionDenied("No tienes permiso para borrar tarjetas.")
    
    tarjeta = get_object_or_404(Tarjeta, id=tarjeta_id)
    tarjeta.delete()
    return redirect("mis_tarjetas")


# --------------------------
# CARGAR RESULTADOS
# --------------------------
@login_required
def cargar_resultados(request, fecha_id):
    if not request.user.is_superuser:
        raise PermissionDenied("No tienes permiso para cargar resultados.")

    fecha = get_object_or_404(Fecha, id=fecha_id)
    partidos = Partido.objects.filter(fecha=fecha)

    if request.method == "POST":
        for partido in partidos:
            valor = request.POST.get(f"partido_{partido.id}")
            if valor:
                partido.resultado_real = int(valor)
                partido.save()

        tarjetas = Tarjeta.objects.filter(fecha=fecha)
        for tarjeta in tarjetas:
            puntos = 0
            pronosticos = Pronostico.objects.filter(tarjeta=tarjeta)
            for p in pronosticos:
                if p.partido.resultado_real:
                    if p.opcion1 == p.partido.resultado_real or (p.opcion2 and p.partido.resultado_real == p.opcion2):
                        puntos += 1
            tarjeta.puntos = puntos
            tarjeta.save()

        return redirect("mis_tarjetas")

    return render(request, "prode_app/cargar_resultados.html", {
        "fecha": fecha,
        "partidos": partidos,
    })


# --------------------------
# RANKING
# --------------------------
@login_required
def ranking_fecha(request, fecha_id):
    fecha = get_object_or_404(Fecha, id=fecha_id)

    tarjetas = (
        Tarjeta.objects
        .filter(fecha=fecha)
        .select_related("usuario")
        .order_by("-puntos", "numero_tarjeta")
    )

    ranking = []
    puesto_actual = 0
    ultimo_puntaje = None

    for idx, t in enumerate(tarjetas):
        if t.puntos != ultimo_puntaje:
            puesto_actual += 1
            ultimo_puntaje = t.puntos

        ranking.append({
            "puesto": puesto_actual,
            "tarjeta": t,
        })

    return render(request, "prode_app/ranking_fecha.html", {
        "fecha": fecha,
        "ranking": ranking,
    })


# --------------------------
# BUSCAR TARJETA
# --------------------------
@login_required
def buscar_tarjeta(request):
    query = request.GET.get('q', '').strip()
    resultados = []
    mensaje = ''

    if query:
        todas_tarjetas = Tarjeta.objects.select_related('usuario', 'fecha')
        for t in todas_tarjetas:
            nombre_tarjeta = f"{t.usuario.username}{t.numero_tarjeta}"
            if nombre_tarjeta.lower() == query.lower():
                resultados.append(t)

        if not resultados:
            mensaje = f"No se encontraron tarjetas para: '{query}'"

    context = {
        'query': query,
        'resultados': resultados,
        'mensaje': mensaje,
    }
    return render(request, 'prode_app/buscar_tarjeta.html', context)


def obtener_cuenta_activa():
    cuentas = [
        {"banco": "NARANJA X", "alias": "germanvarela85", "cbu": "4530000800010436813880", "titular": "Germán Emiliano Varela"},
        {"banco": "SANTANDER", "alias": "deposito.segundo", "cbu": "0720000788000092345678", "titular": "Prode Cuenta 2"},
        {"banco": "BBVA", "alias": "tercera.cuenta.prode", "cbu": "0170201870000004567891", "titular": "Prode Cuenta 3"},
    ]

    total_procesadas = Comprobante.objects.filter(procesado=True).count()
    index = min(total_procesadas // 3, len(cuentas) - 1)
    return cuentas[index]


# --------------------------
# SUBIR COMPROBANTE
# --------------------------
@login_required
def subir_comprobante(request):
    """
    Página donde el usuario elige una de sus tarjetas y sube el comprobante.
    Al enviar, guarda el Comprobante y envía un email al ADMIN_EMAIL y al usuario.
    Cambios:
    - Comprobante se marca automáticamente como PROCESADO=True.
    - Se indica cuáles tarjetas ya tienen comprobante enviado.
    """
    mensaje = None

    CUENTAS_DEPOSITO = [
        {"banco": "NARANJA X", "alias": "germanvarela85", "cbu": "4530000800010436813880", "titular": "Germán Emiliano Varela"},
        {"banco": "BBVA PRUEBA", "alias": "cuenta_prueba_1", "cbu": "0123456789012345678901", "titular": "Cuenta Prueba Uno"},
        {"banco": "HSBC DEMO", "alias": "cuenta_prueba_2", "cbu": "1098765432109876543210", "titular": "Cuenta Prueba Dos"},
    ]

    if request.method == "POST":
        form = ComprobanteForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            comprobante = form.save(commit=False)

            if comprobante.tarjeta.usuario != request.user:
                messages.error(request, "La tarjeta seleccionada no te pertenece.")
                return redirect("subir_comprobante")

            if Comprobante.objects.filter(tarjeta=comprobante.tarjeta, procesado=True).exists():
                messages.warning(request, f"¡La tarjeta {comprobante.tarjeta.nombre_tarjeta} ya tiene comprobante enviado!")
                return redirect("subir_comprobante")

            comprobante.usuario = request.user
            comprobante.procesado = True
            comprobante.save()

            admin_email = getattr(settings, "ADMIN_EMAIL", None) or settings.EMAIL_HOST_USER
            subject_admin = f"Nuevo comprobante: {comprobante.tarjeta.nombre_tarjeta} - {request.user.username}"
            body_admin = (
                f"Usuario: {request.user.username}\n"
                f"Tarjeta: {comprobante.tarjeta.nombre_tarjeta}\n"
                f"Fecha de subida: {comprobante.fecha_subida}\n\n"
                f"Comentario: {comprobante.comentario or '-'}\n\n"
                "Adjunto está el comprobante cargado."
            )
            email_admin = EmailMessage(subject_admin, body_admin, to=[admin_email])
            try:
                if comprobante.archivo and hasattr(comprobante.archivo, 'path'):
                    email_admin.attach_file(comprobante.archivo.path)
                else:
                    comprobante.archivo.open('rb')
                    email_admin.attach(comprobante.archivo.name, comprobante.archivo.read())
                    comprobante.archivo.close()
                email_admin.send(fail_silently=False)
            except Exception as e:
                messages.error(request, f"El comprobante fue guardado pero hubo un error enviando el email al admin: {e}")
                return redirect("mis_tarjetas")

            subject_user = f"Comprobante recibido: {comprobante.tarjeta.nombre_tarjeta}"
            body_user = (
                f"Hola {request.user.username},\n\n"
                f"Hemos recibido tu comprobante para la tarjeta: {comprobante.tarjeta.nombre_tarjeta}.\n"
                f"Fecha de subida: {comprobante.fecha_subida}\n"
                f"Comentario: {comprobante.comentario or '-'}\n\n"
                "Gracias por tu transferencia."
            )
            email_user = EmailMessage(subject_user, body_user, to=[request.user.email])
            try:
                email_user.send(fail_silently=False)
            except Exception as e:
                messages.warning(request, f"Comprobante enviado, pero no se pudo enviar el email de confirmación al usuario: {e}")

            messages.success(request, f"Comprobante enviado correctamente para la tarjeta {comprobante.tarjeta.nombre_tarjeta}.")
            return redirect("mis_tarjetas")

    else:
        form = ComprobanteForm(user=request.user)

    # -------------------------------------------------------------------
    # Determinar qué cuenta mostrar según comprobantes PROCESADOS
    # -------------------------------------------------------------------
    cuenta_info = CUENTAS_DEPOSITO[0]  # por defecto

    try:
        tarjetas_usuario = Tarjeta.objects.filter(usuario=request.user).select_related('fecha')
        tarjetas_con_estado = []
        for t in tarjetas_usuario:
            pagada = Comprobante.objects.filter(tarjeta=t, procesado=True).exists()
            tarjetas_con_estado.append({
                "tarjeta": t,
                "pagada": pagada
            })

        tarjeta_sel = tarjetas_usuario.order_by('-fecha__numero', '-numero_tarjeta').first()
        if tarjeta_sel:
            fecha_rel = tarjeta_sel.fecha
            processed_count = Comprobante.objects.filter(
                tarjeta__fecha=fecha_rel,
                procesado=True
            ).count()

            grupo = processed_count // 3
            if grupo < len(CUENTAS_DEPOSITO):
                cuenta_info = CUENTAS_DEPOSITO[grupo]
            else:
                cuenta_info = CUENTAS_DEPOSITO[-1]

    except Exception:
        tarjetas_con_estado = []

    return render(request, "prode_app/subir_comprobante.html", {
        "form": form,
        "cuenta_info": cuenta_info,
        "mensaje": None,
        "tarjetas_usuario": tarjetas_con_estado,
    })
