from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.contrib.auth import views as auth_views
from prode_app import views
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.conf.urls.static import static


urlpatterns = [
    path("admin/", admin.site.urls),

    # Home → redirige al login si no está autenticado
    path("", lambda request: redirect("login"), name="home"),
    
    # Registro de usuarios
    path("registro/", views.registro, name="registro"),

    # Activación de cuenta vía email
    path("activar/<uidb64>/<token>/", views.activar_cuenta, name="activar_cuenta"),
    
    # Login personalizado
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="prode_app/login.html",
            redirect_authenticated_user=True
        ),
        name="login"
    ),

    # Logout
    path(
        "logout/",
        auth_views.LogoutView.as_view(
            next_page="home"
        ),
        name="logout"
    ),

    # Redirección post-login
    path("post_login/", views.post_login, name="post_login"),

    # -----------------------------
    # 🔐 Recuperar contraseña
    # -----------------------------
    path(
        "password_reset/",
        auth_views.PasswordResetView.as_view(
            template_name="prode_app/password_reset_form.html",
            email_template_name="prode_app/password_reset_email.html",
            subject_template_name="prode_app/password_reset_subject.txt",
            success_url="/password_reset_done/"
        ),
        name="password_reset"
    ),

    path(
        "password_reset_done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="prode_app/password_reset_done.html"
        ),
        name="password_reset_done"
    ),

    path(
        "password_reset_confirm/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="prode_app/password_reset_confirm.html",
            success_url="/password_reset_complete/"
        ),
        name="password_reset_confirm"
    ),

    path(
        "password_reset_complete/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="prode_app/password_reset_complete.html"
        ),
        name="password_reset_complete"
    ),

    # ---------------------------------------------------------
    # 💳 SUBIR COMPROBANTE DE PAGO
    # ---------------------------------------------------------
    path("subir_comprobante/", login_required(views.subir_comprobante), name="subir_comprobante"),

    # ---------------------------------------------------------
    # TARJETAS / FECHAS
    # ---------------------------------------------------------
    path("reglamento/", login_required(views.reglamento), name="reglamento"),
    path("crear_tarjeta/", login_required(views.crear_tarjeta), name="crear_tarjeta"),
    path("mis_tarjetas/", login_required(views.mis_tarjetas), name="mis_tarjetas"),
    path("tarjeta/<int:tarjeta_id>/", login_required(views.detalle_tarjeta), name="detalle_tarjeta"),
    path("tarjeta/<int:tarjeta_id>/borrar/", login_required(views.borrar_tarjeta), name="borrar_tarjeta"),

    path("fecha/<int:fecha_id>/cargar_resultados/", login_required(views.cargar_resultados), name="cargar_resultados"),
    path("fecha/<int:fecha_id>/ranking/", login_required(views.ranking_fecha), name="ranking_fecha"),

    path("buscar_tarjeta/", login_required(views.buscar_tarjeta), name="buscar_tarjeta"),
]

# ---------------------------------------------------------
# 📌 SERVIR MEDIA EN DESARROLLO (NECESARIO PARA ESCUDOS)
# ---------------------------------------------------------
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
