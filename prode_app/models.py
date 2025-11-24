from django.contrib.auth.models import AbstractUser
from django.db import models
from django.conf import settings


class Usuario(AbstractUser):
    telefono = models.CharField(max_length=20, blank=True, null=True)
    cvu_alias = models.CharField(max_length=50, blank=True, null=True)

    def __str__(self):
        return self.username


class Equipo(models.Model):
    nombre = models.CharField(max_length=50)
    escudo = models.ImageField(upload_to="escudos/", blank=True, null=True)

    def __str__(self):
        return self.nombre


# -------------------------------
# FECHAS
# -------------------------------

class Fecha(models.Model):
    numero = models.PositiveIntegerField()
    descripcion = models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return f"Fecha {self.numero}"


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

    # Resultado real del partido (1=local,2=empate,3=visitante)
    resultado_real = models.IntegerField(choices=OPCIONES, blank=True, null=True)

    def __str__(self):
        return f"{self.local} vs {self.visitante} (Fecha {self.fecha.numero})"


# -------------------------------
# TARJETAS
# -------------------------------

class Tarjeta(models.Model):
    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    fecha = models.ForeignKey(Fecha, on_delete=models.CASCADE)
    numero_tarjeta = models.PositiveIntegerField(default=1)  # Tarjeta 1, 2, 3, etc.

    # Puntos calculados según resultados reales
    puntos = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.usuario.username}{self.numero_tarjeta}"

    @property
    def nombre_tarjeta(self):
        return f"{self.usuario.username}{self.numero_tarjeta}"


# -------------------------------
# PRONÓSTICOS
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
# TRANSFERENCIAS / COMPROBANTES
# -------------------------------

class Transferencia(models.Model):
    tarjeta = models.ForeignKey(Tarjeta, on_delete=models.CASCADE)
    comprobante = models.FileField(upload_to="comprobantes/")
    fecha_envio = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transferencia {self.tarjeta} - {self.fecha_envio}"


class Comprobante(models.Model):
    tarjeta = models.ForeignKey('Tarjeta', on_delete=models.CASCADE)
    usuario = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    archivo = models.FileField(upload_to="comprobantes/")
    comentario = models.CharField(max_length=200, blank=True, null=True)
    fecha_subida = models.DateTimeField(auto_now_add=True)
    procesado = models.BooleanField(default=False)

    def __str__(self):
        return f"Comprobante {self.id} - {self.tarjeta.nombre_tarjeta} - {self.usuario.username}"
