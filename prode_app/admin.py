from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    Usuario, Equipo, Fecha, Partido,
    Tarjeta, Pronostico, Transferencia, Comprobante
)

# Usuario personalizado
@admin.register(Usuario)
class CustomUserAdmin(UserAdmin):
    model = Usuario
    fieldsets = UserAdmin.fieldsets + (
        ("Extras", {"fields": ("telefono", "cvu_alias")}),
    )

# Equipo
@admin.register(Equipo)
class EquipoAdmin(admin.ModelAdmin):
    list_display = ("nombre",)
    search_fields = ("nombre",)

# Fecha (jornada)
@admin.register(Fecha)
class FechaAdmin(admin.ModelAdmin):
    list_display = ("numero", "descripcion")
    ordering = ("numero",)
    search_fields = ("numero", "descripcion")

# Partido
@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display = ("fecha", "local", "visitante", "resultado_real")
    list_filter = ("fecha",)
    search_fields = ("local__nombre", "visitante__nombre")
    raw_id_fields = ("local", "visitante")

# Tarjeta
@admin.register(Tarjeta)
class TarjetaAdmin(admin.ModelAdmin):
    list_display = ("usuario", "fecha", "numero_tarjeta")
    list_filter = ("fecha", "usuario")
    search_fields = ("usuario__username",)

# Pronostico
@admin.register(Pronostico)
class PronosticoAdmin(admin.ModelAdmin):
    list_display = ("tarjeta", "partido", "opcion1", "opcion2")
    list_filter = ("partido__fecha",)

# Transferencia
@admin.register(Transferencia)
class TransferenciaAdmin(admin.ModelAdmin):
    list_display = ("tarjeta", "fecha_envio")
    list_filter = ("fecha_envio",)

# Comprobante
@admin.register(Comprobante)
class ComprobanteAdmin(admin.ModelAdmin):
    list_display = ("id", "tarjeta", "usuario", "fecha_subida", "procesado")
    list_filter = ("fecha_subida", "procesado")
    search_fields = ("usuario__username", "tarjeta__numero_tarjeta")