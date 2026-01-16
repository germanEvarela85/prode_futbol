from django import forms
from .models import Tarjeta, Pronostico, Fecha, Comprobante
from django.contrib.auth.forms import UserCreationForm
from .models import Usuario


class RegistroForm(UserCreationForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = Usuario
        fields = ['username', 'email', 'password1', 'password2']


class PronosticoForm(forms.ModelForm):
    class Meta:
        model = Pronostico
        fields = ['partido', 'opcion1', 'opcion2']
        widgets = {
            'opcion1': forms.RadioSelect,
            'opcion2': forms.CheckboxSelectMultiple,
        }

    def clean(self):
        cleaned_data = super().clean()
        opcion2 = cleaned_data.get("opcion2")
        return cleaned_data


class TarjetaForm(forms.ModelForm):
    fecha = forms.ModelChoiceField(
        queryset=Fecha.objects.all().order_by('numero'),
        label="Selecciona la fecha"
    )

    class Meta:
        model = Tarjeta
        fields = ['fecha']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Fecha
        self.fields['fecha'].queryset = Fecha.objects.all().order_by('numero')


class ComprobanteForm(forms.ModelForm):
    class Meta:
        model = Comprobante
        fields = ['tarjeta', 'archivo', 'comentario']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user is not None:
            self.fields['tarjeta'].queryset = Tarjeta.objects.filter(usuario=user)
        self.fields['archivo'].label = "Subir comprobante (jpg, png, pdf)"
        self.fields['comentario'].required = False
