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
from prode_app.utils import enviar_ganadores
from .models import Fecha, Partido, Tarjeta, Pronostico, Comprobante
from .forms import TarjetaForm, RegistroForm, ComprobanteForm


# --------------------------
# Helper: calcular cierre del prode para una Fecha
# --------------------------
def calcular_cierre(fecha_obj: Fecha):
    """
    Prioridad:
    1) si fecha_obj.cierre_prode está definido -> usarlo
    2) si no y fecha_obj.inicio_fecha está definido -> usar inicio_fecha - 1 horas
    3) sino -> None (sin cierre definido)
    """
    if fecha_obj is None:
        return None
    if fecha_obj.cierre_prode:
        return fecha_obj.cierre_prode
    if fecha_obj.inicio_fecha:
        return fecha_obj.inicio_fecha - timedelta(hours=1)
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
def crear_tarjeta(request):
    """
    Crear tarjeta para una fecha.
    La tarjeta se crea INACTIVA.
    El comprobante se sube después.
    """

    todas_fechas = Fecha.objects.order_by("numero")

    fecha_id = request.GET.get("fecha_id")
    if fecha_id:
        fecha = get_object_or_404(Fecha, id=fecha_id)
    else:
        fecha = todas_fechas.first()

    if not fecha:
        return render(request, "prode_app/crear_tarjeta.html", {
            "mensaje": "No hay fechas cargadas."
        })

    partidos = Partido.objects.filter(fecha=fecha)

    cierre = calcular_cierre(fecha)
    ahora = timezone.now()
    tiempo_restante = int((cierre - ahora).total_seconds()) if cierre else None

    # 🔒 Cierre
    if cierre and ahora >= cierre:
        messages.error(
            request,
            "⛔ El tiempo para crear tarjetas para esta fecha ha finalizado."
        )
        return render(request, "prode_app/crear_tarjeta.html", {
            "fecha": fecha,
            "partidos": partidos,
            "primer_partido": fecha.inicio_fecha,
            "cierre_prode": cierre,
            "tiempo_restante": 0,
            "todas_fechas": todas_fechas,
            "opciones_post": {},
            "dobles_post": {},
        })

    # ================= POST =================
    if request.method == "POST":

        opciones_post = {
            f"opcion1_{p.id}": request.POST.get(f"opcion1_{p.id}")
            for p in partidos
        }

        dobles_post = {
            f"opcion2_{p.id}": request.POST.get(f"opcion2_{p.id}")
            for p in partidos
        }

        errores = False

        # Validar opción principal en todos
        for p in partidos:
            if not opciones_post.get(f"opcion1_{p.id}"):
                messages.error(request, "Debes marcar una opción en todos los partidos.")
                errores = True
                break

        # Validar doble
        dobles_seleccionadas = [k for k, v in dobles_post.items() if v]

        if len(dobles_seleccionadas) == 0:
            messages.error(request, "Debes seleccionar UNA opción doble.")
            errores = True
        elif len(dobles_seleccionadas) > 1:
            messages.error(request, "Solo puedes elegir UNA opción doble.")
            errores = True
        else:
            doble_key = dobles_seleccionadas[0]
            partido_id = int(doble_key.split("_")[1])

            if opciones_post.get(f"opcion1_{partido_id}") == dobles_post[doble_key]:
                messages.error(
                    request,
                    "La opción doble no puede ser igual a la opción principal."
                )
                errores = True

        if errores:
            return render(request, "prode_app/crear_tarjeta.html", {
                "fecha": fecha,
                "partidos": partidos,
                "opciones_post": opciones_post,
                "dobles_post": dobles_post,
                "primer_partido": fecha.inicio_fecha,
                "cierre_prode": cierre,
                "tiempo_restante": tiempo_restante,
                "todas_fechas": todas_fechas,
            })

        # ✅ CREAR TARJETA (NO SE SETEA nombre_tarjeta)
        numero = Tarjeta.objects.filter(
            usuario=request.user,
            fecha=fecha
        ).count() + 1

        tarjeta = Tarjeta.objects.create(
            usuario=request.user,
            fecha=fecha,
            numero_tarjeta=numero,
            puntos=0
        )

        # ✅ CREAR PRONÓSTICOS
        for partido in partidos:
            Pronostico.objects.create(
                tarjeta=tarjeta,
                partido=partido,
                opcion1=int(opciones_post[f"opcion1_{partido.id}"]),
                opcion2=int(dobles_post[f"opcion2_{partido.id}"])
                if dobles_post.get(f"opcion2_{partido.id}") else None
            )

        messages.success(
            request,
            "Tarjeta creada correctamente. Ahora debes subir el comprobante para activarla."
        )

        return redirect("subir_comprobante")

    # ================= GET =================
    return render(request, "prode_app/crear_tarjeta.html", {
        "fecha": fecha,
        "partidos": partidos,
        "opciones_post": {},
        "dobles_post": {},
        "primer_partido": fecha.inicio_fecha,
        "cierre_prode": cierre,
        "tiempo_restante": tiempo_restante,
        "todas_fechas": todas_fechas,
    })



# --------------------------
# MIS TARJETAS
# --------------------------
@login_required
def mis_tarjetas(request):
    """
    Mostrar tarjetas filtradas por fecha seleccionada.
    - Dropdown con todas las fechas creadas.
    - Se indica si cada tarjeta está pagada (comprobante procesado).
    - Se ordena: primero las mías, luego las de otros usuarios.
    """
    # Todas las fechas para el dropdown
    todas_fechas = Fecha.objects.order_by("numero")

    # Determinar la fecha seleccionada (GET) o primera por defecto
    fecha_id = request.GET.get('fecha_id')
    if fecha_id:
        fecha = get_object_or_404(Fecha, id=fecha_id)
    else:
        fecha = todas_fechas.first()

    if not fecha:
        return render(request, "prode_app/mis_tarjetas.html", {
            "mensaje": "No hay fechas cargadas."
        })

    # traer todas las tarjetas de esa fecha
    todas_tarjetas_raw = Tarjeta.objects.filter(fecha=fecha).select_related('usuario', 'fecha').order_by('-numero_tarjeta')

    tarjetas_con_estado = []
    ahora = timezone.now()
    for t in todas_tarjetas_raw:
        # comprobar cierre si existe created_at
        cierre = calcular_cierre(t.fecha)
        if cierre and hasattr(t, "created_at"):
            try:
                if t.created_at and t.created_at > cierre:
                    continue
            except Exception:
                pass

        pagada = Comprobante.objects.filter(tarjeta=t, procesado=True).exists()
        tarjetas_con_estado.append({
            "tarjeta": t,
            "pagada": pagada
        })

    # Reordenar: primero las mías
    tarjetas_mias = [x for x in tarjetas_con_estado if x["tarjeta"].usuario == request.user]
    tarjetas_otros = [x for x in tarjetas_con_estado if x["tarjeta"].usuario != request.user]
    tarjetas_final = tarjetas_mias + tarjetas_otros

    return render(request, "prode_app/mis_tarjetas.html", {
        "tarjetas": tarjetas_final,
        "todas_fechas": todas_fechas,
        "fecha": fecha
    })


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
def cargar_resultados(request, fecha_id=None):
    if not request.user.is_superuser:
        raise PermissionDenied("No tenés permiso para esto.")

    # Todas las fechas para el dropdown
    todas_fechas = Fecha.objects.order_by("numero")

    # Determinar fecha seleccionada: GET o URL
    fecha_id_get = request.GET.get('fecha_id')
    if fecha_id_get:
        fecha = get_object_or_404(Fecha, id=fecha_id_get)
    elif fecha_id:
        fecha = get_object_or_404(Fecha, id=fecha_id)
    else:
        fecha = todas_fechas.first()

    if not fecha:
        return render(request, "prode_app/cargar_resultados.html", {
            "mensaje": "No hay fechas cargadas."
        })

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
        "todas_fechas": todas_fechas
    })



# --------------------------
# RANKING (solo tarjetas pagadas)
# --------------------------
@login_required
def ranking_fecha(request, fecha_id=None):
    # Todas las fechas para el dropdown
    todas_fechas = Fecha.objects.order_by("numero")

    # Determinar la fecha seleccionada (GET o parámetro)
    fecha_id_get = request.GET.get('fecha_id')
    if fecha_id_get:
        fecha = get_object_or_404(Fecha, id=fecha_id_get)
    elif fecha_id:
        fecha = get_object_or_404(Fecha, id=fecha_id)
    else:
        fecha = todas_fechas.first()

    if not fecha:
        return render(request, "prode_app/ranking_fecha.html", {
            "mensaje": "No hay fechas cargadas."
        })

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
        "todas_fechas": todas_fechas
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
        {"banco": "MERCADO PAGO", "alias": "german85.varela", "cbu": "0000003100083158571556", "titular": "Germán Emiliano Varela"},
        {"banco": "BBVA", "alias": "tercera.cuenta.prode", "cbu": "0170201870000004567891", "titular": "Prode Cuenta 3"},
    ]

    total_procesadas = Comprobante.objects.filter(procesado=True).count()
    index = min(total_procesadas // 300, len(cuentas) - 1)
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
        {"banco": "NARANJA X", "alias": "PLOPEZ9354.NX.ARS", "cbu": "4530000800016353876397", "titular": "Paola Andrea López"},
        {"banco": "SANTANDER", "alias": "lucasvarela81", "cbu": "0720374788000002053518", "titular": "Lucas Sebastián Varela"},
        {"banco": "MERCADO PAGO", "alias": "german85.varela", "cbu": "0000003100083158571556", "titular": "Germán Emiliano Varela"},
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
        grupo = processed_count // 300
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


# --------------------------
# FUNCION HELPER DE EMAIL (reutilizable)
# --------------------------
def enviar_email(subject, body, destinatarios, archivo=None):
    """
    Helper para enviar email.
    - archivo: ruta del archivo o archivo tipo InMemoryUploadedFile
    """
    from django.core.mail import EmailMessage
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


@login_required
def enviar_pozo(request, fecha_id):
    if not request.user.is_superuser:
        raise PermissionDenied("Solo admin puede enviar el pozo.")

    fecha = get_object_or_404(Fecha, id=fecha_id)

    if fecha.pozo_enviado:
        messages.info(request, f"El pozo de la Fecha {fecha.numero} ya fue enviado. Monto: ${fecha.pozo_total:,}")
        return redirect("mis_tarjetas")  # redirigir a donde quieras

    if request.method == "POST":
        # monto confirmado por admin
        try:
            monto_total = int(request.POST.get("monto_total"))
        except:
            messages.error(request, "Monto inválido.")
            return redirect("enviar_pozo", fecha_id=fecha.id)

        # obtener tarjetas pagas
        tarjetas_pagas = Tarjeta.objects.filter(
            fecha=fecha,
            comprobante__procesado=True
        ).distinct()

        if not tarjetas_pagas.exists():
            messages.warning(request, "No hay usuarios con tarjetas pagas para enviar el pozo.")
            return redirect("mis_tarjetas")

        # obtener emails únicos
        emails = list(tarjetas_pagas.values_list("usuario__email", flat=True).distinct())

        # preparar email
        subject = f"Prode Farina - Pozo de la Fecha {fecha.numero}"
        body = (
            f"Hola!\n\n"
            f"La fecha {fecha.numero} del Prode Farina ha finalizado.\n"
            f"Cantidad de tarjetas válidas y pagas: {tarjetas_pagas.count()}\n"
            f"Pozo total confirmado: ${monto_total:,} ARS\n\n"
            "¡Gracias por participar!"
        )

        # enviar email masivo usando tu helper
        try:
            enviar_email(subject, body, emails)
        except Exception as e:
            messages.error(request, f"Error enviando emails: {e}")
            return redirect("mis_tarjetas")

        # marcar fecha como enviada
        fecha.pozo_enviado = True
        fecha.pozo_total = monto_total
        fecha.save()

        messages.success(request, f"Mail del pozo enviado a {len(emails)} participantes.")
        return redirect("mis_tarjetas")

    return render(request, "prode_app/enviar_pozo.html", {"fecha": fecha})


@login_required
def enviar_ganadores_view(request, fecha_id):
    if not request.user.is_superuser:
        raise PermissionDenied("Solo admin puede enviar los ganadores.")

    fecha = get_object_or_404(Fecha, id=fecha_id)

    if not fecha.pozo_total:
        messages.error(request, "❌ La fecha no tiene pozo cargado.")
        return redirect("mis_tarjetas")

    tarjetas_pagas = Tarjeta.objects.filter(
        fecha=fecha,
        comprobante__procesado=True
    ).select_related("usuario")

    if not tarjetas_pagas.exists():
        messages.warning(request, "❌ No hay tarjetas pagadas.")
        return redirect("mis_tarjetas")

    max_puntos = tarjetas_pagas.order_by("-puntos").first().puntos
    ganadores = tarjetas_pagas.filter(puntos=max_puntos)

    cantidad = ganadores.count()
    premio = fecha.pozo_total / cantidad if cantidad > 0 else 0

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

    if request.method == "POST":
        if emails:
            send_mail(
                subject,
                body,
                settings.DEFAULT_FROM_EMAIL,
                list(set(emails)),
                fail_silently=False
            )
            messages.success(request, f"✅ Email enviado a {len(set(emails))} ganador/es")
        else:
            messages.warning(request, "⚠️ No hay emails para enviar")

        return redirect("mis_tarjetas")

    return render(request, "prode_app/enviar_ganadores.html", {"fecha": fecha, "cantidad": cantidad})