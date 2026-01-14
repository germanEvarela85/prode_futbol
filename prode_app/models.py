from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta


# -------------------------------
# USUARIO
# -------------------------------

class Usuario(AbstractUser):
    telefono = models.CharField(max_length=20, blank=True, null=True)
    cvu_alias = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.username


# -------------------------------
# EQUIPOS
# -------------------------------

class Equipo(models.Model):
    nombre = models.CharField(max_length=50)
    escudo = models.ImageField(upload_to="escudos/", blank=True, null=True)

    def __str__(self):
        return self.nombre


# -------------------------------
# FECHA
# -------------------------------

class Fecha(models.Model):
    numero = models.PositiveIntegerField()
    descripcion = models.CharField(max_length=100, blank=True, null=True)

    inicio_fecha = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Hora del primer partido."
    )

    cierre_prode = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Límite para crear y pagar tarjetas."
    )

    pozo_enviado = models.BooleanField(default=False)
    pozo_total = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"Fecha {self.numero}"

    # -------------------------------
    # MÉTODOS DE CONTROL
    # -------------------------------

    @property
    def hora_cierre(self):
        """
        Hora límite para crear y pagar tarjetas.
        Si cierre_prode está definido se usa, si no se calcula 2h antes del primer partido.
        """
        if self.cierre_prode:
            return self.cierre_prode
        if self.inicio_fecha:
            return self.inicio_fecha - timedelta(hours=2)
        return None

    @property
    def tiempo_restante(self):
        """
        Segundos que quedan hasta el cierre.
        """
        cierre = self.hora_cierre
        if cierre:
            return max(0, int((cierre - timezone.now()).total_seconds()))
        return None

    @property
    def esta_cerrada(self):
        """
        True si ya pasó la hora de cierre.
        """
        cierre = self.hora_cierre
        if cierre:
            return timezone.now() >= cierre
        return False

    # -----------------------------------
    # GENERAR AUTOMÁTICAMENTE EL CIERRE
    # -----------------------------------
    def save(self, *args, **kwargs):
        if self.inicio_fecha:
            # Calculamos automáticamente el cierre: 2 horas antes
            self.cierre_prode = self.inicio_fecha - timedelta(hours=2)
        super().save(*args, **kwargs)

    # -----------------------------------
    # MÉTODOS DE CONTROL
    # -----------------------------------

    @property
    def ya_empezo(self):
        """Retorna True si ya arrancó el primer partido."""
        if not self.inicio_fecha:
            return False
        return timezone.now() >= self.inicio_fecha

    @property
    def queda_tiempo(self):
        """True si aún se puede crear y pagar tarjetas."""
        return not self.esta_cerrada


# -------------------------------
# PARTIDOS
# -------------------------------

class Partido(models.Model):
    OPCIONES = [
        (1, "Local"),
        (2, "Empate"),
        (3, "Visitante"),
    ]

    fecha = models.ForeignKey(Fecha, on_delete=models.CASCADE)
    local = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name="partidos_local")
    visitante = models.ForeignKey(Equipo, on_delete=models.CASCADE, related_name="partidos_visitante")

    resultado_real = models.IntegerField(choices=OPCIONES, blank=True, null=True)

    def __str__(self):
        return f"{self.local} vs {self.visitante} (Fecha {self.fecha.numero})"


# -------------------------------
# TARJETAS
# -------------------------------

class Tarjeta(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    fecha = models.ForeignKey(Fecha, on_delete=models.CASCADE)
    numero_tarjeta = models.PositiveIntegerField(default=1)

    puntos = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.usuario.username}{self.numero_tarjeta}"

    @property
    def nombre_tarjeta(self):
        return f"{self.usuario.username}{self.numero_tarjeta}"


# -------------------------------
# PRONOSTICOS
# -------------------------------

class Pronostico(models.Model):
    OPCIONES = [
        (1, "Local"),
        (2, "Empate"),
        (3, "Visitante"),
    ]

    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.CASCADE)
    partido = models.ForeignKey(Partido, on_delete=models.CASCADE)
    opcion1 = models.IntegerField(choices=OPCIONES)
    opcion2 = models.IntegerField(choices=OPCIONES, blank=True, null=True)

    def __str__(self):
        return f"{self.tarjeta} - {self.partido}"


# -------------------------------
# COMPROBANTES
# -------------------------------

class Transferencia(models.Model):
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.CASCADE)
    comprobante = models.FileField(upload_to="comprobantes/")
    fecha_envio = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transferencia {self.tarjeta} - {self.fecha_envio}"


class Comprobante(models.Model):
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.CASCADE)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    archivo = models.FileField(upload_to="comprobantes/")
    comentario = models.CharField(max_length=200, blank=True, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    procesado = models.BooleanField(default=False)

    def __str__(self):
        return f"Comprobante {self.id} - {self.tarjeta.nombre_tarjeta} - {self.usuario.username}"
