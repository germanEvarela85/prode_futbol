from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.contrib.sites.shortcuts import get_current_site
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import EmailMessage
from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from .models import Fecha, Partido, Tarjeta, Pronostico, Comprobante
from .forms import TarjetaForm, RegistroForm, ComprobanteForm


# --------------------------
# Helper: calcular cierre del prode para una Fecha
# --------------------------
def calcular_cierre(fecha_obj: Fecha):
    """
    Prioridad:
    1) si fecha_obj.cierre_prode está definido -> usarlo
    2) si no y fecha_obj.inicio_fecha está definido -> usar inicio_fecha - 2 horas
    3) sino -> None (sin cierre definido)
    """
    if fecha_obj is None:
        return None
    if fecha_obj.cierre_prode:
        return fecha_obj.cierre_prode
    if fecha_obj.inicio_fecha:
        return fecha_obj.inicio_fecha - timedelta(hours=2)
    return None


# --------------------------
# REGISTRO
# --------------------------
def registro(request):
    enviado_email = False

    if request.method == "POST":
        form = RegistroForm(request.POST)
        if form.is_valid():
            usuario = form.save(commit=False)
            usuario.is_active = False  # desactivar hasta confirmar email
            usuario.save()

            # Enviar email de activación al usuario
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


# --------------------------
# ACTIVACIÓN DE CUENTA
# --------------------------
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

        # Enviar email al admin notificando usuario activado
        admin_email = getattr(settings, "ADMIN_EMAIL", "prodefarina26@gmail.com")
        subject_admin = f"Usuario activado: {usuario.username}"
        body_admin = (
            f"El usuario {usuario.username} ({usuario.email}) ha activado su cuenta correctamente.\n"
            f"Fecha y hora: {timezone.now().strftime('%d/%m/%Y %H:%M:%S')}"
        )
        try:
            EmailMessage(subject_admin, body_admin, to=[admin_email]).send()
        except Exception as e:
            messages.warning(request, f"Cuenta activada, pero no se pudo enviar email al admin: {e}")

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
        # el id/numero de fecha por defecto lo podés cambiar
        primera_fecha = Fecha.objects.order_by("numero").first()
        if primera_fecha:
            return redirect("cargar_resultados", fecha_id=primera_fecha.id)
        return redirect("mis_tarjetas")
    else:
        return redirect("mis_tarjetas")


# --------------------------
# REGLAMENTO
# --------------------------
@login_required
def reglamento(request):
    return render(request, 'prode_app/reglamento.html')


@login_required
def crear_tarjeta(request, fecha_id=None):
    """
    Crear tarjeta para una fecha.
    Bloquea creación si pasó el cierre.
    Maneja errores de doble opción y mantiene opciones seleccionadas.
    """
    # Obtener la fecha
    if fecha_id:
        fecha = get_object_or_404(Fecha, id=fecha_id)
    else:
        fecha = Fecha.objects.first()
    
    if not fecha:
        return render(request, "prode_app/crear_tarjeta.html", {
            "mensaje": "No hay fechas cargadas."
        })

    # Partidos de la fecha
    partidos = Partido.objects.filter(fecha=fecha)

    # Calcular cierre
    cierre = calcular_cierre(fecha)
    ahora = timezone.now()
    tiempo_restante = int((cierre - ahora).total_seconds()) if cierre else None

    # Bloqueo si ya cerró
    if cierre and ahora >= cierre:
        messages.error(request, "⛔ El tiempo para crear tarjetas para esta fecha ha finalizado.")
        return render(request, "prode_app/crear_tarjeta.html", {
            "fecha": fecha,
            "partidos": partidos,
            "tarjeta_form": TarjetaForm(),
            "primer_partido": fecha.inicio_fecha,
            "cierre_prode": cierre,
            "tiempo_restante": 0
        })

    if request.method == "POST":
        tarjeta_form = TarjetaForm(request.POST)
        opciones_post = {f"opcion1_{p.id}": request.POST.get(f"opcion1_{p.id}") for p in partidos}
        dobles_post = {f"opcion2_{p.id}": request.POST.get(f"opcion2_{p.id}") for p in partidos}

        # Validaciones de doble opción
        dobles_seleccionadas = [k for k,v in dobles_post.items() if v]
        if len(dobles_seleccionadas) == 0:
            messages.error(request, "Debes seleccionar UNA opción doble en tu tarjeta.")
        elif len(dobles_seleccionadas) > 1:
            messages.error(request, "Solo puedes elegir UNA opción doble por tarjeta.")
        else:
            # Validar que la doble no sea igual a la principal
            doble_key = dobles_seleccionadas[0]
            partido_id = int(doble_key.split("_")[1])
            if opciones_post[f"opcion1_{partido_id}"] == dobles_post[doble_key]:
                messages.error(request, "La opción doble no puede ser igual a la opción principal del partido.")

        # Si hay errores, renderizamos y mantenemos las opciones
        if messages.get_messages(request):
            return render(request, "prode_app/crear_tarjeta.html", {
                "fecha": fecha,
                "partidos": partidos,
                "tarjeta_form": tarjeta_form,
                "opciones_post": opciones_post,
                "dobles_post": dobles_post,
                "primer_partido": fecha.inicio_fecha,
                "cierre_prode": cierre,
                "tiempo_restante": tiempo_restante
            })

        # Guardar tarjeta
        tarjeta = tarjeta_form.save(commit=False)
        tarjeta.usuario = request.user
        tarjeta.fecha = fecha
        tarjeta.numero_tarjeta = Tarjeta.objects.filter(usuario=request.user, fecha=fecha).count() + 1
        tarjeta.save()

        # Guardar pronósticos
        for partido in partidos:
            opcion1 = opciones_post.get(f"opcion1_{partido.id}")
            opcion2 = dobles_post.get(f"opcion2_{partido.id}")
            Pronostico.objects.create(
                tarjeta=tarjeta,
                partido=partido,
                opcion1=int(opcion1),
                opcion2=int(opcion2) if opcion2 else None
            )

        messages.success(request, "Tarjeta creada correctamente. Ahora debes subir el comprobante para activarla.")
        return redirect("subir_comprobante")

    else:
        tarjeta_form = TarjetaForm()
        opciones_post = {}
        dobles_post = {}

    return render(request, "prode_app/crear_tarjeta.html", {
        "fecha": fecha,
        "partidos": partidos,
        "tarjeta_form": tarjeta_form,
        "opciones_post": opciones_post,
        "dobles_post": dobles_post,
        "primer_partido": fecha.inicio_fecha,
        "cierre_prode": cierre,
        "tiempo_restante": tiempo_restante
    })

# --------------------------
# MIS TARJETAS
# --------------------------
@login_required
def mis_tarjetas(request):
    """
    Mostrar todas las tarjetas de todos los usuarios.
    - Primero las tarjetas del usuario actual (más recientes primero).
    - Luego las tarjetas del resto de los usuarios.
    - Si la Fecha tiene cierre, se intenta ocultar tarjetas creadas después del cierre (si existe created_at).
    - Se indica si cada tarjeta está pagada (comprobante procesado).
    """
    # traer todas las tarjetas ordenadas por fecha y numero (lo mismo que tenías)
    todas_tarjetas_raw = Tarjeta.objects.select_related('usuario', 'fecha').order_by('-fecha__numero', '-numero_tarjeta')

    tarjetas_con_estado = []
    ahora = timezone.now()
    for t in todas_tarjetas_raw:
        # intentar filtrar según cierre si existe created_at en el modelo Tarjeta
        cierre = calcular_cierre(t.fecha)
        if cierre and hasattr(t, "created_at"):
            try:
                # si la tarjeta fue creada después del cierre, la ignoramos
                if t.created_at and t.created_at > cierre:
                    continue
            except Exception:
                pass  # si hay problemas con el formato, ignoramos la restricción
        # comprobar si está pagada
        pagada = Comprobante.objects.filter(tarjeta=t, procesado=True).exists()
        tarjetas_con_estado.append({
            "tarjeta": t,
            "pagada": pagada
        })

    # reordenar para poner primero las mias
    tarjetas_mias = [x for x in tarjetas_con_estado if x["tarjeta"].usuario == request.user]
    tarjetas_otros = [x for x in tarjetas_con_estado if x["tarjeta"].usuario != request.user]
    tarjetas_final = tarjetas_mias + tarjetas_otros

    return render(request, "prode_app/mis_tarjetas.html", {"tarjetas": tarjetas_final})


# --------------------------
# DETALLE TARJETA
# --------------------------
@login_required
def detalle_tarjeta(request, tarjeta_id):
    tarjeta = get_object_or_404(Tarjeta, pk=tarjeta_id)
    pronosticos = Pronostico.objects.filter(tarjeta=tarjeta).select_related('partido__fecha', 'partido__local', 'partido__visitante')

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
# BORRAR TARJETA (solo superuser)
# --------------------------
@login_required
def borrar_tarjeta(request, tarjeta_id):
    if not request.user.is_superuser:
        raise PermissionDenied("No tienes permiso para borrar tarjetas.")

    tarjeta = get_object_or_404(Tarjeta, id=tarjeta_id)
    tarjeta.delete()
    return redirect("mis_tarjetas")


# --------------------------
# CARGAR RESULTADOS (solo admin)
# --------------------------
@login_required
def cargar_resultados(request, fecha_id):
    if not request.user.is_superuser:
        raise PermissionDenied("No tenés permiso para esto.")

    fecha = get_object_or_404(Fecha, id=fecha_id)
    partidos = Partido.objects.filter(fecha=fecha)

    if request.method == "POST":
        for partido in partidos:
            valor = request.POST.get(f"partido_{partido.id}")
            if valor:
                partido.resultado_real = int(valor)
                partido.save()

        # Calcular puntos SOLO para tarjetas pagadas (comprobante procesado)
        tarjetas = Tarjeta.objects.filter(fecha=fecha)
        for tarjeta in tarjetas:
            if not Comprobante.objects.filter(tarjeta=tarjeta, procesado=True).exists():
                tarjeta.puntos = 0
                tarjeta.save()
                continue

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
# RANKING (solo tarjetas pagadas)
# --------------------------
@login_required
def ranking_fecha(request, fecha_id):
    fecha = get_object_or_404(Fecha, id=fecha_id)

    tarjetas = (
        Tarjeta.objects
        .filter(fecha=fecha)
        .select_related("usuario")
        .filter(comprobante__procesado=True)
        .distinct()
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


# --------------------------
# Rotación de cuentas según comprobantes procesados
# --------------------------
def obtener_cuenta_activa():
    cuentas = [
        {"banco": "NARANJA X", "alias": "germanvarela85", "cbu": "4530000800010436813880", "titular": "Germán Emiliano Varela"},
        {"banco": "SANTANDER", "alias": "deposito.segundo", "cbu": "0720000788000092345678", "titular": "Prode Cuenta 2"},
        {"banco": "BBVA", "alias": "tercera.cuenta.prode", "cbu": "0170201870000004567891", "titular": "Prode Cuenta 3"},
    ]

    total_procesadas = Comprobante.objects.filter(procesado=True).count()
    index = min(total_procesadas // 3, len(cuentas) - 1)
    return cuentas[index]


@login_required
def subir_comprobante(request):
    """
    Subir comprobante:
    - bloquea si ya pasó el cierre de la tarjeta
    - marca comprobante como procesado=True automáticamente
    - evita subir si ya existe comprobante procesado para esa tarjeta
    - envía email al admin y al usuario
    """

    CUENTAS_DEPOSITO = [
        {"banco": "NARANJA X", "alias": "germanvarela85", "cbu": "4530000800010436813880", "titular": "Germán Emiliano Varela"},
        {"banco": "BBVA PRUEBA", "alias": "cuenta_prueba_1", "cbu": "0123456789012345678901", "titular": "Cuenta Prueba Uno"},
        {"banco": "HSBC DEMO", "alias": "cuenta_prueba_2", "cbu": "1098765432109876543210", "titular": "Cuenta Prueba Dos"},
    ]

    def enviar_email(subject, body, destinatarios, archivo=None):
        """
        Helper para enviar email.
        - archivo: ruta del archivo o archivo tipo InMemoryUploadedFile
        """
        email = EmailMessage(subject, body, to=destinatarios)
        if archivo:
            try:
                if hasattr(archivo, 'path'):  # archivo físico
                    email.attach_file(archivo.path)
                else:  # archivo en memoria
                    archivo.open('rb')
                    email.attach(archivo.name, archivo.read())
                    archivo.close()
            except Exception as e:
                raise Exception(f"Error adjuntando archivo: {e}")
        email.send(fail_silently=False)

    if request.method == "POST":
        form = ComprobanteForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            comprobante = form.save(commit=False)

            # seguridad: la tarjeta debe pertenecer al usuario
            if comprobante.tarjeta.usuario != request.user:
                messages.error(request, "La tarjeta seleccionada no te pertenece.")
                return redirect("subir_comprobante")

            # bloqueo por cierre
            cierre = calcular_cierre(comprobante.tarjeta.fecha)
            if cierre and timezone.now() >= cierre:
                messages.error(request, "El periodo para subir comprobantes para esta fecha ya cerró.")
                return redirect("mis_tarjetas")

            # evitar segundo comprobante pagado
            if Comprobante.objects.filter(tarjeta=comprobante.tarjeta, procesado=True).exists():
                messages.warning(request, f"¡La tarjeta {comprobante.tarjeta.nombre_tarjeta} ya tiene comprobante enviado!")
                return redirect("subir_comprobante")

            # guardar comprobante
            comprobante.usuario = request.user
            comprobante.procesado = True
            comprobante.save()

            # -----------------------------
            # EMAIL AL ADMIN
            # -----------------------------
            admin_email = getattr(settings, "ADMIN_EMAIL", "prodefarina26@gmail.com")
            subject_admin = f"Nuevo comprobante: {comprobante.tarjeta.nombre_tarjeta} - {request.user.username}"
            body_admin = (
                f"Usuario: {request.user.username}\n"
                f"Tarjeta: {comprobante.tarjeta.nombre_tarjeta}\n"
                f"Fecha de subida: {comprobante.fecha_subida}\n"
                f"Comentario: {comprobante.comentario or '-'}\n"
            )
            try:
                enviar_email(subject_admin, body_admin, [admin_email], archivo=comprobante.archivo)
            except Exception as e:
                messages.error(request, f"El comprobante fue guardado, pero hubo un error enviando el email al admin: {e}")
                return redirect("mis_tarjetas")

            # -----------------------------
            # EMAIL AL USUARIO
            # -----------------------------
            subject_user = f"Comprobante recibido: {comprobante.tarjeta.nombre_tarjeta}"
            body_user = (
                f"Hola {request.user.username},\n\n"
                f"Hemos recibido tu comprobante para la tarjeta: {comprobante.tarjeta.nombre_tarjeta}.\n"
                f"Fecha de subida: {comprobante.fecha_subida}\n"
                f"Comentario: {comprobante.comentario or '-'}\n\n"
                "Gracias por tu transferencia."
            )
            try:
                enviar_email(subject_user, body_user, [request.user.email])
            except Exception as e:
                messages.warning(request, f"Comprobante enviado, pero no se pudo enviar el email de confirmación al usuario: {e}")

            messages.success(request, f"Comprobante enviado correctamente para la tarjeta {comprobante.tarjeta.nombre_tarjeta}.")
            return redirect("mis_tarjetas")
    else:
        form = ComprobanteForm(user=request.user)

    # -----------------------------
    # Preparar datos para mostrar en el template
    # -----------------------------
    cuenta_info = CUENTAS_DEPOSITO[0]
    tarjetas_usuario = Tarjeta.objects.filter(usuario=request.user).select_related('fecha')
    tarjetas_con_estado = []
    for t in tarjetas_usuario:
        pagada = Comprobante.objects.filter(tarjeta=t, procesado=True).exists()
        tarjetas_con_estado.append({"tarjeta": t, "pagada": pagada})

    # determinar cuenta activa según cantidad de comprobantes procesados
    tarjeta_sel = tarjetas_usuario.order_by('-fecha__numero', '-numero_tarjeta').first()
    if tarjeta_sel:
        fecha_rel = tarjeta_sel.fecha
        processed_count = Comprobante.objects.filter(tarjeta__fecha=fecha_rel, procesado=True).count()
        grupo = processed_count // 3
        if grupo < len(CUENTAS_DEPOSITO):
            cuenta_info = CUENTAS_DEPOSITO[grupo]
        else:
            cuenta_info = CUENTAS_DEPOSITO[-1]

    primer_partido = tarjeta_sel.fecha.inicio_fecha if tarjeta_sel else None
    cierre_fecha = calcular_cierre(tarjeta_sel.fecha) if tarjeta_sel else None

    return render(request, "prode_app/subir_comprobante.html", {
        "form": form,
        "cuenta_info": cuenta_info,
        "mensaje": None,
        "tarjetas_usuario": tarjetas_con_estado,
        "primer_partido": primer_partido,
        "cierre_prode": cierre_fecha,
    })
